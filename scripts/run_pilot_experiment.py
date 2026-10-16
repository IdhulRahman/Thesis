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

DATA_DIR = os.getenv("MONITORING_DATA_DIR", "/opt/oran/monitoring/data")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_SCRIPT = os.path.join(SCRIPTS_DIR, "record_dual_stream.py")
LOG_EVENT_SCRIPT = os.path.join(SCRIPTS_DIR, "log_event.py")
ANALYZE_SCRIPT = os.path.join(SCRIPTS_DIR, "analyze_dataset.py")
COLLECTOR_URL = "http://127.0.0.1:9100/metrics"

REQUIRED_COLUMNS = [
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

SCENARIO_ACTIONS = {
    "S1": "Trafik normal baseline ringan (VM-5: 10 Mbps). Pastikan PRB ~35% dan buffer UPF 0 B.",
    "S2": "Trafik normal tinggi (VM-5: 22 Mbps). Pastikan PRB ~80% dan buffer UPF tetap 0 B.",
    "S3": "Injeksi RAN Overload (VM-5: naikkan trafik ke 35-40 Mbps melebihi kapasitas radio).",
    "S6": "Injeksi Core Queue Bottleneck (VM-3: terapkan TBF rate-limit 12 Mbps pada interface UPF-1).",
    "S9": "Injeksi Joint Overload (RAN 40M di VM-5 + Core TBF 12M di VM-3 secara simultan).",
    "S10_A": "Pelepasan Gangguan RAN (VM-5: turunkan trafik ke 20M, biarkan Core TBF aktif).",
    "S10_B": "Pelepasan Gangguan Core (VM-3: hapus rate-limit TBF, amati buffer UPF drain ke 0 B)."
}

# Canonical Scenario Identifier Mappings (shared with log_event.py)
SCENARIO_CANONICAL_MAP = {
    "S1": "S1_NORMAL_LIGHT",
    "S2": "S2_NORMAL_HIGH",
    "S3": "S3_RAN_OVERLOAD",
    "S6": "S6_CORE_QUEUE_TBF",
    "S9": "S9_JOINT_OVERLOAD",
    "S10_A": "S10_A_RELEASE_RAN",
    "S10_B": "S10_B_RELEASE_CORE",
    "RECOVERY": "RECOVERY_TRANSITION",
    "RECOVERY_TIMEOUT": "RECOVERY_FAILED",
    "CLEAR": "S1_NORMAL_LIGHT",
    "ABORT": "RUN_ABORTED"
}

REVERSE_CANONICAL_MAP = {v: k for k, v in SCENARIO_CANONICAL_MAP.items()}


def is_scenario_matching(actual_scen, planned_scen):
    """
    Checks if an observed scenario identifier matches the planned scenario.
    Accepts both short keys ('S1') and canonical long IDs ('S1_NORMAL_LIGHT') bidirectionally.
    """
    if not actual_scen or not planned_scen:
        return False
    act = str(actual_scen).strip()
    pln = str(planned_scen).strip()
    if act == pln:
        return True

    # 1. Canonical expansion comparison
    pln_canonical = SCENARIO_CANONICAL_MAP.get(pln, pln)
    act_canonical = SCENARIO_CANONICAL_MAP.get(act, act)
    if act == pln_canonical or act_canonical == pln or act_canonical == pln_canonical:
        return True

    # 2. Short key comparison
    pln_short = REVERSE_CANONICAL_MAP.get(pln, pln)
    act_short = REVERSE_CANONICAL_MAP.get(act, act)
    if act == pln_short or act_short == pln or act_short == pln_short:
        return True

    # 3. Prefix matching
    if act.startswith(f"{pln}_") or pln.startswith(f"{act}_"):
        return True

    return False

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
        "ue1_rtt_ms": float("nan"),
        "ue1_loss_pct": float("nan"),
        "ue2_rtt_ms": float("nan"),
        "ue2_loss_pct": float("nan"),
        "e2e_rtt_ms": float("nan"),
        "e2e_loss_pct": float("nan"),
        "ue1_probe_freshness": 0,
        "ue2_probe_freshness": 0,
        "e2e_probe_freshness": 0,
        "nwdaf_comm_freshness": 0,
        "nwdaf_raw_polls_total": 0,
        "nwdaf_raw_polls_written": 0,
        "nwdaf_raw_polls_failed": 0,
        "nwdaf_run_raw_polls_written": 0,
        "nwdaf_run_raw_polls_failed": 0,
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
                    elif name == "e2e_slice1_latency_rtt_ms":
                        res["ue1_rtt_ms"] = val_float
                    elif name == "e2e_slice1_packet_loss_pct":
                        res["ue1_loss_pct"] = val_float
                    elif name == "e2e_slice2_latency_rtt_ms":
                        res["ue2_rtt_ms"] = val_float
                        res["e2e_rtt_ms"] = val_float
                    elif name == "e2e_slice2_packet_loss_pct":
                        res["ue2_loss_pct"] = val_float
                        res["e2e_loss_pct"] = val_float
                    elif name == "nwdaf_comm_freshness":
                        res["nwdaf_comm_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "e2e_slice1_probe_freshness":
                        res["ue1_probe_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "e2e_slice2_probe_freshness":
                        res["ue2_probe_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "e2e_probe_freshness":
                        res["e2e_probe_freshness"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_total":
                        res["nwdaf_raw_polls_total"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_written":
                        res["nwdaf_raw_polls_written"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_raw_polls_failed":
                        res["nwdaf_raw_polls_failed"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_run_raw_polls_written":
                        res["nwdaf_run_raw_polls_written"] = int(val_float) if not math.isnan(val_float) else 0
                    elif name == "nwdaf_run_raw_polls_failed":
                        res["nwdaf_run_raw_polls_failed"] = int(val_float) if not math.isnan(val_float) else 0
    except Exception:
        res["available"] = False
    return res


def check_collector_alive():
    try:
        with urllib.request.urlopen(COLLECTOR_URL, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def verify_recovery(unattended, timeout_sec=30, stability_sec=3, target_backlog=0.0, target_prb=40.0, target_rtt_ms=30.0, target_loss_pct=5.0, require_probe=False):
    """
    Verifies network recovery with empirical observation proof.
    Ensures both resource conditions (backlog, PRB) and service probe conditions (UE-1 RTT, Loss) recover.
    Returns: (verified: bool, evidence: dict, reason: str)
    """
    evidence = {
        "mode": "unattended" if unattended else "interactive",
        "start_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verified_time_utc": None,
        "duration_sec": 0,
        "target_backlog_bytes": target_backlog,
        "target_prb_pct": target_prb,
        "target_rtt_ms": target_rtt_ms,
        "target_loss_pct": target_loss_pct,
        "require_probe": require_probe,
        "evidence_source": "",
        "samples": []
    }
    t_start = time.monotonic()

    if unattended:
        print(f"\n[*] [VERIFIKASI PEMULIHAN OTOMATIS] Menunggu kondisi baseline stabil:")
        print(f"    - Target Backlog UPF-1: <= {target_backlog} Bytes")
        print(f"    - Target PRB Cell-1   : <= {target_prb}%")
        if require_probe:
            print(f"    - Target Probe UE-1   : RTT <= {target_rtt_ms}ms, Loss <= {target_loss_pct}%, Freshness > 0")
        print(f"    - Jendela Stabil      : {stability_sec}s berturut-turut (Timeout: {timeout_sec}s)")

        consecutive_stable = 0
        stable_start = None
        while (time.monotonic() - t_start) < timeout_sec:
            now_m = fetch_live_metrics()
            b_log = now_m["upf_backlog_embb"]
            prb = now_m["ran_prb_cell1"]
            u1_rtt = now_m.get("ue1_rtt_ms", float("nan"))
            u1_loss = now_m.get("ue1_loss_pct", float("nan"))
            probe_fresh = now_m.get("ue1_probe_freshness", now_m.get("e2e_probe_freshness", 0))
            u2_rtt = now_m.get("ue2_rtt_ms", float("nan"))
            u2_loss = now_m.get("ue2_loss_pct", float("nan"))
            u2_fresh = now_m.get("ue2_probe_freshness", now_m.get("e2e_probe_freshness", 0))

            is_avail = bool(now_m.get("available"))
            is_finite = math.isfinite(b_log) and math.isfinite(prb)
            is_in_range = is_finite and (b_log >= 0.0) and (0.0 <= prb <= 100.0)
            resource_ok = is_avail and is_in_range and (b_log <= target_backlog) and (prb <= target_prb)

            # Target service probe (UE-1 Slice 1 eMBB is the fault subject)
            if require_probe:
                probe_fresh_ok = (probe_fresh > 0)
                u1_rtt_ok = math.isfinite(u1_rtt) and (0.0 < u1_rtt <= target_rtt_ms)
                u1_loss_ok = math.isfinite(u1_loss) and (0.0 <= u1_loss <= target_loss_pct)
                service_ok = probe_fresh_ok and u1_rtt_ok and u1_loss_ok
            else:
                service_ok = True
                if probe_fresh > 0 and math.isfinite(u1_loss):
                    service_ok = (u1_loss <= target_loss_pct)

            is_healthy = resource_ok and service_ok

            now_mono = time.monotonic()
            evidence["samples"].append({
                "elapsed_sec": round(now_mono - t_start, 1),
                "backlog": b_log,
                "prb": prb,
                "ue1_rtt_ms": u1_rtt,
                "ue1_loss_pct": u1_loss,
                "ue1_probe_freshness": probe_fresh,
                "ue2_rtt_ms": u2_rtt,
                "ue2_loss_pct": u2_loss,
                "ue2_probe_freshness": u2_fresh,
                "available": is_avail,
                "resource_ok": resource_ok,
                "service_ok": service_ok,
                "healthy": is_healthy
            })

            if is_healthy:
                if stable_start is None:
                    stable_start = now_mono
                stable_duration = now_mono - stable_start
                print(f"    -> Kondisi normal teramati: Backlog={b_log:.0f}B, PRB={prb:.1f}%, UE1_Loss={u1_loss:.1f}%, UE1_Fresh={probe_fresh} (stabil: {stable_duration:.1f}/{stability_sec}s)...")
                if stable_duration >= stability_sec:
                    evidence["verified_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    evidence["duration_sec"] = round(now_mono - t_start, 1)
                    evidence["stable_window_sec"] = round(stable_duration, 1)
                    evidence["evidence_source"] = f"Collector :9100 live metric polling ({round(stable_duration, 1)}s continuous monotonic stability)"
                    evidence["final_backlog"] = b_log
                    evidence["final_prb"] = prb
                    evidence["final_ue1_rtt_ms"] = u1_rtt
                    evidence["final_ue1_loss_pct"] = u1_loss
                    evidence["final_ue1_probe_freshness"] = probe_fresh
                    evidence["ue2_isolation_control"] = {
                        "rtt_ms": u2_rtt,
                        "loss_pct": u2_loss,
                        "freshness": u2_fresh
                    }
                    print(f"[+] Pemulihan terverifikasi secara objektif dalam {evidence['duration_sec']} detik!")
                    return True, evidence, "Verified stable baseline"
            else:
                stable_start = None
                print(f"    -> Menunggu drain/tersedia: Backlog={b_log}B, PRB={prb}%, UE1_Loss={u1_loss}%, UE1_Fresh={probe_fresh}, Avail={is_avail} (elapsed: {round(now_mono - t_start)}s)...")

            time.sleep(1.0)

        evidence["duration_sec"] = round(time.monotonic() - t_start, 1)
        return False, evidence, f"Recovery timeout ({timeout_sec}s): antrean, PRB radio, atau probe UE-1 belum kembali normal"

    else:
        print("\n[Verifikasi Pemulihan Operator]")
        try:
            obs_b = input(f"    -> Masukkan Backlog UPF-1 teramati (Bytes) [Target <={target_backlog}]: ").strip()
            obs_p = input(f"    -> Masukkan PRB Cell-1 teramati (%) [Target <={target_prb}%]: ").strip()
            b_val = float(obs_b)
            p_val = float(obs_p)

            is_probe_valid = True
            rtt_val = float("nan")
            loss_val = float("nan")
            fresh_val = 0

            if require_probe:
                obs_rtt = input(f"    -> Masukkan RTT UE-1 teramati (ms) [Target <={target_rtt_ms}ms]: ").strip()
                obs_loss = input(f"    -> Masukkan Packet Loss UE-1 teramati (%) [Target <={target_loss_pct}%]: ").strip()
                obs_fresh = input("    -> Masukkan Freshness Probe UE-1 (1=Fresh, 0=Stale) [Target == 1]: ").strip()
                rtt_val = float(obs_rtt)
                loss_val = float(obs_loss)
                fresh_val = int(obs_fresh)

                is_probe_valid = (
                    math.isfinite(rtt_val) and (0.0 < rtt_val <= target_rtt_ms) and
                    math.isfinite(loss_val) and (0.0 <= loss_val <= target_loss_pct) and
                    (fresh_val == 1)
                )

            obs_src = input("    -> Sumber bukti pemulihan & status probe (misal: Grafana Panel 4 / tc qdisc / ping RTT=12ms): ").strip()
            obs_win = input("    -> Durasi pengamatan kondisi stabil (detik) [min 5s]: ").strip()
            win_val = float(obs_win)

            is_valid_input = (
                math.isfinite(b_val) and (b_val >= 0.0) and
                math.isfinite(p_val) and (0.0 <= p_val <= 100.0) and
                math.isfinite(win_val) and (win_val >= 5.0) and
                bool(obs_src) and
                is_probe_valid
            )

            evidence["verified_time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            evidence["final_backlog"] = b_val
            evidence["final_prb"] = p_val
            evidence["final_ue1_rtt_ms"] = rtt_val
            evidence["final_ue1_loss_pct"] = loss_val
            evidence["final_ue1_probe_freshness"] = fresh_val
            evidence["evidence_source"] = obs_src
            evidence["duration_sec"] = win_val

            if is_valid_input and b_val <= target_backlog and p_val <= target_prb:
                return True, evidence, "Verified by operator with empirical proof"
            else:
                return False, evidence, f"Input operator tidak memenuhi syarat baseline (Backlog={b_val}, PRB={p_val}, RTT={rtt_val}, Loss={loss_val}, Freshness={fresh_val}, Window={win_val}s, Source='{obs_src}')"
        except Exception as e:
            return False, evidence, f"Gagal membaca input verifikasi operator: {e}"


def is_valid_finite_number(val, min_val=None, max_val=None):
    if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    if not math.isfinite(val):
        return False
    if min_val is not None and val < min_val:
        return False
    if max_val is not None and val > max_val:
        return False
    return True


def validate_receiver_archive(file_path):
    """
    Validates receiver export archive supporting:
    1. Standard formatted JSON (iperf3 --json)
    2. JSON-stream (iperf3 --json-stream)
    3. Summary JSON (receiver_*_summary.json with session_complete)
    
    Enforces strict boolean type checks and finite numeric validations for bytes, duration, goodput, and loss.
    Returns: (is_valid: bool, reason: str, metadata: dict)
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False, "Berkas tidak ditemukan atau 0 Byte", {}

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
    except Exception as e:
        return False, f"Gagal membaca berkas: {e}", {}

    if not content:
        return False, "Berkas kosong", {}

    # Attempt 1: Single standard JSON or Summary JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # Case 1A: Exported Summary JSON (from receiver_iperf.sh export)
            if "session_complete" in data or "goodput_mbps" in data or "bytes_received" in data:
                if data.get("session_complete") is not True:
                    return False, "Sesi receiver tidak lengkap (session_complete harus bernilai boolean True)", data
                
                bytes_rx = data.get("bytes_received")
                if not is_valid_finite_number(bytes_rx, min_val=1):
                    return False, f"Jumlah bytes_received ({bytes_rx}) tidak valid (harus finite number > 0)", data

                if "raw_bytes_received" in data:
                    raw_b = data.get("raw_bytes_received")
                    if not is_valid_finite_number(raw_b, min_val=0):
                        return False, f"Jumlah raw_bytes_received ({raw_b}) tidak valid (harus finite number >= 0)", data

                if "duration_seconds" in data:
                    dur = data.get("duration_seconds")
                    if not is_valid_finite_number(dur, min_val=0.001):
                        return False, f"duration_seconds ({dur}) tidak valid (harus finite number > 0)", data

                if "goodput_mbps" in data:
                    gp = data.get("goodput_mbps")
                    if not is_valid_finite_number(gp, min_val=0.0):
                        return False, f"goodput_mbps ({gp}) tidak valid (harus finite number >= 0)", data

                if "bits_per_second" in data:
                    bps = data.get("bits_per_second")
                    if not is_valid_finite_number(bps, min_val=0.0):
                        return False, f"bits_per_second ({bps}) tidak valid (harus finite number >= 0)", data

                if "packet_loss_pct" in data or "receiver_loss_pct" in data:
                    loss = data.get("packet_loss_pct") if "packet_loss_pct" in data else data.get("receiver_loss_pct")
                    if not is_valid_finite_number(loss, min_val=0.0, max_val=100.0):
                        return False, f"packet_loss_pct / receiver_loss_pct ({loss}) tidak valid (harus rentang 0.0 - 100.0)", data

                if "packets_total" in data:
                    pkt_tot = data.get("packets_total")
                    if not is_valid_finite_number(pkt_tot, min_val=0):
                        return False, f"packets_total ({pkt_tot}) tidak valid", data

                if "packets_lost" in data:
                    pkt_lost = data.get("packets_lost")
                    if not is_valid_finite_number(pkt_lost, min_val=0):
                        return False, f"packets_lost ({pkt_lost}) tidak valid", data

                return True, "Valid summary JSON", data

            # Case 1B: Standard iperf3 full JSON
            if "end" in data:
                end_val = data["end"]
                if end_val is None or not isinstance(end_val, dict):
                    return False, "Blok 'end' bernilai null atau bukan dict", {}
                sum_rx = (end_val.get("sum_received") or 
                          end_val.get("sum") or 
                          (end_val.get("streams", [{}])[0].get("receiver") if end_val.get("streams") else None) or
                          (end_val.get("streams", [{}])[0].get("udp") if end_val.get("streams") else None) or
                          end_val)
                if not isinstance(sum_rx, dict):
                    return False, "Blok 'end' tidak memuat ringkasan sum yang valid", {}
                
                bytes_rx = sum_rx.get("bytes")
                if not is_valid_finite_number(bytes_rx, min_val=1):
                    return False, f"Blok 'end' tidak memuat ringkasan bytes yang valid (>0, received: {bytes_rx})", {}

                if "seconds" in sum_rx:
                    sec = sum_rx.get("seconds")
                    if not is_valid_finite_number(sec, min_val=0.001):
                        return False, f"Blok 'end' memuat seconds tidak valid ({sec})", {}

                if "lost_percent" in sum_rx:
                    lp = sum_rx.get("lost_percent")
                    if not is_valid_finite_number(lp, min_val=0.0, max_val=100.0):
                        return False, f"Blok 'end' memuat lost_percent tidak valid ({lp})", {}

                if "bits_per_second" in sum_rx:
                    bps = sum_rx.get("bits_per_second")
                    if not is_valid_finite_number(bps, min_val=0.0):
                        return False, f"Blok 'end' memuat bits_per_second tidak valid ({bps})", {}

                return True, "Valid standard iperf3 JSON", {"bytes_received": bytes_rx}
            else:
                return False, "JSON standar tidak memuat blok 'end' atau 'session_complete'", {}
    except json.JSONDecodeError:
        pass

    # Attempt 2: JSON-Stream (one JSON object per line)
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return False, "Tidak ada baris JSON ditemukan", {}

    parsed_lines = []
    for idx, l in enumerate(lines, 1):
        try:
            parsed_lines.append(json.loads(l))
        except Exception as ex:
            return False, f"Baris #{idx} pada JSON-stream korup: {ex}", {}

    end_data = None
    for rec in reversed(parsed_lines):
        if isinstance(rec, dict):
            if rec.get("event") == "end" and isinstance(rec.get("data"), dict):
                end_data = rec["data"]
                break
            elif "end" in rec and isinstance(rec.get("end"), dict):
                end_data = rec["end"]
                break

    if end_data is None:
        return False, "JSON-stream tidak memuat event 'end' summary yang lengkap", {}

    sum_rx = (end_data.get("sum_received") or 
              end_data.get("sum") or 
              (end_data.get("streams", [{}])[0].get("receiver") if end_data.get("streams") else None) or
              end_data)
    if not isinstance(sum_rx, dict):
        return False, "Event 'end' pada JSON-stream tidak memuat ringkasan sum yang valid", {}

    bytes_rx = sum_rx.get("bytes")
    if not is_valid_finite_number(bytes_rx, min_val=1):
        return False, f"Event 'end' pada JSON-stream tidak memuat bytes received valid ({bytes_rx})", {}

    if "seconds" in sum_rx:
        sec = sum_rx.get("seconds")
        if not is_valid_finite_number(sec, min_val=0.001):
            return False, f"Event 'end' pada JSON-stream memuat seconds tidak valid ({sec})", {}

    if "lost_percent" in sum_rx:
        lp = sum_rx.get("lost_percent")
        if not is_valid_finite_number(lp, min_val=0.0, max_val=100.0):
            return False, f"Event 'end' pada JSON-stream memuat lost_percent tidak valid ({lp})", {}

    if "bits_per_second" in sum_rx:
        bps = sum_rx.get("bits_per_second")
        if not is_valid_finite_number(bps, min_val=0.0):
            return False, f"Event 'end' pada JSON-stream memuat bits_per_second tidak valid ({bps})", {}

    return True, "Valid JSON-stream", {"bytes_received": bytes_rx}


def parse_tc_qdisc_rate_bps(text):
    """
    Parses rate value specifically from Linux tc qdisc output (e.g. 'tc qdisc show').
    Strictly requires the explicit 'rate' keyword followed by value and optional unit.
    Returns None if the 'rate' token is absent or invalid.
    """
    if not text:
        return None
    m = re.search(r"\brate\s+([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?\b", text, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit.startswith("g"):
        return val * 1e9
    elif unit.startswith("m"):
        return val * 1e6
    elif unit.startswith("k"):
        return val * 1e3
    elif unit in ("bit", "bits", "bps"):
        return val
    elif unit in ("b", "byte", "bytes"):
        return val * 8.0
    return val


def parse_planned_rate_bps(text):
    """
    Parses rate value from planned configuration strings or concise parameter specs.
    Examples:
    - 'rate=12M,latency=200ms' -> 12000000.0
    - 'rate: 12Mbit' -> 12000000.0
    - '12Mbit' -> 12000000.0
    - '12M' -> 12000000.0
    """
    if not text:
        return None
    m = re.search(r"\brate[=:\s]+([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?\b", text, re.IGNORECASE)
    if not m:
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?\s*$", text)
        if not m:
            return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit.startswith("g"):
        return val * 1e9
    elif unit.startswith("m"):
        return val * 1e6
    elif unit.startswith("k"):
        return val * 1e3
    elif unit in ("bit", "bits", "bps"):
        return val
    elif unit in ("b", "byte", "bytes"):
        return val * 8.0
    return val


def parse_tc_rate_bps(text):
    """Backward-compatible alias pointing to parse_planned_rate_bps."""
    return parse_planned_rate_bps(text)


def validate_tbf_observed_config(s_data, ep, exp_scen, planned_config, run_id, phase_event_ts=None, max_drift_sec=300):
    """
    Validates empirical observed TBF configuration archive against strict scientific traceability gates:
    - Must be a valid dictionary
    - Run & Phase identity: run_id and phase_id are mandatory and must match current run/phase
    - Target container: mandatory and must match planned container (oai-upf-slice1), rejecting slice2/non-UPF
    - Target interface: mandatory and must match planned interface (eth0), strictly rejecting loopback (lo)
    - Mechanism: qdisc must explicitly be 'qdisc tbf'
    - Parameters: must specify rate explicitly via parse_tc_qdisc_rate_bps matching planned rate (within 25%), burst, and (latency or limit per man 8 tc-tbf)
    - Timestamp: observation timestamp is mandatory, normalized to UTC, year >= 2024, and within experiment observation window (default <= 300s of phase event)
    - Applied vs Observed: distinguishes TBF application time from fresh snapshot observation time
    """
    if not isinstance(s_data, dict):
        return False, "Data snapshot bukan berupa JSON dictionary valid"

    raw_snap = str(s_data.get("qdisc_snapshot", "")).strip()
    if not raw_snap:
        return False, "Field 'qdisc_snapshot' kosong atau tidak ditemukan"

    raw_snap_lower = raw_snap.lower()

    # 1. Mechanism check: must explicitly be TBF
    if "qdisc tbf" not in raw_snap_lower:
        return False, f"Jenis qdisc pada snapshot bukan TBF (ditemukan: '{raw_snap[:60]}')"

    # 2. Parameters check: explicit rate token, burst, and (latency or limit per man 8 tc-tbf)
    actual_rate_bps = parse_tc_qdisc_rate_bps(raw_snap)
    if actual_rate_bps is None:
        return False, "Snapshot qdisc TBF tidak memuat parameter 'rate' yang eksplisit dan sah"

    planned_param_str = planned_config.get("planned_parameters", "")
    planned_rate_bps = parse_planned_rate_bps(planned_param_str) or 12e6
    rate_ratio = actual_rate_bps / planned_rate_bps if planned_rate_bps > 0 else 0.0
    if not (0.75 <= rate_ratio <= 1.25):
        return False, f"Nilai rate snapshot ({actual_rate_bps/1e6:.1f} Mbps) tidak cocok dengan konfigurasi rencana ({planned_rate_bps/1e6:.1f} Mbps)"

    if "burst" not in raw_snap_lower:
        return False, "Snapshot qdisc TBF tidak memuat parameter 'burst'"

    has_latency_or_limit = any(k in raw_snap_lower for k in ("lat ", "latency ", "lat", "latency", "limit ", "limit"))
    if not has_latency_or_limit:
        return False, "Snapshot qdisc TBF tidak memuat parameter antrean yang sah ('latency' atau 'limit' sesuai man 8 tc-tbf)"

    # 3. Mandatory Identity Checks: run_id, phase_id, target_container, target_interface
    snap_run_id = str(s_data.get("run_id", "")).strip()
    if not snap_run_id:
        return False, "Snapshot TBF tidak memuat identitas 'run_id' wajib"
    if snap_run_id != str(run_id).strip():
        return False, f"run_id pada snapshot ('{snap_run_id}') tidak cocok dengan target run ('{run_id}')"

    snap_phase_id = str(s_data.get("phase_id", "")).strip()
    if not snap_phase_id:
        return False, "Snapshot TBF tidak memuat identitas 'phase_id' wajib"
    if snap_phase_id != str(ep).strip():
        return False, f"phase_id pada snapshot ('{snap_phase_id}') tidak cocok dengan target fase ('{ep}')"

    expected_container = planned_config.get("target_container", "oai-upf-slice1").strip().lower()
    container = str(s_data.get("target_container", "")).strip().lower()
    if not container:
        return False, "Snapshot TBF tidak memuat identitas 'target_container' wajib"
    if "slice2" in container or "oai-upf-slice2" in container:
        return False, f"Target container '{container}' menargetkan slice2, bukan target UPF-1 ('{expected_container}')"
    if container != expected_container and container not in ("upf-1_slice-1", "upf-1"):
        return False, f"Target container '{container}' tidak cocok dengan target skenario UPF-1 ('{expected_container}')"

    exec_cmd = str(s_data.get("execution_command", "")).strip().lower()
    if "oai-upf-slice2" in exec_cmd or "slice2" in exec_cmd:
        return False, f"Execution command snapshot menargetkan slice2 ('{exec_cmd}'), bukan target UPF-1 ('{expected_container}')"

    expected_interface = planned_config.get("target_interface", "eth0").strip().lower()
    interface = str(s_data.get("target_interface", "")).strip().lower()
    if not interface:
        return False, "Snapshot TBF tidak memuat identitas 'target_interface' wajib"
    if interface in ("lo", "loopback", "127.0.0.1"):
        return False, f"Target interface '{interface}' tidak valid (interface loopback ditolak)"
    if interface != expected_interface:
        return False, f"Target interface '{interface}' tidak cocok dengan target interface skenario ('{expected_interface}')"

    # Check interface in raw snapshot text
    if "dev lo" in raw_snap_lower or "dev loopback" in raw_snap_lower:
        return False, "Snapshot qdisc teramati pada interface loopback ('dev lo'), bukan interface data plane eth0"
    if "dev " in raw_snap_lower:
        dev_match = re.search(r"dev\s+([a-zA-Z0-9_\-]+)", raw_snap)
        if dev_match:
            obs_dev = dev_match.group(1).lower()
            if obs_dev in ("lo", "loopback"):
                return False, f"Snapshot qdisc teramati pada interface loopback '{obs_dev}', bukan eth0"
            if obs_dev != expected_interface:
                return False, f"Snapshot qdisc teramati pada interface '{obs_dev}', bukan target data plane '{expected_interface}'"

    # 4. Mandatory Timestamp Validation with Timezone Normalization and Observation Window Check
    obs_ts_str = s_data.get("observed_time_utc") or s_data.get("snapshot_time_utc") or s_data.get("timestamp_utc") or s_data.get("applied_time_utc")
    if not obs_ts_str:
        return False, "Snapshot TBF tidak memuat waktu observasi/penerapan wajib"

    try:
        obs_dt = datetime.datetime.fromisoformat(str(obs_ts_str).replace("Z", "+00:00"))
    except Exception as ex:
        return False, f"Format timestamp observasi TBF tidak valid '{obs_ts_str}': {ex}"

    # Normalize observation time to UTC aware
    if obs_dt.tzinfo is None:
        obs_dt = obs_dt.replace(tzinfo=datetime.timezone.utc)
    else:
        obs_dt = obs_dt.astimezone(datetime.timezone.utc)

    if obs_dt.year < 2024:
        return False, f"Waktu observasi snapshot TBF tidak valid: '{obs_ts_str}' (tahun {obs_dt.year} < 2024)"

    applied_ts_str = s_data.get("applied_time_utc")
    if applied_ts_str:
        try:
            app_dt = datetime.datetime.fromisoformat(str(applied_ts_str).replace("Z", "+00:00"))
            if app_dt.tzinfo is None:
                app_dt = app_dt.replace(tzinfo=datetime.timezone.utc)
            else:
                app_dt = app_dt.astimezone(datetime.timezone.utc)

            if app_dt.year < 2024:
                return False, f"Waktu penerapan TBF tidak valid: '{applied_ts_str}' (tahun {app_dt.year} < 2024)"

            if app_dt > obs_dt + datetime.timedelta(seconds=60):
                return False, f"Waktu penerapan TBF '{applied_ts_str}' tidak valid karena berada di masa depan relatif terhadap waktu observasi '{obs_ts_str}'"
        except Exception as ex:
            return False, f"Format timestamp penerapan TBF tidak valid '{applied_ts_str}': {ex}"

    # Check observation alignment against phase event timestamp
    if phase_event_ts:
        try:
            phase_dt = datetime.datetime.fromisoformat(str(phase_event_ts).replace("Z", "+00:00"))
            if phase_dt.tzinfo is None:
                phase_dt = phase_dt.replace(tzinfo=datetime.timezone.utc)
            else:
                phase_dt = phase_dt.astimezone(datetime.timezone.utc)

            diff_sec = abs((obs_dt - phase_dt).total_seconds())
            if diff_sec > max_drift_sec:
                return False, f"Waktu observasi snapshot TBF '{obs_ts_str}' berada di luar jendela observasi fase '{phase_event_ts}' (selisih {diff_sec:.0f}s > {max_drift_sec}s)"
        except Exception as ex:
            return False, f"Format timestamp event fase tidak valid '{phase_event_ts}': {ex}"

    return True, ""


def evaluate_run_dataset(run_dir, run_id, planned_scenarios, recovery_verified=True, recovery_evidence=None, config_params=None, collector_metrics=None, initial_collector_metrics=None):
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

    # Planned phase definitions for exact semantic matching
    expected_phases = [f"phase_{idx}_{scen}" for idx, scen in enumerate(planned_scenarios, 1)]
    expected_phase_scenarios = {f"phase_{idx}_{scen}": scen for idx, scen in enumerate(planned_scenarios, 1)}

    total_rows = 0
    phase_rows = {}
    phase_ran_valid = {}
    phase_nwdaf_valid = {}
    phase_max_prb = {}
    phase_max_backlog = {}
    phase_max_drops = {}
    phase_prb_values = {}
    phase_backlog_values = {}
    phase_drops_values = {}
    phase_s6_row_status = {}
    csv_phase_scenarios = {}
    total_nwdaf_valid_rows = 0
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
                        phase_prb_values[row_phase] = []
                        phase_backlog_values[row_phase] = []
                        phase_drops_values[row_phase] = []
                        phase_s6_row_status[row_phase] = []
                        csv_phase_scenarios[row_phase] = set()

                    phase_rows[row_phase] += 1
                    csv_phase_scenarios[row_phase].add(row_scen)

                    if prb_str not in ("", "NaN", "nan", "None", None):
                        try:
                            p_val = float(prb_str)
                            if math.isfinite(p_val):
                                phase_ran_valid[row_phase] += 1
                                phase_prb_values[row_phase].append(p_val)
                                if row_phase not in phase_max_prb or p_val > phase_max_prb[row_phase]:
                                    phase_max_prb[row_phase] = p_val
                        except ValueError:
                            pass

                    cur_row_backlog = 0.0
                    b_str = r.get("upf_backlog_bytes_embb")
                    if b_str is None or b_str == "":
                        b_str = r.get("upf_queue_backlog_bytes", "")
                    if b_str not in ("", "NaN", "nan", "None", None):
                        try:
                            b_val = float(b_str)
                            if math.isfinite(b_val):
                                cur_row_backlog = b_val
                                phase_backlog_values[row_phase].append(b_val)
                                if row_phase not in phase_max_backlog or b_val > phase_max_backlog[row_phase]:
                                    phase_max_backlog[row_phase] = b_val
                        except ValueError:
                            pass

                    cur_row_drops = 0.0
                    d_str = r.get("upf_drops_embb")
                    if d_str is None or d_str == "":
                        d_str = r.get("upf_queue_drops_embb", "")
                    if d_str not in ("", "NaN", "nan", "None", None):
                        try:
                            d_val = float(d_str)
                            if math.isfinite(d_val):
                                cur_row_drops = d_val
                                phase_drops_values[row_phase].append(d_val)
                                if row_phase not in phase_max_drops or d_val > phase_max_drops[row_phase]:
                                    phase_max_drops[row_phase] = d_val
                        except ValueError:
                            pass

                    # Row-aligned S6 active status: active if either backlog or drops is positive
                    row_s6_active = (cur_row_backlog > 0.0 or cur_row_drops > 0.0)
                    phase_s6_row_status[row_phase].append(row_s6_active)

                    if vol_str not in ("", "NaN", "nan", "None", None):
                        try:
                            if math.isfinite(float(vol_str)):
                                phase_nwdaf_valid[row_phase] += 1
                                total_nwdaf_valid_rows += 1
                        except ValueError:
                            pass

                    if row_scen == "UNINITIALIZED" and row_phase in expected_phases:
                        uninitialized_test_rows += 1

            if has_inf:
                data_quality_reasons.append("Ditemukan nilai 'inf' / '-inf' pada data telemetri")
            if has_out_of_range:
                data_quality_reasons.append("Ditemukan nilai di luar rentang fisik (PRB di luar [0,100] atau volume negatif)")
            if invalid_run_ids > 0:
                data_quality_reasons.append(f"Ditemukan {invalid_run_ids} baris dengan run_id tidak cocok")
            if total_rows < min_total_rows:
                data_quality_reasons.append(f"Jumlah sampel telemetri tidak memadai ({total_rows} < {min_total_rows})")

            # Validate that CSV recorded scenarios match planned scenarios for each planned phase
            for ep in expected_phases:
                if ep in csv_phase_scenarios:
                    exp_scen = expected_phase_scenarios[ep]
                    for actual_scen in csv_phase_scenarios[ep]:
                        if actual_scen != "UNINITIALIZED" and not is_scenario_matching(actual_scen, exp_scen):
                            data_quality_reasons.append(f"Inkonsistensi skenario pada CSV untuk fase '{ep}': tercatat '{actual_scen}' yang tidak cocok dengan skenario terencana '{exp_scen}'")

        except Exception as e:
            data_quality_reasons.append(f"Gagal membaca/mem-parsing CSV telemetri: {e}")

    # 2. Evaluate Event CSV Annotations (Strict Timestamp & Semantic Matching)
    events_count = 0
    event_phases = {}
    event_details = {}
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
                    if not ts_str:
                        data_quality_reasons.append("Ditemukan event dengan timestamp_utc kosong")
                    else:
                        try:
                            cur_ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if prev_ts and cur_ts < prev_ts:
                                ts_decreasing = True
                            prev_ts = cur_ts
                        except Exception as ex:
                            data_quality_reasons.append(f"Format timestamp event tidak valid '{ts_str}': {ex}")

                    ev_run_id = ev.get("run_id", "")
                    if ev_run_id != run_id:
                        data_quality_reasons.append(f"Event run_id '{ev_run_id}' tidak cocok dengan '{run_id}'")

                    ev_phase = ev.get("phase_id", "")
                    ev_scen = ev.get("scenario_id", "")
                    if ev_phase:
                        event_phases[ev_phase] = ev_scen
                        event_details[ev_phase] = {
                            "timestamp_utc": ts_str,
                            "scenario_id": ev_scen,
                            "event_type": ev.get("event_type", ""),
                            "target_component": ev.get("target_component", ""),
                            "mechanism": ev.get("mechanism", ""),
                            "parameters": ev.get("parameters", ""),
                            "notes": ev.get("notes", "")
                        }
                    if ev_phase in expected_phase_scenarios:
                        exp_scen = expected_phase_scenarios[ev_phase]
                        if not is_scenario_matching(ev_scen, exp_scen):
                            data_quality_reasons.append(f"Event fase '{ev_phase}' memiliki scenario_id '{ev_scen}' yang tidak cocok dengan skenario terencana '{exp_scen}'")

                if events_count == 0:
                    data_quality_reasons.append("Berkas event hanya berisi header tanpa record event nyata")
                if ts_decreasing:
                    data_quality_reasons.append("Stempel waktu event tidak terurut secara monotonik naik")

                # Verify all expected planned phases are recorded in events
                for ep in expected_phases:
                    if ep not in event_phases:
                        data_quality_reasons.append(f"Fase terencana '{ep}' tidak tercatat dalam berkas event ground-truth")

        except Exception as e:
            data_quality_reasons.append(f"Gagal membaca/mem-parsing event CSV: {e}")

    # 3. Evaluate Raw NWDAF JSONL Archive (Run ID, HTTP 200, and AnLF Feature Payload)
    jsonl_lines = 0
    raw_polls_with_200 = 0
    raw_polls_with_valid_payload = 0
    foreign_poll_run_ids = 0

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

                    # Check run_id identity
                    poll_run_id = rec.get("run_id", "")
                    if poll_run_id and poll_run_id != run_id:
                        foreign_poll_run_ids += 1

                    if rec.get("http_status") == 200:
                        raw_polls_with_200 += 1

                        # Strict AnLF feature payload check (3GPP TS 29.520 V17.8.0 §5.1.6.2.13 Type UeCommunication)
                        # Empty body {} or HTTP 200 without substantive analytic metrics is NOT valid training evidence
                        body = rec.get("response_body")
                        has_payload = False
                        if isinstance(body, dict) and body:
                            ue_comms = body.get("ueComms")
                            if isinstance(ue_comms, list) and len(ue_comms) > 0:
                                for comm in ue_comms:
                                    if isinstance(comm, dict):
                                        if (comm.get("commDur", 0) > 0 or 
                                            comm.get("ulVol", 0) > 0 or 
                                            comm.get("dlVol", 0) > 0 or 
                                            comm.get("numSamples", 0) > 0 or 
                                            comm.get("dataWindow")):
                                            has_payload = True
                                            break
                            elif any(k in body for k in ("sliceLoadLevel", "loads", "congestionInfo", "nwPerfInfos")):
                                has_payload = True

                        if has_payload:
                            raw_polls_with_valid_payload += 1

            if jsonl_lines == 0:
                data_quality_reasons.append("Berkas arsip raw NWDAF JSONL tidak memuat entri poll valid")
            if foreign_poll_run_ids > 0:
                data_quality_reasons.append(f"Poll raw NWDAF mencantumkan run_id eksperimen lain ({foreign_poll_run_ids} record asing)")

        except Exception as e:
            data_quality_reasons.append(f"Berkas arsip raw NWDAF JSONL korup / gagal di-parse: {e}")

    # 4. Evaluate Archive Failure Counter (H5 / Isolated Per-Run)
    if collector_metrics:
        # Determine per-run written and failed counts:
        # Priority 1: Explicit per-run counters from exporter
        if "nwdaf_run_raw_polls_written" in collector_metrics:
            polls_written = collector_metrics.get("nwdaf_run_raw_polls_written", 0)
            polls_failed = collector_metrics.get("nwdaf_run_raw_polls_failed", 0)
        # Priority 2: Counter delta between run start and run end
        elif initial_collector_metrics:
            c_written = collector_metrics.get("nwdaf_raw_polls_written", 0)
            i_written = initial_collector_metrics.get("nwdaf_raw_polls_written", 0)
            polls_written = max(0, c_written - i_written)

            c_failed = collector_metrics.get("nwdaf_raw_polls_failed", 0)
            i_failed = initial_collector_metrics.get("nwdaf_raw_polls_failed", 0)
            polls_failed = max(0, c_failed - i_failed)
        # Priority 3: Fallback to cumulative counter (isolated single-run tests)
        else:
            polls_written = collector_metrics.get("nwdaf_raw_polls_written", 0)
            polls_failed = collector_metrics.get("nwdaf_raw_polls_failed", 0)

        if polls_failed > 0:
            data_quality_reasons.append(f"Terjadi kegagalan penulisan arsip raw NWDAF ({polls_failed} poll gagal diarsipkan)")
        if polls_written > 0 and jsonl_lines != polls_written:
            data_quality_reasons.append(f"Ketidaksesuaian jumlah baris arsip raw NWDAF ({jsonl_lines} di JSONL vs {polls_written} di exporter)")

    data_quality_pass = (len(data_quality_reasons) == 0)

    # 5. Evaluate Training Eligibility (Strict Scientific & Empirical Gates)
    fault_evidence = {}
    if not data_quality_pass:
        training_reasons.append("Gagal di tahap validasi kualitas dasar (data_quality_pass == False)")
    else:
        if not recovery_verified:
            training_reasons.append("Pemulihan tidak terverifikasi (recovery timeout atau tidak memenuhi bukti baseline)")

        if uninitialized_test_rows > 0:
            training_reasons.append(f"Ditemukan {uninitialized_test_rows} baris dengan label 'UNINITIALIZED' pada fase pengujian aktif")

        # Exact planned phase matching
        for ep in expected_phases:
            scen_total = phase_rows.get(ep, 0)
            scen_ran = phase_ran_valid.get(ep, 0)

            if scen_total < min_phase_rows:
                training_reasons.append(f"Fase terencana '{ep}' kekurangan sampel ({scen_total} baris < {min_phase_rows})")
            else:
                cov = scen_ran / scen_total if scen_total > 0 else 0.0
                if cov < min_ran_coverage:
                    training_reasons.append(f"Fase terencana '{ep}' cakupan telemetri RAN di bawah ambang batas ({cov*100:.1f}% < {min_ran_coverage*100:.1f}%)")

        # Strict physical fault realization verification per planned phase
        verify_fault_signatures = config_params.get("verify_fault_signatures", False)
        if verify_fault_signatures:
            for ep in expected_phases:
                exp_scen = expected_phase_scenarios.get(ep, "")
                p_max_prb = phase_max_prb.get(ep, 0.0)
                p_max_backlog = phase_max_backlog.get(ep, 0.0)
                p_max_drops = phase_max_drops.get(ep, 0.0)
                prb_samples = phase_prb_values.get(ep, [])
                backlog_samples = phase_backlog_values.get(ep, [])
                drops_samples = phase_drops_values.get(ep, [])
                ev_det = event_details.get(ep, {})

                if "S3" in exp_scen:
                    # S3 is RAN Overload: peak PRB must show radio saturation (>= 65.0%)
                    # and must be sustained over the phase (>= 50% of valid samples >= 60.0%)
                    elevated_count = sum(1 for p in prb_samples if p >= 60.0)
                    elevated_ratio = elevated_count / len(prb_samples) if prb_samples else 0.0
                    if p_max_prb < 65.0:
                        training_reasons.append(f"Fase '{ep}' (S3 RAN Overload) tidak membuktikan signature saturasi radio (peak PRB {p_max_prb:.1f}% < 65.0%)")
                    elif elevated_ratio < 0.50:
                        training_reasons.append(f"Fase '{ep}' (S3 RAN Overload) tidak membuktikan overload yang berkelanjutan ({elevated_ratio*100:.1f}% sampel >= 60.0% < 50% syarat durasi fase)")
                    
                    fault_evidence[ep] = {
                        "scenario": exp_scen,
                        "peak_prb": p_max_prb,
                        "elevated_ratio": elevated_ratio,
                        "total_samples": len(prb_samples),
                        "sustained": elevated_ratio >= 0.50
                    }

                elif "S6" in exp_scen:
                    # S6 is Core Bottleneck (TBF queue limit): backlog or drops must be non-zero
                    # and sustained for at least 30% of total phase samples (row-aligned)
                    row_statuses = phase_s6_row_status.get(ep, [])
                    n_samples = len(row_statuses)
                    active_count = sum(1 for active in row_statuses if active)
                    active_ratio = active_count / n_samples if n_samples > 0 else 0.0

                    if p_max_backlog <= 0.0 and p_max_drops <= 0.0:
                        training_reasons.append(f"Fase '{ep}' (S6 Core Bottleneck) tidak membuktikan antrean atau paket drop UPF (peak backlog={p_max_backlog:.0f}B, drops={p_max_drops})")
                    elif active_ratio < 0.30:
                        training_reasons.append(f"Fase '{ep}' (S6 Core Bottleneck) gangguan antrean/drops tidak berlangsung memadai ({active_ratio*100:.1f}% sampel aktif < 30% syarat durasi fase)")

                    # Scientific Traceability: Distinguish planned configuration from empirical observed actual snapshot
                    planned_config = {
                        "scenario_id": exp_scen,
                        "target_component": ev_det.get("target_component", "UPF-1_Slice-1"),
                        "planned_mechanism": ev_det.get("mechanism", "TBF_RATELIMIT"),
                        "planned_parameters": ev_det.get("parameters", "rate=12M,latency=200ms"),
                        "target_container": "oai-upf-slice1",
                        "target_interface": "eth0"
                    }

                    observed_config = None
                    observed_config_validation_error = None
                    candidate_snapshot_paths = [
                        os.path.join(run_dir, f"tbf_observed_config_{ep}.json"),
                        os.path.join(run_dir, f"tbf_actual_config_{ep}.json"),
                        os.path.join(run_dir, "tbf_observed_config.json")
                    ]
                    for sp in candidate_snapshot_paths:
                        if os.path.exists(sp) and os.path.getsize(sp) > 0:
                            try:
                                with open(sp, "r", encoding="utf-8") as sf:
                                    s_data = json.load(sf)
                                    max_drift_sec = config_params.get("tbf_snapshot_max_drift_sec", 300)
                                    is_ok, err_msg = validate_tbf_observed_config(
                                        s_data, ep=ep, exp_scen=exp_scen,
                                        planned_config=planned_config, run_id=run_id,
                                        phase_event_ts=ev_det.get("timestamp_utc", ""),
                                        max_drift_sec=max_drift_sec
                                    )
                                    if is_ok:
                                        observed_config = s_data
                                        observed_config_validation_error = None
                                        break
                                    else:
                                        observed_config_validation_error = err_msg
                            except Exception as ex:
                                observed_config_validation_error = f"Gagal membaca/parse JSON snapshot TBF: {ex}"

                    if not observed_config:
                        if observed_config_validation_error:
                            training_reasons.append(f"Fase '{ep}' (S6 Core Bottleneck) arsip konfigurasi TBF aktual tidak valid: {observed_config_validation_error}")
                        else:
                            training_reasons.append(f"Fase '{ep}' (S6 Core Bottleneck) tidak memuat bukti arsip konfigurasi TBF aktual (berkas snapshot qdisc/container/interface tidak ditemukan)")

                    fault_evidence[ep] = {
                        "scenario": exp_scen,
                        "peak_backlog_bytes": p_max_backlog,
                        "peak_drops": p_max_drops,
                        "active_ratio": active_ratio,
                        "total_samples": n_samples,
                        "planned_configuration": planned_config,
                        "observed_actual_configuration": observed_config,
                        "tbf_qdisc_config": observed_config.get("qdisc_snapshot") if observed_config else None,
                        "tbf_interface": observed_config.get("target_interface", "eth0") if observed_config else None,
                        "tbf_applied_time_utc": observed_config.get("applied_time_utc", "") if observed_config else None,
                        "tbf_observed_time_utc": observed_config.get("observed_time_utc", observed_config.get("applied_time_utc", "")) if observed_config else None,
                        "tbf_mechanism": "TBF_RATELIMIT"
                    }

                elif "S1" in exp_scen:
                    # S1 is Baseline Normal: PRB must be nominal (<= 55.0%) and backlog == 0
                    if p_max_backlog > 0.0:
                        training_reasons.append(f"Fase '{ep}' (S1 Baseline) terdeteksi memiliki backlog antrean UPF ({p_max_backlog:.0f}B > 0B)")
                    if p_max_prb > 60.0:
                        training_reasons.append(f"Fase '{ep}' (S1 Baseline) terdeteksi kelebihan beban radio (peak PRB {p_max_prb:.1f}% > 60.0%)")

                    fault_evidence[ep] = {
                        "scenario": exp_scen,
                        "peak_prb": p_max_prb,
                        "peak_backlog_bytes": p_max_backlog
                    }

        # Strict NWDAF eligibility (3GPP TS 29.520 V17.8.0 §5.1.6.2.13 Type UeCommunication)
        if raw_polls_with_200 == 0:
            training_reasons.append("Tidak ada observasi sumber NWDAF yang berhasil terekam (HTTP 200 tidak ditemukan di arsip raw poll)")
        if raw_polls_with_valid_payload == 0:
            training_reasons.append("Tidak ada payload analitik NWDAF yang valid dalam arsip raw poll (body kosong atau tanpa fitur AnLF ueComms/durasi/volume)")
        if total_nwdaf_valid_rows == 0:
            training_reasons.append("Seluruh data observasi volume/durasi NWDAF bernilai NaN pada CSV telemetri (kelayakan NWDAF tidak terpenuhi)")

        # Strict Receiver verification (standard JSON, JSON-stream, or summary JSON)
        require_receiver = config_params.get("require_receiver", False)
        required_receivers = config_params.get("required_receivers", [])
        if require_receiver and not required_receivers:
            if any(s in planned_scenarios for s in ["S1", "S3", "S6"]):
                required_receivers = ["s1_embb"]

        found_receiver_sessions = set()
        receiver_files = [f for f in os.listdir(run_dir) if f.startswith("receiver_") and f.endswith(".json")]
        for rf in receiver_files:
            rf_path = os.path.join(run_dir, rf)
            is_val, val_msg, meta = validate_receiver_archive(rf_path)
            if not is_val:
                training_reasons.append(f"Berkas arsip receiver '{rf}' tidak valid: {val_msg}")
            else:
                sess = rf.replace("receiver_", "").replace("_summary.json", "").replace(".json", "")
                found_receiver_sessions.add(sess)

        if require_receiver:
            for req_sess in required_receivers:
                if req_sess not in found_receiver_sessions:
                    training_reasons.append(f"Arsip receiver wajib untuk session '{req_sess}' (receiver_{req_sess}.json / summary) tidak ditemukan di VM-6")

    training_eligible = (data_quality_pass and len(training_reasons) == 0)

    summary = {
        "total_rows": total_rows,
        "events_count": events_count,
        "jsonl_polls": jsonl_lines,
        "raw_polls_with_200": raw_polls_with_200,
        "raw_polls_with_valid_payload": raw_polls_with_valid_payload,
        "total_nwdaf_valid_rows": total_nwdaf_valid_rows,
        "phase_breakdown": {},
        "fault_evidence": fault_evidence
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
    parser.add_argument("--require-receiver", dest="require_receiver", action="store_true", default=True, help="Require valid receiver archive for training eligibility (default: True)")
    parser.add_argument("--no-require-receiver", dest="require_receiver", action="store_false", help="Bypass receiver archive requirement")
    parser.add_argument("--verify-fault-signatures", dest="verify_fault_signatures", action="store_true", default=True, help="Verify that PRB and UPF queue reflect actual fault conditions (default: True)")
    parser.add_argument("--no-verify-fault-signatures", dest="verify_fault_signatures", action="store_false", help="Bypass physical fault signature verification")
    args = parser.parse_args()

    run_ts = time.strftime('%Y%m%d_%H%M%S')
    run_id = args.run_id if args.run_id else f"PILOT_{run_ts}"
    phase_dur = max(30, args.phase_duration)
    warmup_dur = args.warmup
    scenarios = [s.strip().upper() for s in args.scenarios.split(",") if s.strip() and s.strip().upper() != "CLEAR"]

    run_dir = os.path.join(DATA_DIR, "raw", run_id)
    os.makedirs(run_dir, exist_ok=True)

    # Immediately synchronize active_run_id.txt before ANY events are logged
    run_state_file = os.path.join(DATA_DIR, "active_run_id.txt")
    with open(run_state_file, "w") as f:
        f.write(run_id + "\n")

    config_params = {
        "phase_duration_sec": phase_dur,
        "warmup_duration_sec": warmup_dur,
        "planned_scenarios": scenarios,
        "unattended_mode": getattr(args, "unattended", False),
        "recovery_timeout_sec": getattr(args, "recovery_timeout", 30),
        "recovery_stability_sec": getattr(args, "recovery_stability_sec", 3),
        "recovery_target_backlog_bytes": 0.0,
        "recovery_target_prb_pct": 40.0,
        "min_ran_coverage": getattr(args, "min_ran_coverage", 0.70),
        "min_total_rows": 30,
        "min_phase_rows": max(15, int(phase_dur * 0.5)),
        "require_receiver": getattr(args, "require_receiver", True),
        "verify_fault_signatures": getattr(args, "verify_fault_signatures", True)
    }

    print(f"\n[Pilot Experiment] Run ID: {run_id} | Durasi: {phase_dur}s | Skenario: {scenarios} | Mode: {'Unattended' if args.unattended else 'Interactive'}")
    print(f"Direktori: {run_dir}")

    # 1. Pre-flight Check: Is Collector Exporter Alive?
    if not check_collector_alive():
        print(f"[!] Warning: Collector :9100 tidak merespons di {COLLECTOR_URL}!")
        print("    Pastikan telemetry_collector.py sudah berjalan di VM-6.")
        if not args.unattended:
            input("    Tekan [Enter] jika ingin tetap melanjutkan atau Ctrl+C untuk batal...")

    # Take initial baseline snapshot of collector metrics before run begins
    initial_collector_metrics = fetch_live_metrics()

    # 2. Pre-set WARMUP event so logger immediately starts with valid phase
    if warmup_dur > 0:
        if not log_event("S1", "System Warm-up & Pipeline Sync", phase_id="phase_0_WARMUP"):
            raise RuntimeError("Gagal mencatat event WARMUP S1 ke file event!")

    # 3. Start Telemetry Logger as subprocess
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
        # 4. Warm-up Phase
        if warmup_dur > 0:
            print(f"\n[*] [PHASE 0: WARMUP] Menunggu warm-up telemetri ({warmup_dur}s)...")
            time.sleep(warmup_dur)

        # 4. Step through planned fault scenarios
        for idx, scen in enumerate(scenarios, 1):
            phase_id = f"phase_{idx}_{scen}"
            action_desc = SCENARIO_ACTIONS.get(scen, "Terapkan kondisi skenario.")
            print(f"\n[Fase {idx}/{len(scenarios)}: {phase_id} ({scen})] {action_desc} ({phase_dur}s)")

            if not args.unattended:
                notes_input = input(f"    -> Terapkan aksi fisik di VM terkait, masukkan catatan kondisi teramati (atau [Enter] untuk default): ").strip()
                phase_notes = f"{scen}: {notes_input}" if notes_input else f"Phase {idx}/{len(scenarios)}: {scen}"

                if scen == "S6":
                    print("    [TBF Observasi Aktual] Jalankan di VM-3: sudo docker exec oai-upf-slice1 tc qdisc show dev eth0")
                    print("    (Contoh output: qdisc tbf 8001: dev eth0 root rate 12Mbit burst 10Kb lat 200.0ms)")
                    obs_qdisc = input("    -> Masukkan output mentah 'tc qdisc show dev eth0' dari VM-3 (wajib diisi, kosongkan jika tidak ada): ").strip()
                    obs_cmd = input("    -> Masukkan perintah tc yang telah dieksekusi di VM-3 (opsional): ").strip()

                    if obs_qdisc:
                        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        tbf_snap = {
                            "run_id": run_id,
                            "phase_id": phase_id,
                            "qdisc_snapshot": obs_qdisc,
                            "execution_command": obs_cmd if obs_cmd else "sudo docker exec oai-upf-slice1 tc qdisc show dev eth0",
                            "target_container": "oai-upf-slice1",
                            "target_interface": "eth0",
                            "applied_time_utc": now_utc,
                            "observed_time_utc": now_utc,
                            "verification_source": "Operator runtime terminal observation"
                        }
                        snap_path = os.path.join(run_dir, f"tbf_observed_config_{phase_id}.json")
                        with open(snap_path, "w", encoding="utf-8") as sf:
                            json.dump(tbf_snap, sf, indent=2)
                        print("    [+] Bukti observasi TBF berhasil diarsipkan.")
                    else:
                        print("    [!] Input observasi TBF kosong. Berkas snapshot tidak dibuat (kelayakan training S6 akan ditolak).")
            else:
                phase_notes = f"Phase {idx}/{len(scenarios)}: {scen}"
                if scen == "S6":
                    snap_path = os.path.join(run_dir, f"tbf_observed_config_{phase_id}.json")
                    if os.path.exists(snap_path):
                        print(f"    [TBF Bukti Teramati] Ditemukan arsip snapshot TBF aktual di {snap_path}")
                    else:
                        print(f"    [!] Peringatan: Berkas bukti TBF aktual ({snap_path}) belum tersedia dari VM-3. Kelayakan training S6 akan ditolak.")

            if not log_event(scen, phase_notes, phase_id=phase_id):
                raise RuntimeError(f"Gagal mencatat event label {scen} ke file event!")

            for sec_left in range(phase_dur, 0, -10):
                if log_proc.poll() is not None:
                    raise RuntimeError(f"Logger process crash mendadak di tengah fase {scen} (code: {log_proc.returncode})!")
                print(f"    -> Observasi {phase_id} sisa waktu: {sec_left}s...", flush=True)
                time.sleep(min(10, sec_left))

        # 5. Three-Step Recovery Protocol
        print("\n[Pemulihan 1/3] Hapus antrean UPF (VM-3) & turunkan trafik ke 10 Mbps (VM-5)")

        if not args.unattended:
            input("    -> Eksekusi pelepasan gangguan di VM-3/VM-5, lalu tekan [Enter] untuk mencatat transisi...")

        # Step 2: Record RECOVERY_TRANSITION (NOT NORMAL!)
        print("\n[Pemulihan 2/3] Merekam transisi drain (15s)...")
        if not log_event("RECOVERY", "Transisi pemulihan: Gangguan dilepas, antrean buffer sedang drain ke Normal", phase_id="phase_recovery"):
            raise RuntimeError("Gagal mencatat event RECOVERY ke file event!")
        time.sleep(15.0)

        # Step 3: Verified Recovery
        recovery_verified, recovery_evidence, rec_msg = verify_recovery(
            unattended=args.unattended,
            timeout_sec=args.recovery_timeout,
            stability_sec=args.recovery_stability_sec,
            target_backlog=config_params["recovery_target_backlog_bytes"],
            target_prb=config_params["recovery_target_prb_pct"],
            require_probe=True
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
        final_collector_metrics = fetch_live_metrics()
        data_quality_pass, training_eligible, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=run_dir,
            run_id=run_id,
            planned_scenarios=scenarios,
            recovery_verified=recovery_verified,
            recovery_evidence=recovery_evidence,
            config_params=config_params,
            collector_metrics=final_collector_metrics,
            initial_collector_metrics=initial_collector_metrics
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

        print("\n--- Evaluasi Kontrak Riset ---")
        print(f"Run ID              : {run_id}")
        print(f"execution_complete  : {execution_complete} {'(ABORTED: ' + abort_reason + ')' if not execution_complete else ''}")
        print(f"data_quality_pass   : {data_quality_pass} {'(Alasan: ' + '; '.join(dq_reasons) + ')' if not data_quality_pass else ''}")
        print(f"training_eligible   : {training_eligible} {'(Alasan: ' + '; '.join(tr_reasons) + ')' if not training_eligible else ''}")
        print(f"Keputusan Final     : {mf_data['final_decision']}")
        print(f"Arsip Manifest      : {manifest_path}")
        print("-------------------------------")

        if not training_eligible:
            sys.exit(1)


if __name__ == "__main__":
    main()
