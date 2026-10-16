#!/usr/bin/env python3
"""
5G O-RAN RIC-NWDAF Experiment Annotation Timeline Scheduler & Verification Runner
Location on VM-6: /opt/oran/monitoring/scripts/run_pilot_experiment.py
Pure Python 3 Standard Library - Zero External Dependencies

Architectural Role & Demarcation:
This script serves as an Annotation Timeline Scheduler and Dataset Quality Verifier.
It enforces the research contract by evaluating three distinct outcome statuses:
- execution_complete: Experiment completed all scheduled phases without crash or abort
- data_quality_pass : Dataset passes syntactic, schema, finiteness, and file integrity gates
- training_eligible : Dataset satisfies strict methodological criteria for model training
"""

import argparse
import csv
import datetime
import json
import math
import os
import re
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

REQUIRED_COLUMNS = [
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
    "event_phase_id", "event_scenario", "event_domain", "event_component"
]

SCENARIO_ACTIONS = {
    "S1": "Trafik normal baseline ringan (VM-5: 10 Mbps). Pastikan PRB ~35% dan buffer UPF 0 B.",
    "S2": "Trafik normal tinggi (VM-5: 22 Mbps). Pastikan PRB ~80% dan buffer UPF tetap 0 B.",
    "S3": "Injeksi RAN Overload (VM-5: naikkan trafik ke 35-40 Mbps melebihi kapasitas radio).",
    "S6": "Injeksi Core Queue Bottleneck (VM-3: terapkan TBF rate-limit 12 Mbps pada interface UPF-1).",
    "S9": "Injeksi Joint Overload (RAN 40M di VM-5 + Core TBF 12M di VM-3 secara simultan).",
    "S10_A": "Pelepasan Gangguan RAN (VM-5: turunkan trafik ke 20M, biarkan Core TBF aktif).",
    "S10_B": "Pelepasan Gangguan Core (VM-3: hapus rate-limit TBF, amati buffer UPF drain ke 0 B)."
}

PROM_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$')
LABEL_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*=\s*"([^"]*)"')


def log_event(key, note="", phase_id=""):
    cmd = [sys.executable, LOG_EVENT_SCRIPT, key, note]
    if phase_id:
        cmd.extend(["--phase-id", phase_id])
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print(f"[FATAL ERROR] Gagal mencatat event '{key}' (exit code: {res.returncode})!")
        return False
    return True


