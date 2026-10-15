#!/usr/bin/env python3
"""
High-Precision Dual-Stream Telemetry Logger for 5G O-RAN Thesis
Location on VM-6: /opt/oran/monitoring/scripts/record_dual_stream.py
Pure Python 3 Standard Library - Zero External Dependencies
Records 1.000 Hz continuous time-series telemetry from Prometheus Exporter (:9100)
with zero-drift monotonic timing and synchronizes active fault event annotations.
"""

import csv
import datetime
import json
import math
import os
import re
import signal
import sys
import time
import urllib.request

METRICS_URL = "http://127.0.0.1:9100/metrics"
DATA_DIR = "/opt/oran/monitoring/data"
ACTIVE_EVENT_FILE = os.path.join(DATA_DIR, "active_event.json")
RUN_STATE_FILE = os.path.join(DATA_DIR, "active_run_id.txt")
os.makedirs(DATA_DIR, exist_ok=True)

RUN_TIMESTAMP = time.strftime('%Y%m%d_%H%M%S')
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else f"PILOT_{RUN_TIMESTAMP}"
with open(RUN_STATE_FILE, "w") as f:
    f.write(RUN_ID + "\n")

RUN_DIR = os.path.join(DATA_DIR, "raw", RUN_ID)
os.makedirs(RUN_DIR, exist_ok=True)

CSV_FILE = os.path.join(RUN_DIR, f"telemetry_{RUN_ID}.csv")
LEGACY_CSV_FILE = os.path.join(DATA_DIR, f"telemetry_raw_{RUN_ID}_{os.getpid()}.csv")

HEADERS = [
    "timestamp_utc", "elapsed_sec", "run_id", "scrape_ok", "scrape_latency_ms",
    "e2e_slice1_tput_mbps", "e2e_slice1_jitter_ms", "e2e_slice2_rtt_ms", "e2e_slice2_loss_pct",
    "e2e_probe_freshness",
    "nwdaf_load_embb", "nwdaf_load_urllc",
    "nwdaf_comm_ul_bytes", "nwdaf_comm_dl_bytes", "nwdaf_comm_duration_sec",
    "nwdaf_comm_vol_std_bytes", "nwdaf_comm_freshness", "nwdaf_api_status",
    "estimated_load_embb", "estimated_load_urllc",
    "upf_backlog_bytes_embb", "upf_backlog_bytes_urllc",
    "upf_drops_embb", "upf_drops_urllc",
    "ran_prb_cell1", "ran_prb_cell2",
    "ran_mcs_cell1", "ran_mcs_cell2",
    "ran_bler_cell1", "ran_bler_cell2",
    "ran_snr_cell1", "ran_snr_cell2",
    "rapp_diagnosed_bottleneck", "rapp_confidence",
    "event_scenario", "event_domain", "event_component"
]

PROM_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$')
LABEL_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*=\s*"([^"]*)"')

running = True


def sig_handler(sig, frame):
    global running
    print("\n[*] Sinyal stop diterima (Ctrl+C). Menyimpan dataset final...", flush=True)
    running = False


signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)


def parse_prometheus_text(text):
    parsed = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = PROM_LINE_RE.match(line)
        if not m:
            continue
        name, raw_labels, val_str = m.group(1), m.group(2), m.group(3)
        labels = {}
        if raw_labels:
            for lm in LABEL_RE.finditer(raw_labels):
                labels[lm.group(1)] = lm.group(2)
        parsed.append((name, labels, val_str))
    return parsed


NAN_STR = "NaN"


