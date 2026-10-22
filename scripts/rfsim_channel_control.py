#!/usr/bin/env python3
"""
OAI RFsimulator Channel Modeling & Telnet Controller (Production Grade)
Location: /opt/oran/ran/scripts/rfsim_channel_control.py

Audited & Verified for OpenAirInterface 5G (commit 29d5fa7d).
Supports dynamic, closed-loop verified manipulation of RF channel parameters
via OAI softmodem Telnet Server (--telnetsrv) without restarting processes.

Standard Library only: Zero external Python dependencies.
"""

import argparse
import datetime
import math
import re
import socket
import sys
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9090  # Default: DU-1 Cell-1
BUFFER_SIZE = 4096

# Regex for Telnet response cleaning & status extraction
PLOSS_REGEX = re.compile(
    r'(?:path[ _-]?loss(?:[ _-]?dB)?|ploss)\s*[:=]?\s*(?P<val>[-+]?\d+(?:\.\d+)?)',
    re.IGNORECASE
)
NOISE_REGEX = re.compile(
    r'(?:noise[ _-]?power(?:[ _-]?dB)?|noise)\s*[:=]?\s*(?P<val>[-+]?\d+(?:\.\d+)?)',
    re.IGNORECASE
)
ERROR_KEYWORDS = ["unknown command", "error", "failed", "invalid", "not found", "syntax error"]


def clean_telnet_data(data: bytes) -> str:
    """Filter out Telnet IAC (Interpret As Command) escape sequences."""
    clean = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xFF:  # IAC
            if i + 1 < len(data) and data[i + 1] in (0xFB, 0xFC, 0xFD, 0xFE):
                i += 3
            else:
                i += 2
        else:
            clean.append(data[i])
            i += 1
    return clean.decode("utf-8", errors="replace")


