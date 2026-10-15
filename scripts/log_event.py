#!/usr/bin/env python3
"""
Experiment Event Logger for 5G O-RAN Thesis (Atomic Update)
Location on VM-6: /opt/oran/monitoring/scripts/log_event.py
Pure Python 3 Standard Library - Zero External Dependencies
Records ground-truth scenario fault injection events to experiment_events_<RUN_ID>.csv
and atomically syncs active state to active_event.json for record_dual_stream.py.
"""

import csv
import datetime
import json
import os
import sys

DATA_DIR = "/opt/oran/monitoring/data"
ACTIVE_EVENT_FILE = os.path.join(DATA_DIR, "active_event.json")
RUN_STATE_FILE = os.path.join(DATA_DIR, "active_run_id.txt")

RUN_ID = "PILOT_MANUAL"
if os.path.exists(RUN_STATE_FILE):
    try:
        with open(RUN_STATE_FILE, "r") as f:
            content = f.read().strip()
            if content:
                RUN_ID = content
    except Exception:
        pass

EVENT_CSV = os.path.join(DATA_DIR, f"experiment_events_{RUN_ID}.csv")
HEADERS = ["timestamp_utc", "run_id", "event_type", "scenario_id", "target_domain", "target_component", "mechanism", "parameters", "notes"]

if not os.path.exists(EVENT_CSV):
    try:
        with open(EVENT_CSV, "w", newline="") as f:
            csv.writer(f).writerow(HEADERS)
    except Exception:
        pass

PRESETS = {
    "S1": ("START_SCENARIO", "S1_NORMAL_LIGHT", "BASELINE", "NONE", "NONE", "load=10M", "Normal ringan (35% Cran UL)"),
    "S2": ("START_SCENARIO", "S2_NORMAL_HIGH", "BASELINE", "NONE", "OFFERED_LOAD", "load=22M", "Beban tinggi tapi sehat (80% Cran UL)"),
    "S3": ("INJECT_FAULT", "S3_RAN_OVERLOAD", "RAN", "DU-1_Cell-1", "OFFERED_LOAD", "load=40M", "RAN overload melebihi kapasitas radio 28.4M"),
    "S6": ("INJECT_FAULT", "S6_CORE_QUEUE_TBF", "CORE", "UPF-1_Slice-1", "TBF_RATELIMIT", "rate=12M,latency=200ms", "Core queue bottleneck via UPF-1 TBF"),
    "S9": ("INJECT_FAULT", "S9_JOINT_OVERLOAD", "JOINT", "Cell-1+UPF-1", "LOAD+TBF", "ran=40M,core_tbf=12M", "Joint bottleneck (RAN + Core bersamaan)"),
    "S10_A": ("STEP_RECOVERY", "S10_A_RELEASE_RAN", "CORE", "UPF-1_Slice-1", "TRAFFIC_DROP_TO_20M", "load=20M,core_tbf=12M", "Transisi S10: Turunkan offered load ke 20M, amati Core bottleneck berlanjut"),
    "S10_B": ("STEP_RECOVERY", "S10_B_RELEASE_CORE", "BASELINE", "NONE", "CLEAR_TBF", "load=20M,tbf=none", "Transisi S10: Hapus limit TBF UPF-1, amati backlog drain ke Normal"),
    "RECOVERY": ("STEP_RECOVERY", "RECOVERY_TRANSITION", "TRANSITION", "ALL", "DRAIN", "load=10M,tbf=none", "Transisi pemulihan: Gangguan dilepas, menunggu drain antrean ke Normal"),
    "ABORT": ("ABORT_RUN", "RUN_ABORTED", "INVALID", "NONE", "NONE", "none", "Eksperimen dibatalkan sebelum selesai"),
    "CLEAR": ("CLEAR_FAULT", "S1_NORMAL_LIGHT", "BASELINE", "ALL", "NONE", "load=10M", "Seluruh gangguan dinonaktifkan")
}


def main():
    if len(sys.argv) < 2:
        print("Penggunaan: python3 log_event.py <S1|S2|S3|S6|S9|S10_A|S10_B|RECOVERY|CLEAR|ABORT> [catatan]")
        sys.exit(1)

    key = sys.argv[1].upper()
    notes_extra = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if key in PRESETS:
        ev_type, scen_id, domain, comp, mech, param, desc = PRESETS[key]
        notes = f"{desc} | {notes_extra}".strip(" |")
    else:
        ev_type, scen_id, domain, comp, mech, param, notes = "CUSTOM_EVENT", key, "UNKNOWN", "NONE", "MANUAL", "NONE", notes_extra

    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        # 1. Update atomik ke active_event.json
        tmp_file = ACTIVE_EVENT_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump({"scenario": scen_id, "domain": domain, "component": comp, "param": param}, f)
        os.replace(tmp_file, ACTIVE_EVENT_FILE)

        # 2. Catat event ke CSV
        with open(EVENT_CSV, "a", newline="") as f:
            csv.writer(f).writerow([now_utc, RUN_ID, ev_type, scen_id, domain, comp, mech, param, notes])

        run_dir = os.path.join(DATA_DIR, "raw", RUN_ID)
        if os.path.exists(run_dir):
            raw_event_csv = os.path.join(run_dir, f"experiment_events_{RUN_ID}.csv")
            write_header = not os.path.exists(raw_event_csv)
            with open(raw_event_csv, "a", newline="") as rf:
                writer = csv.writer(rf)
                if write_header:
                    writer.writerow(HEADERS)
                writer.writerow([now_utc, RUN_ID, ev_type, scen_id, domain, comp, mech, param, notes])
    except Exception as e:
        print(f"[FATAL ERROR] Gagal mencatat event: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[EVENT LOGGED] {now_utc} | Run: {RUN_ID} | {scen_id} | {domain} | {comp} | {param}")


if __name__ == "__main__":
    main()
