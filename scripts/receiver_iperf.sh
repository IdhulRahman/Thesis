#!/usr/bin/env bash
# ==============================================================================
# Receiver-Side Throughput & Packet Loss Logger for 5G O-RAN Thesis
# Location on VM-3: /opt/oran/5gc/scripts/receiver_iperf.sh
# Target Container: oai-ext-dn (192.168.70.145)
# ==============================================================================
# Usage:
#   ./receiver_iperf.sh check                               # Check iperf3 version & available JSON streaming options
#   ./receiver_iperf.sh start [RUN_ID] [SESSION_ID] [PORT]  # Start dedicated receiver for run session
#   ./receiver_iperf.sh export [RUN_ID] [SESSION_ID]        # Export & parse completed JSON log
#   ./receiver_iperf.sh status                              # Check running receivers & listening ports
#   ./receiver_iperf.sh stop [PORT]                         # Stop receiver process
# ==============================================================================

ACTION="${1:-check}"
RUN_ID="${2:-PILOT_MANUAL}"
SESSION_ID="${3:-session_1}"
PORT="${4:-5201}"
CONTAINER="oai-ext-dn"

case "$ACTION" in
  check)
    echo "[*] Checking iperf3 version inside $CONTAINER:"
    sudo docker exec "$CONTAINER" iperf3 --version | head -n 3
    echo ""
    echo "[*] Checking --json-stream support:"
    if sudo docker exec "$CONTAINER" iperf3 --help 2>&1 | grep -q -- "--json-stream"; then
      echo "  [+] --json-stream is SUPPORTED (real-time interval JSON streaming available)"
    else
      echo "  [-] --json-stream is not present in this iperf3 build. Using standard --json with --one-off."
    fi
    ;;

  start)
    LOG_FILE="/tmp/receiver_${RUN_ID}_${SESSION_ID}.json"
    echo "[*] Starting dedicated one-off receiver on $CONTAINER for Run: $RUN_ID | Session: $SESSION_ID | Port: $PORT"
    echo "    Output file inside container: $LOG_FILE"

    # Terminate any stale process on this port inside the container
    sudo docker exec "$CONTAINER" pkill -f "iperf3.*${PORT}" 2>/dev/null || true
    sleep 0.2

    # Evaluate support for --json-stream vs standard --json
    if sudo docker exec "$CONTAINER" iperf3 --help 2>&1 | grep -q -- "--json-stream"; then
      STREAM_OPT="--json-stream"
    else
      STREAM_OPT="--json"
    fi

    # Launch dedicated one-off server process bound to target port
    sudo docker exec -d "$CONTAINER" iperf3 -s -p "$PORT" -i 1 --one-off $STREAM_OPT --logfile "$LOG_FILE"
    EXEC_RC=$?
    if [ $EXEC_RC -ne 0 ]; then
      echo "[ERROR] Docker exec command failed with exit code $EXEC_RC"
      exit 1
    fi

    # Verify listener readiness using ss / netstat inside container
    READY=0
    for i in {1..10}; do
      if sudo docker exec "$CONTAINER" ss -lnt "sport = :$PORT" 2>/dev/null | grep -q "$PORT" || \
         sudo docker exec "$CONTAINER" ss -lnt 2>/dev/null | grep -q ":$PORT " || \
         sudo docker exec "$CONTAINER" netstat -lnt 2>/dev/null | grep -q ":$PORT "; then
        READY=1
        break
      fi
      sleep 0.3
    done

    if [ $READY -eq 1 ]; then
      PID=$(sudo docker exec "$CONTAINER" pgrep -f "iperf3.*${PORT}" | head -n 1)
      echo "[SUCCESS] Dedicated receiver iperf3 is actively LISTENING on port $PORT (Container PID: $PID, Session: $SESSION_ID, Mode: $STREAM_OPT)."
    else
      echo "[ERROR] Listener readiness check failed: port $PORT is not in LISTEN state inside $CONTAINER."
      exit 1
    fi
    ;;

  export)
    LOG_FILE="/tmp/receiver_${RUN_ID}_${SESSION_ID}.json"
    HOST_EXPORT_DIR="/opt/oran/5gc/data/raw/${RUN_ID}"
    TARGET_FILE="${HOST_EXPORT_DIR}/receiver_${SESSION_ID}.json"
    SUMMARY_FILE="${HOST_EXPORT_DIR}/receiver_${SESSION_ID}_summary.json"
    mkdir -p "$HOST_EXPORT_DIR"

    echo "[*] Checking and copying receiver JSON log from $CONTAINER:$LOG_FILE"
    if sudo docker exec "$CONTAINER" test -s "$LOG_FILE"; then
      sudo docker cp "${CONTAINER}:${LOG_FILE}" "$TARGET_FILE"
      cp "$TARGET_FILE" "${HOST_EXPORT_DIR}/receiver_goodput.json" 2>/dev/null || true

      if [[ -s "$TARGET_FILE" ]]; then
        # Parse output handling both --json-stream and standard --json
        python3 - "$TARGET_FILE" "$SUMMARY_FILE" << 'EOF'
