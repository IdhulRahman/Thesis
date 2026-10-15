#!/usr/bin/env python3
"""
Telemetry Collector & Prometheus Exporter for 5G O-RAN Thesis Testbed
Location on VM-6: /opt/oran/monitoring/collector/telemetry_collector.py
Pure Python 3 Standard Library - Zero External Pip Dependencies
Ingests telemetry from VM-3 (UPF Core), VM-4 (RAN E2/FlexRIC), and VM-5 (UE QoS),
exposing Prometheus metrics on http://10.102.0.67:9100/metrics and ingesting on /report.
"""

from datetime import datetime, timezone, timedelta
import http.server
import json
import math
import os
import threading
import time
import urllib.request
import urllib.parse
import urllib.error

LISTEN_PORT = 9100
LISTEN_HOST = "0.0.0.0"
RUN_STATE_FILE = "/opt/oran/monitoring/data/active_run_id.txt"
COLLECTOR_START_TIME = datetime.now(timezone.utc)

METRICS_LOCK = threading.Lock()
metrics_store = {
    # Domain 4: End-to-End UE Metrics (VM-5)
    "e2e_slice1_throughput_mbps": float("nan"),
    "e2e_slice1_jitter_ms": float("nan"),
    "e2e_slice2_latency_rtt_ms": float("nan"),
    "e2e_slice2_packet_loss_pct": float("nan"),
    "e2e_slice2_last_seq": float("nan"),
    "e2e_slice2_reply_age_sec": float("nan"),
    "e2e_probe_freshness": 0,

    # Domain 1: 5G Core & NWDAF (VM-3)
    "nwdaf_slice_load_level": {
        "01000001": float("nan"),     # eMBB (SST 1, SD 1) - Retains NaN (load % uncalculated upstream)
        "de00007b": float("nan")      # URLLC (SST 222, SD 123) - Retains NaN
    },
    # 3GPP TS 29.520 UE_COMMUNICATION Analytics (PoC Slice 1 URR Ingestion)
    "nwdaf_api_status": 0,            # 1 = NBI REST API polling succeeded (HTTP 200), 0 = Error/Unreachable
    "nwdaf_comm_duration_sec": float("nan"),
    "nwdaf_comm_ul_bytes": float("nan"),
    "nwdaf_comm_dl_bytes": float("nan"),
    "nwdaf_comm_vol_std_bytes": float("nan"),
    "nwdaf_comm_freshness": 0,        # 1 = Fresh source measurement received within 45s, 0 = Stale / unchanged / expired
    "estimated_slice_load_level": {
        "01000001": float("nan"),     # Empirical load estimate (Tx / Quota * 100%)
        "de00007b": float("nan")
    },
    "upf_queue_backlog_bytes": {
        "01000001": float("nan"),
        "de00007b": float("nan")
    },
    "upf_packet_drops": {
        "01000001": float("nan"),     # Rate: packets/sec
        "de00007b": float("nan")
    },
    "upf_packet_drops_delta": {
        "01000001": float("nan"),     # Delta: packets
        "de00007b": float("nan")
    },
    "upf_packet_drops_per_sec": {
        "01000001": float("nan"),     # Explicit rate: packets/sec
        "de00007b": float("nan")
    },
    "upf_bytes_sent": {
        "01000001": float("nan"),
        "de00007b": float("nan")
    },

    # Domain 2: Split RAN Radio Metrics (VM-4)
    "ran_cell_prb_utilization": {
        "1": float("nan"),           # Cell-1 (DU-1 :4043)
        "2": float("nan")            # Cell-2 (DU-2 :4044)
    },
    "ran_cell_mcs": {
        "1": float("nan"),
        "2": float("nan")
    },
    "ran_cell_bler": {
        "1": float("nan"),
        "2": float("nan")
    },
    "ran_cell_snr_db": {
        "1": float("nan"),
        "2": float("nan")
    },
    "ran_cell_rssi_dbm": {
        "1": float("nan"),
        "2": float("nan")
    },
    "ran_cell_ulsch_errors": {
        "1": float("nan"),
        "2": float("nan")
    },

    # Domain 3: RIC Intelligence (VM-1 / VM-2)
    "rapp_diagnosed_bottleneck": -1,   # -1: UNINITIALIZED, 0: NORMAL, 1: RAN, 2: CORE, 3: JOINT
    "rapp_confidence": 0.0,
    "a1_policy_threshold": 20.0        # URLLC SLA latency threshold (ms)
}


