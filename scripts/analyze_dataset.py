#!/usr/bin/env python3
"""
Dataset Statistical Audit & Analysis Script for 5G O-RAN Thesis
Location on VM-6: /opt/oran/monitoring/scripts/analyze_dataset.py
Pure Python 3 Standard Library - Zero External Dependencies
Evaluates recorded CSV telemetry: PRB saturation, Core buffer backlog,
packet drops, throughput delivery, and URLLC SLA violation rates per scenario.
"""

import csv
import glob
import math
import os
import re
import sys

DATA_DIR = os.getenv("MONITORING_DATA_DIR", "/opt/oran/monitoring/data")


def make_metrics_bucket():
    return {
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
        "s2_sla_compliant_rows": 0,
        "s2_sla_unknown_rows": 0,
        "s2_rtt": [],
        "s2_loss": [],

        # Infrastructure (RAN & Core)
        "prb_c1": [],
        "prb_c2": [],
        "backlog": [],
        "drops": [],
        "mcs_c1": [],
        "bler_c1": [],
        "snr_c1": [],

        # 3GPP NWDAF AnLF Metrics
        "nwdaf_ul": [],
        "nwdaf_dl": [],
        "nwdaf_dur": [],
        "nwdaf_std": [],
        "nwdaf_fresh": [],
        "nwdaf_api": []
    }


def parse_val(row, *cols):
    for col in cols:
        val = row.get(col, "")
        if val not in ("", "NaN", "nan", "None", "null", None):
            try:
                return float(val)
            except ValueError:
                pass
    return math.nan


def update_bucket(d, row):
    d["total_rows"] += 1

    # --- Slice 1 Telemetry (eMBB / UE-1 via UPF-1) ---
    s1_tput = parse_val(row, "e2e_slice1_tput_mbps", "e2e_slice1_throughput_mbps")
    if not math.isnan(s1_tput):
        d["s1_tput"].append(s1_tput)
        d["s1_valid_tput_rows"] += 1

    s1_rtt = parse_val(row, "e2e_slice1_rtt_ms", "e2e_slice1_latency_rtt_ms")
    s1_loss = parse_val(row, "e2e_slice1_loss_pct", "e2e_slice1_packet_loss_pct")

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
    s2_rtt = parse_val(row, "e2e_slice2_rtt_ms", "e2e_slice2_latency_rtt_ms")
    s2_loss = parse_val(row, "e2e_slice2_loss_pct", "e2e_slice2_packet_loss_pct")

    if math.isnan(s2_rtt) and math.isnan(s2_loss):
        d["s2_missing_rows"] += 1
    else:
        d["s2_measured_rows"] += 1
        is_outage = (not math.isnan(s2_loss) and s2_loss >= 100.0)
        is_latency_violation = (not math.isnan(s2_rtt) and s2_rtt > 20.0)
        is_loss_violation = (not math.isnan(s2_loss) and s2_loss > 1.0 and s2_loss < 100.0)

        if not math.isnan(s2_rtt):
            d["s2_rtt"].append(s2_rtt)
            d["s2_valid_rtt_rows"] += 1
            if is_latency_violation:
                d["s2_latency_violated_rows"] += 1

        if not math.isnan(s2_loss):
            d["s2_loss"].append(s2_loss)
            if is_outage:
                d["s2_outage_rows"] += 1
            elif is_loss_violation:
                d["s2_loss_violated_rows"] += 1

        # SLA evaluation: RTT <= 20ms AND loss <= 1.0%
        # Definite violation if any measured component violates
        if is_outage or is_latency_violation or is_loss_violation:
            d["s2_sla_violated_rows"] += 1
        elif (not math.isnan(s2_rtt) and s2_rtt <= 20.0) and (not math.isnan(s2_loss) and s2_loss <= 1.0):
            d["s2_sla_compliant_rows"] += 1
        else:
            # Partial measurement (e.g. RTT <= 20ms but loss is NaN): status is Unknown
            d["s2_sla_unknown_rows"] += 1

    # --- Infrastructure Telemetry (RAN & Core) ---
    prb1 = parse_val(row, "ran_prb_cell1", "ran_cell_prb_utilization_1")
    if not math.isnan(prb1):
        d["prb_c1"].append(prb1)

    prb2 = parse_val(row, "ran_prb_cell2", "ran_cell_prb_utilization_2")
    if not math.isnan(prb2):
        d["prb_c2"].append(prb2)

    b_log = parse_val(row, "upf_backlog_bytes_embb", "upf_queue_backlog_bytes_01000001")
    if not math.isnan(b_log):
        d["backlog"].append(b_log)

    drop = parse_val(row, "upf_drops_embb", "upf_packet_drops_01000001")
    if not math.isnan(drop):
        d["drops"].append(drop)

    mcs1 = parse_val(row, "ran_mcs_cell1", "ran_cell_mcs_1")
    if not math.isnan(mcs1):
        d["mcs_c1"].append(mcs1)

    bler1 = parse_val(row, "ran_bler_cell1", "ran_cell_bler_1")
    if not math.isnan(bler1):
        d["bler_c1"].append(bler1)

    snr1 = parse_val(row, "ran_snr_cell1", "ran_cell_snr_db_1")
    if not math.isnan(snr1):
        d["snr_c1"].append(snr1)

    # --- 3GPP NWDAF AnLF Telemetry ---
    ul = parse_val(row, "nwdaf_comm_ul_bytes")
    if not math.isnan(ul):
        d["nwdaf_ul"].append(ul)

    dl = parse_val(row, "nwdaf_comm_dl_bytes")
    if not math.isnan(dl):
        d["nwdaf_dl"].append(dl)

    dur = parse_val(row, "nwdaf_comm_duration_sec")
    if not math.isnan(dur):
        d["nwdaf_dur"].append(dur)

    std = parse_val(row, "nwdaf_comm_vol_std_bytes")
    if not math.isnan(std):
        d["nwdaf_std"].append(std)

    fresh = parse_val(row, "nwdaf_comm_freshness")
    if not math.isnan(fresh):
        d["nwdaf_fresh"].append(fresh)

    api = parse_val(row, "nwdaf_api_status")
    if not math.isnan(api):
        d["nwdaf_api"].append(api)


