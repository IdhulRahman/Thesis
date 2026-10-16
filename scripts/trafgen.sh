#!/usr/bin/env bash

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
      else
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 1, \"rtt_ms\": ${rtt}, \"packet_loss_pct\": ${loss}}" "$MONITOR_URL" >/dev/null 2>&1 &
      fi
    done < "$STATE_FILE"
    ;;

  run|start)
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    cleanup

    IPERF_LOG=""
    UE1_PING_LOG=""
    PING_LOG=""
    UE1_NS=""
    UE2_NS=""

    while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
      tun_ip=$(ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
      [[ "$tun_ip" == "DOWN" ]] && continue

      if [[ "$slice" == *"eMBB"* ]]; then
        UE1_NS="$ns"
        IPERF_LOG="$LOG_DIR/iperf_${ns}_${TIMESTAMP}.log"
        UE1_PING_LOG="$LOG_DIR/ping_${ns}_${TIMESTAMP}.log"
        > "$IPERF_LOG"
        > "$UE1_PING_LOG"
        nohup ip netns exec "$ns" iperf3 -c "$EXT_DN_IP" -u -b "${EMBB_RATE}M" -t "$DURATION" -i 1 --logfile "$IPERF_LOG" </dev/null >/dev/null 2>&1 &
        nohup ip netns exec "$ns" ping -I oaitun_ue1 -i 0.2 -c $(( DURATION * 5 )) "$EXT_DN_IP" </dev/null > "$UE1_PING_LOG" 2>&1 &
      else
        UE2_NS="$ns"
        PING_LOG="$LOG_DIR/ping_${ns}_${TIMESTAMP}.log"
        > "$PING_LOG"
        nohup ip netns exec "$ns" ping -I oaitun_ue1 -i 0.1 -c $(( DURATION * 10 )) "$EXT_DN_IP" </dev/null > "$PING_LOG" 2>&1 &
      fi
    done < "$STATE_FILE"

    echo "[TrafGen] Durasi: ${DURATION}s | Target: eMBB ${EMBB_RATE}M, URLLC 100ms | TSDB: 10.102.0.67"
    printf "%-5s | %-12s | %-11s | %-10s | %-12s | %-11s | %-7s | %s\n" \
      "Sec" "eMBB Tput" "eMBB RTT" "eMBB Loss" "URLLC RTT" "URLLC Jitt" "Loss %" "SLA (<20ms)"
    echo "------+--------------+-------------+------------+--------------+-------------+---------+-------------"

    prev_rtt="0.0"
    prev_eval_seq=0
    last_rx_seq=0
    prev_ue1_rtt="0.0"
    prev_ue1_eval_seq=0
    last_ue1_rx_seq=0
    T_START=$(date +%s)
    last_rx_ts=$T_START
    last_ue1_rx_ts=$T_START

    for ((sec=1; sec<=DURATION; sec++)); do
      sleep 1

      tput="0.0"
      if [[ -n "$IPERF_LOG" && -f "$IPERF_LOG" ]]; then
        tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || echo "0.0")
        [[ -z "$tput" ]] && tput="0.0"
      fi

      ue1_rtt="NaN"
      ue1_loss_pct="NaN"
      ue1_measurement_age=0

      if [[ -n "$UE1_PING_LOG" && -f "$UE1_PING_LOG" ]]; then
        now_ts=$(date +%s)
        ue1_elapsed=$(( now_ts - T_START ))
        (( ue1_elapsed < 1 )) && ue1_elapsed=sec
        # Since UE-1 runs ping with -i 0.2 (5 probes/sec), target seq = elapsed * 5 - 1
        target_ue1_seq=$(( ue1_elapsed * 5 - 1 ))
        (( target_ue1_seq < 1 )) && target_ue1_seq=1
        expected_ue1_probes=$(( target_ue1_seq - prev_ue1_eval_seq ))

        rx_ue1_probes=0
        window_ue1_rtt=""
        window_ue1_max_seq=0

        while read -r seq rtt_val; do
          if [[ -n "$seq" && "$seq" =~ ^[0-9]+$ ]]; then
            if (( seq > prev_ue1_eval_seq && seq <= target_ue1_seq )); then
              rx_ue1_probes=$(( rx_ue1_probes + 1 ))
              if (( seq > window_ue1_max_seq )); then
                window_ue1_max_seq=$seq
                window_ue1_rtt="$rtt_val"
              fi
            fi
          fi
        done < <(tail -n 60 "$UE1_PING_LOG" 2>/dev/null | awk '/bytes from.*time=/ {
          s=0; r=0;
          for(i=1;i<=NF;i++) {
            if($i ~ /^icmp_seq=/) { split($i, a, "="); s=a[2]+0 }
            if($i ~ /^time=/) { split($i, b, "="); r=b[2] }
          }
          if(s > 0) print s, r
        }' | sort -k1,1n -u)

        if (( rx_ue1_probes > 0 )); then
          ue1_rtt="$window_ue1_rtt"
          last_ue1_rx_seq=$window_ue1_max_seq
          last_ue1_rx_ts=$now_ts
          ue1_measurement_age=0

          if (( expected_ue1_probes > 0 )); then
            ue1_loss_pct=$(echo "scale=1; ($expected_ue1_probes - $rx_ue1_probes) * 100.0 / $expected_ue1_probes" | bc -l 2>/dev/null || echo "0.0")
            if (( $(echo "$ue1_loss_pct < 0" | bc -l 2>/dev/null || echo 0) )); then
              ue1_loss_pct="0.0"
            fi
          else
            ue1_loss_pct="0.0"
          fi
          prev_ue1_rtt="$ue1_rtt"
        else
          # No new reply in this window: mark RTT as NaN and record elapsed age
          ue1_rtt="NaN"
          ue1_measurement_age=$(( now_ts - last_ue1_rx_ts ))
          ue1_loss_pct="100.0"
          prev_ue1_rtt="0.0"
        fi
        prev_ue1_eval_seq=$target_ue1_seq
      fi

      rtt="NaN"
      jitter="0.00"
      loss_pct="NaN"
      measurement_age=0

      if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
        now_ts=$(date +%s)
        elapsed_sec=$(( now_ts - T_START ))
        (( elapsed_sec < 1 )) && elapsed_sec=sec
        target_seq=$(( elapsed_sec * 10 - 2 ))
        if (( target_seq < 1 )); then
          target_seq=1
        fi
        expected_probes=$(( target_seq - prev_eval_seq ))

        rx_probes=0
        window_rtt=""
        window_max_seq=0

        # Strict filter: ONLY count successful echo replies containing 'bytes from' and 'time='.
        # Ignores ICMP error messages (e.g. Destination Host Unreachable) and deduplicates sequence numbers.
        while read -r seq rtt_val; do
          if [[ -n "$seq" && "$seq" =~ ^[0-9]+$ ]]; then
            if (( seq > prev_eval_seq && seq <= target_seq )); then
              rx_probes=$(( rx_probes + 1 ))
              if (( seq > window_max_seq )); then
                window_max_seq=$seq
                window_rtt="$rtt_val"
              fi
            fi
          fi
        done < <(tail -n 60 "$PING_LOG" 2>/dev/null | awk '/bytes from.*time=/ {
          s=0; r=0;
          for(i=1;i<=NF;i++) {
            if($i ~ /^icmp_seq=/) { split($i, a, "="); s=a[2]+0 }
            if($i ~ /^time=/) { split($i, b, "="); r=b[2] }
          }
          if(s > 0) print s, r
        }' | sort -k1,1n -u)

        if (( rx_probes > 0 )); then
          rtt="$window_rtt"
          last_rx_seq=$window_max_seq
          last_rx_ts=$now_ts
          measurement_age=0

          if (( expected_probes > 0 )); then
            loss_pct=$(echo "scale=1; ($expected_probes - $rx_probes) * 100.0 / $expected_probes" | bc -l 2>/dev/null || echo "0.0")
            if (( $(echo "$loss_pct < 0" | bc -l 2>/dev/null || echo 0) )); then
              loss_pct="0.0"
            fi
          else
            loss_pct="0.0"
          fi

          if (( $(echo "$prev_rtt > 0 && $rtt > 0" | bc -l 2>/dev/null || echo 0) )); then
            jitter=$(echo "scale=2; sqrt(($rtt - $prev_rtt)^2)" | bc -l 2>/dev/null || echo "0.00")
          fi
          prev_rtt="$rtt"
        else
          # No new reply received in this window: mark RTT as NaN and record elapsed measurement age
          rtt="NaN"
          measurement_age=$(( now_ts - last_rx_ts ))
          loss_pct="100.0"
          prev_rtt="0.0"
        fi
        prev_eval_seq=$target_seq
      fi

      sla="OK"
      if [[ "$rtt" == "NaN" ]]; then
        sla="NO_REPLY"
      elif (( $(echo "$rtt > 20.0" | bc -l 2>/dev/null || echo 0) )); then
        sla="VIOLATED"
      fi

      ue1_loss_json="null"
      [[ "$ue1_loss_pct" != "NaN" ]] && ue1_loss_json="$ue1_loss_pct"

      ue2_loss_json="null"
      [[ "$loss_pct" != "NaN" ]] && ue2_loss_json="$loss_pct"

      if [[ "$ue1_rtt" != "NaN" && -n "$ue1_rtt" ]]; then
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 1, \"throughput_mbps\": $tput, \"rtt_ms\": $ue1_rtt, \"packet_loss_pct\": $ue1_loss_json, \"last_seq\": $last_ue1_rx_seq, \"reply_age_sec\": $ue1_measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_ue1_rtt="${ue1_rtt} ms"
      else
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 1, \"throughput_mbps\": $tput, \"rtt_ms\": null, \"packet_loss_pct\": $ue1_loss_json, \"last_seq\": $last_ue1_rx_seq, \"reply_age_sec\": $ue1_measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_ue1_rtt="NO_REPLY"
      fi

      if [[ "$rtt" != "NaN" ]]; then
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 2, \"rtt_ms\": $rtt, \"packet_loss_pct\": $ue2_loss_json, \"last_seq\": $last_rx_seq, \"reply_age_sec\": $measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_rtt="${rtt} ms"
      else
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 2, \"rtt_ms\": null, \"packet_loss_pct\": $ue2_loss_json, \"last_seq\": $last_rx_seq, \"reply_age_sec\": $measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_rtt="NO_NEW_REPLY"
      fi

      disp_ue1_loss="N/A"
      [[ "$ue1_loss_pct" != "NaN" ]] && disp_ue1_loss="${ue1_loss_pct}%"

      disp_ue2_loss="N/A"
      [[ "$loss_pct" != "NaN" ]] && disp_ue2_loss="${loss_pct}%"

      printf "%4ds | %-12s | %-11s | %-10s | %-12s | %-11s | %-7s | %s\n" \
        "$sec" "${tput} Mbps" "$disp_ue1_rtt" "$disp_ue1_loss" "$disp_rtt" "${jitter} ms" "$disp_ue2_loss" "$sla"
    done

    echo "------+-------------------+-----------------+------------+--------+-------------"

    final_tput=""
    if [[ -n "$IPERF_LOG" && -f "$IPERF_LOG" ]]; then
      final_tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec\s+receiver)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || true)
      [[ -z "$final_tput" ]] && final_tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || true)
    fi
    [[ -z "$final_tput" ]] && final_tput="$EMBB_RATE"

    ping_stat=""
    if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
      ping_stat=$(tail -n 2 "$PING_LOG" 2>/dev/null | grep -oP '(?<=rtt min/avg/max/mdev = )[^ ]+' || echo "N/A")
    fi
    [[ -z "$ping_stat" ]] && ping_stat="N/A"

    echo "Hasil : eMBB (Sender): ${final_tput} Mbps | URLLC RTT (min/avg/max/mdev): ${ping_stat} ms | Loss: ${loss_pct}%"
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
