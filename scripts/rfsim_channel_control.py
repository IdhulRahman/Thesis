#!/usr/bin/env python3
"""
OAI RFsimulator Channel Modeling & Telnet Controller
Location on VM-4: /opt/oran/ran/scripts/rfsim_channel_control.py (or /opt/oran/monitoring/scripts)

Interacts directly with OAI softmodem telnet server (--telnetsrv) to dynamically
inspect and manipulate RF channel parameters (path loss, noise, fading) for
Uplink (Cell-1 DU-1) and Downlink in real time without restarting processes.

Standard Library only: Zero external Python dependencies.
"""

import argparse
import socket
import sys
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9090  # DU-1 Cell-1 Telnet port (9091 for DU-2)
BUFFER_SIZE = 4096
PROMPT_MARKERS = [b"softmodem", b">", b"#"]


def clean_telnet_data(data: bytes) -> str:
    """Filter out Telnet IAC (Interpret As Command) escape sequences."""
    clean = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xFF:  # IAC
            # Skip IAC command (2 or 3 bytes)
            if i + 1 < len(data) and data[i + 1] in (0xFB, 0xFC, 0xFD, 0xFE):
                i += 3
            else:
                i += 2
        else:
            clean.append(data[i])
            i += 1
    return clean.decode("utf-8", errors="replace")


class OaiTelnetClient:
    """Telnet client tailored for OAI softmodem telnetsrv."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        # Consume initial greeting banner
        time.sleep(0.2)
        initial = self._read_available()
        return initial

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(b"exit\n")
            except Exception:
                pass
            self.sock.close()
            self.sock = None

    def _read_available(self, wait_sec=0.3):
        time.sleep(wait_sec)
        out = []
        while True:
            try:
                self.sock.settimeout(0.4)
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
        full_cmd = (cmd.strip() + "\n").encode("utf-8")
        self.sock.sendall(full_cmd)
        response = self._read_available(wait_sec=0.5)
        return response.strip()


def cmd_show(args):
    client = OaiTelnetClient(args.host, args.port)
    try:
        print(f"Connecting to OAI Telnet server at {args.host}:{args.port}...")
        client.connect()
        print("\n--- [1] Current Channel Modeling Status ---")
        out_curr = client.execute("channelmod show current")
        print(out_curr if out_curr else "(No output from 'channelmod show current')")

        print("\n--- [2] Available Channel Models ---")
        out_models = client.execute("channelmod show models")
        print(out_models if out_models else "(No output from 'channelmod show models')")
    except Exception as e:
        print(f"Error communicating with Telnet server: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_set_ploss(args):
    client = OaiTelnetClient(args.host, args.port)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()
        cmd = f"channelmod modify {args.channel_id} ploss {args.ploss}"
        print(f"Executing: {cmd}")
        res = client.execute(cmd)
        print(res)
        print("\nVerifying updated channel status:")
        print(client.execute("channelmod show current"))
    except Exception as e:
        print(f"Error setting path loss: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_set_noise(args):
    client = OaiTelnetClient(args.host, args.port)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()
        cmd = f"channelmod modify {args.channel_id} noise_power_dB {args.noise_db}"
        print(f"Executing: {cmd}")
        res = client.execute(cmd)
        print(res)
        print("\nVerifying updated channel status:")
        print(client.execute("channelmod show current"))
    except Exception as e:
        print(f"Error setting noise power: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def cmd_sweep(args):
    client = OaiTelnetClient(args.host, args.port)
    try:
        print(f"Connecting to OAI Telnet at {args.host}:{args.port}...")
        client.connect()
        print(f"Starting Attenuation Sweep: channel={args.channel_id}, start={args.start}dB, stop={args.stop}dB, step={args.step}dB, step_duration={args.duration}s")
        print("=" * 70)

        cur = args.start
        while cur <= args.stop:
            print(f"\n[{time.strftime('%H:%M:%S')}] Applying ploss = {cur} dB on channel {args.channel_id}...")
            cmd = f"channelmod modify {args.channel_id} ploss {cur}"
            res = client.execute(cmd)
            print(f"  Response: {res.splitlines()[-1] if res.splitlines() else 'OK'}")
            time.sleep(args.duration)
            cur += args.step

        if args.reset_after:
            print(f"\nResetting ploss to 0 dB...")
            client.execute(f"channelmod modify {args.channel_id} ploss 0")
            print("Channel reset to 0 dB.")

        print("\nSweep completed.")
    except KeyboardInterrupt:
        print("\nSweep aborted by user.")
        if args.reset_after:
            try:
                client.execute(f"channelmod modify {args.channel_id} ploss 0")
                print("Reset ploss to 0 dB on abort.")
            except Exception:
                pass
    except Exception as e:
        print(f"Error during sweep: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description="OAI RFsimulator Channel Modeling Telnet Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 rfsim_channel_control.py show --port 9090
  python3 rfsim_channel_control.py set-ploss 25 --port 9090 --channel-id 0
  python3 rfsim_channel_control.py sweep --start 0 --stop 30 --step 5 --duration 10 --port 9090
        """
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Telnet host IP (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Telnet port (default: {DEFAULT_PORT} for DU-1, 9091 for DU-2)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: show
    p_show = subparsers.add_parser("show", help="Show current channel modeling status and available models")
    p_show.set_defaults(func=cmd_show)

    # Subcommand: set-ploss
    p_ploss = subparsers.add_parser("set-ploss", help="Set path loss in dB on target channel")
    p_ploss.add_argument("ploss", type=float, help="Path loss value in dB (e.g. 15, 25, 35)")
    p_ploss.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_ploss.set_defaults(func=cmd_set_ploss)

    # Subcommand: set-noise
    p_noise = subparsers.add_parser("set-noise", help="Set noise power in dB on target channel")
    p_noise.add_argument("noise_db", type=float, help="Noise power in dB (e.g. -10, 0, 10)")
    p_noise.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_noise.set_defaults(func=cmd_set_noise)

    # Subcommand: sweep
    p_sweep = subparsers.add_parser("sweep", help="Sweep attenuation step-by-step for empirical calibration")
    p_sweep.add_argument("--start", type=float, default=0.0, help="Starting path loss in dB (default: 0)")
    p_sweep.add_argument("--stop", type=float, default=30.0, help="Ending path loss in dB (default: 30)")
    p_sweep.add_argument("--step", type=float, default=5.0, help="Step size in dB (default: 5)")
    p_sweep.add_argument("--duration", type=float, default=10.0, help="Duration in seconds per step (default: 10)")
    p_sweep.add_argument("--channel-id", type=int, default=0, help="Channel index (default: 0)")
    p_sweep.add_argument("--no-reset", dest="reset_after", action="store_false", help="Do not reset to 0 dB after sweep")
    p_sweep.set_defaults(reset_after=True, func=cmd_sweep)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