import json, sys

path = sys.argv[1]
summary_path = sys.argv[2]

try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read().strip()
    if not content:
        print("[ERROR] Receiver file is empty", file=sys.stderr)
        sys.exit(1)

    is_stream = False
    end_data = {}
    try:
        data = json.loads(content)
        end_data = data.get("end", {})
    except json.JSONDecodeError:
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        parsed_lines = []
        for l in lines:
            try:
                parsed_lines.append(json.loads(l))
            except Exception:
                pass
        is_stream = True
        for rec in reversed(parsed_lines):
            if "end" in rec:
                end_data = rec["end"]
                break
            elif "sum" in rec:
                end_data = {"sum": rec["sum"]}
                break
        if not end_data and parsed_lines:
            end_data = parsed_lines[-1]

    sum_rx = end_data.get("sum_received") or end_data.get("sum") or {}
    bytes_rx = sum_rx.get("bytes", 0)
    bps_rx = sum_rx.get("bits_per_second", 0.0)
    mbps_rx = round(bps_rx / 1e6, 3)
    lost_pkts = sum_rx.get("lost_packets", 0)
    total_pkts = sum_rx.get("packets", 0)
    loss_pct = round(sum_rx.get("lost_percent", 0.0), 2)
    jitter_ms = round(sum_rx.get("jitter_ms", 0.0), 3)

    summary = {
        "format": "json_stream" if is_stream else "standard_json",
        "bytes_received": bytes_rx,
        "goodput_mbps": mbps_rx,
        "packets_total": total_pkts,
        "packets_lost": lost_pkts,
        "packet_loss_pct": loss_pct,
        "jitter_ms": jitter_ms
    }
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    print(f"[SUCCESS] Receiver Goodput: {mbps_rx} Mbps | Loss: {loss_pct}% ({lost_pkts}/{total_pkts} pkts) | Jitter: {jitter_ms} ms | Format: {'Stream' if is_stream else 'Single'}")
except Exception as ex:
    print(f"[WARNING] Parsing receiver JSON log: {ex}", file=sys.stderr)
EOF
      else
        echo "[ERROR] Target export file is empty on host."
        exit 1
      fi
    else
      echo "[ERROR] Log file $LOG_FILE inside $CONTAINER is missing or empty. Ensure client traffic has completed."
      exit 1
    fi
    ;;

  status)
    echo "[*] Active iperf3 receivers in $CONTAINER:"
    sudo docker exec "$CONTAINER" pgrep -a iperf3 || echo "  No iperf3 processes running."
    echo "[*] Listening ports in $CONTAINER:"
    sudo docker exec "$CONTAINER" ss -lnt 2>/dev/null || sudo docker exec "$CONTAINER" netstat -lnt 2>/dev/null || true
    ;;

  stop)
    echo "[*] Stopping iperf3 receiver on port $PORT in $CONTAINER..."
    sudo docker exec "$CONTAINER" pkill -f "iperf3.*${PORT}" 2>/dev/null || true
    echo "[DONE] Receiver stopped."
    ;;

  *)
    echo "Usage: $0 {check|start [RUN_ID] [SESSION_ID] [PORT]|export [RUN_ID] [SESSION_ID]|status|stop [PORT]}"
    exit 1
    ;;
esac

