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
import threading
import time
import urllib.request
import urllib.error

LISTEN_PORT = 9100
LISTEN_HOST = "0.0.0.0"

METRICS_LOCK = threading.Lock()
metrics_store = {
    # Domain 4: End-to-End UE Metrics (VM-5)
    "e2e_slice1_throughput_mbps": 0.0,
    "e2e_slice1_jitter_ms": 0.0,
    "e2e_slice2_latency_rtt_ms": 0.0,
    "e2e_slice2_packet_loss_pct": 0.0,

    # Domain 1: 5G Core & NWDAF (VM-3)
    "nwdaf_slice_load_level": {
        "01000001": 5.0,     # eMBB (SST 1, SD 1)
        "de00007b": 5.0      # URLLC (SST 222, SD 123)
    },
    "upf_queue_backlog_bytes": {
        "01000001": 0.0,
        "de00007b": 0.0
    },
    "upf_packet_drops": {
        "01000001": 0.0,
        "de00007b": 0.0
    },
    "upf_bytes_sent": {
        "01000001": 0.0,
        "de00007b": 0.0
    },

    # Domain 2: Split RAN Radio Metrics (VM-4)
    "ran_cell_prb_utilization": {
        "1": 10.0,           # Cell-1 (DU-1 :4043)
        "2": 10.0            # Cell-2 (DU-2 :4044)
    },
    "ran_cell_mcs": {
        "1": 0.0,
        "2": 0.0
    },
    "ran_cell_bler": {
        "1": 0.0,
        "2": 0.0
    },
    "ran_cell_snr_db": {
        "1": 25.0,
        "2": 25.0
    },
    "ran_cell_rssi_dbm": {
        "1": -42.0,
        "2": -42.0
    },
    "ran_cell_ulsch_errors": {
        "1": 0.0,
        "2": 0.0
    },

    # Domain 3: RIC Intelligence (VM-1 / VM-2)
    "rapp_diagnosed_bottleneck": 0,    # 0: NORMAL, 1: RAN, 2: CORE, 3: JOINT
    "rapp_confidence": 1.0,
    "a1_policy_threshold": 20.0        # URLLC SLA latency threshold (ms)
}


last_report_ue1 = 0.0
last_report_ue2 = 0.0
last_nwdaf_poll_time = 0.0