def fetch_live_metrics(url=COLLECTOR_URL):
    """Queries Prometheus /metrics from collector to inspect live testbed status."""
    res = {
        "upf_backlog_embb": float("nan"),
        "ran_prb_cell1": float("nan"),
        "nwdaf_comm_freshness": 0,
        "e2e_probe_freshness": 0,
        "nwdaf_raw_polls_total": 0,
        "nwdaf_raw_polls_written": 0,
        "nwdaf_raw_polls_failed": 0,
        "available": False
    }
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PilotRunner/2.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                text = resp.read().decode("utf-8", errors="replace")
                res["available"] = True
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = PROM_LINE_RE.match(line)
                    if not m:
                        continue
                    name, raw_labels, val_str = m.group(1), m.group(2) or "", m.group(3)
                    labels = dict(LABEL_RE.findall(raw_labels))

                    try:
                        val_float = float(val_str)
                    except ValueError:
                        val_float = float("nan")

                    if name == "upf_queue_backlog_bytes" and labels.get("snssai") in ("01000001", "1"):
                        res["upf_backlog_embb"] = val_float
                    elif name == "ran_cell_prb_utilization" and labels.get("cell_id") == "1":
                        res["ran_prb_cell1"] = val_float
                    elif name == "nwdaf_comm_freshness":
                        res["nwdaf_comm_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "e2e_probe_freshness":
                        res["e2e_probe_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_total":
                        res["nwdaf_raw_polls_total"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_written":
                        res["nwdaf_raw_polls_written"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_failed":
                        res["nwdaf_raw_polls_failed"] = int(val_float) if not math.isnan(val_float) else 0
    except Exception:
        res["available"] = False
    return res


def check_collector_alive():
    try:
        with urllib.request.urlopen(COLLECTOR_URL, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def verify_recovery(unattended, timeout_sec=30, stability_sec=3, target_backlog=0.0, target_prb=40.0):
    """
    Verifies network recovery with empirical observation proof.
    Returns: (verified: bool, evidence: dict, reason: str)
    """
    evidence = {
        "mode": "unattended" if unattended else "interactive",
        "start_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verified_time_utc": None,
        "duration_sec": 0,
        "target_backlog_bytes": target_backlog,
        "target_prb_pct": target_prb,
        "evidence_source": "",
        "samples": []
    }
    t_start = time.monotonic()

    if unattended:
        print(f"\n[*] [VERIFIKASI PEMULIHAN OTOMATIS] Menunggu kondisi baseline stabil:")
        print(f"    - Target Backlog UPF-1: <= {target_backlog} Bytes")
        print(f"    - Target PRB Cell-1   : <= {target_prb}%")
        print(f"    - Jendela Stabil      : {stability_sec}s berturut-turut (Timeout: {timeout_sec}s)")

        consecutive_stable = 0
        while (time.monotonic() - t_start) < timeout_sec:
            now_m = fetch_live_metrics()
            b_log = now_m["upf_backlog_embb"]
            prb = now_m["ran_prb_cell1"]
            is_finite = math.isfinite(b_log) and math.isfinite(prb)
            is_healthy = is_finite and (b_log <= target_backlog) and (prb <= target_prb)

            evidence["samples"].append({
                "elapsed_sec": round(time.monotonic() - t_start, 1),
                "backlog": b_log,
                "prb": prb,
                "available": now_m["available"],
                "healthy": is_healthy
            })

            if is_healthy:
                consecutive_stable += 1
                print(f"    -> Kondisi normal teramati: Backlog={b_log:.0f}B, PRB={prb:.1f}% ({consecutive_stable}/{stability_sec}s)...")
                if consecutive_stable >= stability_sec:
                    evidence["verified_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    evidence["duration_sec"] = round(time.monotonic() - t_start, 1)
                    evidence["evidence_source"] = f"Collector :9100 live metric polling ({consecutive_stable}s continuous stability)"
                    evidence["final_backlog"] = b_log
                    evidence["final_prb"] = prb
                    print(f"[+] Pemulihan terverifikasi secara objektif dalam {evidence['duration_sec']} detik!")
                    return True, evidence, "Verified stable baseline"
            else:
                consecutive_stable = 0
                print(f"    -> Menunggu drain: Backlog={b_log}B, PRB={prb}% (elapsed: {round(time.monotonic() - t_start)}s)...")

            time.sleep(1.0)

        evidence["duration_sec"] = round(time.monotonic() - t_start, 1)
        return False, evidence, f"Recovery timeout ({timeout_sec}s): antrean atau PRB radio belum kembali normal"

    else:
        print("\n" + "=" * 85)
        print("[*] [VERIFIKASI PEMULIHAN OPERATOR INTERAKTIF]")
        print("    Catat nilai pengamatan pemulihan dari Grafana / terminal:")
        print("=" * 85)
        try:
            obs_b = input(f"    -> Masukkan Backlog UPF-1 teramati (Bytes) [Target <={target_backlog}]: ").strip()
            obs_p = input(f"    -> Masukkan PRB Cell-1 teramati (%) [Target <={target_prb}%]: ").strip()
            obs_src = input("    -> Sumber bukti (misal: Grafana Panel 4 / tc qdisc terminal): ").strip()
            obs_win = input("    -> Durasi pengamatan kondisi stabil (detik) [min 5s]: ").strip()

            b_val = float(obs_b)
            p_val = float(obs_p)
            win_val = float(obs_win)

            evidence["verified_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            evidence["final_backlog"] = b_val
            evidence["final_prb"] = p_val
            evidence["evidence_source"] = obs_src
            evidence["duration_sec"] = win_val

            if b_val <= target_backlog and p_val <= target_prb and win_val >= 5.0 and obs_src:
                return True, evidence, "Verified by operator with empirical proof"
            else:
                return False, evidence, f"Input operator tidak memenuhi syarat baseline (Backlog={b_val}, PRB={p_val}, Window={win_val}s)"
        except Exception as e:
            return False, evidence, f"Gagal membaca input verifikasi operator: {e}"


def evaluate_run_dataset(run_dir, run_id, planned_scenarios, recovery_verified=True, recovery_evidence=None, config_params=None):
    """
    Strict multi-dimensional dataset evaluator enforcing the 3 research contract statuses:
    - execution_complete: Experiment completed all scheduled phases without crash/abort
    - data_quality_pass : Dataset passes syntactic, schema, finiteness, and file integrity gates
    - training_eligible : Dataset satisfies strict methodological criteria for model training
    """
    if config_params is None:
        config_params = {}

    min_total_rows = config_params.get("min_total_rows", 30)
    min_phase_rows = config_params.get("min_phase_rows", 20)
    min_ran_coverage = config_params.get("min_ran_coverage", 0.70)

    data_quality_reasons = []
    training_reasons = []

    csv_path = os.path.join(run_dir, f"telemetry_{run_id}.csv")
    events_path = os.path.join(run_dir, f"experiment_events_{run_id}.csv")
    jsonl_path = os.path.join(run_dir, "nwdaf_raw_poll_responses.jsonl")

    total_rows = 0
    phase_rows = {}
    phase_ran_valid = {}
    phase_nwdaf_valid = {}
    has_inf = False
    has_out_of_range = False
    invalid_run_ids = 0
    uninitialized_test_rows = 0

    # 1. Evaluate CSV Telemetry File
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        data_quality_reasons.append("Berkas telemetri CSV hilang atau 0 byte")
    else:
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                missing_cols = [c for c in REQUIRED_COLUMNS if c not in headers]
                if missing_cols:
                    data_quality_reasons.append(f"Schema CSV tidak lengkap, kolom hilang: {missing_cols}")

                for r in reader:
                    total_rows += 1
                    r_id = r.get("run_id", "")
                    if r_id != run_id:
                        invalid_run_ids += 1

                    for k, v in r.items():
                        if v in ("inf", "-inf", "Infinity", "-Infinity"):
                            has_inf = True

                    prb_str = r.get("ran_prb_cell1", "")
                    if prb_str not in ("", "NaN", "nan", "None", None):
                        try:
                            p_val = float(prb_str)
                            if not math.isnan(p_val):
                                if not (0.0 <= p_val <= 100.0) or math.isinf(p_val):
                                    has_out_of_range = True
                        except ValueError:
                            pass

                    vol_str = r.get("nwdaf_comm_ul_bytes", "")
                    if vol_str not in ("", "NaN", "nan", "None", None):
                        try:
                            v_val = float(vol_str)
                            if not math.isnan(v_val):
                                if v_val < 0.0 or math.isinf(v_val):
                                    has_out_of_range = True
                        except ValueError:
                            pass

                    row_phase = r.get("event_phase_id", r.get("event_scenario", "UNKNOWN"))
                    row_scen = r.get("event_scenario", "UNKNOWN")

                    if row_phase not in phase_rows:
                        phase_rows[row_phase] = 0
                        phase_ran_valid[row_phase] = 0
                        phase_nwdaf_valid[row_phase] = 0

                    phase_rows[row_phase] += 1

                    if prb_str not in ("", "NaN", "nan", "None", None):
                        try:
                            if math.isfinite(float(prb_str)):
                                phase_ran_valid[row_phase] += 1
                        except ValueError:
                            pass

                    if vol_str not in ("", "NaN", "nan", "None", None):
                        try:
                            if math.isfinite(float(vol_str)):
                                phase_nwdaf_valid[row_phase] += 1
                        except ValueError:
                            pass

                    if row_scen == "UNINITIALIZED" and not (row_phase.startswith("phase_0_WARMUP") or row_phase == "phase_WARMUP"):
                        uninitialized_test_rows += 1

            if has_inf:
                data_quality_reasons.append("Ditemukan nilai 'inf' / '-inf' pada data telemetri")
            if has_out_of_range:
                data_quality_reasons.append("Ditemukan nilai di luar rentang fisik (PRB di luar [0,100] atau volume negatif)")
            if invalid_run_ids > 0:
                data_quality_reasons.append(f"Ditemukan {invalid_run_ids} baris dengan run_id tidak cocok")
            if total_rows < min_total_rows:
                data_quality_reasons.append(f"Jumlah sampel telemetri tidak memadai ({total_rows} < {min_total_rows})")

        except Exception as e:
            data_quality_reasons.append(f"Gagal membaca/mem-parsing CSV telemetri: {e}")

    # 2. Evaluate Event CSV Annotations
    events_count = 0
    if not os.path.exists(events_path) or os.path.getsize(events_path) == 0:
        data_quality_reasons.append("Berkas event anotasi ground-truth hilang atau 0 byte")
    else:
        try:
            with open(events_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                prev_ts = None
                ts_decreasing = False
                for ev in reader:
                    events_count += 1
                    ts_str = ev.get("timestamp_utc", "")
                    if ts_str:
                        try:
                            cur_ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if prev_ts and cur_ts < prev_ts:
                                ts_decreasing = True
                            prev_ts = cur_ts
                        except Exception:
                            pass
                    if ev.get("run_id") != run_id:
                        data_quality_reasons.append(f"Event run_id '{ev.get('run_id')}' tidak cocok dengan '{run_id}'")

                if events_count == 0:
                    data_quality_reasons.append("Berkas event hanya berisi header tanpa record event nyata")
                if ts_decreasing:
                    data_quality_reasons.append("Stempel waktu event tidak terurut secara monotonik naik")
        except Exception as e:
            data_quality_reasons.append(f"Gagal membaca/mem-parsing event CSV: {e}")

    # 3. Evaluate Raw NWDAF JSONL Archive
    jsonl_lines = 0
    raw_polls_with_200 = 0
    if not os.path.exists(jsonl_path) or os.path.getsize(jsonl_path) == 0:
        data_quality_reasons.append("Berkas arsip raw NWDAF JSONL hilang atau 0 byte")
    else:
        try:
            with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    jsonl_lines += 1
                    if rec.get("http_status") == 200:
                        raw_polls_with_200 += 1
            if jsonl_lines == 0:
                data_quality_reasons.append("Berkas arsip raw NWDAF JSONL tidak memuat entri poll valid")
        except Exception as e:
            data_quality_reasons.append(f"Berkas arsip raw NWDAF JSONL korup / gagal di-parse: {e}")

    data_quality_pass = (len(data_quality_reasons) == 0)

    # 4. Evaluate Training Eligibility
    if not data_quality_pass:
        training_reasons.append("Gagal di tahap validasi kualitas dasar (data_quality_pass == False)")
    else:
        if not recovery_verified:
            training_reasons.append("Pemulihan tidak terverifikasi (recovery timeout atau tidak memenuhi bukti baseline)")

        if uninitialized_test_rows > 0:
            training_reasons.append(f"Ditemukan {uninitialized_test_rows} baris dengan label 'UNINITIALIZED' pada fase pengujian aktif")

        for scen in planned_scenarios:
            scen_total = sum(phase_rows[p] for p in phase_rows if scen in p)
            scen_ran = sum(phase_ran_valid[p] for p in phase_ran_valid if scen in p)

            if scen_total < min_phase_rows:
                training_reasons.append(f"Fase skenario {scen} kekurangan sampel ({scen_total} baris < {min_phase_rows})")
            else:
                cov = scen_ran / scen_total if scen_total > 0 else 0.0
                if cov < min_ran_coverage:
                    training_reasons.append(f"Fase skenario {scen} cakupan telemetri RAN di bawah ambang batas ({cov*100:.1f}% < {min_ran_coverage*100:.1f}%)")

        if raw_polls_with_200 == 0:
            training_reasons.append("Tidak ada observasi sumber NWDAF yang berhasil terekam (HTTP 200 tidak ditemukan di arsip raw poll)")

    training_eligible = (data_quality_pass and len(training_reasons) == 0)

    summary = {
        "total_rows": total_rows,
        "events_count": events_count,
        "jsonl_polls": jsonl_lines,
        "raw_polls_with_200": raw_polls_with_200,
        "phase_breakdown": {}
    }
    for p, count in phase_rows.items():
        summary["phase_breakdown"][p] = {
            "total_rows": count,
            "ran_valid_rows": phase_ran_valid.get(p, 0),
            "nwdaf_valid_rows": phase_nwdaf_valid.get(p, 0)
        }

    return data_quality_pass, training_eligible, summary, data_quality_reasons, training_reasons


def main():
    parser = argparse.ArgumentParser(description="5G O-RAN RIC-NWDAF Experiment Annotation Timeline Scheduler & Verifier")
    parser.add_argument("run_id", nargs="?", default="", help="Unique identifier for experiment run")
    parser.add_argument("--phase-duration", type=int, default=60, help="Duration in seconds for each scenario phase (default: 60s)")
    parser.add_argument("--warmup", type=int, default=15, help="Warmup duration in seconds before first scenario (default: 15s)")
    parser.add_argument("--scenarios", default="S1,S3,S6", help="Comma-separated fault scenario sequence (default: S1,S3,S6)")
    parser.add_argument("--unattended", action="store_true", help="Run automatically on timers and live telemetric verification")
    parser.add_argument("--recovery-timeout", type=int, default=30, help="Timeout in seconds for recovery stabilization (default: 30s)")
    parser.add_argument("--recovery-stability-sec", type=int, default=3, help="Required continuous healthy samples for recovery (default: 3s)")
    parser.add_argument("--min-ran-coverage", type=float, default=0.70, help="Minimum valid RAN coverage per phase (default: 0.70)")
    args = parser.parse_args()

    run_ts = time.strftime('%Y%m%d_%H%M%S')
    run_id = args.run_id if args.run_id else f"PILOT_{run_ts}"
    phase_dur = max(30, args.phase_duration)
    warmup_dur = args.warmup
    scenarios = [s.strip().upper() for s in args.scenarios.split(",") if s.strip() and s.strip().upper() != "CLEAR"]

    run_dir = os.path.join(DATA_DIR, "raw", run_id)
    os.makedirs(run_dir, exist_ok=True)

    config_params = {
        "phase_duration_sec": phase_dur,
        "warmup_duration_sec": warmup_dur,
        "planned_scenarios": scenarios,
        "unattended_mode": args.unattended,
        "recovery_timeout_sec": args.recovery_timeout,
        "recovery_stability_sec": args.recovery_stability_sec,
        "recovery_target_backlog_bytes": 0.0,
        "recovery_target_prb_pct": 40.0,
        "min_ran_coverage": args.min_ran_coverage,
        "min_total_rows": 30,
        "min_phase_rows": max(15, int(phase_dur * 0.5))
    }

    print("=" * 90)
    print("  5G O-RAN RIC-NWDAF EXPERIMENT TIMELINE SCHEDULER & QUALITY VERIFIER")
    print(f"  Run ID          : {run_id}")
    print(f"  Output Directory: {run_dir}")
    print(f"  Phase Duration  : {phase_dur} s (aligned with NWDAF ~30s URR cadence)")
    print(f"  Planned Faults  : {scenarios}")
    print(f"  Recovery Protocol: 3-Step Empirical (Request -> Transition Drain -> Verified Baseline)")
    print(f"  Mode            : {'UNATTENDED (Live Telemetric Proof)' if args.unattended else 'INTERACTIVE (Operator Guided & Empirical Proof)'}")
    print("=" * 90)

    # 1. Pre-flight Check: Is Collector Exporter Alive?
    if not check_collector_alive():
        print(f"[!] Warning: Collector :9100 tidak merespons di {COLLECTOR_URL}!")
        print("    Pastikan telemetry_collector.py sudah berjalan di VM-6.")
        if not args.unattended:
            input("    Tekan [Enter] jika ingin tetap melanjutkan atau Ctrl+C untuk batal...")

    # 2. Start Telemetry Logger as subprocess
    log_proc = subprocess.Popen([sys.executable, RECORD_SCRIPT, run_id])
    time.sleep(1.5)

    if log_proc.poll() is not None:
        print(f"\n[FATAL ERROR] Logger process (record_dual_stream.py) gagal berjalan!")
        print(f"Exit code: {log_proc.returncode}. Membatalkan eksperimen.")
        sys.exit(1)

    execution_complete = False
    abort_reason = ""
    recovery_verified = False
    recovery_evidence = {}

    try:
        # 3. Warm-up Phase
        if warmup_dur > 0:
            print(f"\n[*] [PHASE 0: WARMUP] Menunggu warm-up telemetri ({warmup_dur}s)...")
            if not log_event("S1", "System Warm-up & Pipeline Sync", phase_id="phase_0_WARMUP"):
                raise RuntimeError("Gagal mencatat event WARMUP S1 ke file event!")
            time.sleep(warmup_dur)

        # 4. Step through planned fault scenarios
        for idx, scen in enumerate(scenarios, 1):
            phase_id = f"phase_{idx}_{scen}"
            action_desc = SCENARIO_ACTIONS.get(scen, "Terapkan kondisi skenario.")
            print(f"\n" + "-" * 90)
            print(f"[*] [PHASE {idx}/{len(scenarios)}: {phase_id} ({scen})]")
            print(f"    Instruksi Aksi : {action_desc}")
            print(f"    Durasi Observasi: {phase_dur} detik")
            print("-" * 90)

            if not args.unattended:
                input(f"    -> Terapkan aksi fisik di VM terkait, lalu tekan [Enter] untuk mencatat event {scen}...")

            if not log_event(scen, f"Phase {idx}/{len(scenarios)}: {scen}", phase_id=phase_id):
                raise RuntimeError(f"Gagal mencatat event label {scen} ke file event!")

            for sec_left in range(phase_dur, 0, -10):
                if log_proc.poll() is not None:
                    raise RuntimeError(f"Logger process crash mendadak di tengah fase {scen} (code: {log_proc.returncode})!")
                print(f"    -> Observasi {phase_id} sisa waktu: {sec_left}s...", flush=True)
                time.sleep(min(10, sec_left))

        # 5. Three-Step Recovery Protocol
        print("\n" + "=" * 90)
        print("[*] [FASE PEMULIHAN 1/3: PERMINTAAN PELEPASAN GANGGUAN]")
        print("    1. Pada VM-3: Hapus limitasi antrean UPF (misal: sudo tc qdisc del dev eth0 root).")
        print("    2. Pada VM-5: Turunkan offered traffic kembali ke baseline normal 10 Mbps.")
        print("=" * 90)

        if not args.unattended:
            input("    -> Eksekusi pelepasan gangguan di VM-3/VM-5, lalu tekan [Enter] untuk mencatat transisi...")

        # Step 2: Record RECOVERY_TRANSITION (NOT NORMAL!)
        print("\n[*] [FASE PEMULIHAN 2/3: MEREKAM TRANSISI DRAIN (15s)]...")
        if not log_event("RECOVERY", "Transisi pemulihan: Gangguan dilepas, antrean buffer sedang drain ke Normal", phase_id="phase_recovery"):
            raise RuntimeError("Gagal mencatat event RECOVERY ke file event!")
        time.sleep(15.0)

        # Step 3: Verified Recovery
        recovery_verified, recovery_evidence, rec_msg = verify_recovery(
            unattended=args.unattended,
            timeout_sec=args.recovery_timeout,
            stability_sec=args.recovery_stability_sec,
            target_backlog=config_params["recovery_target_backlog_bytes"],
            target_prb=config_params["recovery_target_prb_pct"]
        )

        if recovery_verified:
            print("[*] Pemulihan terverifikasi! Mencatat status CLEAR (Verified Baseline)...")
            if not log_event("CLEAR", f"Pemulihan terverifikasi: {rec_msg}", phase_id="phase_clear"):
                raise RuntimeError("Gagal mencatat event CLEAR ke file event!")
            time.sleep(10.0)
            execution_complete = True
        else:
            print(f"[!] Pemulihan GAGAL diverifikasi: {rec_msg}")
            log_event("RECOVERY_TIMEOUT", f"Gagal stabilisasi: {rec_msg}", phase_id="phase_recovery_failed")
            execution_complete = True

    except KeyboardInterrupt:
        print("\n[!] Eksekusi dibatalkan manual oleh operator (Ctrl+C).")
        log_event("ABORT", "Eksperimen dibatalkan manual sebelum selesai", phase_id="phase_abort")
        execution_complete = False
        abort_reason = "Interrupted by user (ABORTED)"
    except Exception as e:
        print(f"\n[!] Error fatal selama eksekusi: {e}")
        log_event("ABORT", f"Eksperimen error: {e}", phase_id="phase_error")
        execution_complete = False
        abort_reason = str(e)

    finally:
        # 6. Gracefully terminate logger process
        print("\n[*] Menghentikan logger telemetry...")
        log_proc.send_signal(signal.SIGINT)
        try:
            log_proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            log_proc.terminate()
            log_proc.wait()

        # 7. Evaluate Dataset under 3-Status Research Contract
        data_quality_pass, training_eligible, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=run_dir,
            run_id=run_id,
            planned_scenarios=scenarios,
            recovery_verified=recovery_verified,
            recovery_evidence=recovery_evidence,
            config_params=config_params
        )

        # 8. Run Analyzer for statistical summary text
        summary_txt = os.path.join(run_dir, "quality_summary.txt")
        csv_path = os.path.join(run_dir, f"telemetry_{run_id}.csv")
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            print(f"\n[*] Menjalankan audit statistik: {csv_path} ({summary['total_rows']} baris)...")
            with open(summary_txt, "w", encoding="utf-8") as sf:
                res = subprocess.run([sys.executable, ANALYZE_SCRIPT, csv_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                sf.write(res.stdout)
                print(res.stdout)

        # 9. Update manifest.json with 3-Status Contract
        manifest_path = os.path.join(run_dir, "manifest.json")
        mf_data = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as mf:
                    mf_data = json.load(mf)
            except Exception:
                pass

        mf_data["run_id"] = run_id
        mf_data["execution_complete"] = execution_complete
        mf_data["data_quality_pass"] = data_quality_pass
        mf_data["training_eligible"] = training_eligible
        mf_data["abort_reason"] = abort_reason
        mf_data["data_quality_rejection_reasons"] = dq_reasons
        mf_data["training_rejection_reasons"] = tr_reasons
        mf_data["recovery_evidence"] = recovery_evidence
        mf_data["config_parameters"] = config_params
        mf_data["summary_stats"] = summary
        mf_data["final_decision"] = "TRAINING_ELIGIBLE" if training_eligible else ("DATA_QUALITY_PASS_ONLY" if data_quality_pass else "DATA_QUALITY_REJECTED")

        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(mf_data, mf, indent=2)

        print("\n" + "=" * 90)
        print("  LAPORAN HASIL EVALUASI KONTRAK RISET EXPERIMEN")
        print(f"  Run ID              : {run_id}")
        print(f"  execution_complete  : {execution_complete} {'(ABORTED: ' + abort_reason + ')' if not execution_complete else ''}")
        print(f"  data_quality_pass   : {data_quality_pass} {'(Alasan: ' + '; '.join(dq_reasons) + ')' if not data_quality_pass else ''}")
        print(f"  training_eligible   : {training_eligible} {'(Alasan: ' + '; '.join(tr_reasons) + ')' if not training_eligible else ''}")
        print(f"  Keputusan Final     : {mf_data['final_decision']}")
        print(f"  Arsip Manifest      : {manifest_path}")
        print("=" * 90)

        if not training_eligible:
            sys.exit(1)


if __name__ == "__main__":
    main()