last_report_ue1 = 0.0
last_report_ue2 = 0.0
last_reply_ue2 = 0.0
last_report_core = 0.0
last_report_ran = 0.0
last_nwdaf_poll_time = 0.0
last_nwdaf_data_change_time = 0.0
last_nwdaf_signature = None
active_run_id = None
active_run_mtime = 0.0
active_run_start_dt = None


def fmt_val(v, fmt=".2f"):
    return f"{v:{fmt}}" if (v is not None and not math.isnan(v)) else "NaN"


def format_prometheus_metrics():
    global last_report_ue1, last_report_ue2, last_reply_ue2, last_report_core, last_report_ran
    lines = []
    now = time.time()
    with METRICS_LOCK:
        # Auto-reset stale UE metrics if trafgen stopped pushing (> 3.5 seconds)
        ue1_reporting = (last_report_ue1 > 0.0) and (now - last_report_ue1 <= 3.5)
        ue2_reporting = (last_report_ue2 > 0.0) and (now - last_report_ue2 <= 3.5)

        # True measurement freshness: is there a non-NaN RTT measurement received within 3.5s?
        ue2_meas_fresh = ue2_reporting and (last_reply_ue2 > 0.0) and (now - last_reply_ue2 <= 3.5) and not math.isnan(metrics_store["e2e_slice2_latency_rtt_ms"])

        if not ue1_reporting:
            metrics_store["e2e_slice1_throughput_mbps"] = float("nan")
            metrics_store["e2e_slice1_jitter_ms"] = float("nan")

        if not ue2_reporting:
            metrics_store["e2e_slice2_packet_loss_pct"] = float("nan")
            metrics_store["e2e_slice2_last_seq"] = float("nan")
            metrics_store["e2e_slice2_reply_age_sec"] = float("nan")

        if not ue2_meas_fresh:
            metrics_store["e2e_slice2_latency_rtt_ms"] = float("nan")

        # Probe freshness reflects the actual freshness of active QoS canary probing (URLLC RTT)
        metrics_store["e2e_probe_freshness"] = 1 if ue2_meas_fresh else 0

        # Auto-reset stale Core metrics if core_adapter stopped pushing (> 3.5 seconds)
        if last_report_core > 0.0 and (now - last_report_core > 3.5):
            for snssai in ("01000001", "de00007b"):
                metrics_store["upf_queue_backlog_bytes"][snssai] = float("nan")
                metrics_store["upf_packet_drops"][snssai] = float("nan")
                metrics_store["upf_packet_drops_delta"][snssai] = float("nan")
                metrics_store["upf_packet_drops_per_sec"][snssai] = float("nan")
                metrics_store["estimated_slice_load_level"][snssai] = float("nan")

        # Auto-reset stale NWDAF metrics if external Nnwdaf daemon stopped responding (> 35 seconds, matching UPF 30s loop + 5s buffer)
        if last_nwdaf_poll_time > 0.0 and (now - last_nwdaf_poll_time > 35.0):
            metrics_store["nwdaf_api_status"] = 0
            metrics_store["nwdaf_comm_freshness"] = 0
            metrics_store["nwdaf_comm_duration_sec"] = float("nan")
            metrics_store["nwdaf_comm_ul_bytes"] = float("nan")
            metrics_store["nwdaf_comm_dl_bytes"] = float("nan")
            metrics_store["nwdaf_comm_vol_std_bytes"] = float("nan")
            for snssai in ("01000001", "de00007b"):
                metrics_store["nwdaf_slice_load_level"][snssai] = float("nan")

        # Check source measurement age: if source values have not changed in > 45 seconds, mark freshness = 0
        if last_nwdaf_data_change_time > 0.0 and (now - last_nwdaf_data_change_time > 45.0):
            metrics_store["nwdaf_comm_freshness"] = 0

        # Auto-reset stale RAN metrics if ran_adapter stopped pushing (> 3.5 seconds)
        if last_report_ran > 0.0 and (now - last_report_ran > 3.5):
            for cid in ("1", "2"):
                metrics_store["ran_cell_prb_utilization"][cid] = float("nan")
                metrics_store["ran_cell_mcs"][cid] = float("nan")
                metrics_store["ran_cell_bler"][cid] = float("nan")
                metrics_store["ran_cell_snr_db"][cid] = float("nan")
                metrics_store["ran_cell_rssi_dbm"][cid] = float("nan")
                metrics_store["ran_cell_ulsch_errors"][cid] = float("nan")

        lines.append("# HELP e2e_slice1_throughput_mbps End-to-end throughput for Slice 1 (eMBB) in Mbps")
        lines.append("# TYPE e2e_slice1_throughput_mbps gauge")
        lines.append(f"e2e_slice1_throughput_mbps {fmt_val(metrics_store['e2e_slice1_throughput_mbps'])}")

        lines.append("# HELP e2e_slice1_jitter_ms End-to-end jitter for Slice 1 (eMBB) in ms")
        lines.append("# TYPE e2e_slice1_jitter_ms gauge")
        lines.append(f"e2e_slice1_jitter_ms {fmt_val(metrics_store['e2e_slice1_jitter_ms'], '.3f')}")

        lines.append("# HELP e2e_slice2_latency_rtt_ms End-to-end precision RTT latency for Slice 2 (URLLC) in ms")
        lines.append("# TYPE e2e_slice2_latency_rtt_ms gauge")
        lines.append(f"e2e_slice2_latency_rtt_ms {fmt_val(metrics_store['e2e_slice2_latency_rtt_ms'])}")

        lines.append("# HELP e2e_slice2_packet_loss_pct End-to-end packet loss percentage for Slice 2 (URLLC)")
        lines.append("# TYPE e2e_slice2_packet_loss_pct gauge")
        lines.append(f"e2e_slice2_packet_loss_pct {fmt_val(metrics_store['e2e_slice2_packet_loss_pct'])}")

        lines.append("# HELP e2e_probe_freshness Freshness indicator for UE probe telemetry (1=Fresh, 0=Stale/Offline)")
        lines.append("# TYPE e2e_probe_freshness gauge")
        lines.append(f"e2e_probe_freshness {int(metrics_store['e2e_probe_freshness'])}")

        lines.append("# HELP e2e_slice2_reply_age_sec Age of latest valid URLLC ICMP canary reply in seconds")
        lines.append("# TYPE e2e_slice2_reply_age_sec gauge")
        lines.append(f"e2e_slice2_reply_age_sec {fmt_val(metrics_store['e2e_slice2_reply_age_sec'], '.1f')}")

        lines.append("# HELP e2e_slice2_last_seq Sequence number of latest valid URLLC ICMP canary reply")
        lines.append("# TYPE e2e_slice2_last_seq gauge")
        lines.append(f"e2e_slice2_last_seq {fmt_val(metrics_store['e2e_slice2_last_seq'], '.0f')}")

        lines.append("# HELP nwdaf_slice_load_level NWDAF reported slice load level percentage (NaN until load % is supported upstream)")
        lines.append("# TYPE nwdaf_slice_load_level gauge")
        for snssai, val in metrics_store["nwdaf_slice_load_level"].items():
            lines.append(f'nwdaf_slice_load_level{{snssai="{snssai}"}} {fmt_val(val)}')

        lines.append("# HELP nwdaf_api_status NWDAF Northbound REST API connectivity status (1=OK/200, 0=Error/Unreachable)")
        lines.append("# TYPE nwdaf_api_status gauge")
        lines.append(f"nwdaf_api_status {int(metrics_store['nwdaf_api_status'])}")

        lines.append("# HELP nwdaf_comm_duration_sec NWDAF reported communication duration in seconds (note: upstream sums report elapsed times)")
        lines.append("# TYPE nwdaf_comm_duration_sec gauge")
        lines.append(f"nwdaf_comm_duration_sec {fmt_val(metrics_store['nwdaf_comm_duration_sec'])}")

        lines.append("# HELP nwdaf_comm_ul_bytes NWDAF reported uplink user-plane volume in bytes")
        lines.append("# TYPE nwdaf_comm_ul_bytes gauge")
        lines.append(f"nwdaf_comm_ul_bytes {fmt_val(metrics_store['nwdaf_comm_ul_bytes'], '.0f')}")

        lines.append("# HELP nwdaf_comm_dl_bytes NWDAF reported downlink user-plane volume in bytes")
        lines.append("# TYPE nwdaf_comm_dl_bytes gauge")
        lines.append(f"nwdaf_comm_dl_bytes {fmt_val(metrics_store['nwdaf_comm_dl_bytes'], '.0f')}")

        lines.append("# HELP nwdaf_comm_vol_std_bytes NWDAF reported volume standard deviation in bytes (computed via math.Sqrt in upstream engine)")
        lines.append("# TYPE nwdaf_comm_vol_std_bytes gauge")
        lines.append(f"nwdaf_comm_vol_std_bytes {fmt_val(metrics_store['nwdaf_comm_vol_std_bytes'], '.0f')}")

        lines.append("# HELP nwdaf_comm_freshness Freshness indicator for NWDAF user-plane telemetry (1=Fresh source report within 45s, 0=Stale/Unchanged)")
        lines.append("# TYPE nwdaf_comm_freshness gauge")
        lines.append(f"nwdaf_comm_freshness {int(metrics_store['nwdaf_comm_freshness'])}")

        lines.append("# HELP estimated_slice_load_level Estimated slice load percentage derived from UPF interface Tx throughput")
        lines.append("# TYPE estimated_slice_load_level gauge")
        for snssai, val in metrics_store["estimated_slice_load_level"].items():
            lines.append(f'estimated_slice_load_level{{snssai="{snssai}"}} {fmt_val(val)}')

        lines.append("# HELP upf_queue_backlog_bytes UPF egress kernel queue backlog bytes")
        lines.append("# TYPE upf_queue_backlog_bytes gauge")
        for snssai, val in metrics_store["upf_queue_backlog_bytes"].items():
            lines.append(f'upf_queue_backlog_bytes{{snssai="{snssai}"}} {fmt_val(val)}')

        lines.append("# HELP upf_packet_drops UPF kernel queue packet drops rate (packets/sec)")
        lines.append("# TYPE upf_packet_drops gauge")
        for snssai, val in metrics_store["upf_packet_drops"].items():
            lines.append(f'upf_packet_drops{{snssai="{snssai}"}} {fmt_val(val)}')

        lines.append("# HELP upf_packet_drops_delta UPF kernel queue packet drops delta count")
        lines.append("# TYPE upf_packet_drops_delta gauge")
        for snssai, val in metrics_store["upf_packet_drops_delta"].items():
            lines.append(f'upf_packet_drops_delta{{snssai="{snssai}"}} {fmt_val(val, ".0f")}')

        lines.append("# HELP upf_packet_drops_per_sec UPF kernel queue packet drops per second")
        lines.append("# TYPE upf_packet_drops_per_sec gauge")
        for snssai, val in metrics_store["upf_packet_drops_per_sec"].items():
            lines.append(f'upf_packet_drops_per_sec{{snssai="{snssai}"}} {fmt_val(val)}')

        lines.append("# HELP upf_bytes_sent UPF egress total sent bytes")
        lines.append("# TYPE upf_bytes_sent counter")
        for snssai, val in metrics_store["upf_bytes_sent"].items():
            lines.append(f'upf_bytes_sent{{snssai="{snssai}"}} {fmt_val(val, ".0f")}')

        lines.append("# HELP ran_cell_prb_utilization RAN PRB resource block utilization percentage")
        lines.append("# TYPE ran_cell_prb_utilization gauge")
        for cell, val in metrics_store["ran_cell_prb_utilization"].items():
            lines.append(f'ran_cell_prb_utilization{{cell_id="{cell}"}} {fmt_val(val)}')

        lines.append("# HELP ran_cell_mcs RAN Modulation and Coding Scheme (MCS)")
        lines.append("# TYPE ran_cell_mcs gauge")
        for cell, val in metrics_store["ran_cell_mcs"].items():
            lines.append(f'ran_cell_mcs{{cell_id="{cell}"}} {fmt_val(val, ".1f")}')

        lines.append("# HELP ran_cell_bler RAN Block Error Rate (BLER)")
        lines.append("# TYPE ran_cell_bler gauge")
        for cell, val in metrics_store["ran_cell_bler"].items():
            lines.append(f'ran_cell_bler{{cell_id="{cell}"}} {fmt_val(val, ".4f")}')

        lines.append("# HELP ran_cell_snr_db RAN Signal to Noise Ratio in dB")
        lines.append("# TYPE ran_cell_snr_db gauge")
        for cell, val in metrics_store["ran_cell_snr_db"].items():
            lines.append(f'ran_cell_snr_db{{cell_id="{cell}"}} {fmt_val(val)}')

        lines.append("# HELP ran_cell_rssi_dbm RAN Received Signal Strength Indicator in dBm")
        lines.append("# TYPE ran_cell_rssi_dbm gauge")
        for cell, val in metrics_store["ran_cell_rssi_dbm"].items():
            lines.append(f'ran_cell_rssi_dbm{{cell_id="{cell}"}} {fmt_val(val)}')

        lines.append("# HELP ran_cell_ulsch_errors Cumulative MAC layer ULSCH transmission errors")
        lines.append("# TYPE ran_cell_ulsch_errors gauge")
        for cell, val in metrics_store["ran_cell_ulsch_errors"].items():
            lines.append(f'ran_cell_ulsch_errors{{cell_id="{cell}"}} {fmt_val(val, ".0f")}')

        lines.append("# HELP rapp_diagnosed_bottleneck Bottleneck classification (0=NORMAL, 1=RAN, 2=CORE, 3=JOINT)")
        lines.append("# TYPE rapp_diagnosed_bottleneck gauge")
        lines.append(f"rapp_diagnosed_bottleneck {int(metrics_store['rapp_diagnosed_bottleneck'])}")

        lines.append("# HELP rapp_confidence Confidence level of bottleneck diagnosis (0.0 - 1.0)")
        lines.append("# TYPE rapp_confidence gauge")
        lines.append(f"rapp_confidence {metrics_store['rapp_confidence']:.2f}")

        lines.append("# HELP a1_policy_threshold A1 policy URLLC latency SLA threshold in ms")
        lines.append("# TYPE a1_policy_threshold gauge")
        lines.append(f"a1_policy_threshold {metrics_store['a1_policy_threshold']:.2f}")

    return "\n".join(lines) + "\n"


class TelemetryHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/metrics":
            content = format_prometheus_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path in ("/", "/health"):
            data = json.dumps({"status": "UP", "service": "5g-oran-telemetry-collector"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/report":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body)

                global last_report_ue1, last_report_ue2, last_reply_ue2, last_report_core, last_report_ran
                with METRICS_LOCK:
                    if "slice" in payload:
                        slice_id = str(payload["slice"])
                        if slice_id in ("1", "embb"):
                            last_report_ue1 = time.time()
                            if "throughput_mbps" in payload:
                                metrics_store["e2e_slice1_throughput_mbps"] = float(payload["throughput_mbps"])
                            if "jitter_ms" in payload:
                                metrics_store["e2e_slice1_jitter_ms"] = float(payload["jitter_ms"])
                        elif slice_id in ("2", "urllc"):
                            last_report_ue2 = time.time()
                            rtt_val = payload.get("rtt_ms")
                            if rtt_val is not None and str(rtt_val).lower() not in ("nan", "none", "null"):
                                metrics_store["e2e_slice2_latency_rtt_ms"] = float(rtt_val)
                                last_reply_ue2 = time.time()
                            else:
                                metrics_store["e2e_slice2_latency_rtt_ms"] = float("nan")

                            loss_val = payload.get("packet_loss_pct")
                            if loss_val is not None and str(loss_val).lower() not in ("nan", "none", "null"):
                                metrics_store["e2e_slice2_packet_loss_pct"] = float(loss_val)
                            else:
                                metrics_store["e2e_slice2_packet_loss_pct"] = float("nan")

                            if "last_seq" in payload and payload["last_seq"] is not None:
                                try:
                                    metrics_store["e2e_slice2_last_seq"] = float(payload["last_seq"])
                                except (ValueError, TypeError):
                                    pass

                            if "reply_age_sec" in payload and payload["reply_age_sec"] is not None:
                                try:
                                    metrics_store["e2e_slice2_reply_age_sec"] = float(payload["reply_age_sec"])
                                except (ValueError, TypeError):
                                    pass

                    for key in ("e2e_slice1_throughput_mbps", "e2e_slice1_jitter_ms",
                                "rapp_diagnosed_bottleneck", "rapp_confidence", "a1_policy_threshold"):
                        if key in payload:
                            if "slice1" in key:
                                last_report_ue1 = time.time()
                            try:
                                val = payload[key]
                                metrics_store[key] = float(val) if (val is not None and str(val).lower() not in ("nan", "none", "null")) else float("nan")
                            except (ValueError, TypeError):
                                pass

                    # RAN Telemetry Ingestion
                    if "ran_cell_prb_utilization" in payload or "ran_cell_radio_stats" in payload:
                        last_report_ran = time.time()

                    if "ran_cell_prb_utilization" in payload and isinstance(payload["ran_cell_prb_utilization"], dict):
                        for cell, val in payload["ran_cell_prb_utilization"].items():
                            metrics_store["ran_cell_prb_utilization"][str(cell)] = float(val) if val is not None else float("nan")

                    if "ran_cell_radio_stats" in payload and isinstance(payload["ran_cell_radio_stats"], dict):
                        for cell, stats in payload["ran_cell_radio_stats"].items():
                            cid = str(cell)
                            if isinstance(stats, dict):
                                is_valid = stats.get("valid", True)
                                if not is_valid:
                                    metrics_store["ran_cell_prb_utilization"][cid] = float("nan")
                                    metrics_store["ran_cell_mcs"][cid] = float("nan")
                                    metrics_store["ran_cell_bler"][cid] = float("nan")
                                    metrics_store["ran_cell_snr_db"][cid] = float("nan")
                                    metrics_store["ran_cell_rssi_dbm"][cid] = float("nan")
                                    metrics_store["ran_cell_ulsch_errors"][cid] = float("nan")
                                else:
                                    for k, m_dict in (("mcs", "ran_cell_mcs"), ("bler", "ran_cell_bler"),
                                                      ("snr_db", "ran_cell_snr_db"), ("rssi_dbm", "ran_cell_rssi_dbm")):
                                        val = stats.get(k)
                                        metrics_store[m_dict][cid] = float(val) if val is not None else float("nan")
                                    err_val = stats.get("ulsch_errors")
                                    metrics_store["ran_cell_ulsch_errors"][cid] = float(err_val) if err_val is not None else float("nan")
                                    if stats.get("prb_pct") is not None:
                                        metrics_store["ran_cell_prb_utilization"][cid] = float(stats["prb_pct"])

                    # Core & UPF Telemetry Ingestion (safe against null / None values from core_adapter.py v9)
                    core_metric_keys = (
                        "upf_interface_tx_mbps", "upf_interface_rx_mbps",
                        "upf_tx_bytes_total", "upf_rx_bytes_total",
                        "upf_qdisc_backlog_bytes", "upf_queue_backlog_bytes",
                        "upf_qdisc_drops_delta", "upf_packet_drops", "upf_qdisc_drops_per_sec"
                    )
                    if any(k in payload for k in core_metric_keys):
                        last_report_core = time.time()

                    for m_key in core_metric_keys:
                        if m_key in payload and isinstance(payload[m_key], dict):
                            if m_key not in metrics_store:
                                metrics_store[m_key] = {}
                            for snssai, val in payload[m_key].items():
                                try:
                                    metrics_store[m_key][str(snssai)] = float(val) if val is not None else float("nan")
                                except (ValueError, TypeError):
                                    pass

                    # Synchronize aliases for Prometheus /metrics format
                    if "upf_qdisc_backlog_bytes" in payload and isinstance(payload["upf_qdisc_backlog_bytes"], dict):
                        for snssai, val in payload["upf_qdisc_backlog_bytes"].items():
                            try:
                                metrics_store["upf_queue_backlog_bytes"][str(snssai)] = float(val) if val is not None else float("nan")
                            except (ValueError, TypeError):
                                pass

                    # Strictly decouple drop rate (packets/sec) and drop delta (packets)
                    if "upf_qdisc_drops_per_sec" in payload and isinstance(payload["upf_qdisc_drops_per_sec"], dict):
                        for snssai, val in payload["upf_qdisc_drops_per_sec"].items():
                            try:
                                rate_val = float(val) if val is not None else float("nan")
                                metrics_store["upf_packet_drops"][str(snssai)] = rate_val
                                metrics_store["upf_packet_drops_per_sec"][str(snssai)] = rate_val
                            except (ValueError, TypeError):
                                pass

                    if "upf_qdisc_drops_delta" in payload and isinstance(payload["upf_qdisc_drops_delta"], dict):
                        for snssai, val in payload["upf_qdisc_drops_delta"].items():
                            try:
                                metrics_store["upf_packet_drops_delta"][str(snssai)] = float(val) if val is not None else float("nan")
                            except (ValueError, TypeError):
                                pass

                    if "upf_tx_bytes_total" in payload and isinstance(payload["upf_tx_bytes_total"], dict):
                        for snssai, val in payload["upf_tx_bytes_total"].items():
                            try:
                                metrics_store["upf_bytes_sent"][str(snssai)] = float(val) if val is not None else float("nan")
                            except (ValueError, TypeError):
                                pass

                    # Dynamic estimation of slice load derived from UPF Tx throughput (empirical research proxy)
                    # Uses max(0.0, ...) to ensure 0 Mbps maps accurately to 0.0% without synthetic minimum floors
                    if "upf_interface_tx_mbps" in payload and isinstance(payload["upf_interface_tx_mbps"], dict):
                        tx1 = payload["upf_interface_tx_mbps"].get("01000001")
                        load1 = round(min(100.0, max(0.0, (float(tx1) / 25.0) * 100.0)), 2) if tx1 is not None else float("nan")
                        metrics_store["estimated_slice_load_level"]["01000001"] = load1

                        tx2 = payload["upf_interface_tx_mbps"].get("de00007b")
                        load2 = round(min(100.0, max(0.0, (float(tx2) / 5.0) * 100.0)), 2) if tx2 is not None else float("nan")
                        metrics_store["estimated_slice_load_level"]["de00007b"] = load2



                response = json.dumps({"status": "SUCCESS"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
        else:
            self.send_response(404)
            self.end_headers()


def check_run_state_change():
    """Detects active run_id changes and resets NWDAF state/freshness on run transitions."""
    global active_run_id, active_run_mtime, active_run_start_dt
    global last_nwdaf_signature, last_nwdaf_data_change_time

    env_start = os.getenv("NWDAF_START_TIME")
    if env_start:
        return env_start

    current_id = None
    current_mtime = 0.0
    if os.path.exists(RUN_STATE_FILE):
        try:
            current_mtime = os.path.getmtime(RUN_STATE_FILE)
            with open(RUN_STATE_FILE, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().strip()
                if content:
                    current_id = content
        except Exception:
            pass

    # Check if run transition occurred
    if current_id != active_run_id or abs(current_mtime - active_run_mtime) > 1.0:
        active_run_id = current_id
        active_run_mtime = current_mtime
        if current_mtime > 0.0:
            active_run_start_dt = datetime.fromtimestamp(current_mtime, timezone.utc)
        else:
            active_run_start_dt = COLLECTOR_START_TIME

        # Explicitly reset NWDAF state and freshness upon run transition
        last_nwdaf_signature = None
        last_nwdaf_data_change_time = 0.0
        with METRICS_LOCK:
            metrics_store["nwdaf_comm_freshness"] = 0
            metrics_store["nwdaf_comm_duration_sec"] = float("nan")
            metrics_store["nwdaf_comm_ul_bytes"] = float("nan")
            metrics_store["nwdaf_comm_dl_bytes"] = float("nan")
            metrics_store["nwdaf_comm_vol_std_bytes"] = float("nan")

    if active_run_start_dt:
        return active_run_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return COLLECTOR_START_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_nwdaf_query_window():
    """Calculates an isolated RFC3339 query window for NWDAF NBI analytics."""
    start_ts = check_run_state_change()
    end_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start_ts, end_ts


def poll_external_nfs():
    global last_nwdaf_poll_time, last_nwdaf_data_change_time, last_nwdaf_signature
    while True:
        try:
            # Query 3GPP TS 29.520 UE_COMMUNICATION analytics from NWDAF via Kong Gateway port 8080.
            # Upstream OAI NWDAF Engine (ue_communication.go) filters MongoDB documents by startTs/endTs.
            # Using an isolated per-run window prevents aggregation of historical metrics from prior experiments.
            start_ts, end_ts = get_nwdaf_query_window()
            ana_req = json.dumps({"startTs": start_ts, "endTs": end_ts})
            query = urllib.parse.urlencode({
                "event-id": "UE_COMMUNICATION",
                "ana-req": ana_req
            })
            url = f"http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?{query}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Thesis-Collector/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    with METRICS_LOCK:
                        now = time.time()
                        last_nwdaf_poll_time = now
                        metrics_store["nwdaf_api_status"] = 1
                        ue_comms = data.get("ueComms", [])
                        if ue_comms:
                            comm = ue_comms[0]
                            dur = float(comm.get("commDur", float("nan")))
                            traf = comm.get("trafChar", {})
                            ul = float(traf.get("ulVol", float("nan")))
                            dl = float(traf.get("dlVol", float("nan")))
                            # Note: Upstream OAI NWDAF ue_communication.go computes std dev (math.Sqrt)
                            # into the ulVolVariance field:
                            std_dev = float(traf.get("ulVolVariance", float("nan")))

                            sig = (dur, ul, dl, std_dev)
                            if last_nwdaf_signature is None:
                                # Initial poll baseline: establish signature without falsely asserting freshness
                                last_nwdaf_signature = sig
                            elif sig != last_nwdaf_signature:
                                # Authentic data change detected during this active session
                                last_nwdaf_signature = sig
                                last_nwdaf_data_change_time = now

                            metrics_store["nwdaf_comm_duration_sec"] = dur
                            metrics_store["nwdaf_comm_ul_bytes"] = ul
                            metrics_store["nwdaf_comm_dl_bytes"] = dl
                            metrics_store["nwdaf_comm_vol_std_bytes"] = std_dev

                            # Freshness is 1 only if authentic new data was received within 45 seconds (exceeding UPF 30s URR loop)
                            if last_nwdaf_data_change_time > 0 and (now - last_nwdaf_data_change_time <= 45.0):
                                metrics_store["nwdaf_comm_freshness"] = 1
                            else:
                                metrics_store["nwdaf_comm_freshness"] = 0
                        else:
                            # Empty ueComms array indicates no active telemetry reports in queried window
                            metrics_store["nwdaf_comm_freshness"] = 0
                            metrics_store["nwdaf_comm_duration_sec"] = float("nan")
                            metrics_store["nwdaf_comm_ul_bytes"] = float("nan")
                            metrics_store["nwdaf_comm_dl_bytes"] = float("nan")
                            metrics_store["nwdaf_comm_vol_std_bytes"] = float("nan")
                else:
                    with METRICS_LOCK:
                        metrics_store["nwdaf_api_status"] = 0
        except Exception:
            with METRICS_LOCK:
                metrics_store["nwdaf_api_status"] = 0

        time.sleep(2)


def run_server():
    server = http.server.ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), TelemetryHandler)
    poller = threading.Thread(target=poll_external_nfs, daemon=True)
    poller.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    run_server()
