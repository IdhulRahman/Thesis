#!/usr/bin/env python3
"""
Experiment Annotation Timeline Scheduler & Verification Runner
Location on VM-6: /opt/oran/monitoring/scripts/run_pilot_experiment.py
Pure Python 3 Standard Library - Zero External Dependencies

Architectural Role & Demarcation:
This script serves as an Annotation Timeline Scheduler and Dataset Quality Verifier.
Physical traffic generation (VM-5 trafgen.sh) and fault injections (VM-3 UPF qdisc)
are triggered by the testbed operator. This runner:
- Establishes isolated data/raw/<RUN_ID>/ directory with manifest metadata
- Spawns and strictly monitors record_dual_stream.py (verifying PID & exit code)
- Steps through planned scenario phases (>=60s each to match ~30s NWDAF URR cadence)
- Synchronizes ground-truth event tagging via log_event.py (fails run on event error)
- Enforces a 3-step recovery protocol (Release -> Recovery Transition -> Verified Baseline)
- Enforces strict dataset validation (row count >= 30, non-zero NWDAF & RAN coverage)
"""

import argparse
import csv
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
COLLECTOR_URL = "http://127.0.0.1:9100/metrics"

SCENARIO_ACTIONS = {
    "S1": "Trafik normal baseline ringan (VM-5: 10 Mbps). Pastikan PRB ~35% dan buffer UPF 0 B.",
    "S2": "Trafik normal tinggi (VM-5: 22 Mbps). Pastikan PRB ~80% dan buffer UPF tetap 0 B.",
    "S3": "Injeksi RAN Overload (VM-5: naikkan trafik ke 35-40 Mbps melebihi kapasitas radio).",
    "S6": "Injeksi Core Queue Bottleneck (VM-3: terapkan TBF rate-limit 12 Mbps pada interface UPF-1).",
    "S9": "Injeksi Joint Overload (RAN 40M di VM-5 + Core TBF 12M di VM-3 secara simultan).",
    "S10_A": "Pelepasan Gangguan RAN (VM-5: turunkan trafik ke 20M, biarkan Core TBF aktif).",
    "S10_B": "Pelepasan Gangguan Core (VM-3: hapus rate-limit TBF, amati buffer UPF drain ke 0 B)."
}


def log_event(key, note=""):
    cmd = [sys.executable, LOG_EVENT_SCRIPT, key, note]
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print(f"[FATAL ERROR] Gagal mencatat event '{key}' (exit code: {res.returncode})!")
        return False
    return True


