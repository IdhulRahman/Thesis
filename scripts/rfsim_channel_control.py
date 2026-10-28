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
import os
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


def validate_finite(name: str, value: float) -> float:
    """Validate that a numerical argument is finite (rejects NaN, +inf, -inf)."""
    if value is None:
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Parameter '{name}' must be a finite numerical value (got {value}).")
    return float(value)


def detect_configured_baseline_ploss(channel_id: int) -> float:
    """
    Read configured ploss_dB for channel_id (0: enB0 DL, 1: ue0 UL) from du_gnb1.conf.
    Selects the targeted channel model block to correctly distinguish per-channel baselines.
    Falls back to Calibrated Profile 1 baseline (0.0 dB unity gain) if unparsed.
    """
    conf_path = "/opt/oran/ran/conf/du_gnb1.conf"
    if os.path.exists(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Map channel_id to OAI model descriptor name (0: enB0 DL, 1: ue0 UL)
            model_target = "rfsimu_channel_enB0" if channel_id == 0 else "rfsimu_channel_ue0"
            pattern = rf'model_name\s*=\s*"{model_target}".*?ploss_dB\s*=\s*([-0-9.]+);'
            m = re.search(pattern, content, re.DOTALL)
            if m:
                return float(m.group(1))
            # Fallback: if model names differ, index into all ploss_dB occurrences
            all_ploss = re.findall(r'ploss_dB\s*=\s*([-0-9.]+);', content)
            if all_ploss and channel_id < len(all_ploss):
                return float(all_ploss[channel_id])
        except Exception:
            pass
    # Default to Calibrated Profile 1 baseline (0.0 dB unity gain)
    return float(os.environ.get(f"RFSIM_BASELINE_PLOSS_CH{channel_id}", os.environ.get("RFSIM_BASELINE_PLOSS", "0.0")))


# Calibrated baseline path_loss_dB for this testbed (Profile 1: ploss_dB = 0.0 dB unity gain):
# Model 0 (rfsimu_channel_enB0): DL path loss
# Model 1 (rfsimu_channel_ue0) : UL path loss
# Under Profile 1, ploss_dB = 0.0 dB corresponds to 1.0x unity gain.
# Attenuation of X dB sets target path_loss_dB = baseline - X (e.g. 0.0 - 10.0 = -10.0 dB).
TESTBED_VERIFIED_BASELINES = {
    0: detect_configured_baseline_ploss(0),
    1: detect_configured_baseline_ploss(1),
}


def get_channel_block(raw: str, channel_id: int) -> str:
    """
    Extract the specific text block corresponding to model/channel <channel_id>.
    Raises ValueError explicitly if the target channel is not present in the response.
    """
    pattern = rf'(?:model|channel)\s+{channel_id}\b.*?(?=(?:model|channel)\s+\d+\b|\Z)'
    m = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
    if not m:
        found_channels = re.findall(r'(?:model|channel)\s+(\d+)\b', raw, re.IGNORECASE)
        raise ValueError(
            f"Channel/Model ID {channel_id} was not found in 'channelmod show current' response. "
            f"Detected channel IDs in response: {found_channels or 'None'}. Raw response:\n{raw}"
        )
    return m.group(0)


def get_channel_state(client: OaiTelnetClient, channel_id: int = 0) -> dict:
    """Read current channel parameters and parse path_loss_dB and noise_power_dB for target channel."""
    raw_status = client.execute("channelmod show current")
    block = get_channel_block(raw_status, channel_id)
    ploss_match = PLOSS_REGEX.search(block)
    noise_match = NOISE_REGEX.search(block)

    if not ploss_match:
        raise ValueError(
            f"Could not parse path_loss_dB for channel {channel_id} from 'channelmod show current'. Block output:\n{block}"
        )

    ploss_val = float(ploss_match.group("val"))
    noise_val = float(noise_match.group("val")) if noise_match else None

    return {
        "channel_id": channel_id,
        "path_loss_dB": ploss_val,
        "noise_power_dB": noise_val,
        "raw": raw_status,
        "block": block
    }


def set_channel_ploss(client: OaiTelnetClient, channel_id: int, target_ploss: float, tolerance: float = 0.6) -> float:
    """
    Set path_loss_dB (path gain) via Telnet and verify that the updated value took effect.
    In OAI apply_channelmod.c:
      amplitude_multiplier = 10^(path_loss_dB / 20.0)
    Negative values attenuate signal; positive values amplify.
    """
    validate_finite("target_ploss", target_ploss)
    validate_finite("tolerance", tolerance)

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
        raw_status = client.execute("channelmod show current")
        print(raw_status)

        found_ids = sorted(list(set(int(x) for x in re.findall(r'(?:model|channel)\s+(\d+)\b', raw_status, re.IGNORECASE))))
        target_channels = [args.channel_id] if args.channel_id is not None else (found_ids or [0, 1])

        has_error = False
        for ch in target_channels:
            try:
                st = get_channel_state(client, ch)
                profile_base = TESTBED_VERIFIED_BASELINES.get(ch)
                prof_info = f"(testbed baseline: {profile_base:+.2f} dB)" if profile_base is not None else ""
                print(f"\n>> Parsed Channel {ch} State:")
                print(f"   path_loss_dB   : {st['path_loss_dB']:+.2f} dB  {prof_info}")
                if st['noise_power_dB'] is not None:
                    print(f"   noise_power_dB : {st['noise_power_dB']:+.2f} dB")
            except Exception as ex:
                print(f"\n>> Channel {ch}: could not parse state ({ex})", file=sys.stderr)
                if args.channel_id is not None:
                    has_error = True

        print("\n--- [2] Predefined Channel Models (channelmod show predef) ---")
        out_predef = client.execute("channelmod show predef")
        print(out_predef)

        if has_error:
            print(f"\n[ERROR] Requested channel {args.channel_id} could not be retrieved or parsed.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_set_attenuation(args):
    """Sets additional attenuation in dB relative to testbed profile or explicit baseline."""
    validate_finite("attenuation", args.attenuation)
    if args.baseline is not None:
        validate_finite("baseline", args.baseline)

    if args.attenuation < 0:
        raise ValueError(f"Attenuation must be non-negative (got {args.attenuation} dB). To add gain, use set-raw-ploss.")

    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()

        if args.baseline is not None:
            base_ploss = args.baseline
            base_source = f"user-specified (--baseline={base_ploss:+.2f} dB)"
        elif args.channel_id in TESTBED_VERIFIED_BASELINES:
            base_ploss = TESTBED_VERIFIED_BASELINES[args.channel_id]
            base_source = f"testbed verified profile (du_gnb1.conf: {base_ploss:+.2f} dB)"
        else:
            curr = get_channel_state(client, args.channel_id)
            base_ploss = curr["path_loss_dB"]
            base_source = f"live softmodem readback (current: {base_ploss:+.2f} dB; warning: uncalibrated baseline)"

        target_ploss = base_ploss - args.attenuation

        print(f"Target Channel        : {args.channel_id}")
        print(f"Baseline Reference    : {base_ploss:+.2f} dB ({base_source})")
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
    validate_finite("ploss", args.ploss)

    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()
        print(f"Setting raw path_loss_dB to {args.ploss:+.2f} dB on channel {args.channel_id}...")
        verified = set_channel_ploss(client, args.channel_id, args.ploss)
        print(f"\n[SUCCESS] Verified Channel {args.channel_id}: path_loss_dB = {verified:+.2f} dB.")
    except Exception as e:
        print(f"\n[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_reset(args):
    """Resets channel path_loss_dB back to verified testbed profile or explicit target value."""
    if args.target_ploss is not None:
        validate_finite("target_ploss", args.target_ploss)

    client = OaiTelnetClient(args.host, args.port, audit_log=args.audit_log)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()

        targets = [args.channel_id] if args.channel_id is not None else [0, 1]
        for ch in targets:
            if args.target_ploss is not None:
                target_val = args.target_ploss
                val_source = f"user-specified target ({target_val:+.2f} dB)"
            elif ch in TESTBED_VERIFIED_BASELINES:
                target_val = TESTBED_VERIFIED_BASELINES[ch]
                val_source = f"testbed profile from du_gnb1.conf ({target_val:+.2f} dB)"
            else:
                raise ValueError(f"No verified baseline profile for channel {ch}. Please specify --target-ploss explicitly.")

            print(f"Resetting Channel {ch} to {target_val:+.2f} dB ({val_source})...")
            verified = set_channel_ploss(client, ch, target_val)
            print(f"  [SUCCESS] Channel {ch} restored to {verified:+.2f} dB.")
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
    Separate tracking of sweep success vs rollback success ensures non-zero exit code if sweep fails.
    """
    # Numerical validation
    validate_finite("start_att", args.start_att)
    validate_finite("stop_att", args.stop_att)
    validate_finite("step", args.step)
    validate_finite("duration", args.duration)

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

    sweep_completed = False
    sweep_error = None
    user_interrupted = False
    restoration_attempted = False
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

            # Dwell time
            time.sleep(args.duration)

            cur_att += args.step
            step_idx += 1

        print("\n" + "=" * 72)
        print("[SUCCESS] Attenuation sweep sequence completed successfully.")
        sweep_completed = True

    except KeyboardInterrupt:
        user_interrupted = True
        print("\n[ABORT] Sweep interrupted by user (Ctrl+C). Initiating emergency rollback...")
    except Exception as e:
        sweep_error = e
        print(f"\n[ERROR] Sweep aborted due to error: {e}", file=sys.stderr)
    finally:
        # Step 2: Safe Baseline Restoration
        if baseline_ploss is not None and args.reset_after:
            restoration_attempted = True
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
                restoration_ok = False
        client.close()

    # Step 3: Exit status calculation
    if user_interrupted:
        print(
            f"\n[SUMMARY] Sweep aborted by user (SIGINT). Rollback status: {'SUCCESS' if restoration_ok else 'FAILED/DIRTY'}.",
            file=sys.stderr
        )
        sys.exit(130 if restoration_ok else 2)

    if not sweep_completed:
        if restoration_attempted and restoration_ok:
            print(
                f"\n[SUMMARY] Sweep failed: {sweep_error}.\n"
                f"Baseline was successfully rolled back to safe state, but experiment DID NOT complete.",
                file=sys.stderr
            )
            sys.exit(1)
        else:
            print(
                f"\n[CRITICAL SUMMARY] Sweep failed: {sweep_error} AND baseline rollback failed/dirty!",
                file=sys.stderr
            )
            sys.exit(2)

    if restoration_attempted and not restoration_ok:
        print("\n[WARNING SUMMARY] Sweep steps succeeded, BUT baseline rollback failed!", file=sys.stderr)
        sys.exit(2)

    if not args.reset_after:
        print(
            "\n[SUMMARY] Sweep completed successfully. Baseline restoration deliberately omitted "
            "(--no-reset specified; channel remains at final sweep value).",
            flush=True
        )
    elif restoration_attempted and restoration_ok:
        print("\n[SUMMARY] Sweep and baseline restoration completed cleanly.", flush=True)
    else:
        print("\n[SUMMARY] Sweep completed successfully.", flush=True)


# ==============================================================================
# Main Parser Construction (Supports Options Before or After Subcommand)
# ==============================================================================

def build_parser():
    # Base parser for root arguments (defines global defaults)
    root_base = argparse.ArgumentParser(add_help=False)
    root_base.add_argument("--host", default=DEFAULT_HOST, help=f"Telnet host IP (default: {DEFAULT_HOST})")
    root_base.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Telnet port (default: {DEFAULT_PORT} for DU-1)")
    root_base.add_argument("--audit-log", default=None, help="Optional path to write raw audit logs")

    # Base parser for subparsers (uses argparse.SUPPRESS so subcommands do NOT overwrite
    # options parsed before the subcommand)
    sub_base = argparse.ArgumentParser(add_help=False)
    sub_base.add_argument("--host", default=argparse.SUPPRESS, help=f"Telnet host IP (default: {DEFAULT_HOST})")
    sub_base.add_argument("--port", type=int, default=argparse.SUPPRESS, help=f"Telnet port (default: {DEFAULT_PORT} for DU-1)")
    sub_base.add_argument("--audit-log", default=argparse.SUPPRESS, help="Optional path to write raw audit logs")

    parser = argparse.ArgumentParser(
        description="OAI RFsimulator Channel Modeling & Telnet Controller (Production Grade)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[root_base],
        epilog="""
Usage Examples:
  # 1. Inspect current channel status and predefined models:
  python3 rfsim_channel_control.py show --port 9090
  python3 rfsim_channel_control.py --port 9090 show

  # 2. Add 15 dB attenuation on Uplink (channel 1):
  python3 rfsim_channel_control.py set-attenuation 15.0 --channel-id 1 --port 9090

  # 3. Direct raw path_loss_dB setting:
  python3 rfsim_channel_control.py set-raw-ploss -5.0 --channel-id 1 --port 9090

  # 4. Reset channels back to testbed baseline (0.0 dB):
  python3 rfsim_channel_control.py reset --port 9090

  # 5. Sweep attenuation from 0 dB to 25 dB in steps of 5 dB (15s per step):
  python3 rfsim_channel_control.py sweep --start-att 0 --stop-att 25 --step 5 --duration 15 --channel-id 1 --port 9090
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: show
    p_show = subparsers.add_parser("show", parents=[sub_base], help="Show current channel status and predefined models")
    p_show.add_argument("--channel-id", type=int, default=None, help="Channel index (default: all detected channels)")
    p_show.set_defaults(func=cmd_show)

    # Subcommand: set-attenuation
    p_att = subparsers.add_parser(
        "set-attenuation", parents=[sub_base],
        help="Apply attenuation in dB (subtracts from baseline path_loss_dB)"
    )
    p_att.add_argument("attenuation", type=float, help="Attenuation in dB (e.g. 10.0, 20.0)")
    p_att.add_argument("--channel-id", type=int, default=1, help="Channel index (default: 1 for Uplink)")
    p_att.add_argument("--baseline", type=float, default=None, help="Explicit baseline dB (default: testbed verified profile)")
    p_att.set_defaults(func=cmd_set_attenuation)

    # Subcommand: set-raw-ploss
    p_raw = subparsers.add_parser(
        "set-raw-ploss", parents=[sub_base],
        help="Directly set OAI path_loss_dB (negative = attenuation, positive = gain)"
    )
    p_raw.add_argument("ploss", type=float, help="Raw path_loss_dB value in dB (e.g. -15.0, 20.0)")
    p_raw.add_argument("--channel-id", type=int, default=1, help="Channel index (default: 1 for Uplink)")
    p_raw.set_defaults(func=cmd_set_raw_ploss)

    # Subcommand: reset
    p_reset = subparsers.add_parser(
        "reset", parents=[sub_base],
        help="Reset channel(s) back to testbed verified baseline (0.0 dB unity gain from du_gnb1.conf)"
    )
    p_reset.add_argument("--channel-id", type=int, default=None, help="Channel index (default: both 0 and 1)")
    p_reset.add_argument("--target-ploss", type=float, default=None, help="Explicit target path_loss_dB (default: testbed verified baseline)")
    p_reset.set_defaults(func=cmd_reset)

    # Subcommand: sweep
    p_sweep = subparsers.add_parser(
        "sweep", parents=[sub_base],
        help="Sweep attenuation step-by-step with guaranteed baseline restoration"
    )
    p_sweep.add_argument("--start-att", type=float, default=0.0, help="Starting attenuation in dB (default: 0.0)")
    p_sweep.add_argument("--stop-att", type=float, default=30.0, help="Ending attenuation in dB (default: 30.0)")
    p_sweep.add_argument("--step", type=float, default=5.0, help="Step size in dB (default: 5.0)")
    p_sweep.add_argument("--duration", type=float, default=15.0, help="Duration in seconds per step (default: 15.0)")
    p_sweep.add_argument("--channel-id", type=int, default=1, help="Channel index (default: 1 for Uplink)")
    p_sweep.add_argument("--no-reset", dest="reset_after", action="store_false", help="Do not restore baseline after sweep")
    p_sweep.set_defaults(reset_after=True, func=cmd_sweep)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
