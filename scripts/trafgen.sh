#!/usr/bin/env bash
# Multi-slice traffic generator (VM-5)
# Usage: ./trafgen.sh [start|ping|status|stop] [sec] [mbps]

export LC_ALL=C
export LC_NUMERIC=C

PID_FILE="/opt/oran/ue/trafgen.pid"
STATE_FILE="/opt/oran/ue/active_ues.txt"
LOG_DIR="/opt/oran/ue/logs"
EXT_DN_IP="192.168.70.145"
MONITOR_URL="http://10.102.0.67:9100/report"

mkdir -p "$LOG_DIR"

if [[ ! -f "$STATE_FILE" || ! -s "$STATE_FILE" ]]; then
  echo "Error: file status UE ($STATE_FILE) tidak ditemukan atau kosong." >&2
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

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    while read -r p; do
      if [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; then
        kill "$p" 2>/dev/null || true
      fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  else
    pkill -f "iperf3.*$EXT_DN_IP" 2>/dev/null || true
    pkill -f "ping.*$EXT_DN_IP" 2>/dev/null || true
  fi
}

trap 'cleanup; echo ""; exit 0' INT TERM

parse_ping() {
  local log_file="$1"
  local prev_seq="$2"
  local state_file="${log_file}.state"
  tail -n 60 "$log_file" 2>/dev/null | awk -v prev_seq="$prev_seq" -v state_file="$state_file" '
  BEGIN {
    if (state_file != "") {
      while ((getline line < state_file) > 0) {
        split(line, arr, ":");
        if (arr[1] != "") {
          already_acked[arr[1] + 0] = 1;
        }
      }
      close(state_file);
    }
  }
  {
    s = 0; r = -1; is_no_ans = 0;
    for (i = 1; i <= NF; i++) {
      if ($i ~ /^icmp_seq=/) { split($i, a, "="); s = a[2] + 0 }
      if ($i ~ /^time=/)     { split($i, b, "="); r = b[2] + 0.0 }
    }
    if ($0 ~ /no answer yet/) { is_no_ans = 1 }

    if (s > 0) {
      if (s > max_seen) max_seen = s;
      if (is_no_ans) {
        has_no_ans[s] = 1;
      }
      if (r >= 0.0) {
        if (!already_acked[s] && !newly_rx[s]++) {
          if (s > prev_seq) {
            rx_count++;
            last_rtt = r;
          } else {
            delayed_rx++;
          }
          # Record ack for the sequence in state file (updating origin request state)
          new_ack_list[s] = r;
        }
      }
    }
  }
  END {
    eval_max = max_seen;
    if (eval_max > prev_seq && has_no_ans[eval_max] && !newly_rx[eval_max] && !already_acked[eval_max]) {
      if (eval_max - 1 > prev_seq) {
        eval_max = eval_max - 1;
      }
    }

    if (eval_max > prev_seq) {
      sent = eval_max - prev_seq;
      # Current window loss is strictly determined by packets transmitted within this window (rx_count).
      # Delayed replies for requests belonging to earlier windows update their origin state in state_file
      # and must not reduce the packet loss of newly transmitted requests.
      loss = (sent - rx_count) * 100.0 / sent;
      if (loss < 0.0) loss = 0.0;

      if (rx_count > 0 && last_rtt >= 0.0) {
        printf "%d %.2f %.1f %d %d\n", eval_max, last_rtt, loss, sent, rx_count;
      } else {
        printf "%d NaN 100.0 %d 0\n", eval_max, sent;
      }
    } else {
      printf "%d NaN 0.0 0 0\n", prev_seq;
    }

    if (state_file != "") {
      for (sq in new_ack_list) {
        print sq ":" new_ack_list[sq] >> state_file;
      }
      close(state_file);
    }
  }'
}