def check_collector_alive():
    try:
        with urllib.request.urlopen(COLLECTOR_URL, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="5G O-RAN RIC-NWDAF Experiment Annotation Timeline Scheduler & Verifier")
    parser.add_argument("run_id", nargs="?", default="", help="Unique identifier for experiment run")
    parser.add_argument("--phase-duration", type=int, default=60, help="Duration in seconds for each scenario phase (default: 60s)")
    parser.add_argument("--warmup", type=int, default=15, help="Warmup duration in seconds before first scenario (default: 15s)")
    parser.add_argument("--scenarios", default="S1,S3,S6", help="Comma-separated fault scenario sequence (default: S1,S3,S6)")
    parser.add_argument("--unattended", action="store_true", help="Run automatically on timers without interactive confirmation prompts")
    args = parser.parse_args()

    run_ts = time.strftime('%Y%m%d_%H%M%S')
    run_id = args.run_id if args.run_id else f"PILOT_{run_ts}"
    phase_dur = max(30, args.phase_duration)  # Enforce minimum 30s to cover UPF URR reporting cadence
    warmup_dur = args.warmup
    scenarios = [s.strip().upper() for s in args.scenarios.split(",") if s.strip() and s.strip().upper() != "CLEAR"]

    run_dir = os.path.join(DATA_DIR, "raw", run_id)
    os.makedirs(run_dir, exist_ok=True)

    print("=" * 85)
    print(f"  5G O-RAN RIC-NWDAF EXPERIMENT TIMELINE SCHEDULER & VERIFIER")
    print(f"  Run ID          : {run_id}")
    print(f"  Output Directory: {run_dir}")
    print(f"  Phase Duration  : {phase_dur} s (aligned with NWDAF ~30s URR cadence)")
    print(f"  Planned Faults  : {scenarios}")
    print(f"  Recovery Protocol: 3-Step (Release Request -> Transition Drain -> Verified Baseline)")
    print(f"  Mode            : {'UNATTENDED (Pure Timers)' if args.unattended else 'INTERACTIVE (Operator Guided & Verified)'}")
    print("=" * 85)

    # 1. Pre-flight Check: Is Collector Exporter Alive?
    if not check_collector_alive():
        print(f"[!] Warning: Collector :9100 tidak merespons di {COLLECTOR_URL}!")
        print("    Pastikan telemetry_collector.py sudah berjalan di VM-6.")
        if not args.unattended:
            input("    Tekan [Enter] jika ingin tetap melanjutkan atau Ctrl+C untuk batal...")

    # 2. Start Telemetry Logger as subprocess
    log_proc = subprocess.Popen([sys.executable, RECORD_SCRIPT, run_id])
    time.sleep(1.5)

    # Strict Startup Verification: Did logger fail immediately?
    if log_proc.poll() is not None:
        print(f"\n[FATAL ERROR] Logger process (record_dual_stream.py) gagal berjalan!")
        print(f"Exit code: {log_proc.returncode}. Membatalkan eksperimen.")
        sys.exit(1)

    execution_failed = False
    failure_reason = ""
    events_logged_count = 0

    try:
        # 3. Warm-up Phase
        if warmup_dur > 0:
            print(f"\n[*] [PHASE: WARMUP] Menunggu warm-up telemetri ({warmup_dur}s)...")
            if not log_event("S1", "System Warm-up & Pipeline Sync"):
                raise RuntimeError("Gagal mencatat event WARMUP S1 ke file event!")
            events_logged_count += 1
            time.sleep(warmup_dur)

        # 4. Step through planned fault scenarios
        for idx, scen in enumerate(scenarios, 1):
            action_desc = SCENARIO_ACTIONS.get(scen, "Terapkan kondisi skenario.")
            print(f"\n" + "-" * 85)
            print(f"[*] [PHASE {idx}/{len(scenarios)}: {scen}]")
            print(f"    Instruksi Aksi : {action_desc}")
            print(f"    Durasi Observasi: {phase_dur} detik")
            print("-" * 85)

            if not args.unattended:
                input(f"    -> Terapkan aksi fisik di VM terkait, lalu tekan [Enter] untuk mencatat event {scen}...")

            if not log_event(scen, f"Phase {idx}/{len(scenarios)}: {scen}"):
                raise RuntimeError(f"Gagal mencatat event label {scen} ke file event!")
            events_logged_count += 1

            # Verification of logger process liveness during the run
            for sec_left in range(phase_dur, 0, -10):
                if log_proc.poll() is not None:
                    raise RuntimeError(f"Logger process crash mendadak di tengah fase {scen} (code: {log_proc.returncode})!")
                print(f"    -> Observasi {scen} sisa waktu: {sec_left}s...", flush=True)
                time.sleep(min(10, sec_left))

        # 5. Three-Step Recovery Protocol (Strict Demarcation of Fault Release vs Verified Baseline)
        print("\n" + "=" * 85)
        print("[*] [FASE PEMULIHAN 1/3: PERMINTAAN PELEPASAN GANGGUAN]")
        print("    1. Pada VM-3: Hapus limitasi antrean UPF (misal: sudo tc qdisc del dev eth0 root).")
        print("    2. Pada VM-5: Turunkan offered traffic kembali ke baseline normal 10 Mbps.")
        print("=" * 85)

        if not args.unattended:
            input("    -> Eksekusi pelepasan gangguan di VM-3/VM-5, lalu tekan [Enter] untuk mencatat transisi...")

        # Step 2: Record RECOVERY_TRANSITION (NOT NORMAL!)
        print("\n[*] [FASE PEMULIHAN 2/3: MEREKAM TRANSISI DRAIN (15s)]...")
        if not log_event("RECOVERY", "Transisi pemulihan: Gangguan dilepas, antrean buffer sedang drain ke Normal"):
            raise RuntimeError("Gagal mencatat event RECOVERY ke file event!")
        events_logged_count += 1
        time.sleep(15.0)

        # Step 3: Verify Recovery Observed
        print("\n" + "=" * 85)
        print("[*] [FASE PEMULIHAN 3/3: VERIFIKASI PEMULIHAN TERAMATI]")
        print("    Periksa Grafana / terminal:")
        print("    - Apakah buffer UPF sudah drain ke 0 B?")
        print("    - Apakah PRB radio sudah kembali stabil ke baseline (~35%)?")
        print("=" * 85)

        if not args.unattended:
            input("    -> Tekan [Enter] setelah pemulihan terbukti di Grafana/telemetri...")

        print("[*] Mencatat status CLEAR (Pemulihan terverifikasi)...")
        if not log_event("CLEAR", "Pemulihan terverifikasi: Seluruh gangguan bersih, kondisi steady-state"):
            raise RuntimeError("Gagal mencatat event CLEAR ke file event!")
        events_logged_count += 1
        time.sleep(10.0)

    except KeyboardInterrupt:
        print("\n[!] Eksekusi dibatalkan manual oleh operator (Ctrl+C).")
        log_event("ABORT", "Eksperimen dibatalkan manual sebelum selesai")
        execution_failed = True
        failure_reason = "Interrupted by user (ABORTED)"
    except Exception as e:
        print(f"\n[!] Error fatal selama eksekusi: {e}")
        log_event("ABORT", f"Eksperimen error: {e}")
        execution_failed = True
        failure_reason = str(e)

    finally:
        # 6. Gracefully terminate logger process
        print("\n[*] Menghentikan logger telemetry...")
        log_proc.send_signal(signal.SIGINT)
        try:
            log_proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            log_proc.terminate()
            log_proc.wait()

        # 7. Strict Multi-Dimensional Validation of Dataset
        csv_path = os.path.join(run_dir, f"telemetry_{run_id}.csv")
        legacy_csv_path = os.path.join(DATA_DIR, f"telemetry_raw_{run_id}_{log_proc.pid}.csv")
        target_csv = csv_path if os.path.exists(csv_path) else legacy_csv_path

        csv_valid = False
        row_count = 0
        nwdaf_valid_rows = 0
        ran_valid_rows = 0
        nwdaf_unique_volumes = set()

        if os.path.exists(target_csv) and os.path.getsize(target_csv) > 0:
            try:
                with open(target_csv, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        row_count += 1
                        # Track NWDAF AnLF validity
                        ul_vol = r.get("nwdaf_comm_ul_bytes", "")
                        if ul_vol not in ("", "NaN", "nan", "None", None):
                            try:
                                v_float = float(ul_vol)
                                nwdaf_valid_rows += 1
                                nwdaf_unique_volumes.add(v_float)
                            except ValueError:
                                pass
                        # Track RAN validity
                        prb1 = r.get("ran_prb_cell1", "")
                        if prb1 not in ("", "NaN", "nan", "None", None):
                            try:
                                float(prb1)
                                ran_valid_rows += 1
                            except ValueError:
                                pass
                csv_valid = (row_count > 0)
            except Exception as e:
                print(f"[!] Error reading CSV during validation: {e}")

        # Check Event Annotations File
        events_csv = os.path.join(run_dir, f"experiment_events_{run_id}.csv")
        events_valid = os.path.exists(events_csv) and (os.path.getsize(events_csv) > 0)

        summary_txt = os.path.join(run_dir, "quality_summary.txt")
        audit_success = False

        if csv_valid:
            print(f"\n[*] Menjalankan audit dataset: {target_csv} (Total: {row_count} baris)...")
            with open(summary_txt, "w", encoding="utf-8") as sf:
                res = subprocess.run([sys.executable, ANALYZE_SCRIPT, target_csv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                sf.write(res.stdout)
                print(res.stdout)
                audit_success = (res.returncode == 0)
            print(f"[+] Laporan kualitas tersimpan: {summary_txt}")

        # Strict Quality Gates
        if not execution_failed:
            if not csv_valid or row_count < 30:
                execution_failed = True
                failure_reason = f"Durasi sampel tidak memadai ({row_count} baris < 30 baris minimum)"
            elif not events_valid:
                execution_failed = True
                failure_reason = "File event anotasi ground-truth hilang atau kosong (unlabeled dataset)"
            elif nwdaf_valid_rows == 0:
                execution_failed = True
                failure_reason = "Data analitik NWDAF AnLF seluruhnya NaN (100% missing; kontribusi AnLF tidak dapat dibuktikan)"
            elif ran_valid_rows == 0:
                execution_failed = True
                failure_reason = "Data telemetri radio RAN seluruhnya NaN (100% missing)"

        # Update manifest.json status
        manifest_path = os.path.join(run_dir, "manifest.json")
        final_status = "COMPLETED_SUCCESS" if (not execution_failed and csv_valid and audit_success and events_valid) else f"FAILED: {failure_reason}"
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as mf:
                    mf_data = json.load(mf)
                mf_data["status"] = final_status
                mf_data["verified_rows"] = row_count
                mf_data["nwdaf_valid_rows"] = nwdaf_valid_rows
                mf_data["nwdaf_unique_updates"] = len(nwdaf_unique_volumes)
                mf_data["ran_valid_rows"] = ran_valid_rows
                mf_data["events_recorded"] = events_logged_count
                with open(manifest_path, "w") as mf:
                    json.dump(mf_data, mf, indent=2)
            except Exception:
                pass

        print("\n" + "=" * 85)
        if final_status == "COMPLETED_SUCCESS":
            print(f"[SUCCESS] Eksperimen {run_id} BERHASIL TERVALIDASI!")
            print(f"Total baris telemetri : {row_count} baris")
            print(f"Cakupan NWDAF AnLF     : {nwdaf_valid_rows}/{row_count} baris ({len(nwdaf_unique_volumes)} pembaruan unik)")
            print(f"Cakupan Radio RAN      : {ran_valid_rows}/{row_count} baris")
            print(f"Event Teranotasi       : {events_logged_count} event")
            print(f"Direktori arsip data   : {run_dir}")
        else:
            print(f"[VALIDATION FAILED] Eksperimen TIDAK LAYAK TRAINING!")
            print(f"Alasan Kegagalan: {failure_reason}")
            print(f"Periksa log dan laporan di: {run_dir}")
            sys.exit(1)
        print("=" * 85)


if __name__ == "__main__":
    main()
