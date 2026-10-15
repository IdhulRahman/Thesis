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
        raw_files = sorted(glob.glob(os.path.join(DATA_DIR, "telemetry_raw_*.csv")), key=os.path.getmtime)

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
                    "valid_rtt_rows": 0,
                    "valid_tput_rows": 0,
                    "outage_rows": 0,
                    "missing_probe_rows": 0,
                    "latency_violated_rows": 0,
                    "loss_violated_rows": 0,
                    "sla_violated_rows": 0,
                    "tput": [],
                    "rtt": [],
                    "loss": [],
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

            tput = parse_val("e2e_slice1_tput_mbps", "e2e_slice1_throughput_mbps")
            if not math.isnan(tput):
                d["tput"].append(tput)
                d["valid_tput_rows"] += 1

            rtt = parse_val("e2e_slice2_rtt_ms", "e2e_slice2_latency_rtt_ms")
            loss = parse_val("e2e_slice2_loss_pct", "e2e_slice2_packet_loss_pct")

            # Classification of probe telemetry:
            # 1. Missing / Unmeasured: probe not started or collector missed report (both RTT & loss NaN)
            # 2. Confirmed Outage: probe active but measured packet loss >= 100%
            # 3. Valid measurement: RTT and/or partial packet loss measured
            if math.isnan(rtt) and math.isnan(loss):
                d["missing_probe_rows"] += 1
            else:
                is_outage = (not math.isnan(loss) and loss >= 100.0)
                is_latency_violation = (not math.isnan(rtt) and rtt > 20.0)
                is_loss_violation = (not math.isnan(loss) and 0.0 < loss < 100.0)

                if is_outage:
                    d["outage_rows"] += 1
                    d["loss"].append(loss)
                    d["sla_violated_rows"] += 1
                else:
                    if not math.isnan(rtt):
                        d["rtt"].append(rtt)
                        d["valid_rtt_rows"] += 1
                        if is_latency_violation:
                            d["latency_violated_rows"] += 1

                    if not math.isnan(loss):
                        d["loss"].append(loss)
                        if is_loss_violation:
                            d["loss_violated_rows"] += 1

                    if is_latency_violation or is_loss_violation:
                        d["sla_violated_rows"] += 1

            prb1 = parse_val("ran_prb_cell1", "ran_cell_prb_utilization_1")
            if not math.isnan(prb1):
                d["prb_c1"].append(prb1)

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

    print(f"{'Skenario Event':<16} | {'Total':<5} | {'Valid':<5} | {'Outage':<6} | {'Miss':<4} | {'Coverage':<8} | {'Loss Avg':<8} | {'RTT Mean':<10} | {'RTT Max':<9} | {'SLA Viol %':<10} | {'Tput Avg':<9} | {'PRB C1':<7} | {'Backlog Max'}")
    print("-" * 141)

    for scen, d in sorted(scen_data.items()):
        n_total = d["total_rows"]
        n_valid_rtt = d["valid_rtt_rows"]
        n_outage = d["outage_rows"]
        n_missing = d["missing_probe_rows"]
        n_measured = n_valid_rtt + n_outage

        coverage_pct = (n_valid_rtt / n_total * 100.0) if n_total > 0 else 0.0

        if n_measured > 0:
            avg_loss = (sum(d["loss"]) / len(d["loss"])) if d["loss"] else 0.0
            loss_str = f"{avg_loss:>6.1f} %"
            sla_pct = (d["sla_violated_rows"] / n_measured * 100.0)
            sla_str = f"{sla_pct:>9.1f}%"
        else:
            loss_str = f"{'N/A':>8}"
            sla_str = f"{'N/A':>10}"

        avg_rtt_str = f"{sum(d['rtt']) / len(d['rtt']):>7.2f} ms" if d["rtt"] else f"{'N/A':>10}"
        max_rtt_str = f"{max(d['rtt']):>6.2f} ms" if d["rtt"] else f"{'N/A':>9}"

        avg_tput_str = f"{sum(d['tput']) / len(d['tput']):>6.2f} M" if d["tput"] else f"{'N/A':>9}"
        avg_prb_str = f"{sum(d['prb_c1']) / len(d['prb_c1']):>5.1f} %" if d["prb_c1"] else f"{'N/A':>7}"
        max_b_str = f"{max(d['backlog']):>10,.0f} B" if d["backlog"] else f"{'0 B':>12}"

        print(f"{scen:<16} | {n_total:<5} | {n_valid_rtt:<5} | {n_outage:<6} | {n_missing:<4} | {coverage_pct:>7.1f}% | {loss_str} | {avg_rtt_str} | {max_rtt_str} | {sla_str} | {avg_tput_str} | {avg_prb_str} | {max_b_str}")

    print("=" * 141)
    print(f"Total Sampel Dievaluasi: {total_rows} baris")
    print("Catatan Metrik URLLC:")
    print(" - Valid: Sampel dengan RTT valid terukur.")
    print(" - Outage: Outage terkonfirmasi (probe aktif, loss terukur >= 100%).")
    print(" - Miss: Data tidak tersedia (probe belum aktif atau telemetri hilang; bukan outage).")
    print(" - SLA Viol % dihitung dari sampel probe terukur (Valid + Outage).")


if __name__ == "__main__":
    main()
