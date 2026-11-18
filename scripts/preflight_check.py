#!/usr/bin/env python3
"""
Pre-Flight Telemetry Gate Check for 5G O-RAN Thesis Testbed
Location on VM-6: /opt/oran/monitoring/scripts/preflight_check.py
Pure Python 3 Standard Library - Zero External Dependencies

Evaluates all 4 telemetry pillars before recording to prevent wasted runs:
1. RAN PRB & BLER
2. Core UPF Backlog
3. Core NWDAF API & Volume (> 0)
4. End-to-End UE Traffic
"""

import math
import re
import sys
import urllib.request
import urllib.error

METRICS_URL = "http://127.0.0.1:9100/metrics"

PROM_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$')
LABEL_RE = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*=\s*"([^"]*)"')


def scrape_metrics(url=METRICS_URL):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PreFlightCheck/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[ERROR] Cannot connect to Telemetry Collector at {url}: {e}", file=sys.stderr)
        return None

    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = PROM_LINE_RE.match(line)
        if not m:
            continue
        name, raw_labels, val_str = m.group(1), m.group(2), m.group(3)
        labels = {}
        if raw_labels:
            for lm in LABEL_RE.finditer(raw_labels):
                labels[lm.group(1)] = lm.group(2)
        try:
            val = float(val_str)
        except ValueError:
            val = float("nan")

        key = name
        if "cell_id" in labels:
            key = f"{name}:cell_{labels['cell_id']}"
        elif "snssai" in labels:
            key = f"{name}:slice_{labels['snssai']}"
        metrics[key] = val

    return metrics


def main():
    print("=" * 75)
    print("5G O-RAN TESTBED PRE-FLIGHT TELEMETRY GATE CHECK (VM-6)")
    print("=" * 75)

    metrics = scrape_metrics()
    if not metrics:
        print("\n[RESULT] BLOCKED: Collector (:9100) is unreachable. Do not start recording!\n")
        sys.exit(1)

    checks = []

    # 1. RAN PRB Cell-1
    prb_c1 = metrics.get("ran_cell_prb_utilization:cell_1", float("nan"))
    prb_ok = not math.isnan(prb_c1)
    checks.append(("RAN PRB (Cell-1)", f"{prb_c1:.1f}%" if prb_ok else "NaN", prb_ok, "Verify ran_adapter.py on VM-4"))

    # 2. RAN BLER Cell-1
    bler_c1 = metrics.get("ran_cell_bler:cell_1", float("nan"))
    bler_ok = not math.isnan(bler_c1)
    checks.append(("RAN BLER (Cell-1)", f"{bler_c1*100:.2f}%" if bler_ok else "NaN", bler_ok, "Verify du1.log on VM-4"))

    # 3. Core UPF Backlog
    upf_b = metrics.get("upf_queue_backlog_bytes:slice_01000001", float("nan"))
    upf_ok = not math.isnan(upf_b)
    checks.append(("Core UPF Backlog", f"{upf_b:.0f} B" if upf_ok else "NaN", upf_ok, "Verify core_adapter.py on VM-3"))

    # 4. Core NWDAF API Status
    nwdaf_api = metrics.get("nwdaf_api_status", float("nan"))
    api_ok = (nwdaf_api == 1.0)
    checks.append(("Core NWDAF API", "HTTP 200 (UP)" if api_ok else "DOWN", api_ok, "Check Kong Gateway (:8080) on VM-3"))

    # 5. Core NWDAF Volume (CRITICAL GATE)
    nwdaf_vol = metrics.get("nwdaf_comm_ul_bytes", float("nan"))
    vol_ok = not math.isnan(nwdaf_vol) and nwdaf_vol > 0
    checks.append(("Core NWDAF Volume", f"{nwdaf_vol/1e6:.2f} MB ({nwdaf_vol:.0f} B)" if (not math.isnan(nwdaf_vol) and nwdaf_vol > 0) else f"{nwdaf_vol} (ZERO/FAIL)", vol_ok, "Restart oai-nwdaf-sbi on VM-3!"))

    # 6. UE eMBB Traffic
    tput = metrics.get("e2e_slice1_throughput_mbps", float("nan"))
    tput_ok = not math.isnan(tput) and tput > 0.0
    checks.append(("UE eMBB Traffic", f"{tput:.2f} Mbps" if tput_ok else "0.00 Mbps / Offline", tput_ok, "Start trafgen.sh on VM-5"))

    print(f"{'Pillar / Metric':<25} | {'Current Value':<22} | {'Status':<6} | {'Remediation if FAILED'}")
    print("-" * 75)

    all_pass = True
    for name, val_str, ok, rem in checks:
        status_str = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"{name:<25} | {val_str:<22} | {status_str:<6} | {rem}")

    print("=" * 75)
    if all_pass:
        print("[RESULT] ALL 6 GATES PASSED! Safe to start long-duration recording.\n")
        sys.exit(0)
    else:
        print("[RESULT] GATE CHECK FAILED! DO NOT START RECORDING!")
        print("         Resolve the failed pillars above before initiating recording.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