def is_recorder_placeholder(raw_phase, scen_upper):
    if not raw_phase:
        return True
    rp = raw_phase.strip().upper()
    if rp in ("IDLE", "UNKNOWN", "NONE", "NAN", "NULL", ""):
        return True
    # Match default single-run placeholder: phase_1_<scen> or phase_1_s<N>
    scen_short = scen_upper.split("_")[0]
    if rp in (f"PHASE_1_{scen_upper}", f"PHASE_1_{scen_short}"):
        return True
    if re.fullmatch(r"PHASE_1_S\d+", rp):
        return True
    return False


def resolve_phase(scen, row):
    scen_upper = scen.upper()
    raw_phase = row.get("event_phase_id", "").strip()

    # 1. Actual event phase annotation priority:
    # Any explicit annotation that is not a static recorder placeholder takes precedence
    if not is_recorder_placeholder(raw_phase, scen_upper):
        return raw_phase

    # 2. Reference normal baseline scenarios (S1, S2): steady-state reference throughout the entire run
    if any(k in scen_upper for k in ("S1", "S2", "NORMAL_LIGHT", "NORMAL_HIGH")):
        return "1_REFERENCE_STEADY"

    # 3. Continuous saturated load scenario (S5): fixed capacity overload throughout the run
    if any(k in scen_upper for k in ("S5", "RAN_OVERLOAD")):
        return "1_SATURATED_STEADY"

    # 4. Fault injection scenarios (S3, S4, S6, S7, S8, S9):
    # Scheduled nominal windows [0-120s], [120-420s], [420-600s]
    el_sec = parse_val(row, "elapsed_sec")
    if not math.isnan(el_sec):
        if el_sec < 120.0:
            return "1_BASELINE_NOMINAL [0-120s]"
        elif el_sec < 420.0:
            return "2_ACTIVE_FAULT_NOMINAL [120-420s]"
        else:
            return "3_RECOVERY_NOMINAL [420-600s]"

    return raw_phase if raw_phase and raw_phase.upper() not in ("NAN", "NULL") else "UNKNOWN"


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

    print("=" * 115)
    print(f"ANALISIS TELEMETRI DATASET: {filename} ({size_kb:.1f} KB)")
    print("=" * 115)

    scen_data = {}
    phase_data = {}
    total_rows = 0

    with open(raw_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            scen = row.get("event_scenario", row.get("scenario", "UNKNOWN"))
            if scen not in scen_data:
                scen_data[scen] = make_metrics_bucket()

            update_bucket(scen_data[scen], row)

            # Phase segmentation
            ph = resolve_phase(scen, row)

            phase_key = (scen, ph)
            if phase_key not in phase_data:
                phase_data[phase_key] = make_metrics_bucket()
            update_bucket(phase_data[phase_key], row)

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
    print("\n--- 2. SLICE 2: URLLC (UE-2 @ UPF-2) AUDIT SLA (<20ms, Loss <=1%) ---")
    print(f"{'Skenario Event':<16} | {'Total':<5} | {'Valid':<5} | {'Outage':<6} | {'Miss':<4} | {'Unk':<4} | {'Cov %':<7} | {'RTT Mean':<10} | {'RTT Max':<9} | {'Loss Avg':<8} | {'SLA Viol %':<10}")
    print("-" * 110)

    for scen, d in sorted(scen_data.items()):
        n_tot = d["total_rows"]
        s2_val = d["s2_valid_rtt_rows"]
        s2_out = d["s2_outage_rows"]
        s2_mis = d["s2_missing_rows"]
        s2_unk = d["s2_sla_unknown_rows"]
        s2_cov = (s2_val / n_tot * 100.0) if n_tot > 0 else 0.0

        rtt_mean_str = f"{sum(d['s2_rtt'])/len(d['s2_rtt']):>7.2f} ms" if d["s2_rtt"] else f"{'N/A':>10}"
        rtt_max_str = f"{max(d['s2_rtt']):>6.2f} ms" if d["s2_rtt"] else f"{'N/A':>9}"

        if d["s2_measured_rows"] > 0:
            avg_loss = (sum(d["s2_loss"]) / len(d["s2_loss"])) if d["s2_loss"] else None
            loss_avg_str = f"{avg_loss:>6.1f} %" if avg_loss is not None else f"{'N/A':>8}"
            evaluable_s2 = d["s2_sla_violated_rows"] + d["s2_sla_compliant_rows"]
            if evaluable_s2 > 0:
                sla_pct = (d["s2_sla_violated_rows"] / evaluable_s2 * 100.0)
                sla_str = f"{sla_pct:>9.1f}%"
            else:
                sla_str = f"{'N/A':>10}"
        else:
            loss_avg_str = f"{'N/A':>8}"
            sla_str = f"{'N/A':>10}"

        print(f"{scen:<16} | {n_tot:<5} | {s2_val:<5} | {s2_out:<6} | {s2_mis:<4} | {s2_unk:<4} | {s2_cov:>6.1f}% | {rtt_mean_str} | {rtt_max_str} | {loss_avg_str} | {sla_str}")

    # --- 3. Print Infrastructure Telemetry (RAN & Core) ---
    print("\n--- 3. TELEMETRI INFRASTRUKTUR (RAN CELL-1 & CORE UPF-1) ---")
    print(f"{'Skenario Event':<16} | {'PRB C1 Avg':<10} | {'PRB C1 Max':<10} | {'Backlog Max':<12} | {'Drop Rate Max':<13} | {'MCS C1 Avg':<10} | {'BLER C1 Avg':<11} | {'SNR C1 Avg':<10}")
    print("-" * 107)

    for scen, d in sorted(scen_data.items()):
        prb_avg_str = f"{sum(d['prb_c1'])/len(d['prb_c1']):>8.1f} %" if d["prb_c1"] else f"{'N/A':>10}"
        prb_max_str = f"{max(d['prb_c1']):>8.1f} %" if d["prb_c1"] else f"{'N/A':>10}"
        b_max_str = f"{max(d['backlog']):>10,.0f} B" if d["backlog"] else f"{'N/A':>12}"
        drops_max_str = f"{max(d['drops']):>7.1f} pkt/s" if d["drops"] else f"{'N/A':>13}"
        mcs_avg_str = f"{sum(d['mcs_c1'])/len(d['mcs_c1']):>8.1f}" if d["mcs_c1"] else f"{'N/A':>10}"
        bler_avg_str = f"{sum(d['bler_c1'])/len(d['bler_c1'])*100:>8.2f} %" if d["bler_c1"] else f"{'N/A':>11}"
        snr_avg_str = f"{sum(d['snr_c1'])/len(d['snr_c1']):>7.1f} dB" if d["snr_c1"] else f"{'N/A':>10}"

        print(f"{scen:<16} | {prb_avg_str} | {prb_max_str} | {b_max_str} | {drops_max_str} | {mcs_avg_str} | {bler_avg_str} | {snr_avg_str}")

    # --- 3B. Print 3GPP NWDAF AnLF Telemetry Report ---
    print("\n--- 3B. 3GPP NWDAF AnLF (VM-07 NBI :8080) TELEMETRI ANALITIK USER-PLANE ---")
    print(f"{'Skenario Event':<16} | {'API Status':<10} | {'Freshness':<10} | {'URR Updates':<11} | {'UL Total':<12} | {'DL Total':<12} | {'Max Duration':<12}")
    print("-" * 95)

    for scen, d in sorted(scen_data.items()):
        api_str = f"{sum(d['nwdaf_api'])/len(d['nwdaf_api'])*100:>8.1f} %" if d["nwdaf_api"] else f"{'N/A':>10}"
        fresh_str = f"{sum(d['nwdaf_fresh'])/len(d['nwdaf_fresh'])*100:>8.1f} %" if d["nwdaf_fresh"] else f"{'N/A':>10}"

        urr_updates = 0
        if len(d["nwdaf_ul"]) > 1:
            for i in range(1, len(d["nwdaf_ul"])):
                if d["nwdaf_ul"][i] != d["nwdaf_ul"][i-1] or (i < len(d["nwdaf_dl"]) and d["nwdaf_dl"][i] != d["nwdaf_dl"][i-1]):
                    urr_updates += 1
            urr_str = f"{urr_updates:>11}"
        else:
            urr_str = f"{'N/A':>11}"

        if d["nwdaf_ul"]:
            delta_ul = d["nwdaf_ul"][-1] - d["nwdaf_ul"][0]
            ul_str = f"{delta_ul/1e6:>8.2f} MB" if delta_ul >= 0 else f"{d['nwdaf_ul'][-1]/1e6:>8.2f} MB"
        else:
            ul_str = f"{'N/A':>12}"

        if d["nwdaf_dl"]:
            delta_dl = d["nwdaf_dl"][-1] - d["nwdaf_dl"][0]
            dl_str = f"{delta_dl/1e6:>8.2f} MB" if delta_dl >= 0 else f"{d['nwdaf_dl'][-1]/1e6:>8.2f} MB"
        else:
            dl_str = f"{'N/A':>12}"

        dur_str = f"{d['nwdaf_dur'][-1]:>10.1f} s" if d["nwdaf_dur"] else f"{'N/A':>12}"

        print(f"{scen:<16} | {api_str} | {fresh_str} | {urr_str} | {ul_str} | {dl_str} | {dur_str}")

    # --- 4. Print Operational Phase Segmentation Report (if multiple phases present) ---
    if len(phase_data) > len(scen_data):
        print("\n--- 4. AUDIT SEGMENTASI FASE OPERASIONAL (Jadwal Nominal Gangguan S3-S4/S6-S9: Baseline [0-120s] -> Active Fault [120-420s] -> Recovery [420-600s]) ---")
        print(f"{'Skenario / Fase':<44} | {'Rows':<5} | {'PRB C1':<8} | {'Backlog Max':<12} | {'Drop Max':<11} | {'MCS':<5} | {'BLER C1':<9} | {'URLLC RTT':<10} | {'SLA Viol %':<10}")
        print("-" * 132)
        for (scen, ph), d in sorted(phase_data.items()):
            label = f"{scen} [{ph}]"
            n_r = d["total_rows"]
            prb_s = f"{sum(d['prb_c1'])/len(d['prb_c1']):>6.1f} %" if d["prb_c1"] else f"{'N/A':>8}"
            b_s = f"{max(d['backlog']):>10,.0f} B" if d["backlog"] else f"{'N/A':>12}"
            d_s = f"{max(d['drops']):>7.1f} p/s" if d["drops"] else f"{'N/A':>11}"
            m_s = f"{sum(d['mcs_c1'])/len(d['mcs_c1']):>5.1f}" if d["mcs_c1"] else f"{'N/A':>5}"
            bl_s = f"{sum(d['bler_c1'])/len(d['bler_c1'])*100:>6.2f} %" if d["bler_c1"] else f"{'N/A':>9}"
            r_s = f"{sum(d['s2_rtt'])/len(d['s2_rtt']):>7.2f} ms" if d["s2_rtt"] else f"{'N/A':>10}"
            ev = d["s2_sla_violated_rows"] + d["s2_sla_compliant_rows"]
            if ev > 0:
                s_s = f"{(d['s2_sla_violated_rows']/ev*100):>9.1f}%"
            else:
                s_s = f"{'N/A':>10}"
            print(f"{label:<44} | {n_r:<5} | {prb_s} | {b_s} | {d_s} | {m_s} | {bl_s} | {r_s} | {s_s}")

    print("=" * 115)
    print(f"Total Sampel Dievaluasi: {total_rows} baris")
    jsonl_file = os.path.join(os.path.dirname(raw_file), "nwdaf_raw_poll_responses.jsonl")
    if os.path.isfile(jsonl_file):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as jf:
                poll_count = sum(1 for line in jf if line.strip())
            print(f"Arsip NWDAF Raw        : {poll_count} poll responses tersimpan di {os.path.basename(jsonl_file)}")
        except Exception:
            pass
    print("Definisi Audit Telemetri & Klasifikasi Probe:")
    print(" - Valid      : Sampel dengan pengukuran RTT numerik yang berhasil diterima dalam jendela evaluasi.")
    print(" - Outage     : Gangguan total terkonfirmasi (probe aktif, packet loss terukur >= 100%).")
    print(" - Miss       : Probe tidak aktif / data belum tersedia (bukan outage terkonfirmasi).")
    print(" - Unk        : Status SLA parsial / unknown (komponen terukur normal, komponen lain missing).")
    print(" - Cov %      : Rasio sampel valid terhadap total baris fase (Valid / Total * 100%).")
    print(" - SLA Viol % : Rasio pelanggaran SLA terhadap sampel definitif (SLA Viol / (Violated + Compliant) * 100%).")
    print(" - Joint SLA  : Evaluasi SLA gabungan eMBB+URLLC bersyarat ketersediaan receiver goodput EXT-DN.")
    print(" - Segmentasi : Batas 120s/420s pada skenario gangguan (S3-S4, S6-S9) adalah interval jadwal nominal injeksi, bukan bukti definitif status fisik jaringan. Skenario S1/S2 dan S5 dievaluasi sebagai fase tunak tunggal (steady-state).")


if __name__ == "__main__":
    main()
