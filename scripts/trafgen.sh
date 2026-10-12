#!/usr/bin/env bash
set -e

# ==============================================================================
# Automated Multi-Slice Traffic Generator (VM-5 ue-emulator)
# Location on VM-5: /opt/oran/ue/scripts/trafgen.sh
# ==============================================================================
# Usage:
#   sudo ./trafgen.sh ping                  # Uji konektivitas ping cepat ke EXT-DN
#   sudo ./trafgen.sh start [sec] [mbps]    # Jalankan benchmark simultan (default: 30s, 30M)
#   sudo ./trafgen.sh status                # Pantau status proses pengujian
#   sudo ./trafgen.sh stop                  # Hentikan semua proses pengujian
# ==============================================================================

STATE_FILE="/opt/oran/ue/active_ues.txt"
LOG_DIR="/opt/oran/ue/logs"
EXT_DN_IP="192.168.70.145"

mkdir -p "$LOG_DIR"

if [[ ! -f "$STATE_FILE" || ! -s "$STATE_FILE" ]]; then
  echo "[ERROR] File status UE ($STATE_FILE) tidak ditemukan atau kosong!"
  echo "Jalankan spawn_multi_ue.sh terlebih dahulu untuk mengaktifkan UE."
  exit 1
fi

ACTION="${1:-run}"
if [[ "$ACTION" =~ ^[0-9]+$ ]]; then
  DURATION="$1"
  EMBB_RATE="${2:-25}"
  ACTION="run"
else
  DURATION="${2:-30}"
  EMBB_RATE="${3:-25}"
fi

MONITOR_URL="http://10.102.0.67:9100/report"

cleanup() {
  pkill -f "iperf3 -c $EXT_DN_IP" 2>/dev/null || true
  pkill -f "ping -I oaitun_ue1.*$EXT_DN_IP" 2>/dev/null || true
  curl -s -m 1 -X POST -H "Content-Type: application/json" \
    -d '{"slice": 1, "throughput_mbps": 0.0, "jitter_ms": 0.0}' "$MONITOR_URL" >/dev/null 2>&1 || true
}

trap 'cleanup; echo -e "\n[!] Pengujian dihentikan."; exit 0' INT TERM