def format_prometheus_metrics():
    global last_report_ue1, last_report_ue2
    lines = []
    now = time.time()
    with METRICS_LOCK:
        # Auto-reset stale UE metrics if trafgen stopped pushing (> 3.5 seconds)
        if last_report_ue1 > 0.0 and (now - last_report_ue1 > 3.5):
            metrics_store["e2e_slice1_throughput_mbps"] = 0.0
            metrics_store["e2e_slice1_jitter_ms"] = 0.0
        if last_report_ue2 > 0.0 and (now - last_report_ue2 > 3.5):
            metrics_store["e2e_slice2_latency_rtt_ms"] = 0.0
            metrics_store["e2e_slice2_packet_loss_pct"] = 0.0

        lines.append("# HELP e2e_slice1_throughput_mbps End-to-end throughput for Slice 1 (eMBB) in Mbps")
        lines.append("# TYPE e2e_slice1_throughput_mbps gauge")
        lines.append(f"e2e_slice1_throughput_mbps {metrics_store['e2e_slice1_throughput_mbps']:.2f}")

        lines.append("# HELP e2e_slice1_jitter_ms End-to-end jitter for Slice 1 (eMBB) in ms")
        lines.append("# TYPE e2e_slice1_jitter_ms gauge")
        lines.append(f"e2e_slice1_jitter_ms {metrics_store['e2e_slice1_jitter_ms']:.3f}")

        lines.append("# HELP e2e_slice2_latency_rtt_ms End-to-end precision RTT latency for Slice 2 (URLLC) in ms")
        lines.append("# TYPE e2e_slice2_latency_rtt_ms gauge")
        lines.append(f"e2e_slice2_latency_rtt_ms {metrics_store['e2e_slice2_latency_rtt_ms']:.2f}")

        lines.append("# HELP e2e_slice2_packet_loss_pct End-to-end packet loss percentage for Slice 2 (URLLC)")
        lines.append("# TYPE e2e_slice2_packet_loss_pct gauge")
        lines.append(f"e2e_slice2_packet_loss_pct {metrics_store['e2e_slice2_packet_loss_pct']:.2f}")

        lines.append("# HELP nwdaf_slice_load_level NWDAF reported slice load level percentage")
        lines.append("# TYPE nwdaf_slice_load_level gauge")
        for snssai, val in metrics_store["nwdaf_slice_load_level"].items():
            lines.append(f'nwdaf_slice_load_level{{snssai="{snssai}"}} {val:.2f}')

        lines.append("# HELP upf_queue_backlog_bytes UPF egress kernel queue backlog bytes")
        lines.append("# TYPE upf_queue_backlog_bytes gauge")
        for snssai, val in metrics_store["upf_queue_backlog_bytes"].items():
            lines.append(f'upf_queue_backlog_bytes{{snssai="{snssai}"}} {val:.2f}')

        lines.append("# HELP upf_packet_drops UPF kernel queue packet drops delta")
        lines.append("# TYPE upf_packet_drops gauge")
        for snssai, val in metrics_store["upf_packet_drops"].items():
            lines.append(f'upf_packet_drops{{snssai="{snssai}"}} {val:.2f}')

        lines.append("# HELP upf_bytes_sent UPF egress total sent bytes")
        lines.append("# TYPE upf_bytes_sent counter")
        for snssai, val in metrics_store["upf_bytes_sent"].items():
            lines.append(f'upf_bytes_sent{{snssai="{snssai}"}} {val:.0f}')

        lines.append("# HELP ran_cell_prb_utilization RAN PRB resource block utilization percentage")
        lines.append("# TYPE ran_cell_prb_utilization gauge")
        for cell, val in metrics_store["ran_cell_prb_utilization"].items():
            lines.append(f'ran_cell_prb_utilization{{cell_id="{cell}"}} {val:.2f}')

        lines.append("# HELP ran_cell_mcs RAN Modulation and Coding Scheme (MCS)")
        lines.append("# TYPE ran_cell_mcs gauge")
        for cell, val in metrics_store["ran_cell_mcs"].items():
            lines.append(f'ran_cell_mcs{{cell_id="{cell}"}} {val:.1f}')

        lines.append("# HELP ran_cell_bler RAN Block Error Rate (BLER)")
        lines.append("# TYPE ran_cell_bler gauge")
        for cell, val in metrics_store["ran_cell_bler"].items():
            lines.append(f'ran_cell_bler{{cell_id="{cell}"}} {val:.4f}')

        lines.append("# HELP ran_cell_snr_db RAN Signal to Noise Ratio in dB")
        lines.append("# TYPE ran_cell_snr_db gauge")
        for cell, val in metrics_store["ran_cell_snr_db"].items():
            lines.append(f'ran_cell_snr_db{{cell_id="{cell}"}} {val:.2f}')

        lines.append("# HELP ran_cell_rssi_dbm RAN Received Signal Strength Indicator in dBm")
        lines.append("# TYPE ran_cell_rssi_dbm gauge")
        for cell, val in metrics_store["ran_cell_rssi_dbm"].items():
            lines.append(f'ran_cell_rssi_dbm{{cell_id="{cell}"}} {val:.2f}')

        lines.append("# HELP ran_cell_ulsch_errors Cumulative MAC layer ULSCH transmission errors")
        lines.append("# TYPE ran_cell_ulsch_errors gauge")
        for cell, val in metrics_store["ran_cell_ulsch_errors"].items():
            lines.append(f'ran_cell_ulsch_errors{{cell_id="{cell}"}} {val:.0f}')

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

                global last_report_ue1, last_report_ue2
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
                            if "rtt_ms" in payload:
                                metrics_store["e2e_slice2_latency_rtt_ms"] = float(payload["rtt_ms"])
                            if "packet_loss_pct" in payload:
                                metrics_store["e2e_slice2_packet_loss_pct"] = float(payload["packet_loss_pct"])

                    for key in ("e2e_slice1_throughput_mbps", "e2e_slice1_jitter_ms",
                                "e2e_slice2_latency_rtt_ms", "e2e_slice2_packet_loss_pct",
                                "rapp_diagnosed_bottleneck", "rapp_confidence", "a1_policy_threshold"):
                        if key in payload:
                            if "slice1" in key:
                                last_report_ue1 = time.time()
                            elif "slice2" in key:
                                last_report_ue2 = time.time()
                            metrics_store[key] = float(payload[key])

                    if "ran_cell_prb_utilization" in payload and isinstance(payload["ran_cell_prb_utilization"], dict):
                        for cell, val in payload["ran_cell_prb_utilization"].items():
                            metrics_store["ran_cell_prb_utilization"][str(cell)] = float(val)

                    if "ran_cell_radio_stats" in payload and isinstance(payload["ran_cell_radio_stats"], dict):
                        for cell, stats in payload["ran_cell_radio_stats"].items():
                            cid = str(cell)
                            if isinstance(stats, dict):
                                if "mcs" in stats and stats["mcs"] is not None:
                                    metrics_store["ran_cell_mcs"][cid] = float(stats["mcs"])
                                if "bler" in stats and stats["bler"] is not None:
                                    metrics_store["ran_cell_bler"][cid] = float(stats["bler"])
                                if "snr_db" in stats and stats["snr_db"] is not None:
                                    metrics_store["ran_cell_snr_db"][cid] = float(stats["snr_db"])
                                if "rssi_dbm" in stats and stats["rssi_dbm"] is not None:
                                    metrics_store["ran_cell_rssi_dbm"][cid] = float(stats["rssi_dbm"])
                                if "ulsch_errors" in stats and stats["ulsch_errors"] is not None:
                                    metrics_store["ran_cell_ulsch_errors"][cid] = float(stats["ulsch_errors"])

                    # Core & UPF telemetry handling (safe against null / None values from core_adapter.py v9)
                    core_metric_keys = [
                        "upf_interface_tx_mbps", "upf_interface_rx_mbps",
                        "upf_tx_bytes_total", "upf_rx_bytes_total",
                        "upf_qdisc_backlog_bytes", "upf_queue_backlog_bytes",
                        "upf_qdisc_drops_delta", "upf_packet_drops", "upf_qdisc_drops_per_sec"
                    ]
                    for m_key in core_metric_keys:
                        if m_key in payload and isinstance(payload[m_key], dict):
                            if m_key not in metrics_store:
                                metrics_store[m_key] = {}
                            for snssai, val in payload[m_key].items():
                                if val is not None:
                                    try:
                                        metrics_store[m_key][str(snssai)] = float(val)
                                    except (ValueError, TypeError):
                                        pass

                    # Synchronize aliases for Prometheus /metrics format
                    if "upf_qdisc_backlog_bytes" in payload and isinstance(payload["upf_qdisc_backlog_bytes"], dict):
                        for snssai, val in payload["upf_qdisc_backlog_bytes"].items():
                            if val is not None:
                                try:
                                    metrics_store["upf_queue_backlog_bytes"][str(snssai)] = float(val)
                                except (ValueError, TypeError):
                                    pass
                    if "upf_qdisc_drops_delta" in payload and isinstance(payload["upf_qdisc_drops_delta"], dict):
                        for snssai, val in payload["upf_qdisc_drops_delta"].items():
                            if val is not None:
                                try:
                                    metrics_store["upf_packet_drops"][str(snssai)] = float(val)
                                except (ValueError, TypeError):
                                    pass
                    elif "upf_qdisc_drops_per_sec" in payload and isinstance(payload["upf_qdisc_drops_per_sec"], dict):
                        for snssai, val in payload["upf_qdisc_drops_per_sec"].items():
                            if val is not None:
                                try:
                                    metrics_store["upf_packet_drops"][str(snssai)] = float(val)
                                except (ValueError, TypeError):
                                    pass
                    if "upf_tx_bytes_total" in payload and isinstance(payload["upf_tx_bytes_total"], dict):
                        for snssai, val in payload["upf_tx_bytes_total"].items():
                            if val is not None:
                                try:
                                    metrics_store["upf_bytes_sent"][str(snssai)] = float(val)
                                except (ValueError, TypeError):
                                    pass

                    # Dynamic estimation of NWDAF slice load if external Nnwdaf is unavailable
                    if "upf_interface_tx_mbps" in payload and isinstance(payload["upf_interface_tx_mbps"], dict):
                        if (time.time() - last_nwdaf_poll_time) > 5.0:
                            # Slice 1 (eMBB): capacity ~25 Mbps
                            tx1 = payload["upf_interface_tx_mbps"].get("01000001")
                            if tx1 is not None:
                                try:
                                    metrics_store["nwdaf_slice_load_level"]["01000001"] = round(min(100.0, max(5.0, (float(tx1) / 25.0) * 100.0)), 2)
                                except (ValueError, TypeError):
                                    pass
                            # Slice 2 (URLLC): capacity ~5 Mbps
                            tx2 = payload["upf_interface_tx_mbps"].get("de00007b")
                            if tx2 is not None:
                                try:
                                    metrics_store["nwdaf_slice_load_level"]["de00007b"] = round(min(100.0, max(5.0, (float(tx2) / 5.0) * 100.0)), 2)
                                except (ValueError, TypeError):
                                    pass

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
