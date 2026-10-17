#!/usr/bin/env python3
"""
Simplified Single-Scenario Telemetry Recorder for 5G O-RAN Thesis
Location on VM-6: /opt/oran/monitoring/scripts/record_experiment.py
Pure Python 3 Standard Library - Zero External Dependencies

Responsibilities:
1. Provide a single, straightforward entry point to record one experiment scenario per session.
2. Scrape telemetry from Prometheus Exporter (:9100) at 1.000 Hz monotonic cadence.
3. Save data and raw responses transparently with zero synthetic data and zero quality-gate decisions.
4. Stop cleanly on target duration or operator signals (SIGINT / SIGTERM), persisting metadata in manifest.json.
5. Explicitly manage collector lifecycle by closing active_run_id upon completion and tracking storage health.
"""

import argparse
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

METRICS_URL_DEFAULT = "http://127.0.0.1:9100/metrics"
DATA_DIR_DEFAULT = os.getenv("MONITORING_DATA_DIR", "/opt/oran/monitoring/data")

HEADERS = [
    "timestamp_utc", "elapsed_sec", "run_id", "scrape_ok", "scrape_latency_ms",
    "e2e_slice1_tput_mbps", "e2e_slice1_jitter_ms", "e2e_slice1_rtt_ms", "e2e_slice1_loss_pct",
    "e2e_slice2_rtt_ms", "e2e_slice2_loss_pct",
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
    "event_phase_id", "event_scenario", "event_domain", "event_component"
]

CANONICAL_PRESETS = {
    "S1": ("S1_NORMAL_LIGHT", "BASELINE", "NONE"),
    "S2": ("S2_NORMAL_HIGH", "BASELINE", "NONE"),
    "S3": ("S3_RAN_OVERLOAD", "RAN", "DU-1_Cell-1"),
    "S6": ("S6_CORE_QUEUE_TBF", "CORE", "UPF-1_Slice-1"),
    "S9": ("S9_JOINT_OVERLOAD", "JOINT", "Cell-1+UPF-1"),
    "S10_A": ("S10_A_RELEASE_RAN", "CORE", "UPF-1_Slice-1"),
    "S10_B": ("S10_B_RELEASE_CORE", "BASELINE", "NONE"),
    "RECOVERY": ("RECOVERY_TRANSITION", "BASELINE", "NONE"),
    "CLEAR": ("CLEAR_FAULT", "BASELINE", "NONE"),
}

PROM_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$')
LABEL_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*=\s*"([^"]*)"')
NAN_STR = "NaN"


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


