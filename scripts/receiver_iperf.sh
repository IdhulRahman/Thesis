#!/usr/bin/env bash
# ==============================================================================
# Receiver-Side Throughput & Packet Loss Logger for 5G O-RAN Thesis
# Location on VM-3: /opt/oran/5gc/scripts/receiver_iperf.sh
# Target Container: oai-ext-dn (192.168.70.145)
# ==============================================================================
# Usage:
#   ./receiver_iperf.sh check             # Check iperf3 version & available JSON streaming options
#   ./receiver_iperf.sh start [RUN_ID]    # Start dedicated one-off receiver for active run
#   ./receiver_iperf.sh export [RUN_ID]   # Export completed JSON log from oai-ext-dn to host
# ==============================================================================

ACTION="${1:-check}"
RUN_ID="${2:-PILOT_MANUAL}"
CONTAINER="oai-ext-dn"

case "$ACTION" in
  check)
    echo "[*] Checking iperf3 version inside $CONTAINER:"
    sudo docker exec "$CONTAINER" iperf3 --version | head -n 3
    echo ""
    echo "[*] Checking --json-stream support:"
    if sudo docker exec "$CONTAINER" iperf3 --help | grep -q -- "--json-stream"; then
      echo "  [+] --json-stream is SUPPORTED (real-time interval JSON streaming available)"
    else
      echo "  [-] --json-stream is not present in this iperf3 build. Using standard --json with --one-off."
    fi
    ;;

  start)
    LOG_FILE="/tmp/receiver_${RUN_ID}.json"
    echo "[*] Starting dedicated one-off receiver on $CONTAINER for Run: $RUN_ID"
    echo "    Output file inside container: $LOG_FILE"

    # Evaluate support for --json-stream vs standard --json
    if sudo docker exec "$CONTAINER" iperf3 --help | grep -q -- "--json-stream"; then
      STREAM_OPT="--json-stream"
    else
      STREAM_OPT="--json"
    fi

    # Launch dedicated one-off server process bound to port 5201
    sudo docker exec -d "$CONTAINER" iperf3 -s -p 5201 -i 1 --one-off $STREAM_OPT --logfile "$LOG_FILE"
    echo "[+] Receiver server listening on :5201. Will auto-terminate upon client disconnection."
    ;;

  export)
    LOG_FILE="/tmp/receiver_${RUN_ID}.json"
    HOST_EXPORT_DIR="/opt/oran/5gc/data/raw/${RUN_ID}"
    mkdir -p "$HOST_EXPORT_DIR"
    echo "[*] Copying completed receiver JSON log from $CONTAINER:$LOG_FILE to $HOST_EXPORT_DIR/receiver_goodput.json"
    sudo docker cp "${CONTAINER}:${LOG_FILE}" "${HOST_EXPORT_DIR}/receiver_goodput.json"
    if [[ -f "${HOST_EXPORT_DIR}/receiver_goodput.json" ]]; then
      echo "[SUCCESS] Receiver log exported successfully ($(du -h "${HOST_EXPORT_DIR}/receiver_goodput.json" | cut -f1))"
    else
      echo "[ERROR] Log file not found. Ensure the client run completed before exporting."
    fi
    ;;

  *)
    echo "Usage: $0 {check|start [RUN_ID]|export [RUN_ID]}"
    exit 1
    ;;
esac
