#!/usr/bin/env python3
"""
RAN Telemetry Adapter for OAI gNB DU (Cell-1 & Cell-2)
Location: VM-4 (oai-ran — 10.102.0.167)
Tails DU scheduler logs and exports authentic MAC radio link telemetry (NPRB, MCS, BLER, SNR, RSSI)
to VM-6 telemetry collector (:9100/report).
Pure Python 3 Standard Library - Zero external dependencies.
"""

import json
import os
import re
import subprocess
import time
import urllib.request

COLLECTOR_URL = "http://10.102.0.67:9100/report"
DU1_LOG = "/opt/oran/ran/du1.log"
DU2_LOG = "/opt/oran/ran/du2.log"
MAX_PRB = 106.0

# Comprehensive regex to parse OAI DU scheduler telemetry per UE
RADIO_STATS_PATTERN = re.compile(
    r'ulsch_errors\s+(?P<errors>\d+).*?'
    r'BLER\s+(?P<bler>[0-9.]+).*?'
    r'MCS\s*(?:\([^)]*\))?\s*(?P<mcs>\d+).*?'
    r'NPRB\s+(?P<nprb>\d+).*?'
    r'SNR\s+(?P<snr>[-0-9.]+).*?'
    r'RSSI\s+(?P<rssi>[-0-9.]+)'
)
NPRB_FALLBACK = re.compile(r'NPRB\s+(\d+)')


def extract_latest_radio_stats(log_path):
    stats = {
        "nprb": None,
        "prb_pct": None,
        "mcs": None,
        "bler": None,
        "snr_db": None,
        "rssi_dbm": None,
        "ulsch_errors": None,
        "valid": False
    }
    if not os.path.exists(log_path):
        return stats
    try:
        cmd = ["tail", "-n", "30", log_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.5)
        matches = RADIO_STATS_PATTERN.findall(res.stdout)
        if matches:
            last = matches[-1]
            nprb_val = int(last[3])
            stats["ulsch_errors"] = int(last[0])
            stats["bler"] = float(last[1])
            stats["mcs"] = int(last[2])
            stats["nprb"] = nprb_val
            stats["prb_pct"] = round((nprb_val / MAX_PRB) * 100.0, 2)
            stats["snr_db"] = float(last[4])
            stats["rssi_dbm"] = float(last[5])
            stats["valid"] = True
            return stats

        nprb_matches = NPRB_FALLBACK.findall(res.stdout)
        if nprb_matches:
            nprb_val = int(nprb_matches[-1])
            stats["nprb"] = nprb_val
            stats["prb_pct"] = round((nprb_val / MAX_PRB) * 100.0, 2)
            stats["valid"] = True
    except Exception:
        pass
    return stats


def send_to_collector(stats1, stats2):
    payload = {
        "ran_cell_prb_utilization": {
            "1": stats1["prb_pct"],
            "2": stats2["prb_pct"]
        },
        "ran_cell_radio_stats": {
            "1": stats1,
            "2": stats2
        }
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            COLLECTOR_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    print("[RAN-Adapter v2] Memulai telemetry radio link gNB DU (Cell-1 & Cell-2)...", flush=True)
    print(f"{'Time':<8} | {'C1 PRB%':<9} | {'C1 MCS':<6} | {'C1 BLER':<8} | {'C1 SNR':<7} | {'C2 PRB%':<9} | {'Status'}", flush=True)
    print("-" * 68, flush=True)

    while True:
        try:
            s1 = extract_latest_radio_stats(DU1_LOG)
            s2 = extract_latest_radio_stats(DU2_LOG)

            ok = send_to_collector(s1, s2)
            status_str = "SUCCESS" if ok else "FAILED"
            t_str = time.strftime("%H:%M:%S")

            prb1_str = f"{s1['prb_pct']:>7.1f}%" if s1['prb_pct'] is not None else f"{'N/A':>8}"
            prb2_str = f"{s2['prb_pct']:>7.1f}%" if s2['prb_pct'] is not None else f"{'N/A':>8}"
            mcs_str = f"{s1['mcs']:>6}" if s1['mcs'] is not None else f"{'N/A':>6}"
            bler_str = f"{s1['bler']:>8.4f}" if s1['bler'] is not None else f"{'N/A':>8}"
            snr_str = f"{s1['snr_db']:>5.1f}dB" if s1['snr_db'] is not None else f"{'N/A':>7}"

            print(f"{t_str:<8} | {prb1_str} | {mcs_str} | {bler_str} | {snr_str} | {prb2_str} | {status_str}", flush=True)
        except Exception as e:
            print(f"Error loop: {e}", flush=True)

        time.sleep(1.0)


if __name__ == "__main__":
    main()