def extract_telemetry():
    raw_data = {
        "e2e_slice1_tput_mbps": NAN_STR, "e2e_slice1_jitter_ms": NAN_STR,
        "e2e_slice2_rtt_ms": NAN_STR, "e2e_slice2_loss_pct": NAN_STR,
        "e2e_probe_freshness": "0",
        "nwdaf_load_embb": NAN_STR, "nwdaf_load_urllc": NAN_STR,
        "nwdaf_comm_ul_bytes": NAN_STR, "nwdaf_comm_dl_bytes": NAN_STR,
        "nwdaf_comm_duration_sec": NAN_STR, "nwdaf_comm_vol_std_bytes": NAN_STR,
        "nwdaf_comm_freshness": "0", "nwdaf_api_status": "0",
        "estimated_load_embb": NAN_STR, "estimated_load_urllc": NAN_STR,
        "upf_backlog_bytes_embb": NAN_STR, "upf_backlog_bytes_urllc": NAN_STR,
        "upf_drops_embb": NAN_STR, "upf_drops_urllc": NAN_STR,
        "ran_prb_cell1": NAN_STR, "ran_prb_cell2": NAN_STR,
        "ran_mcs_cell1": NAN_STR, "ran_mcs_cell2": NAN_STR,
        "ran_bler_cell1": NAN_STR, "ran_bler_cell2": NAN_STR,
        "ran_snr_cell1": NAN_STR, "ran_snr_cell2": NAN_STR,
        "rapp_diagnosed_bottleneck": NAN_STR, "rapp_confidence": NAN_STR
    }
    scrape_ok = 0
    t_start = time.monotonic()
    try:
        req = urllib.request.Request(METRICS_URL, headers={"User-Agent": "PrecisionLogger/1.0"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            text = resp.read().decode("utf-8")
            latency_ms = (time.monotonic() - t_start) * 1000.0
            scrape_ok = 1
            for name, labels, val_str in parse_prometheus_text(text):
                if name == "e2e_slice1_throughput_mbps":
                    raw_data["e2e_slice1_tput_mbps"] = val_str
                elif name == "e2e_slice1_jitter_ms":
                    raw_data["e2e_slice1_jitter_ms"] = val_str
                elif name == "e2e_slice2_latency_rtt_ms":
                    raw_data["e2e_slice2_rtt_ms"] = val_str
                elif name == "e2e_slice2_packet_loss_pct":
                    raw_data["e2e_slice2_loss_pct"] = val_str
                elif name == "e2e_probe_freshness":
                    raw_data["e2e_probe_freshness"] = val_str
                elif name == "nwdaf_slice_load_level":
                    s = labels.get("snssai", "")
                    if s in ("01000001", "1"):
                        raw_data["nwdaf_load_embb"] = val_str
                    elif s in ("de00007b", "222"):
                        raw_data["nwdaf_load_urllc"] = val_str
                elif name == "nwdaf_comm_ul_bytes":
                    raw_data["nwdaf_comm_ul_bytes"] = val_str
                elif name == "nwdaf_comm_dl_bytes":
                    raw_data["nwdaf_comm_dl_bytes"] = val_str
                elif name == "nwdaf_comm_duration_sec":
                    raw_data["nwdaf_comm_duration_sec"] = val_str
                elif name == "nwdaf_comm_vol_std_bytes":
                    raw_data["nwdaf_comm_vol_std_bytes"] = val_str
                elif name == "nwdaf_comm_freshness":
                    raw_data["nwdaf_comm_freshness"] = val_str
                elif name == "nwdaf_api_status":
                    raw_data["nwdaf_api_status"] = val_str
                elif name == "estimated_slice_load_level":
                    s = labels.get("snssai", "")
                    if s in ("01000001", "1"):
                        raw_data["estimated_load_embb"] = val_str
                    elif s in ("de00007b", "222"):
                        raw_data["estimated_load_urllc"] = val_str
                elif name == "upf_queue_backlog_bytes":
                    s = labels.get("snssai", "")
                    if s in ("01000001", "1"):
                        raw_data["upf_backlog_bytes_embb"] = val_str
                    elif s in ("de00007b", "222"):
                        raw_data["upf_backlog_bytes_urllc"] = val_str
                elif name == "upf_packet_drops":
                    s = labels.get("snssai", "")
                    if s in ("01000001", "1"):
                        raw_data["upf_drops_embb"] = val_str
                    elif s in ("de00007b", "222"):
                        raw_data["upf_drops_urllc"] = val_str
                elif name == "ran_cell_prb_utilization":
                    cid = labels.get("cell_id", "")
                    if cid == "1":
                        raw_data["ran_prb_cell1"] = val_str
                    elif cid == "2":
                        raw_data["ran_prb_cell2"] = val_str
                elif name == "ran_cell_mcs":
                    cid = labels.get("cell_id", "")
                    if cid == "1":
                        raw_data["ran_mcs_cell1"] = val_str
                    elif cid == "2":
                        raw_data["ran_mcs_cell2"] = val_str
                elif name == "ran_cell_bler":
                    cid = labels.get("cell_id", "")
                    if cid == "1":
                        raw_data["ran_bler_cell1"] = val_str
                    elif cid == "2":
                        raw_data["ran_bler_cell2"] = val_str
                elif name == "ran_cell_snr_db":
                    cid = labels.get("cell_id", "")
                    if cid == "1":
                        raw_data["ran_snr_cell1"] = val_str
                    elif cid == "2":
                        raw_data["ran_snr_cell2"] = val_str
                elif name == "rapp_diagnosed_bottleneck":
                    raw_data["rapp_diagnosed_bottleneck"] = val_str
                elif name == "rapp_confidence":
                    raw_data["rapp_confidence"] = val_str
    except Exception:
        latency_ms = (time.monotonic() - t_start) * 1000.0
        scrape_ok = 0
    return raw_data, scrape_ok, latency_ms


def get_active_event():
    if os.path.exists(ACTIVE_EVENT_FILE):
        try:
            with open(ACTIVE_EVENT_FILE, "r") as f:
                ev = json.load(f)
                return ev.get("scenario", "UNINITIALIZED"), ev.get("domain", "UNINITIALIZED"), ev.get("component", "NONE")
        except Exception:
            pass
    return "UNINITIALIZED", "UNINITIALIZED", "NONE"


def main():
    print("=" * 90)
    print(f"  5G O-RAN High-Precision Telemetry Logger (Run: {RUN_ID})")
    print(f"  Target File: {CSV_FILE}")
    print("  Engine: Monotonic Clock (Zero Drift) | Raw Floats | Mode 'x' Exclusive")
    print("=" * 90)

    # Initial atomic initialization
    tmp_init = ACTIVE_EVENT_FILE + ".tmp"
    with open(tmp_init, "w") as f:
        json.dump({"scenario": "UNINITIALIZED", "domain": "UNINITIALIZED", "component": "NONE"}, f)
    os.replace(tmp_init, ACTIVE_EVENT_FILE)

    # Initialize manifest.json in RUN_DIR
    manifest = {
        "run_id": RUN_ID,
        "start_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "schema_version": "v1.0",
        "csv_filename": f"telemetry_{RUN_ID}.csv",
        "cadence_hz": 1.0,
        "status": "RECORDING"
    }
    with open(os.path.join(RUN_DIR, "manifest.json"), "w") as mf:
        json.dump(manifest, mf, indent=2)

    with open(CSV_FILE, "x", newline="") as f, open(LEGACY_CSV_FILE, "x", newline="") as f_legacy:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer_legacy = csv.writer(f_legacy)
        writer_legacy.writerow(HEADERS)

        start_mono = time.monotonic()
        next_tick = start_mono
        sec_idx = 0

        while running:
            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            elapsed = time.monotonic() - start_mono

            telemetry, scrape_ok, scrape_lat = extract_telemetry()
            scen, domain, comp = get_active_event()

            row = [
                now_utc, f"{elapsed:.6f}", RUN_ID, scrape_ok, f"{scrape_lat:.3f}",
                telemetry["e2e_slice1_tput_mbps"], telemetry["e2e_slice1_jitter_ms"],
                telemetry["e2e_slice2_rtt_ms"], telemetry["e2e_slice2_loss_pct"],
                telemetry["e2e_probe_freshness"],
                telemetry["nwdaf_load_embb"], telemetry["nwdaf_load_urllc"],
                telemetry["nwdaf_comm_ul_bytes"], telemetry["nwdaf_comm_dl_bytes"],
                telemetry["nwdaf_comm_duration_sec"], telemetry["nwdaf_comm_vol_std_bytes"],
                telemetry["nwdaf_comm_freshness"], telemetry["nwdaf_api_status"],
                telemetry["estimated_load_embb"], telemetry["estimated_load_urllc"],
                telemetry["upf_backlog_bytes_embb"], telemetry["upf_backlog_bytes_urllc"],
                telemetry["upf_drops_embb"], telemetry["upf_drops_urllc"],
                telemetry["ran_prb_cell1"], telemetry["ran_prb_cell2"],
                telemetry["ran_mcs_cell1"], telemetry["ran_mcs_cell2"],
                telemetry["ran_bler_cell1"], telemetry["ran_bler_cell2"],
                telemetry["ran_snr_cell1"], telemetry["ran_snr_cell2"],
                telemetry["rapp_diagnosed_bottleneck"], telemetry["rapp_confidence"],
                scen, domain, comp
            ]
            writer.writerow(row)
            f.flush()
            writer_legacy.writerow(row)
            f_legacy.flush()

            if sec_idx % 5 == 0:
                print(f"[{elapsed:>6.1f}s] Skenario: {scen:<18} | eMBB: {telemetry['e2e_slice1_tput_mbps']:>6}M | UPF-1 Backlog: {telemetry['upf_backlog_bytes_embb']:>6}B | Drops: {telemetry['upf_drops_embb']:>3} | Scrape: {'OK' if scrape_ok else 'FAIL'}", flush=True)

            sec_idx += 1
            next_tick += 1.0
            sleep_wait = next_tick - time.monotonic()
            if sleep_wait > 0:
                time.sleep(sleep_wait)

    manifest["end_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest["total_rows"] = sec_idx
    manifest["status"] = "COMPLETED"
    with open(os.path.join(RUN_DIR, "manifest.json"), "w") as mf:
        json.dump(manifest, mf, indent=2)

    print("=" * 90)
    print(f"[+] Perekaman selesai. Total baris: {sec_idx}")
    print(f"[+] File tersimpan: {CSV_FILE}")
    print(f"[+] Manifest: {os.path.join(RUN_DIR, 'manifest.json')}")


if __name__ == "__main__":
    main()