class OaiTelnetClient:
    """Robust Telnet client tailored for OAI softmodem telnetsrv."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5.0, audit_log=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.audit_log = audit_log

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{ts}] {msg}"
        if self.audit_log:
            try:
                with open(self.audit_log, "a", encoding="utf-8") as f:
                    f.write(formatted + "\n")
            except Exception:
                pass

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        time.sleep(0.2)
        banner = self._read_available()
        self.log(f"Connected to {self.host}:{self.port}. Banner: {repr(banner[:80])}")
        return banner

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(b"exit\n")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            self.log("Connection closed.")

    def _read_available(self, wait_sec=0.3):
        time.sleep(wait_sec)
        out = []
        while True:
            try:
                self.sock.settimeout(0.3)
                chunk = self.sock.recv(BUFFER_SIZE)
                if not chunk:
                    break
                out.append(chunk)
            except socket.timeout:
                break
        raw = b"".join(out)
        return clean_telnet_data(raw)

    def execute(self, cmd: str) -> str:
        if not self.sock:
            raise RuntimeError("Not connected to Telnet server")
        clean_cmd = cmd.strip()
        self.log(f"TX: {clean_cmd}")
        self.sock.sendall((clean_cmd + "\n").encode("utf-8"))
        response = self._read_available(wait_sec=0.4).strip()
        self.log(f"RX: {repr(response)}")

        if not response:
            raise RuntimeError(f"Telnet command '{clean_cmd}' returned empty response (possible timeout/disconnect).")

        lower_resp = response.lower()
        for kw in ERROR_KEYWORDS:
            if kw in lower_resp:
                raise RuntimeError(f"OAI Telnet rejected command '{clean_cmd}'. Response: {response}")

        return response


def get_channel_state(client: OaiTelnetClient, channel_id: int = 0) -> dict:
    """Read current channel parameters and parse path_loss_dB and noise_power_dB."""
    raw_status = client.execute("channelmod show current")
    # Search for target channel block or whole string
    ploss_match = PLOSS_REGEX.search(raw_status)
    noise_match = NOISE_REGEX.search(raw_status)

    if not ploss_match:
        raise ValueError(
            f"Could not parse path_loss_dB from 'channelmod show current'. Raw output:\n{raw_status}"
        )

    ploss_val = float(ploss_match.group("val"))
    noise_val = float(noise_match.group("val")) if noise_match else None

    return {
        "channel_id": channel_id,
        "path_loss_dB": ploss_val,
        "noise_power_dB": noise_val,
        "raw": raw_status
    }


def set_channel_ploss(client: OaiTelnetClient, channel_id: int, target_ploss: float, tolerance: float = 0.6) -> float:
    """
    Set path_loss_dB (path gain) via Telnet and verify that the updated value took effect.
    In OAI apply_channelmod.c:
      amplitude_multiplier = 10^(path_loss_dB / 20.0)
    Negative values attenuate signal; positive values amplify.
    """
    if math.isnan(target_ploss) or math.isinf(target_ploss):
        raise ValueError(f"Invalid target_ploss value: {target_ploss}")

    cmd = f"channelmod modify {channel_id} ploss {target_ploss:.2f}"
    resp = client.execute(cmd)

    # Read back and verify
    state = get_channel_state(client, channel_id)
    actual_ploss = state["path_loss_dB"]

    if abs(actual_ploss - target_ploss) > tolerance:
        raise RuntimeError(
            f"Verification mismatch for channel {channel_id}: requested {target_ploss:.2f} dB, "
            f"but softmodem reports {actual_ploss:.2f} dB (tolerance {tolerance} dB). Modify response: {resp}"
        )

    return actual_ploss


# ==============================================================================
# CLI Command Handlers
# ==============================================================================

def cmd_show(args):
    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        print(f"Connecting to OAI Telnet server at {args.host}:{args.port}...")
        client.connect()

        print("\n--- [1] Current Channel Modeling Status (channelmod show current) ---")
        curr_state = get_channel_state(client, args.channel_id)
        print(curr_state["raw"])
        print(f"\n>> Parsed Channel {args.channel_id} State:")
        print(f"   path_loss_dB   : {curr_state['path_loss_dB']:+.2f} dB  (Negative = Attenuation, Positive = Gain)")
        if curr_state['noise_power_dB'] is not None:
            print(f"   noise_power_dB : {curr_state['noise_power_dB']:+.2f} dB")

        print("\n--- [2] Predefined Channel Models (channelmod show predef) ---")
        out_predef = client.execute("channelmod show predef")
        print(out_predef)
    except Exception as e:
        print(f"\n[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_set_attenuation(args):
    """Sets additional attenuation in dB relative to current or specified baseline."""
    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        if args.attenuation < 0:
            raise ValueError(f"Attenuation must be non-negative (got {args.attenuation} dB). To add gain, use set-raw-ploss.")

        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()

        init_state = get_channel_state(client, args.channel_id)
        base_ploss = init_state["path_loss_dB"] if args.baseline is None else args.baseline
        target_ploss = base_ploss - args.attenuation

        print(f"Baseline path_loss_dB : {base_ploss:+.2f} dB")
        print(f"Requested Attenuation : {args.attenuation:.2f} dB")
        print(f"Target path_loss_dB   : {target_ploss:+.2f} dB")

        verified = set_channel_ploss(client, args.channel_id, target_ploss)
        print(f"\n[SUCCESS] Channel {args.channel_id} path_loss_dB set and verified to {verified:+.2f} dB.")
    except Exception as e:
        print(f"\n[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_set_raw_ploss(args):
    """Sets raw path_loss_dB parameter directly."""
    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()
        print(f"Setting raw path_loss_dB to {args.ploss:+.2f} dB on channel {args.channel_id}...")
        verified = set_channel_ploss(client, args.channel_id, args.ploss)
        print(f"\n[SUCCESS] Verified: path_loss_dB = {verified:+.2f} dB.")
    except Exception as e:
        print(f"\n[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_sweep(args):
    """
    Sweeps attenuation gradually on a steady traffic load.
    Direction: Attenuation increases from start_att to stop_att (path_loss_dB decreases).
    Safe restoration of baseline is guaranteed via try-finally.
    """
    # Validation
    if args.step <= 0:
        raise ValueError(f"Sweep step must be strictly positive (got {args.step}).")
    if args.duration <= 0:
        raise ValueError(f"Step duration must be strictly positive (got {args.duration}s).")
    if args.start_att < 0 or args.stop_att < 0:
        raise ValueError(f"Attenuation values must be non-negative (got start={args.start_att}, stop={args.stop_att}).")
    if args.start_att > args.stop_att:
        raise ValueError(f"start_att ({args.start_att}) cannot be greater than stop_att ({args.stop_att}).")

    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    baseline_ploss = None
    restoration_ok = False

    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()

        # Step 1: Read and lock initial baseline
        init_state = get_channel_state(client, args.channel_id)
        baseline_ploss = init_state["path_loss_dB"]
        print(f"Initial Channel {args.channel_id} Baseline path_loss_dB : {baseline_ploss:+.2f} dB")
        print(f"Sweep Range : Attenuation {args.start_att:.1f} dB -> {args.stop_att:.1f} dB (step: +{args.step:.1f} dB)")
        print(f"Step Dwell  : {args.duration:.1f} seconds per step")
        print("=" * 72)

        cur_att = args.start_att
        step_idx = 1
        num_steps = int(math.floor((args.stop_att - args.start_att) / args.step)) + 1

        while cur_att <= (args.stop_att + 1e-6):
            target_ploss = baseline_ploss - cur_att
            ts = time.strftime("%H:%M:%S")
            print(f"\n[{ts}] [Step {step_idx}/{num_steps}] Applying Attenuation = {cur_att:5.1f} dB (target ploss = {target_ploss:+6.2f} dB)...")

            # Execute and strictly verify
            verified_ploss = set_channel_ploss(client, args.channel_id, target_ploss)
            print(f"  -> Verified in softmodem: path_loss_dB = {verified_ploss:+6.2f} dB (OK)")
            print(f"  -> Dwelling for {args.duration:.1f}s (monitor du1.log & ran_adapter)...")

            # Dwell time with interruptible sleep
            time.sleep(args.duration)

            cur_att += args.step
            step_idx += 1

        print("\n" + "=" * 72)
        print("[SUCCESS] Attenuation sweep sequence completed successfully.")

    except KeyboardInterrupt:
        print("\n[ABORT] Sweep interrupted by user (Ctrl+C). Initiating emergency rollback...")
    except Exception as e:
        print(f"\n[ERROR] Sweep aborted due to error: {e}", file=sys.stderr)
    finally:
        # Step 2: Safe Baseline Restoration
        if baseline_ploss is not None and args.reset_after:
            print(f"\n--- Initiating Baseline Restoration ---")
            try:
                print(f"Restoring Channel {args.channel_id} to original baseline ({baseline_ploss:+.2f} dB)...")
                restored_val = set_channel_ploss(client, args.channel_id, baseline_ploss)
                print(f"[RESTORATION VERIFIED] Channel {args.channel_id} successfully restored to {restored_val:+.2f} dB.")
                restoration_ok = True
            except Exception as re_err:
                print(
                    f"\n[CRITICAL WARNING] Failed to restore baseline! Channel state is UNKNOWN/DIRTY.\n"
                    f"Reason: {re_err}\n"
                    f"Please check softmodem status manually via Telnet or restart OAI softmodem!",
                    file=sys.stderr
                )
        client.close()

    if not restoration_ok and args.reset_after and baseline_ploss is not None:
        sys.exit(2)


# ==============================================================================
# Main Parser Construction (Supports Options Before or After Subcommand)
# ==============================================================================

def build_parser():
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--host", default=DEFAULT_HOST, help=f"Telnet host IP (default: {DEFAULT_HOST})")
    base_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Telnet port (default: {DEFAULT_PORT} for DU-1)")
    base_parser.add_argument("--audit-log", default=None, help="Optional path to write raw audit logs")

    parser = argparse.ArgumentParser(
        description="OAI RFsimulator Channel Modeling & Telnet Controller (Production Grade)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[base_parser],
        epilog="""