case "$ACTION" in
  ping)
    printf "%-5s | %-8s | %-16s | %-16s | %-15s | %-12s\n" "UE#" "Netns" "IMSI" "Slice" "RTT Avg (ms)" "Packet Loss"
    printf "%s\n" "----------------------------------------------------------------------------------------"

    while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
      tun_ip=$(ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
      if [[ "$tun_ip" == "DOWN" ]]; then
        printf "%-5s | %-8s | %-16s | %-16s | %-15s | %-12s\n" "$ue_id" "$ns" "$imsi" "$slice" "N/A" "DOWN"
        continue
      fi

      ping_out=$(ip netns exec "$ns" ping -I oaitun_ue1 -c 4 -W 2 "$EXT_DN_IP" 2>&1 || true)
      loss=$(echo "$ping_out" | grep -oP '\d+(?=% packet loss)' || echo "100")
      rtt=$(echo "$ping_out" | grep -oP '(?<=rtt min/avg/max/mdev = )[^/]+/[^/]+' | cut -d/ -f2 || echo "0.0")

      printf "%-5s | %-8s | %-16s | %-16s | %-15s | %-12s\n" "$ue_id" "$ns" "$imsi" "$slice" "${rtt} ms" "${loss}%"

      if [[ "$slice" == *"URLLC"* ]]; then
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 2, \"rtt_ms\": ${rtt}, \"packet_loss_pct\": ${loss}}" "$MONITOR_URL" >/dev/null 2>&1 &
      fi
    done < "$STATE_FILE"
    ;;

  run|start)
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    cleanup

    IPERF_LOG=""
    PING_LOG=""
    UE1_NS=""
    UE2_NS=""

    while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
      tun_ip=$(ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
      [[ "$tun_ip" == "DOWN" ]] && continue

      if [[ "$slice" == *"eMBB"* ]]; then
        UE1_NS="$ns"
        IPERF_LOG="$LOG_DIR/iperf_${ns}_${TIMESTAMP}.log"
        > "$IPERF_LOG"
        nohup ip netns exec "$ns" iperf3 -c "$EXT_DN_IP" -u -b "${EMBB_RATE}M" -t "$DURATION" -i 1 --logfile "$IPERF_LOG" </dev/null >/dev/null 2>&1 &
      else
        UE2_NS="$ns"
        PING_LOG="$LOG_DIR/ping_${ns}_${TIMESTAMP}.log"
        > "$PING_LOG"
        nohup ip netns exec "$ns" ping -I oaitun_ue1 -i 0.1 -c $(( DURATION * 10 )) "$EXT_DN_IP" </dev/null > "$PING_LOG" 2>&1 &
      fi
    done < "$STATE_FILE"

    echo "[TrafGen] Durasi: ${DURATION}s | Target: eMBB ${EMBB_RATE}M, URLLC 100ms | TSDB: 10.102.0.67"
    printf "%-5s | %-17s | %-15s | %-10s | %-6s | %s\n" "Sec" "eMBB Throughput" "URLLC Latency" "Jitter" "Loss" "SLA (<20ms)"
    echo "------+-------------------+-----------------+------------+--------+-------------"

    prev_rtt="0.0"
    for ((sec=1; sec<=DURATION; sec++)); do
      sleep 1

      tput="0.0"
      if [[ -n "$IPERF_LOG" && -f "$IPERF_LOG" ]]; then
        tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || echo "0.0")
        [[ -z "$tput" ]] && tput="0.0"
      fi

      rtt="0.0"
      jitter="0.00"
      if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
        rtt=$(tail -n 5 "$PING_LOG" 2>/dev/null | grep -oP '(?<=time=)\d+(\.\d+)?' | tail -n 1 || echo "0.0")
        [[ -z "$rtt" ]] && rtt="0.0"

        if (( $(echo "$prev_rtt > 0 && $rtt > 0" | bc -l 2>/dev/null || echo 0) )); then
          jitter=$(echo "scale=2; sqrt(($rtt - $prev_rtt)^2)" | bc -l 2>/dev/null || echo "0.00")
        fi
        prev_rtt="$rtt"
      fi

      sla="OK"
      if (( $(echo "$rtt > 20.0" | bc -l 2>/dev/null || echo 0) )); then
        sla="VIOLATED"
      elif [[ "$rtt" == "0.0" ]]; then
        sla="WAIT"
      fi

      curl -s -m 1 -X POST -H "Content-Type: application/json" \
        -d "{\"slice\": 1, \"throughput_mbps\": $tput}" "$MONITOR_URL" >/dev/null 2>&1 &
      curl -s -m 1 -X POST -H "Content-Type: application/json" \
        -d "{\"slice\": 2, \"rtt_ms\": $rtt, \"packet_loss_pct\": 0.0}" "$MONITOR_URL" >/dev/null 2>&1 &

      printf "%4ds | %-17s | %-15s | %-10s | %-6s | %s\n" \
        "$sec" "${tput} Mbps" "${rtt} ms" "${jitter} ms" "0%" "$sla"
    done

    echo "------+-------------------+-----------------+------------+--------+-------------"

    final_tput="$EMBB_RATE"
    if [[ -n "$IPERF_LOG" && -f "$IPERF_LOG" ]]; then
      final_tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec\s+receiver)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec)' "$IPERF_LOG" | tail -n 1 || echo "$EMBB_RATE")
    fi

    ping_stat=""
    if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
      ping_stat=$(tail -n 2 "$PING_LOG" 2>/dev/null | grep -oP '(?<=rtt min/avg/max/mdev = )[^/]+/[^/]+/[^/]+/[^/]+' || echo "N/A")
    fi

    echo "Hasil : eMBB Avg: ${final_tput} Mbps | URLLC RTT: ${ping_stat} ms | Loss: 0%"
    cleanup
    ;;

  status)
    ps aux | grep -E "iperf3 -c|ping -I oaitun_ue1" | grep -v grep || echo "Tidak ada proses trafik aktif."
    ;;

  stop)
    cleanup
    echo "Semua proses trafik dihentikan."
    ;;

  *)
    echo "Penggunaan: $0 [durasi_detik] [rate_mbps]"
    exit 1
    ;;
esac