case "$ACTION" in
  ping)
    printf "%-5s  %-8s  %-16s  %-12s  %-12s  %s\n" "UE" "Netns" "IMSI" "Slice" "RTT Avg" "Loss"
    echo "----------------------------------------------------------------------"

    while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
      tun_ip=$(ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
      if [[ "$tun_ip" == "DOWN" ]]; then
        printf "%-5s  %-8s  %-16s  %-12s  %-12s  %s\n" "$ue_id" "$ns" "$imsi" "$slice" "-" "DOWN"
        continue
      fi

      ping_out=$(ip netns exec "$ns" ping -I oaitun_ue1 -c 4 -W 2 "$EXT_DN_IP" 2>&1 || true)
      loss=$(echo "$ping_out" | grep -oP '\d+(?=% packet loss)' || echo "100")
      rtt=$(echo "$ping_out" | grep -oP '(?<=rtt min/avg/max/mdev = )[^/]+/[^/]+' | cut -d/ -f2 || echo "0.0")
      rtt="${rtt//,/.}"
      loss="${loss//,/.}"

      printf "%-5s  %-8s  %-16s  %-12s  %-12s  %s\n" "$ue_id" "$ns" "$imsi" "$slice" "${rtt} ms" "${loss}%"

      slice_id=1
      [[ "$slice" == *"URLLC"* ]] && slice_id=2
      curl -s -m 1 -X POST -H "Content-Type: application/json" \
        -d "{\"slice\": $slice_id, \"rtt_ms\": ${rtt}, \"packet_loss_pct\": ${loss}}" "$MONITOR_URL" >/dev/null 2>&1 &
    done < "$STATE_FILE"
    ;;

  run|start)
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    cleanup

    IPERF_LOG=""
    IPERF_PID=""
    UE1_PING_LOG=""
    PING_LOG=""
    UE1_NS=""
    UE2_NS=""

    while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
      tun_ip=$(ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
      [[ "$tun_ip" == "DOWN" ]] && continue

      ip netns exec "$ns" ip route replace 192.168.70.0/24 dev oaitun_ue1 2>/dev/null || true

      if [[ "$slice" == *"eMBB"* ]]; then
        UE1_NS="$ns"
        IPERF_LOG="$LOG_DIR/iperf_${ns}_${TIMESTAMP}.log"
        UE1_PING_LOG="$LOG_DIR/ping_${ns}_${TIMESTAMP}.log"
        > "$IPERF_LOG"
        > "$UE1_PING_LOG"
        > "${UE1_PING_LOG}.state"
        nohup ip netns exec "$ns" iperf3 -c "$EXT_DN_IP" -u -b "${EMBB_RATE}M" -t "$DURATION" -i 1 --logfile "$IPERF_LOG" </dev/null >/dev/null 2>&1 &
        IPERF_PID=$!
        echo "$IPERF_PID" >> "$PID_FILE"
        nohup ip netns exec "$ns" ping -D -O -I oaitun_ue1 -i 0.2 -c $(( (DURATION + 5) * 5 )) "$EXT_DN_IP" </dev/null > "$UE1_PING_LOG" 2>&1 &
        echo $! >> "$PID_FILE"
      else
        UE2_NS="$ns"
        PING_LOG="$LOG_DIR/ping_${ns}_${TIMESTAMP}.log"
        > "$PING_LOG"
        > "${PING_LOG}.state"
        nohup ip netns exec "$ns" ping -D -O -I oaitun_ue1 -i 0.1 -c $(( (DURATION + 5) * 10 )) "$EXT_DN_IP" </dev/null > "$PING_LOG" 2>&1 &
        echo $! >> "$PID_FILE"
      fi
    done < "$STATE_FILE"

    echo "TrafGen: ${DURATION}s | eMBB ${EMBB_RATE}M | URLLC 100ms"
    printf "%4s  %-10s  %-9s  %-7s  %-9s  %-8s  %-6s  %s\n" \
      "Sec" "eMBB-Mbps" "eMBB-RTT" "Loss" "URLLC-RTT" "Jitter" "Loss" "SLA"
    echo "-----------------------------------------------------------------------"

    prev_rtt="0.0"
    prev_max_seq=0
    last_rx_seq=0
    prev_ue1_rtt="0.0"
    prev_ue1_max_seq=0
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
        read -r s_max u1_rtt u1_loss u1_sent u1_rx < <(parse_ping "$UE1_PING_LOG" "$prev_ue1_max_seq")

        if [[ -n "$u1_sent" ]] && (( u1_sent > 0 )); then
          prev_ue1_max_seq=$s_max
          if [[ "$u1_rtt" != "NaN" ]]; then
            ue1_rtt="$u1_rtt"
            ue1_loss_pct="$u1_loss"
            last_ue1_rx_seq=$s_max
            last_ue1_rx_ts=$now_ts
            ue1_measurement_age=0
          else
            ue1_rtt="NaN"
            ue1_loss_pct="100.0"
            ue1_measurement_age=$(( now_ts - last_ue1_rx_ts ))
          fi
        else
          ue1_measurement_age=$(( now_ts - last_ue1_rx_ts ))
          if (( ue1_measurement_age >= 2 )); then
            ue1_loss_pct="100.0"
          else
            ue1_loss_pct="0.0"
          fi
        fi
        prev_ue1_rtt="$ue1_rtt"
      fi

      rtt="NaN"
      jitter="0.00"
      loss_pct="NaN"
      measurement_age=0

      if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
        now_ts=$(date +%s)
        read -r s_max u2_rtt u2_loss u2_sent u2_rx < <(parse_ping "$PING_LOG" "$prev_max_seq")

        if [[ -n "$u2_sent" ]] && (( u2_sent > 0 )); then
          prev_max_seq=$s_max
          if [[ "$u2_rtt" != "NaN" ]]; then
            rtt="$u2_rtt"
            loss_pct="$u2_loss"
            last_rx_seq=$s_max
            last_rx_ts=$now_ts
            measurement_age=0

            rtt_clean="${rtt//,/.}"
            prev_rtt_clean="${prev_rtt//,/.}"
            if (( $(echo "$prev_rtt_clean > 0 && $rtt_clean > 0" | bc -l 2>/dev/null || echo 0) )); then
              jitter=$(echo "scale=2; sqrt(($rtt_clean - $prev_rtt_clean)^2)" | bc -l 2>/dev/null || echo "0.00")
            fi
            prev_rtt="$rtt_clean"
          else
            rtt="NaN"
            loss_pct="100.0"
            measurement_age=$(( now_ts - last_rx_ts ))
          fi
        else
          measurement_age=$(( now_ts - last_rx_ts ))
          if (( measurement_age >= 2 )); then
            loss_pct="100.0"
          else
            loss_pct="0.0"
          fi
        fi
      fi

      sla="OK"
      rtt_clean="${rtt//,/.}"
      if [[ "$rtt_clean" == "NaN" ]]; then
        sla="NO_REPLY"
      elif (( $(echo "$rtt_clean > 20.0" | bc -l 2>/dev/null || echo 0) )); then
        sla="VIOLATED"
      fi

      ue1_rtt_json="${ue1_rtt//,/.}"
      ue1_loss_json="null"
      [[ "$ue1_loss_pct" != "NaN" ]] && ue1_loss_json="${ue1_loss_pct//,/.}"

      rtt_json="${rtt//,/.}"
      ue2_loss_json="null"
      [[ "$loss_pct" != "NaN" ]] && ue2_loss_json="${loss_pct//,/.}"

      tput_json="${tput//,/.}"

      if [[ "$ue1_rtt" != "NaN" && -n "$ue1_rtt" ]]; then
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 1, \"throughput_mbps\": $tput_json, \"rtt_ms\": $ue1_rtt_json, \"packet_loss_pct\": $ue1_loss_json, \"last_seq\": $last_ue1_rx_seq, \"reply_age_sec\": $ue1_measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_ue1_rtt="${ue1_rtt_json} ms"
      else
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 1, \"throughput_mbps\": $tput_json, \"rtt_ms\": null, \"packet_loss_pct\": $ue1_loss_json, \"last_seq\": $last_ue1_rx_seq, \"reply_age_sec\": $ue1_measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_ue1_rtt="-"
      fi

      if [[ "$rtt" != "NaN" ]]; then
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 2, \"rtt_ms\": $rtt_json, \"packet_loss_pct\": $ue2_loss_json, \"last_seq\": $last_rx_seq, \"reply_age_sec\": $measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_rtt="${rtt_json} ms"
      else
        curl -s -m 1 -X POST -H "Content-Type: application/json" \
          -d "{\"slice\": 2, \"rtt_ms\": null, \"packet_loss_pct\": $ue2_loss_json, \"last_seq\": $last_rx_seq, \"reply_age_sec\": $measurement_age}" "$MONITOR_URL" >/dev/null 2>&1 &
        disp_rtt="-"
      fi

      disp_ue1_loss="-"
      [[ "$ue1_loss_pct" != "NaN" ]] && disp_ue1_loss="${ue1_loss_pct//,/.}%"

      disp_ue2_loss="-"
      [[ "$loss_pct" != "NaN" ]] && disp_ue2_loss="${loss_pct//,/.}%"

      printf "%3ds  %-10s  %-9s  %-7s  %-9s  %-8s  %-6s  %s\n" \
        "$sec" "${tput_json} Mbps" "$disp_ue1_rtt" "$disp_ue1_loss" "$disp_rtt" "${jitter} ms" "$disp_ue2_loss" "$sla"
    done

    echo "-----------------------------------------------------------------------"

    if [[ -n "$IPERF_PID" ]] && kill -0 "$IPERF_PID" 2>/dev/null; then
      wait "$IPERF_PID" 2>/dev/null || sleep 1
    else
      sleep 0.5
    fi

    final_tput=""
    if [[ -n "$IPERF_LOG" && -f "$IPERF_LOG" ]]; then
      final_tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec\s+receiver)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || true)
      [[ -z "$final_tput" ]] && final_tput=$(grep -oP '\d+(\.\d+)?(?=\s+Mbits/sec)' "$IPERF_LOG" 2>/dev/null | tail -n 1 || true)
    fi
    [[ -z "$final_tput" ]] && final_tput="$EMBB_RATE"

    ping_stat=""
    ping_loss=""
    if [[ -n "$PING_LOG" && -f "$PING_LOG" ]]; then
      ping_stat=$(tail -n 2 "$PING_LOG" 2>/dev/null | grep -oP '(?<=rtt min/avg/max/mdev = )[^ ]+' || echo "N/A")
      ping_loss=$(tail -n 3 "$PING_LOG" 2>/dev/null | grep -oP '\d+(\.\d+)?(?=%\s+(packet\s+)?loss)' || echo "$loss_pct")
    fi
    [[ -z "$ping_stat" ]] && ping_stat="N/A"
    [[ -z "$ping_loss" ]] && ping_loss="$loss_pct"

    echo "Hasil: eMBB=${final_tput} Mbps | URLLC RTT=${ping_stat} ms | Loss=${ping_loss}%"
    cleanup
    ;;

  status)
    if [[ -f "$PID_FILE" ]]; then
      echo "PID terdaftar ($PID_FILE):"
      cat "$PID_FILE"
    fi
    ps aux | grep -E "iperf3.*$EXT_DN_IP|ping.*$EXT_DN_IP" | grep -v grep || echo "Tidak ada proses aktif."
    ;;

  stop)
    cleanup
    echo "Proses trafik dihentikan."
    ;;

  *)
    echo "Penggunaan: $0 [start|ping|status|stop] [durasi_detik] [rate_mbps]"
    exit 1
    ;;
esac
