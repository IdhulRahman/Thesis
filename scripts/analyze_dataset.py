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

DATA_DIR = os.getenv("MONITORING_DATA_DIR", "/opt/oran/monitoring/data")


def main():
    if len(sys.argv) > 1:
        raw_files = [sys.argv[1]]
    else:
        found_files = glob.glob(os.path.join(DATA_DIR, "telemetry_raw_*.csv")) + glob.glob(os.path.join(DATA_DIR, "raw", "*", "telemetry_*.csv"))
        raw_files = sorted(found_files, key=os.path.getmtime)

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
                    "total_rows": 0,
                    # Slice 1 (eMBB / UE-1)
                    "s1_measured_rows": 0,
                    "s1_valid_rtt_rows": 0,
                    "s1_valid_tput_rows": 0,
                    "s1_outage_rows": 0,
                    "s1_missing_rows": 0,
                    "s1_tput": [],
                    "s1_rtt": [],
                    "s1_loss": [],

                    # Slice 2 (URLLC / UE-2)
                    "s2_measured_rows": 0,
                    "s2_valid_rtt_rows": 0,
                    "s2_outage_rows": 0,
                    "s2_missing_rows": 0,
                    "s2_latency_violated_rows": 0,
                    "s2_loss_violated_rows": 0,
                    "s2_sla_violated_rows": 0,
                    "s2_rtt": [],
                    "s2_loss": [],

                    # Infrastructure (RAN & Core)
                    "prb_c1": [],
                    "prb_c2": [],
                    "backlog": [],
                    "drops": [],
                    "mcs_c1": [],
                    "bler_c1": [],
                    "snr_c1": []
                }

            d = scen_data[scen]
            d["total_rows"] += 1

            def parse_val(*cols):
                for col in cols:
                    val = row.get(col, "")
                    if val not in ("", "NaN", "nan", "None", "null", None):
                        try:
                            return float(val)
                        except ValueError:
                            pass
                return math.nan

            # --- Slice 1 Telemetry (eMBB / UE-1 via UPF-1) ---
            s1_tput = parse_val("e2e_slice1_tput_mbps", "e2e_slice1_throughput_mbps")
            if not math.isnan(s1_tput):
                d["s1_tput"].append(s1_tput)
                d["s1_valid_tput_rows"] += 1

            s1_rtt = parse_val("e2e_slice1_rtt_ms", "e2e_slice1_latency_rtt_ms")
            s1_loss = parse_val("e2e_slice1_loss_pct", "e2e_slice1_packet_loss_pct")

            if math.isnan(s1_rtt) and math.isnan(s1_loss):
                d["s1_missing_rows"] += 1
            else:
                d["s1_measured_rows"] += 1
                if not math.isnan(s1_loss) and s1_loss >= 100.0:
                    d["s1_outage_rows"] += 1
                    d["s1_loss"].append(s1_loss)
                else:
                    if not math.isnan(s1_rtt):
                        d["s1_rtt"].append(s1_rtt)
                        d["s1_valid_rtt_rows"] += 1
                    if not math.isnan(s1_loss):
                        d["s1_loss"].append(s1_loss)

            # --- Slice 2 Telemetry (URLLC / UE-2 via UPF-2) ---
            s2_rtt = parse_val("e2e_slice2_rtt_ms", "e2e_slice2_latency_rtt_ms")
            s2_loss = parse_val("e2e_slice2_loss_pct", "e2e_slice2_packet_loss_pct")

            if math.isnan(s2_rtt) and math.isnan(s2_loss):
                d["s2_missing_rows"] += 1
            else:
                d["s2_measured_rows"] += 1
                is_outage = (not math.isnan(s2_loss) and s2_loss >= 100.0)
                is_latency_violation = (not math.isnan(s2_rtt) and s2_rtt > 20.0)
                is_loss_violation = (not math.isnan(s2_loss) and 0.0 < s2_loss < 100.0)

                if is_outage:
                    d["s2_outage_rows"] += 1
                    d["s2_loss"].append(s2_loss)
                    d["s2_sla_violated_rows"] += 1
                else:
                    if not math.isnan(s2_rtt):
                        d["s2_rtt"].append(s2_rtt)
                        d["s2_valid_rtt_rows"] += 1
                        if is_latency_violation:
                            d["s2_latency_violated_rows"] += 1

                    if not math.isnan(s2_loss):
                        d["s2_loss"].append(s2_loss)
                        if is_loss_violation:
                            d["s2_loss_violated_rows"] += 1

                    if is_latency_violation or is_loss_violation:
                        d["s2_sla_violated_rows"] += 1

            # --- Infrastructure Telemetry (RAN & Core) ---
            prb1 = parse_val("ran_prb_cell1", "ran_cell_prb_utilization_1")
            if not math.isnan(prb1):
                d["prb_c1"].append(prb1)

            prb2 = parse_val("ran_prb_cell2", "ran_cell_prb_utilization_2")
            if not math.isnan(prb2):
                d["prb_c2"].append(prb2)

            b_log = parse_val("upf_backlog_bytes_embb", "upf_queue_backlog_bytes_01000001")
            if not math.isnan(b_log):
                d["backlog"].append(b_log)

            drop = parse_val("upf_drops_embb", "upf_packet_drops_01000001")
            if not math.isnan(drop):
                d["drops"].append(drop)

            mcs1 = parse_val("ran_mcs_cell1", "ran_cell_mcs_1")
            if not math.isnan(mcs1):
                d["mcs_c1"].append(mcs1)

            bler1 = parse_val("ran_bler_cell1", "ran_cell_bler_1")
            if not math.isnan(bler1):
                d["bler_c1"].append(bler1)

            snr1 = parse_val("ran_snr_cell1", "ran_cell_snr_db_1")
            if not math.isnan(snr1):
                d["snr_c1"].append(snr1)

    # --- 1. Print Slice 1 (eMBB / UE-1) Report ---
    print("\n--- 1. SLICE 1: eMBB (UE-1 @ UPF-1) TELEMETRI TRAFIK & QOS ---")
    print(f"{'Skenario Event':<16} | {'Total':<5} | {'Valid':<5} | {'Outage':<6} | {'Miss':<4} | {'Cov %':<7} | {'Tput Mean':<10} | {'Tput Max':<9} | {'RTT Mean':<10} | {'RTT Max':<9} | {'Loss Avg':<8}")
    print("-" * 115)

    for scen, d in sorted(scen_data.items()):
        n_tot = d["total_rows"]
        s1_val = d["s1_valid_rtt_rows"]
        s1_out = d["s1_outage_rows"]
        s1_mis = d["s1_missing_rows"]
        s1_cov = (s1_val / n_tot * 100.0) if n_tot > 0 else 0.0

        tput_mean_str = f"{sum(d['s1_tput'])/len(d['s1_tput']):>7.2f} M" if d["s1_tput"] else f"{'N/A':>10}"
        tput_max_str = f"{max(d['s1_tput']):>6.2f} M" if d["s1_tput"] else f"{'N/A':>9}"
        rtt_mean_str = f"{sum(d['s1_rtt'])/len(d['s1_rtt']):>7.2f} ms" if d["s1_rtt"] else f"{'N/A':>10}"
        rtt_max_str = f"{max(d['s1_rtt']):>6.2f} ms" if d["s1_rtt"] else f"{'N/A':>9}"
        loss_avg_str = f"{sum(d['s1_loss'])/len(d['s1_loss']):>6.1f} %" if d["s1_loss"] else f"{'N/A':>8}"

        print(f"{scen:<16} | {n_tot:<5} | {s1_val:<5} | {s1_out:<6} | {s1_mis:<4} | {s1_cov:>6.1f}% | {tput_mean_str} | {tput_max_str} | {rtt_mean_str} | {rtt_max_str} | {loss_avg_str}")

    # --- 2. Print Slice 2 (URLLC / UE-2) Report ---
    print("\n--- 2. SLICE 2: URLLC (UE-2 @ UPF-2) AUDIT SLA (<20ms) ---")
    print(f"{'Skenario Event':<16} | {'Total':<5} | {'Valid':<5} | {'Outage':<6} | {'Miss':<4} | {'Cov %':<7} | {'RTT Mean':<10} | {'RTT Max':<9} | {'Loss Avg':<8} | {'SLA Viol %':<10}")
    print("-" * 103)

    for scen, d in sorted(scen_data.items()):
        n_tot = d["total_rows"]
        s2_val = d["s2_valid_rtt_rows"]
        s2_out = d["s2_outage_rows"]
        s2_mis = d["s2_missing_rows"]
        s2_cov = (s2_val / n_tot * 100.0) if n_tot > 0 else 0.0

        rtt_mean_str = f"{sum(d['s2_rtt'])/len(d['s2_rtt']):>7.2f} ms" if d["s2_rtt"] else f"{'N/A':>10}"
        rtt_max_str = f"{max(d['s2_rtt']):>6.2f} ms" if d["s2_rtt"] else f"{'N/A':>9}"

        if d["s2_measured_rows"] > 0:
            avg_loss = (sum(d["s2_loss"]) / len(d["s2_loss"])) if d["s2_loss"] else 0.0
            loss_avg_str = f"{avg_loss:>6.1f} %"
            sla_pct = (d["s2_sla_violated_rows"] / d["s2_measured_rows"] * 100.0)
            sla_str = f"{sla_pct:>9.1f}%"
        else:
            loss_avg_str = f"{'N/A':>8}"
            sla_str = f"{'N/A':>10}"

        print(f"{scen:<16} | {n_tot:<5} | {s2_val:<5} | {s2_out:<6} | {s2_mis:<4} | {s2_cov:>6.1f}% | {rtt_mean_str} | {rtt_max_str} | {loss_avg_str} | {sla_str}")

    # --- 3. Print Infrastructure Telemetry (RAN & Core) ---
    print("\n--- 3. TELEMETRI INFRASTRUKTUR (RAN CELL-1 & CORE UPF-1) ---")
    print(f"{'Skenario Event':<16} | {'PRB C1 Avg':<10} | {'PRB C1 Max':<10} | {'Backlog Max':<12} | {'Drops Total':<11} | {'MCS C1 Avg':<10} | {'BLER C1 Avg':<11} | {'SNR C1 Avg':<10}")
    print("-" * 105)

    for scen, d in sorted(scen_data.items()):
        prb_avg_str = f"{sum(d['prb_c1'])/len(d['prb_c1']):>8.1f} %" if d["prb_c1"] else f"{'N/A':>10}"
        prb_max_str = f"{max(d['prb_c1']):>8.1f} %" if d["prb_c1"] else f"{'N/A':>10}"
        b_max_str = f"{max(d['backlog']):>10,.0f} B" if d["backlog"] else f"{'0 B':>12}"
        drops_sum_str = f"{sum(d['drops']):>9,.0f} pkt" if d["drops"] else f"{'0 pkt':>11}"
        mcs_avg_str = f"{sum(d['mcs_c1'])/len(d['mcs_c1']):>8.1f}" if d["mcs_c1"] else f"{'N/A':>10}"
        bler_avg_str = f"{sum(d['bler_c1'])/len(d['bler_c1']):>9.2f} %" if d["bler_c1"] else f"{'N/A':>11}"
        snr_avg_str = f"{sum(d['snr_c1'])/len(d['snr_c1']):>7.1f} dB" if d["snr_c1"] else f"{'N/A':>10}"

        print(f"{scen:<16} | {prb_avg_str} | {prb_max_str} | {b_max_str} | {drops_sum_str} | {mcs_avg_str} | {bler_avg_str} | {snr_avg_str}")

    print("=" * 115)
    print(f"Total Sampel Dievaluasi: {total_rows} baris")
    print("Definisi Audit Telemetri & Klasifikasi Probe:")
    print(" - Valid      : Sampel dengan pengukuran RTT numerik yang berhasil diterima dalam jendela evaluasi.")
    print(" - Outage     : Gangguan total terkonfirmasi (probe aktif, packet loss terukur >= 100%).")
    print(" - Miss       : Probe tidak aktif / data belum tersedia (bukan outage terkonfirmasi).")
    print(" - Cov %      : Rasio sampel valid terhadap total baris fase (Valid / Total * 100%).")
    print(" - SLA Viol % : Rasio pelanggaran SLA terhadap sampel terukur (SLA Viol / Measured * 100%, threshold SLA: RTT <= 20ms).")


if __name__ == "__main__":
    main()
