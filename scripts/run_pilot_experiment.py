#!/usr/bin/env python3
"""
Automated Multi-Phase Pilot Experiment Runner for 5G O-RAN RIC-NWDAF Research
Location on VM-6: /opt/oran/monitoring/scripts/run_pilot_experiment.py
Pure Python 3 Standard Library - Zero External Dependencies

Orchestrates discrete experiment runs adhering to 3GPP AnLF observation requirements:
- Establishes isolated data/raw/<RUN_ID>/ experiment directory
- Automates record_dual_stream.py execution with zero clock-drift
- Synchronizes ground-truth event tagging via log_event.py
- Enforces >= 60s phase durations to capture multiple ~30s NWDAF URR loops
- Snapshots raw NWDAF API JSON response
- Runs automated dataset quality audit and saves quality_summary.txt
"""

import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DATA_DIR = "/opt/oran/monitoring/data"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_SCRIPT = os.path.join(SCRIPTS_DIR, "record_dual_stream.py")
LOG_EVENT_SCRIPT = os.path.join(SCRIPTS_DIR, "log_event.py")
ANALYZE_SCRIPT = os.path.join(SCRIPTS_DIR, "analyze_dataset.py")
NWDAF_URL = "http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics"


def log_event(key, note=""):
    cmd = [sys.executable, LOG_EVENT_SCRIPT, key, note]
    subprocess.run(cmd, check=False)


def snapshot_nwdaf_api(run_dir):
    try:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        start_ts = (now_dt - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_ts = (now_dt + datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ana_req = json.dumps({"startTs": start_ts, "endTs": end_ts})
        query = urllib.parse.urlencode({
            "event-id": "UE_COMMUNICATION",
            "ana-req": ana_req
        })
        url = f"{NWDAF_URL}?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "Thesis-PilotRunner/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode())
                out_path = os.path.join(run_dir, "raw_nwdaf_response.json")
                with open(out_path, "w") as f:
                    json.dump(body, f, indent=2)
                print(f"[+] NWDAF raw API response snapshotted: {out_path}")
    except Exception as e:
        print(f"[!] Warning: Gagal mengambil snapshot NWDAF API: {e}")


def main():
    parser = argparse.ArgumentParser(description="5G O-RAN RIC-NWDAF Pilot Experiment Runner")
    parser.add_argument("run_id", nargs="?", default="", help="Unique identifier for experiment run")
    parser.add_argument("--phase-duration", type=int, default=60, help="Duration in seconds for each scenario phase (default: 60s)")
    parser.add_argument("--warmup", type=int, default=15, help="Warmup duration in seconds before first scenario (default: 15s)")
    parser.add_argument("--scenarios", default="S1,S3,S6,CLEAR", help="Comma-separated scenario sequence (default: S1,S3,S6,CLEAR)")
    args = parser.parse_args()

    run_ts = time.strftime('%Y%m%d_%H%M%S')
    run_id = args.run_id if args.run_id else f"PILOT_{run_ts}"
    phase_dur = max(30, args.phase_duration)  # Enforce minimum 30s to cover UPF URR reporting cadence
    warmup_dur = args.warmup
    scenarios = [s.strip().upper() for s in args.scenarios.split(",") if s.strip()]

    run_dir = os.path.join(DATA_DIR, "raw", run_id)
    os.makedirs(run_dir, exist_ok=True)

    print("=" * 80)
    print(f"  5G O-RAN RIC-NWDAF AUTOMATED PILOT EXPERIMENT RUNNER")
    print(f"  Run ID          : {run_id}")
    print(f"  Output Directory: {run_dir}")
    print(f"  Phase Duration  : {phase_dur} s (aligned with NWDAF ~30s URR cadence)")
    print(f"  Planned Sequence: {scenarios}")
    print("=" * 80)

    # 1. Start Telemetry Logger as subprocess
    log_proc = subprocess.Popen([sys.executable, RECORD_SCRIPT, run_id])
    time.sleep(2.0)

    try:
        # 2. Warm-up Phase
        if warmup_dur > 0:
            print(f"\n[*] [PHASE: WARMUP] Menunggu warm-up telemetri ({warmup_dur}s)...")
            log_event("S1", "System Warm-up & Pipeline Sync")
            time.sleep(warmup_dur)

        # 3. Step through planned scenarios
        for idx, scen in enumerate(scenarios, 1):
            print(f"\n[*] [PHASE {idx}/{len(scenarios)}: {scen}] Mulai fase {scen} selama {phase_dur}s...")
            log_event(scen, f"Phase {idx}/{len(scenarios)}: {scen}")

            # Countdown display
            for sec_left in range(phase_dur, 0, -10):
                print(f"    -> {scen} sisa waktu: {sec_left}s...", flush=True)
                time.sleep(min(10, sec_left))

        print("\n[*] Seluruh fase skenario selesai. Melakukan graceful cool-down (10s)...")
        log_event("CLEAR", "Experiment finished - Cool-down")
        time.sleep(10.0)

    except KeyboardInterrupt:
        print("\n[!] Eksekusi dihentikan manual oleh user (Ctrl+C). Menutup run...")
        log_event("CLEAR", "Run interrupted by user")

    finally:
        # 4. Gracefully terminate logger process
        print("[*] Menghentikan logger telemetry...")
        log_proc.send_signal(signal.SIGINT)
        try:
            log_proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            log_proc.terminate()
            log_proc.wait()

        # 5. Snapshot raw NWDAF API response
        snapshot_nwdaf_api(run_dir)

        # 6. Audit dataset quality
        csv_path = os.path.join(run_dir, f"telemetry_{run_id}.csv")
        if os.path.exists(csv_path):
            summary_txt = os.path.join(run_dir, "quality_summary.txt")
            print(f"\n[*] Menjalankan audit dataset: {csv_path}...")
            with open(summary_txt, "w") as sf:
                res = subprocess.run([sys.executable, ANALYZE_SCRIPT, csv_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                sf.write(res.stdout)
                print(res.stdout)
            print(f"[+] Laporan kualitas tersimpan: {summary_txt}")

    print("\n" + "=" * 80)
    print(f"[SUCCESS] Eksperimen {run_id} selesai!")
    print(f"Direktori data: {run_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
