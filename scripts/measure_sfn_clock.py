#!/usr/bin/env python3
"""
measure_sfn_clock.py - Measure OAI gNB DU SFN (System Frame Number) Radio Clock vs Wall Clock

Audits the progression of System Frame Number (SFN) in OAI DU logs against
monotonic host wall-clock time to identify simulator computational dilation.

Theoretical Basis:
- 3GPP TS 38.211 §4.3.1: NR radio frame duration is fixed at 10 ms (0.010 s).
- SFN spans from 0 to 1023 (1024 frames total, cycling every 10.24 seconds).
- In real-time execution, 128 radio frames (1.28 s) advance in ~1.28 s wall-clock (Ratio ~1.0x).
- Under CPU saturation (e.g. chanmod at 106 PRB), 128 radio frames require ~2.9 s (Ratio ~0.44x).

Location: VM-4 (oai-ran — 10.102.0.167)
Usage:
    python3 scripts/measure_sfn_clock.py --log /opt/oran/ran/du1.log
    python3 scripts/measure_sfn_clock.py --log /opt/oran/ran/du2.log --step 128
"""

import argparse
import os
import re
import sys
import time

PATTERN_FRAME_SLOT = re.compile(r"Frame\.Slot\s+(\d+)\.0\b")


def measure_sfn(log_path: str, tail: bool = True, step_filter: int = 0, max_samples: int = 0):
    if not os.path.exists(log_path):
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    print(f"=== OAI DU SFN Radio Clock Audit ===")
    print(f"Target Log File : {log_path}")
    print(f"Mode            : {'Tail from EOF' if tail else 'Read from Start'}")
    print(f"Step Filter     : {step_filter} frames {'(Report every step)' if step_filter <= 0 else ''}")
    print(f"Press Ctrl+C to terminate and view summary.\n")
    print(f"{'Timestamp':<10} {'Frame':<8} {'Radio (s)':<12} {'Wall (s)':<12} {'Instant':<10} {'Average':<10}")
    print("-" * 64)

    previous = None
    radio_total = 0.0
    start_time = None
    sample_count = 0

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            if tail:
                f.seek(0, os.SEEK_END)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                match = PATTERN_FRAME_SLOT.search(line)
                if not match:
                    continue

                frame = int(match.group(1))
                now = time.monotonic()

                if previous is None:
                    previous = (frame, now)
                    start_time = now
                    continue

                delta_frame = (frame - previous[0]) % 1024
                if delta_frame == 0:
                    continue

                # Filter by step size if configured (e.g., only report increments of 128)
                if step_filter > 0 and delta_frame < step_filter:
                    continue

                radio_sec = delta_frame * 0.010  # 10ms per frame (3GPP TS 38.211)
                radio_total += radio_sec
                wall_sec = now - previous[1]
                total_wall = now - start_time

                instant_ratio = (radio_sec / wall_sec) if wall_sec > 1e-6 else 0.0
                avg_ratio = (radio_total / total_wall) if total_wall > 1e-6 else 0.0

                inst_str = f"{instant_ratio:.2f}x"
                avg_str = f"{avg_ratio:.2f}x"

                ts = time.strftime("%H:%M:%S")
                print(f"{ts:<10} {frame:<8d} {radio_sec:<12.2f} {wall_sec:<12.2f} {inst_str:<10} {avg_str:<10}")
                sys.stdout.flush()

                previous = (frame, now)
                sample_count += 1

                if max_samples > 0 and sample_count >= max_samples:
                    break

    except KeyboardInterrupt:
        print("\n[INFO] Audit interrupted by operator.")

    if start_time is not None and sample_count > 0:
        total_wall = time.monotonic() - start_time
        final_ratio = (radio_total / total_wall) if total_wall > 1e-6 else 0.0
        print("\n" + "=" * 64)
        print("=== SFN Progress Audit Summary ===")
        print(f"Total Observed Radio Time : {radio_total:.2f} s")
        print(f"Total Monotonic Wall Time : {total_wall:.2f} s")
        print(f"Cumulative Mean Ratio     : {final_ratio:.2f}x")

        if final_ratio >= 0.95:
            assessment = "REAL-TIME (No significant computational dilation)"
        elif final_ratio >= 0.70:
            assessment = "MODERATE DILATION (Transient CPU contention detected)"
        else:
            assessment = "SEVERE DILATION (Software simulator bottleneck, e.g. chanmod overload)"

        print(f"Performance Assessment    : {assessment}")
        print("=" * 64)
    else:
        print("\n[WARN] No SFN frame transitions were captured during this session.")


def main():
    parser = argparse.ArgumentParser(
        description="Audit OAI DU SFN Radio Clock Progression vs Host Monotonic Wall Clock."
    )
    parser.add_argument(
        "--log",
        default="/opt/oran/ran/du1.log",
        help="Path to OAI DU log file (default: /opt/oran/ran/du1.log)"
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read existing log from start rather than tailing from EOF"
    )
    parser.add_argument(
        "--step",
        type=int,
        default=0,
        help="Minimum frame delta before reporting (e.g., 128; default: 0 reports every step)"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Maximum sample count before exiting (default: 0 = run indefinitely)"
    )

    args = parser.parse_args()
    measure_sfn(
        log_path=args.log,
        tail=not args.from_start,
        step_filter=args.step,
        max_samples=args.max_samples
    )


if __name__ == "__main__":
    main()