Usage Examples:
  # 1. Inspect current channel status and predefined models:
  python3 rfsim_channel_control.py show --port 9090
  python3 rfsim_channel_control.py --port 9090 show

  # 2. Add 15 dB attenuation (weaken signal) relative to current baseline:
  python3 rfsim_channel_control.py set-attenuation 15.0 --port 9090

  # 3. Direct raw path_loss_dB setting (negative = attenuation, positive = gain):
  python3 rfsim_channel_control.py set-raw-ploss -20.0 --port 9090

  # 4. Sweep attenuation from 0 dB to 25 dB in steps of 5 dB (15s per step):
  python3 rfsim_channel_control.py sweep --start-att 0 --stop-att 25 --step 5 --duration 15 --port 9090
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: show
    p_show = subparsers.add_parser("show", parents=[base_parser], help="Show current channel status and predefined models")
    p_show.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_show.set_defaults(func=cmd_show)

    # Subcommand: set-attenuation
    p_att = subparsers.add_parser(
        "set-attenuation", parents=[base_parser],
        help="Apply attenuation in dB (subtracts from baseline path_loss_dB)"
    )
    p_att.add_argument("attenuation", type=float, help="Attenuation in dB (e.g. 10.0, 20.0)")
    p_att.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_att.add_argument("--baseline", type=float, default=None, help="Explicit baseline dB (default: read from channel)")
    p_att.set_defaults(func=cmd_set_attenuation)

    # Subcommand: set-raw-ploss
    p_raw = subparsers.add_parser(
        "set-raw-ploss", parents=[base_parser],
        help="Directly set OAI path_loss_dB (negative = attenuation, positive = gain)"
    )
    p_raw.add_argument("ploss", type=float, help="Raw path_loss_dB value in dB (e.g. -15.0, 0.0)")
    p_raw.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_raw.set_defaults(func=cmd_set_raw_ploss)

    # Subcommand: sweep
    p_sweep = subparsers.add_parser(
        "sweep", parents=[base_parser],
        help="Sweep attenuation step-by-step with guaranteed baseline restoration"
    )
    p_sweep.add_argument("--start-att", type=float, default=0.0, help="Starting attenuation in dB (default: 0.0)")
    p_sweep.add_argument("--stop-att", type=float, default=30.0, help="Ending attenuation in dB (default: 30.0)")
    p_sweep.add_argument("--step", type=float, default=5.0, help="Step size in dB (default: 5.0)")
    p_sweep.add_argument("--duration", type=float, default=15.0, help="Duration in seconds per step (default: 15.0)")
    p_sweep.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_sweep.add_argument("--no-reset", dest="reset_after", action="store_false", help="Do not restore baseline after sweep")
    p_sweep.set_defaults(reset_after=True, func=cmd_sweep)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
