#!/usr/bin/env python3
"""
Telemetry Collector & Prometheus Exporter for 5G O-RAN Thesis Testbed
Location on VM-6: /opt/oran/monitoring/collector/telemetry_collector.py
Pure Python 3 Standard Library - Zero External Pip Dependencies
Ingests telemetry from VM-3 (UPF Core), VM-4 (RAN E2/FlexRIC), and VM-5 (UE QoS),
exposing Prometheus metrics on http://10.102.0.67:9100/metrics and ingesting on /report.
"""

import http.server
import json
import math
import threading
import time
import urllib.request
import urllib.error

LISTEN_PORT = 9100
LISTEN_HOST = "0.0.0.0"

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
        "01000001": float("nan"),     # eMBB (SST 1, SD 1)
        "de00007b": float("nan")      # URLLC (SST 222, SD 123)
    },
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

        # Auto-reset stale NWDAF metrics if external Nnwdaf daemon stopped responding (> 5 seconds)
        if last_nwdaf_poll_time > 0.0 and (now - last_nwdaf_poll_time > 5.0):
            for snssai in ("01000001", "de00007b"):
                metrics_store["nwdaf_slice_load_level"][snssai] = float("nan")

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

        lines.append("# HELP nwdaf_slice_load_level NWDAF reported slice load level percentage")
        lines.append("# TYPE nwdaf_slice_load_level gauge")
        for snssai, val in metrics_store["nwdaf_slice_load_level"].items():
            lines.append(f'nwdaf_slice_load_level{{snssai="{snssai}"}} {fmt_val(val)}')

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

                    # Dynamic estimation of slice load derived from UPF Tx throughput
                    if "upf_interface_tx_mbps" in payload and isinstance(payload["upf_interface_tx_mbps"], dict):
                        tx1 = payload["upf_interface_tx_mbps"].get("01000001")
                        load1 = round(min(100.0, max(5.0, (float(tx1) / 25.0) * 100.0)), 2) if tx1 is not None else float("nan")
                        metrics_store["estimated_slice_load_level"]["01000001"] = load1

                        tx2 = payload["upf_interface_tx_mbps"].get("de00007b")
                        load2 = round(min(100.0, max(5.0, (float(tx2) / 5.0) * 100.0)), 2) if tx2 is not None else float("nan")
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


def poll_external_nfs():
    global last_nwdaf_poll_time
    while True:
        try:
            req = urllib.request.Request(
                "http://10.102.0.164:8080/nnwdaf-eventsubscription/v1/slice-load-level",
                headers={"User-Agent": "Thesis-Collector/1.0"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    with METRICS_LOCK:
                        last_nwdaf_poll_time = time.time()
                        if "sliceLoadLevelInfos" in data:
                            for info in data["sliceLoadLevelInfos"]:
                                snssai = info.get("snssai", {})
                                key = f"{snssai.get('sst', 1):02x}{int(snssai.get('sd', '1'), 16):06x}"
                                metrics_store["nwdaf_slice_load_level"][key] = float(info.get("loadLevel", 0.0))
        except Exception:
            pass

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
