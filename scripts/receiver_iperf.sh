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
      sudo docker exec "$CONTAINER" sh -c "echo $PID > /tmp/receiver_${RUN_ID}_${SESSION_ID}.pid" 2>/dev/null || true
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

    PID_FILE_CONTAINER="/tmp/receiver_${RUN_ID}_${SESSION_ID}.pid"
    REC_PID=""
    if sudo docker exec "$CONTAINER" test -s "$PID_FILE_CONTAINER"; then
      REC_PID=$(sudo docker exec "$CONTAINER" cat "$PID_FILE_CONTAINER" 2>/dev/null | tr -d '\r\n')
    fi

    is_receiver_running() {
      if [ -n "$REC_PID" ] && [[ "$REC_PID" =~ ^[0-9]+$ ]]; then
        sudo docker exec "$CONTAINER" kill -0 "$REC_PID" >/dev/null 2>&1
      else
        sudo docker exec "$CONTAINER" pgrep -f "iperf3.*${PORT}" >/dev/null 2>&1
      fi
    }

    terminate_receiver() {
      if [ -n "$REC_PID" ] && [[ "$REC_PID" =~ ^[0-9]+$ ]]; then
        sudo docker exec "$CONTAINER" kill -INT "$REC_PID" 2>/dev/null || true
      else
        sudo docker exec "$CONTAINER" pkill -INT -f "iperf3.*${PORT}" 2>/dev/null || true
      fi
    }

    # Wait for receiver session to finish naturally instead of immediately sending SIGINT
    WAIT_TIMEOUT=10
    WAIT_COUNT=0
    FORCE_ABORT=0
    while is_receiver_running; do
      if [ "$WAIT_COUNT" -ge "$WAIT_TIMEOUT" ]; then
        echo "[WARNING] Receiver (PID: ${REC_PID:-port $PORT}) still running after ${WAIT_TIMEOUT}s timeout. Sesi belum selesai secara normal; menghentikan paksa..." >&2
        terminate_receiver
        FORCE_ABORT=1
        sleep 1
        break
      fi
      echo "[*] Menunggu receiver (PID: ${REC_PID:-port $PORT}) selesai secara normal (${WAIT_COUNT}/${WAIT_TIMEOUT}s)..."
      sleep 1
      WAIT_COUNT=$((WAIT_COUNT + 1))
    done

    echo "[*] Checking and copying receiver JSON log from $CONTAINER:$LOG_FILE"
    if ! sudo docker exec "$CONTAINER" test -s "$LOG_FILE"; then
      echo "[ERROR] Log file $LOG_FILE inside $CONTAINER is missing or empty. Ensure client traffic has completed." >&2
      exit 1
    fi

    sudo docker cp "${CONTAINER}:${LOG_FILE}" "$TARGET_FILE"
    cp "$TARGET_FILE" "${HOST_EXPORT_DIR}/receiver_goodput.json" 2>/dev/null || true

    if [[ ! -s "$TARGET_FILE" ]]; then
      echo "[ERROR] Target export file $TARGET_FILE is empty on host." >&2
      exit 1
    fi

    # Parse output handling both ESnet --json-stream and standard --json with strict error enforcement
    python3 - "$TARGET_FILE" "$SUMMARY_FILE" "$FORCE_ABORT" << 'EOF'
import json, sys

path = sys.argv[1]
summary_path = sys.argv[2]
force_abort = (len(sys.argv) > 3 and sys.argv[3] == "1")

if force_abort:
    summary = {
        "format": "aborted",
        "session_complete": False,
        "aborted": True,
        "error": "Sesi receiver dihentikan paksa karena timeout"
    }
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    print("[ERROR] Receiver session aborted forcibly before normal completion (session_complete=False)", file=sys.stderr)
    sys.exit(1)

