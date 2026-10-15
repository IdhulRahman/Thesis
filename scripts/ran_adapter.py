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

STALE_THRESHOLD_SEC = 3.5

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


def read_last_lines(file_path, num_lines=30, chunk_size=8192):
    """Read the last N lines of a file without spawning external subprocesses."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return []
            seek_pos = max(0, size - chunk_size)
            f.seek(seek_pos)
            content = f.read()
            lines = content.splitlines()
            return lines[-num_lines:]
    except Exception:
        return []


class DuLogTracker:
    """Tracks DU log file progression, file size, modification time, and measurement staleness."""

    def __init__(self, log_path, cell_id, stale_threshold=STALE_THRESHOLD_SEC):
        self.log_path = log_path
        self.cell_id = cell_id
        self.stale_threshold = stale_threshold
        self.last_size = 0
        self.last_mtime = 0.0
        self.last_meas_time = 0.0
        self.cached_stats = {
            "cell_id": self.cell_id,
            "nprb": None,
            "prb_pct": None,
            "mcs": None,
            "bler": None,
            "snr_db": None,
            "rssi_dbm": None,
            "ulsch_errors": None,
            "valid": False,
            "source_mtime": None,
            "source_age_sec": None,
            "read_time": 0.0
        }

    def update(self):
        now = time.time()
        self.cached_stats["read_time"] = now

        if not os.path.exists(self.log_path):
            self.cached_stats["valid"] = False
            self.cached_stats["source_age_sec"] = None
            return self.cached_stats

        try:
            stat = os.stat(self.log_path)
            cur_size = stat.st_size
            cur_mtime = stat.st_mtime
            age = now - cur_mtime

            # If the log file itself has not been modified within the threshold, DU is idle or halted
            if age > self.stale_threshold:
                self.cached_stats["valid"] = False
                self.cached_stats["source_mtime"] = cur_mtime
                self.cached_stats["source_age_sec"] = round(age, 2)
                return self.cached_stats

            # If file size and mtime are unchanged, verify time since last measurement was extracted
            if cur_size == self.last_size and cur_mtime == self.last_mtime:
                meas_age = (now - self.last_meas_time) if self.last_meas_time > 0.0 else age
                if meas_age > self.stale_threshold:
                    self.cached_stats["valid"] = False
                self.cached_stats["source_age_sec"] = round(meas_age, 2)
                return self.cached_stats

            # New data is available: extract recent log lines
            lines = read_last_lines(self.log_path, num_lines=30)
            text_block = "\n".join(lines)

            matches = RADIO_STATS_PATTERN.findall(text_block)
            if matches:
                last = matches[-1]
                nprb_val = int(last[3])
                self.cached_stats["ulsch_errors"] = int(last[0])
                self.cached_stats["bler"] = float(last[1])
                self.cached_stats["mcs"] = int(last[2])
                self.cached_stats["nprb"] = nprb_val
                self.cached_stats["prb_pct"] = round((nprb_val / MAX_PRB) * 100.0, 2)
                self.cached_stats["snr_db"] = float(last[4])
                self.cached_stats["rssi_dbm"] = float(last[5])
                self.cached_stats["valid"] = True
                self.cached_stats["source_mtime"] = cur_mtime
                self.cached_stats["source_age_sec"] = round(age, 2)

                self.last_meas_time = now
                self.last_size = cur_size
                self.last_mtime = cur_mtime
                return self.cached_stats

            nprb_matches = NPRB_FALLBACK.findall(text_block)
            if nprb_matches:
                nprb_val = int(nprb_matches[-1])
                self.cached_stats["nprb"] = nprb_val
                self.cached_stats["prb_pct"] = round((nprb_val / MAX_PRB) * 100.0, 2)
                self.cached_stats["valid"] = True
                self.cached_stats["source_mtime"] = cur_mtime
                self.cached_stats["source_age_sec"] = round(age, 2)

                self.last_meas_time = now
                self.last_size = cur_size
                self.last_mtime = cur_mtime
                return self.cached_stats

            # Lines were written but no scheduler match
            self.cached_stats["valid"] = False
            self.last_size = cur_size
            self.last_mtime = cur_mtime
            return self.cached_stats

        except Exception:
            self.cached_stats["valid"] = False
            return self.cached_stats


def send_to_collector(stats1, stats2):
    payload = {
        "domain": "ran",
        "ran_cell_prb_utilization": {
            "1": stats1["prb_pct"] if stats1.get("valid") else None,
            "2": stats2["prb_pct"] if stats2.get("valid") else None
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
    print("[RAN-Adapter v3] Starting OAI gNB DU radio link telemetry adapter with staleness tracking...", flush=True)
    print(f"Tracking DU-1: {DU1_LOG} | DU-2: {DU2_LOG} (Stale threshold: {STALE_THRESHOLD_SEC}s)")
    print(f"{'Time':<8} | {'C1 PRB%':<9} | {'C1 MCS':<6} | {'C1 BLER':<8} | {'C1 SNR':<7} | {'C2 PRB%':<9} | {'Status'}", flush=True)
    print("-" * 68, flush=True)

    tracker1 = DuLogTracker(DU1_LOG, cell_id="1")
    tracker2 = DuLogTracker(DU2_LOG, cell_id="2")

    while True:
        try:
            s1 = tracker1.update()
            s2 = tracker2.update()

            ok = send_to_collector(s1, s2)
            status_str = "SUCCESS" if ok else "FAILED"
            t_str = time.strftime("%H:%M:%S")

            if s1["valid"] and s1["prb_pct"] is not None:
                prb1_str = f"{s1['prb_pct']:>7.1f}%"
            elif s1.get("source_age_sec") is not None and s1["source_age_sec"] > STALE_THRESHOLD_SEC:
                prb1_str = f"{'STALE':>8}"
            else:
                prb1_str = f"{'N/A':>8}"

            if s2["valid"] and s2["prb_pct"] is not None:
                prb2_str = f"{s2['prb_pct']:>7.1f}%"
            elif s2.get("source_age_sec") is not None and s2["source_age_sec"] > STALE_THRESHOLD_SEC:
                prb2_str = f"{'STALE':>8}"
            else:
                prb2_str = f"{'N/A':>8}"

            mcs_str = f"{s1['mcs']:>6}" if (s1["valid"] and s1["mcs"] is not None) else f"{'N/A':>6}"
            bler_str = f"{s1['bler']:>8.4f}" if (s1["valid"] and s1["bler"] is not None) else f"{'N/A':>8}"
            snr_str = f"{s1['snr_db']:>5.1f}dB" if (s1["valid"] and s1["snr_db"] is not None) else f"{'N/A':>7}"

            print(f"{t_str:<8} | {prb1_str} | {mcs_str} | {bler_str} | {snr_str} | {prb2_str} | {status_str}", flush=True)
        except Exception as e:
            print(f"Error loop: {e}", flush=True)

        time.sleep(1.0)


if __name__ == "__main__":
    main()
