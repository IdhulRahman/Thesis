#!/usr/bin/env python3
"""
Dataset Statistical Audit & Analysis Script for 5G O-RAN Thesis
Location on VM-6: /opt/oran/monitoring/scripts/analyze_final_dataset.py
Pure Python 3 Standard Library - Zero External Dependencies
Evaluates recorded CSV telemetry: PRB saturation, Core buffer backlog,
packet drops, throughput delivery, and URLLC SLA violation rates per scenario.
"""

import csv
import glob
import math
import os
import sys

DATA_DIR = "/opt/oran/monitoring/data"


def main():
    if len(sys.argv) > 1:
        raw_files = [sys.argv[1]]
    else:
        raw_files = sorted(glob.glob(os.path.join(DATA_DIR, "telemetry_raw_*.csv")))

    if not raw_files or not os.path.exists(raw_files[-1]):
        print(f"[ERROR] File dataset tidak ditemukan di {DATA_DIR}")
        print("Penggunaan: python3 analyze_dataset.py [path_ke_file_csv]")
        sys.exit(1)

    raw_file = raw_files[-1]
    filename = os.path.basename(raw_file)
    size_kb = os.path.getsize(raw_file) / 1024.0

    print("=" * 110)
    print(f"ANALISIS TELEMETRI DATASET: {filename} ({size_kb:.1f} KB)")
    print("=" * 110)

    scen_data = {}
    total_rows = 0

    with open(raw_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            scen = row.get("event_scenario", row.get("scenario", "UNKNOWN"))
            if scen not in scen_data:
                scen_data[scen] = {
                    "tput": [], "rtt": [], "prb_c1": [], "prb_c2": [],
                    "backlog": [], "drops": [], "mcs_c1": [], "bler_c1": [], "snr_c1": [],
                    "sla_violated": 0
                }

            def parse_val(col):
                val = row.get(col, "")
                if val in ("", "NaN", "nan", None):
                    return math.nan
                try:
                    return float(val)
                except ValueError:
                    return math.nan

            tput = parse_val("e2e_slice1_tput_mbps")
            if not math.isnan(tput):
                scen_data[scen]["tput"].append(tput)

            rtt = parse_val("e2e_slice2_rtt_ms")
            if not math.isnan(rtt):
                scen_data[scen]["rtt"].append(rtt)
                if rtt > 20.0:
                    scen_data[scen]["sla_violated"] += 1

            prb1 = parse_val("ran_prb_cell1")
            if not math.isnan(prb1):
                scen_data[scen]["prb_c1"].append(prb1)

            b_log = parse_val("upf_backlog_bytes_embb")
            if not math.isnan(b_log):
                scen_data[scen]["backlog"].append(b_log)

            drop = parse_val("upf_drops_embb")
            if not math.isnan(drop):
                scen_data[scen]["drops"].append(drop)

            mcs1 = parse_val("ran_mcs_cell1")
            if not math.isnan(mcs1):
                scen_data[scen]["mcs_c1"].append(mcs1)

            bler1 = parse_val("ran_bler_cell1")
            if not math.isnan(bler1):
                scen_data[scen]["bler_c1"].append(bler1)

            snr1 = parse_val("ran_snr_cell1")
            if not math.isnan(snr1):
                scen_data[scen]["snr_c1"].append(snr1)

    print(f"{'Skenario Event':<20} | {'Sampel':<6} | {'Tput Avg':<9} | {'PRB C1':<8} | {'MCS C1':<7} | {'BLER C1':<8} | {'SNR C1':<8} | {'Backlog Max':<12} | {'URLLC RTT':<11} | {'SLA Viol %'}")
    print("-" * 125)

    for scen, d in sorted(scen_data.items()):
        n = len(d["rtt"]) or len(d["tput"]) or 1
        avg_tput = (sum(d["tput"]) / len(d["tput"])) if d["tput"] else 0.0
        avg_prb = (sum(d["prb_c1"]) / len(d["prb_c1"])) if d["prb_c1"] else 0.0
        avg_mcs = (sum(d["mcs_c1"]) / len(d["mcs_c1"])) if d["mcs_c1"] else 0.0
        avg_bler = (sum(d["bler_c1"]) / len(d["bler_c1"])) if d["bler_c1"] else 0.0
        avg_snr = (sum(d["snr_c1"]) / len(d["snr_c1"])) if d["snr_c1"] else 0.0
        max_b = max(d["backlog"]) if d["backlog"] else 0.0
        avg_rtt = (sum(d["rtt"]) / len(d["rtt"])) if d["rtt"] else 0.0
        sla_pct = (d["sla_violated"] / len(d["rtt"]) * 100.0) if d["rtt"] else 0.0

        print(f"{scen:<20} | {n:<6} | {avg_tput:>7.2f} M | {avg_prb:>6.1f} % | {avg_mcs:>7.1f} | {avg_bler:>8.4f} | {avg_snr:>6.1f}dB | {max_b:>10,.0f} B | {avg_rtt:>8.2f} ms | {sla_pct:>8.1f} %")

    print("=" * 125)
    print(f"Total Sampel Dievaluasi: {total_rows} baris")


if __name__ == "__main__":
    main()