try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read().strip()
    if not content:
        print("[ERROR] Receiver export file is empty", file=sys.stderr)
        sys.exit(1)

    is_stream = False
    end_data = None
    session_complete = False

    # 1. Try parsing as single standard JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            if "end" in data:
                end_data = data["end"]
                session_complete = True
            elif data.get("event") == "end" and "data" in data:
                end_data = data["data"]
                session_complete = True
            elif "intervals" in data and isinstance(data["intervals"], list) and data["intervals"]:
                last_iv = data["intervals"][-1]
                end_data = last_iv.get("sum") or last_iv
                session_complete = False
    except json.JSONDecodeError:
        pass

    # 2. If not single standard JSON, check if it is formatted multi-line JSON or JSON-Stream
    if end_data is None:
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not lines:
            print("[ERROR] No JSON lines found in receiver log", file=sys.stderr)
            sys.exit(1)

        # Distinguish between indented multi-line JSON and single-line-per-event JSON-Stream
        if lines[0] == "{" or not lines[0].endswith("}"):
            if '"start"' in content and '"end"' not in content:
                print("[ERROR] Receiver session incomplete: log file contains initial connection ('start' block) but lacks final 'end' summary event. iperf3 was interrupted or unfinished.", file=sys.stderr)
            else:
                print("[ERROR] Corrupt or unclosed formatted JSON in receiver log", file=sys.stderr)
            sys.exit(1)
        else:
            # Real JSON-stream (one JSON object per line)
            parsed_lines = []
            for idx, l in enumerate(lines, 1):
                try:
                    parsed_lines.append(json.loads(l))
                except Exception as ex:
                    print(f"[ERROR] Corrupt JSON line #{idx} in stream: {ex}", file=sys.stderr)
                    sys.exit(1)
            is_stream = True

            for rec in reversed(parsed_lines):
                if isinstance(rec, dict):
                    if rec.get("event") == "end" and "data" in rec:
                        end_data = rec["data"]
                        session_complete = True
                        break
                    elif "end" in rec:
                        end_data = rec["end"]
                        session_complete = True
                        break

            if end_data is None:
                for rec in reversed(parsed_lines):
                    if isinstance(rec, dict) and rec.get("event") == "interval" and "data" in rec:
                        end_data = rec["data"]
                        session_complete = False
                        break

    if not isinstance(end_data, dict) or not end_data:
        print("[ERROR] No valid end or summary event found in receiver log", file=sys.stderr)
        sys.exit(1)

    sum_rx = end_data.get("sum_received") or end_data.get("sum")
    if not sum_rx and "streams" in end_data and isinstance(end_data["streams"], list) and end_data["streams"]:
        s0 = end_data["streams"][0]
        sum_rx = s0.get("udp") or s0.get("receiver") or s0
    if not sum_rx and "bytes" in end_data:
        sum_rx = end_data

    if not isinstance(sum_rx, dict) or "bytes" not in sum_rx:
        print("[ERROR] Mandatory throughput/byte fields missing from receiver summary", file=sys.stderr)
        sys.exit(1)

    bytes_rx = sum_rx["bytes"]
    bps_rx = sum_rx.get("bits_per_second")
    if bps_rx is None:
        secs = sum_rx.get("seconds", 1.0)
        bps_rx = (bytes_rx * 8.0) / (secs if secs > 0 else 1.0)

    mbps_rx = round(float(bps_rx) / 1e6, 3)
    lost_pkts = sum_rx.get("lost_packets")
    total_pkts = sum_rx.get("packets")
    loss_pct = sum_rx.get("lost_percent")
    jitter_ms = sum_rx.get("jitter_ms")

    summary = {
        "format": "json_stream" if is_stream else "standard_json",
        "session_complete": session_complete,
        "bytes_received": bytes_rx,
        "goodput_mbps": mbps_rx,
        "bits_per_second": bps_rx,
        "packets_total": total_pkts,
        "packets_lost": lost_pkts,
        "packet_loss_pct": loss_pct,
        "receiver_loss_pct": loss_pct,
        "jitter_ms": jitter_ms
    }
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)

    loss_disp = f"{loss_pct}% ({lost_pkts}/{total_pkts} pkts)" if loss_pct is not None else "N/A"
    jitter_disp = f"{jitter_ms} ms" if jitter_ms is not None else "N/A"

    if not session_complete:
        print(f"[ERROR] Receiver session incomplete: log stream contains only partial interval reports without an 'end' summary event (session_complete=False). Goodput: {mbps_rx} Mbps", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] Receiver Goodput: {mbps_rx} Mbps | Loss: {loss_disp} | Jitter: {jitter_disp} | Format: {'Stream' if is_stream else 'Single'} | Session: COMPLETE")
    sys.exit(0)

except Exception as ex:
    print(f"[ERROR] Failed to parse receiver JSON log: {ex}", file=sys.stderr)
    sys.exit(1)
EOF

    PARSE_RC=$?
    if [ $PARSE_RC -ne 0 ]; then
      echo "[ERROR] Receiver log export failed with error code $PARSE_RC" >&2
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