def extract_telemetry(metrics_url=METRICS_URL_DEFAULT, timeout=0.8):
    raw_data = {
        "e2e_slice1_tput_mbps": NAN_STR, "e2e_slice1_jitter_ms": NAN_STR,
        "e2e_slice1_rtt_ms": NAN_STR, "e2e_slice1_loss_pct": NAN_STR,
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
    storage_stats = {
        "nwdaf_run_polls_written": 0,
        "nwdaf_run_polls_failed": 0,
        "nwdaf_raw_polls_total": 0,
        "nwdaf_raw_polls_failed": 0
    }
    scrape_ok = 0
    t_start = time.monotonic()
    try:
        req = urllib.request.Request(metrics_url, headers={"User-Agent": "ThesisRecorder/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            latency_ms = (time.monotonic() - t_start) * 1000.0
            scrape_ok = 1
            for name, labels, val_str in parse_prometheus_text(text):
                if name == "e2e_slice1_throughput_mbps":
                    raw_data["e2e_slice1_tput_mbps"] = val_str
                elif name == "e2e_slice1_jitter_ms":
                    raw_data["e2e_slice1_jitter_ms"] = val_str
                elif name == "e2e_slice1_latency_rtt_ms":
                    raw_data["e2e_slice1_rtt_ms"] = val_str
                elif name == "e2e_slice1_packet_loss_pct":
                    raw_data["e2e_slice1_loss_pct"] = val_str
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
                elif name == "nwdaf_run_raw_polls_written":
                    try:
                        storage_stats["nwdaf_run_polls_written"] = int(float(val_str))
                    except ValueError:
                        pass
                elif name == "nwdaf_run_raw_polls_failed":
                    try:
                        storage_stats["nwdaf_run_polls_failed"] = int(float(val_str))
                    except ValueError:
                        pass
                elif name == "nwdaf_raw_polls_total":
                    try:
                        storage_stats["nwdaf_raw_polls_total"] = int(float(val_str))
                    except ValueError:
                        pass
                elif name == "nwdaf_raw_polls_failed":
                    try:
                        storage_stats["nwdaf_raw_polls_failed"] = int(float(val_str))
                    except ValueError:
                        pass
    except Exception:
        latency_ms = (time.monotonic() - t_start) * 1000.0
        scrape_ok = 0
    return raw_data, scrape_ok, latency_ms, storage_stats


def resolve_scenario_metadata(raw_scen):
    clean = (raw_scen or "S1").strip()
    key = clean.upper()
    if key in CANONICAL_PRESETS:
        canon, domain, comp = CANONICAL_PRESETS[key]
        return clean, canon, domain, comp
    return clean, key, "CUSTOM", "NONE"


def get_unique_run_dir(base_dir, base_run_id):
    candidate_id = base_run_id
    candidate_dir = os.path.join(base_dir, "raw", candidate_id)
    if not os.path.exists(candidate_dir):
        return candidate_id, candidate_dir
    counter = 1
    while True:
        candidate_id = f"{base_run_id}_{counter}"
        candidate_dir = os.path.join(base_dir, "raw", candidate_id)
        if not os.path.exists(candidate_dir):
            return candidate_id, candidate_dir
        counter += 1


def save_manifest_atomic(manifest_path, manifest_data):
    """Atomically persists manifest metadata via temporary file replacement."""
    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    os.replace(tmp_path, manifest_path)


def count_lines(filepath):
    if not os.path.exists(filepath):
        return 0
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Single-Scenario Telemetry Recorder for 5G O-RAN Thesis (VM-6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh Penggunaan:
  1. Interaktif:
     python3 record_experiment.py
  2. CLI Langsung:
     python3 record_experiment.py S1 --duration 60 --notes "Baseline ringan 10M"
     python3 record_experiment.py S3 --duration 60 --notes "Kandidat overload 80M"
     python3 record_experiment.py S6 --duration 60 --notes "Kandidat TBF Core 12M"
  3. Durasi Tanpa Batas (Manual Stop via Ctrl+C):
     python3 record_experiment.py S1 --duration 0
        """
    )
    parser.add_argument("scenario", nargs="?", default=None, help="Nama skenario eksperimen (misal: S1, S3, S6, atau custom)")
    parser.add_argument("-d", "--duration", type=int, default=None, help="Durasi perekaman dalam detik (default: 60, isi 0 untuk manual Ctrl+C)")
    parser.add_argument("-n", "--notes", default="", help="Catatan kondisi eksperimen (opsional)")
    parser.add_argument("-r", "--run-id", default=None, help="ID unik eksperimen (otomatis jika tidak diisi)")
    parser.add_argument("--metrics-url", default=METRICS_URL_DEFAULT, help=f"URL Prometheus Exporter (default: {METRICS_URL_DEFAULT})")
    parser.add_argument("--data-dir", default=DATA_DIR_DEFAULT, help=f"Direktori data telemetri (default: {DATA_DIR_DEFAULT})")

    args = parser.parse_args()

    # Interactive prompt if scenario is not passed via CLI
    scen_input = args.scenario
    if scen_input is None:
        if sys.stdin.isatty():
            try:
                val = input("Masukkan nama skenario (misal: S1, S3, S6) [S1]: ").strip()
                scen_input = val if val else "S1"
            except (KeyboardInterrupt, EOFError):
                print("\nDibatalkan.")
                sys.exit(0)
        else:
            scen_input = "S1"

    dur_input = args.duration
    if dur_input is None:
        if sys.stdin.isatty():
            try:
                val = input("Durasi perekaman dalam detik (0 = manual sampai Ctrl+C) [60]: ").strip()
                dur_input = int(val) if val else 60
            except (KeyboardInterrupt, EOFError):
                print("\nDibatalkan.")
                sys.exit(0)
            except ValueError:
                dur_input = 60
        else:
            dur_input = 60

    notes_input = args.notes
    if not notes_input and sys.stdin.isatty() and args.scenario is None:
        try:
            val = input("Catatan eksperimen (opsional): ").strip()
            notes_input = val
        except (KeyboardInterrupt, EOFError):
            notes_input = ""

    scenario_name, canonical_scenario, domain, component = resolve_scenario_metadata(scen_input)
    phase_id = f"phase_1_{scen_input.strip().upper()}"

    # Auto-generate unique Run ID if not provided
    ts_now = time.strftime('%Y%m%d_%H%M%S')
    base_run_id = args.run_id if args.run_id else f"EXP_{scen_input.strip().upper()}_{ts_now}"

    data_dir = os.path.abspath(args.data_dir)
    os.makedirs(data_dir, exist_ok=True)

    run_id, run_dir = get_unique_run_dir(data_dir, base_run_id)
    os.makedirs(run_dir, exist_ok=True)

    # Synchronize active run and event states for collector and tools
    try:
        with open(os.path.join(data_dir, "active_run_id.txt"), "w", encoding="utf-8") as f:
            f.write(run_id + "\n")
        with open(os.path.join(data_dir, "active_event.json"), "w", encoding="utf-8") as f:
            json.dump({"phase_id": phase_id, "scenario": canonical_scenario, "domain": domain, "component": component}, f)
    except Exception as e:
        print(f"[!] Warning: Gagal sinkronisasi active_run_id/active_event: {e}", file=sys.stderr)

    csv_file = os.path.join(run_dir, f"telemetry_{run_id}.csv")
    manifest_file = os.path.join(run_dir, "manifest.json")
    jsonl_file = os.path.join(run_dir, "nwdaf_raw_poll_responses.jsonl")

    start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest = {
        "run_id": run_id,
        "scenario": scenario_name,
        "canonical_scenario": canonical_scenario,
        "operator_notes": notes_input,
        "start_time_utc": start_utc,
        "end_time_utc": None,
        "duration_sec": 0.0,
        "target_duration_sec": dur_input,
        "total_samples": 0,
        "scrape_success_samples": 0,
        "scrape_failed_samples": 0,
        "stop_reason": "IN_PROGRESS",
        "telemetry_csv": f"telemetry_{run_id}.csv",
        "nwdaf_raw_jsonl": "nwdaf_raw_poll_responses.jsonl",
        "recording_status": "RECORDING",
        "storage_audit": {},
        "storage_warnings": []
    }
    try:
        save_manifest_atomic(manifest_file, manifest)
    except Exception as e:
        print(f"[!] Warning: Gagal inisialisasi manifest.json: {e}", file=sys.stderr)

    print("=" * 80)
    print("5G O-RAN TELEMETRY RECORDER (VM-6)")
    print(f"Run ID          : {run_id}")
    print(f"Skenario        : {scenario_name} ({canonical_scenario})")
    print(f"Target Durasi   : {'Manual (Ctrl+C)' if dur_input == 0 else f'{dur_input} detik'}")
    if notes_input:
        print(f"Catatan         : {notes_input}")
    print(f"Direktori Run   : {run_dir}")
    print(f"Berkas Output   : {csv_file}")
    print("=" * 80)
    print("[*] Mulai merekam telemetri 1.0 Hz (Tekan Ctrl+C kapan saja untuk berhenti aman)...\n")

    running = True
    stop_reason = "IN_PROGRESS"

    def sig_handler(sig, frame):
        nonlocal running, stop_reason
        if sig == signal.SIGINT:
            stop_reason = "INTERRUPTED_BY_OPERATOR"
            print("\n[*] Sinyal stop diterima (Ctrl+C). Menutup berkas dengan aman...", flush=True)
        elif sig == signal.SIGTERM:
            stop_reason = "TERMINATED_BY_SIGTERM"
            print("\n[*] Sinyal SIGTERM diterima. Menutup berkas dengan aman...", flush=True)
        elif hasattr(signal, "SIGBREAK") and sig == signal.SIGBREAK:
            stop_reason = "INTERRUPTED_BY_OPERATOR"
            print("\n[*] Sinyal stop diterima (Ctrl+Break). Menutup berkas dengan aman...", flush=True)
        else:
            stop_reason = f"TERMINATED_BY_SIGNAL_{sig}"
            print(f"\n[*] Sinyal {sig} diterima. Menutup berkas dengan aman...", flush=True)
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, sig_handler)

    total_samples = 0
    scrape_ok_count = 0
    scrape_fail_count = 0
    last_storage_stats = {
        "nwdaf_run_polls_written": 0,
        "nwdaf_run_polls_failed": 0,
        "nwdaf_raw_polls_total": 0,
        "nwdaf_raw_polls_failed": 0
    }

    write_error = None
    start_mono = time.monotonic()
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
            f.flush()

            next_tick = start_mono

            while running:
                now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                elapsed = time.monotonic() - start_mono

                if dur_input > 0 and elapsed >= dur_input:
                    stop_reason = "DURATION_REACHED"
                    break

                telemetry, scrape_ok, scrape_lat, storage_stats = extract_telemetry(metrics_url=args.metrics_url)
                last_storage_stats = storage_stats
                if scrape_ok:
                    scrape_ok_count += 1
                else:
                    scrape_fail_count += 1

                row = [
                    now_utc, f"{elapsed:.6f}", run_id, scrape_ok, f"{scrape_lat:.3f}",
                    telemetry["e2e_slice1_tput_mbps"], telemetry["e2e_slice1_jitter_ms"],
                    telemetry["e2e_slice1_rtt_ms"], telemetry["e2e_slice1_loss_pct"],
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
                    phase_id, canonical_scenario, domain, component
                ]
                writer.writerow(row)
                f.flush()

                total_samples += 1

                dur_str = f"{dur_input}s" if dur_input > 0 else "inf"
                print(
                    f"[{elapsed:>5.1f}s/{dur_str}] Skenario: {scenario_name:<4} | "
                    f"eMBB: {telemetry['e2e_slice1_tput_mbps']:>6}M | "
                    f"UPF Backlog: {telemetry['upf_backlog_bytes_embb']:>6}B | "
                    f"PRB C1: {telemetry['ran_prb_cell1']:>5}% | "
                    f"Scrape: {'OK' if scrape_ok else 'FAIL'}",
                    flush=True
                )

                next_tick += 1.0
                sleep_wait = next_tick - time.monotonic()
                if sleep_wait > 0:
                    time.sleep(sleep_wait)

            if stop_reason == "IN_PROGRESS":
                stop_reason = "COMPLETED"

    except Exception as e:
        write_error = str(e)
        stop_reason = f"WRITE_ERROR: {e}"
        print(f"\n[!] Error penulisan telemetri CSV: {e}", file=sys.stderr)

    # 1. Close session in active_run_id.txt so collector stops adding polls to this finished run
    try:
        run_file_path = os.path.join(data_dir, "active_run_id.txt")
        with open(run_file_path, "w", encoding="utf-8") as f:
            f.write("")
            f.flush()
            os.fsync(f.fileno())
        event_file_path = os.path.join(data_dir, "active_event.json")
        with open(event_file_path, "w", encoding="utf-8") as f:
            json.dump({"phase_id": "idle", "scenario": "IDLE", "domain": "BASELINE", "component": "NONE"}, f)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"[!] Warning: Gagal menutup status active_run_id/active_event: {e}", file=sys.stderr)

    # Coordinate and drain any in-flight NWDAF poll in the collector daemon
    time.sleep(0.3)

    end_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actual_duration = round(time.monotonic() - start_mono, 3)

    # Final scrape to capture any terminal collector storage counters
    try:
        _, _, _, final_storage = extract_telemetry(metrics_url=args.metrics_url, timeout=0.5)
        if final_storage.get("nwdaf_run_polls_written", 0) > last_storage_stats.get("nwdaf_run_polls_written", 0):
            last_storage_stats["nwdaf_run_polls_written"] = final_storage["nwdaf_run_polls_written"]
        if final_storage.get("nwdaf_run_polls_failed", 0) > last_storage_stats.get("nwdaf_run_polls_failed", 0):
            last_storage_stats["nwdaf_run_polls_failed"] = final_storage["nwdaf_run_polls_failed"]
    except Exception:
        pass

    # Audit storage files on disk
    csv_bytes = os.path.getsize(csv_file) if os.path.exists(csv_file) else 0
    jsonl_bytes = os.path.getsize(jsonl_file) if os.path.exists(jsonl_file) else 0
    jsonl_lines = count_lines(jsonl_file)

    storage_warnings = []
    failed_polls = last_storage_stats.get("nwdaf_run_polls_failed", 0)
    if failed_polls > 0:
        storage_warnings.append(f"Collector melaporkan {failed_polls} kegagalan penulisan raw NWDAF poll ke arsip")

    # Determine recording status strictly based on technical storage facts
    if write_error is not None:
        rec_status = "FAILED"
    elif total_samples == 0:
        rec_status = "FAILED"
    elif failed_polls > 0:
        rec_status = "PARTIAL_STORAGE_WARNING"
    else:
        rec_status = "SUCCESS"

    manifest["end_time_utc"] = end_utc
    manifest["duration_sec"] = actual_duration
    manifest["total_samples"] = total_samples
    manifest["scrape_success_samples"] = scrape_ok_count
    manifest["scrape_failed_samples"] = scrape_fail_count
    manifest["stop_reason"] = stop_reason
    manifest["recording_status"] = rec_status
    manifest["storage_warnings"] = storage_warnings
    manifest["storage_audit"] = {
        "telemetry_csv": {
            "filename": f"telemetry_{run_id}.csv",
            "rows": total_samples,
            "size_bytes": csv_bytes,
            "status": "WRITTEN" if total_samples > 0 else "EMPTY"
        },
        "nwdaf_raw_jsonl": {
            "filename": "nwdaf_raw_poll_responses.jsonl",
            "polls_written_reported": last_storage_stats.get("nwdaf_run_polls_written", 0),
            "polls_failed_reported": failed_polls,
            "file_exists": os.path.exists(jsonl_file),
            "file_bytes": jsonl_bytes,
            "lines_counted": jsonl_lines
        }
    }
    if write_error:
        manifest["error_message"] = write_error

    manifest_write_ok = True
    manifest_error = None
    try:
        save_manifest_atomic(manifest_file, manifest)
    except Exception as e:
        manifest_write_ok = False
        manifest_error = str(e)
        manifest["recording_status"] = "FAILED"
        print(f"[!] Error fatal: Gagal menyimpan manifest akhir {manifest_file}: {e}", file=sys.stderr)

    print("\n" + "=" * 80)
    print("HASIL PEREKAMAN EKSPERIMEN")
    if not manifest_write_ok:
        print(f"Status Teknis    : FAILED (Gagal menyimpan manifest: {manifest_error})")
    elif rec_status == "PARTIAL_STORAGE_WARNING":
        print(f"Status Teknis    : PARTIAL_STORAGE_WARNING ({'; '.join(storage_warnings)})")
    else:
        print(f"Status Teknis    : {rec_status}")
    print(f"Identitas Run    : {run_id}")
    print(f"Skenario         : {scenario_name} ({canonical_scenario})")
    print(f"Total Sampel     : {total_samples} baris ({actual_duration:.1f} detik)")
    print(f"Status Scrape    : {scrape_ok_count} OK, {scrape_fail_count} Gagal")
    print(f"Arsip NWDAF      : {last_storage_stats.get('nwdaf_run_polls_written', 0)} poll tersimpan, {failed_polls} gagal")
    print(f"Alasan Selesai   : {stop_reason}")
    print(f"Direktori Arsip  : {run_dir}")
    print(f"Berkas CSV       : {csv_file}")
    print(f"Berkas Manifest  : {manifest_file}")
    print("=" * 80)

    if not manifest_write_ok or rec_status == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
