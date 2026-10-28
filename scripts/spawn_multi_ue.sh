#!/usr/bin/env bash
set -e

# ==============================================================================
# Dynamic Multi-UE Spawner with Network Namespace Isolation (VM-5 ue-emulator)
# Location on VM-5: /opt/oran/ue/scripts/spawn_multi_ue.sh
# ==============================================================================
# Features:
# - Interactive prompt or CLI arguments (-s1 <count> -s2 <count>)
# - Dynamic 3GPP config generation from pre-provisioned IMSI pool (...001 to ...050)
# - Isolated netns (ue1, ue2, ...) with dedicated veth pairs & NAT
# - Staggered launch to prevent RFsim RACH collisions
# - Automated end-to-end ping validation to EXT-DN (192.168.70.145)
# ==============================================================================

RAN_IP="10.102.0.167"
EXT_DN_IP="192.168.70.145"
BUILD_DIR="/opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build"
CONF_DIR="/opt/oran/ue/conf"
LOG_DIR="/opt/oran/ue/logs"
STATE_FILE="/opt/oran/ue/active_ues.txt"

mkdir -p "$LOG_DIR" "$CONF_DIR"

# Parse CLI arguments or prompt interactively
S1_COUNT=""
S2_COUNT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s1|--slice1) S1_COUNT="$2"; shift 2 ;;
    -s2|--slice2) S2_COUNT="$2"; shift 2 ;;
    -h|--help)
      echo "Penggunaan: $0 [-s1 <jumlah_slice1>] [-s2 <jumlah_slice2>]"
      exit 0 ;;
    *)
      if [[ -z "$S1_COUNT" ]]; then S1_COUNT="$1"; shift
      elif [[ -z "$S2_COUNT" ]]; then S2_COUNT="$1"; shift
      else shift; fi ;;
  esac
done

if [[ -z "$S1_COUNT" || -z "$S2_COUNT" ]]; then
  echo "======================================================================"
  echo "  5G OAI nrUE Multi-Instance Dynamic Spawner (VM-5 ue-emulator)"
  echo "======================================================================"
  echo "Profil Slice yang Tersedia:"
  echo "  [Slice 1 - eMBB]  : SST 1, SD 0x000001, DNN 'default', Target DU-1 (:4043)"
  echo "  [Slice 2 - URLLC] : SST 222, SD 0x00007B, DNN 'lowlatency', Target DU-2 (:4044)"
  echo "----------------------------------------------------------------------"
  read -rp "Jumlah UE untuk Slice 1 (eMBB) [default 1]: " INPUT_S1
  read -rp "Jumlah UE untuk Slice 2 (URLLC) [default 1]: " INPUT_S2
  S1_COUNT="${INPUT_S1:-1}"
  S2_COUNT="${INPUT_S2:-1}"
fi

TOTAL_UE=$(( S1_COUNT + S2_COUNT ))

if [[ "$TOTAL_UE" -lt 1 ]]; then
  echo "[ERROR] Total UE harus minimal 1!"
  exit 1
fi

if [[ "$TOTAL_UE" -gt 50 ]]; then
  echo "[ERROR] Total UE ($TOTAL_UE) melebihi batas subscriber terdaftar di MySQL (50)!"
  exit 1
fi

echo ""
echo "=== [Konfigurasi Terpilih] ==="
echo "Total UE : $TOTAL_UE"
echo "Slice 1  : $S1_COUNT UE(s) (DU-1 / Cell-1 / Port 4043)"
echo "Slice 2  : $S2_COUNT UE(s) (DU-2 / Cell-2 / Port 4044)"
echo "=============================="
echo ""

echo "=== [1/5] Mengaktifkan IP Forwarding & Persiapan Host ==="
sudo sysctl -w net.ipv4.ip_forward=1 > /dev/null
sudo iptables -t nat -C POSTROUTING -s 10.200.0.0/16 -j MASQUERADE 2>/dev/null || \
sudo iptables -t nat -A POSTROUTING -s 10.200.0.0/16 -j MASQUERADE

rm -f "$STATE_FILE"

CURRENT_UE=1

# Helper function to spawn a single UE
spawn_ue() {
  local ue_idx="$1"
  local slice_num="$2"
  local imsi_suffix
  imsi_suffix=$(printf "%02d" "$ue_idx")
  local imsi="2089500000000${imsi_suffix}"
  local ns="ue${ue_idx}"
  local conf_file="$CONF_DIR/ue_${ue_idx}.conf"
  local log_file="$LOG_DIR/ue${ue_idx}.log"
  local rf_port
  local sst
  local sd
  local dnn
  local slice_label

  if [[ "$slice_num" -eq 1 ]]; then
    rf_port="4043"
    sst="1"
    sd="1"
    dnn="default"
    slice_label="Slice-1 (eMBB)"
  else
    rf_port="4044"
    sst="222"
    sd="123"
    dnn="lowlatency"
    slice_label="Slice-2 (URLLC)"
  fi

  echo "--- [Mempersiapkan UE #$ue_idx: $slice_label, IMSI: $imsi] ---"

  # 1. Generate Config File
  cat << EOF_CONF > "$conf_file"
uicc0 = {
  imsi      = "$imsi";
  key       = "0C0A34601D4F07677303652C0462535B";
  opc       = "63bfa50ee6523365ff14c1f45f88737d";
  dnn       = "$dnn";
  nssai_sst = $sst;
  nssai_sd  = $sd;
};
EOF_CONF

  # 2. Setup Namespace & Veth
  if ! ip netns list | grep -q "^$ns\b"; then
    sudo ip netns add "$ns"
  fi
  sudo ip netns exec "$ns" ip link set lo up

  local veth_host="veth-ue${ue_idx}"
  local veth_ns="veth-ue${ue_idx}-ns"
  local host_ip="10.200.${ue_idx}.1"
  local ns_ip="10.200.${ue_idx}.2"

  if ! ip link show "$veth_host" >/dev/null 2>&1; then
    sudo ip link add "$veth_host" type veth peer name "$veth_ns"
    sudo ip link set "$veth_ns" netns "$ns"
    sudo ip addr add "${host_ip}/24" dev "$veth_host"
    sudo ip link set "$veth_host" up
    sudo ip netns exec "$ns" ip addr add "${ns_ip}/24" dev "$veth_ns"
    sudo ip netns exec "$ns" ip link set "$veth_ns" up
    sudo ip netns exec "$ns" ip route add default via "$host_ip"
  fi

  # 3. Launch nr-uesoftmodem inside namespace
  local -a sampling_args=()
  local prb_val="106"
  local freq_val="3619200000"
  if [[ "$slice_num" -eq 1 ]]; then
    sampling_args=(-E)
    prb_val="51"
    freq_val="3609120000"
  fi

  echo "Menjalankan softmodem UE #$ue_idx di namespace $ns mengarah ke port $rf_port (PRB $prb_val, Freq $freq_val)..."
  sudo ip netns exec "$ns" nohup "$BUILD_DIR/nr-uesoftmodem" \
    "${sampling_args[@]}" \
    -r "$prb_val" \
    --numerology 1 \
    --band 78 \
    -C "$freq_val" \
    --rfsim \
    --rfsimulator.serveraddr "$RAN_IP" \
    --rfsimulator.serverport "$rf_port" \
    --ue-timing-correction-disable \
    -O "$conf_file" \
    > "$log_file" 2>&1 &
  local pid=$!

  echo "$ue_idx:$ns:$imsi:$slice_label:$dnn:$rf_port:$pid" >> "$STATE_FILE"
  echo "UE #$ue_idx berjalan (PID: $pid). Menunggu 6 detik untuk registrasi..."
  sleep 6
}

echo "=== [2/5] Menjalankan $S1_COUNT UE(s) pada Slice 1 (eMBB) ==="
for ((i=1; i<=S1_COUNT; i++)); do
  spawn_ue "$CURRENT_UE" 1
  CURRENT_UE=$(( CURRENT_UE + 1 ))
done

echo "=== [3/5] Menjalankan $S2_COUNT UE(s) pada Slice 2 (URLLC) ==="
for ((i=1; i<=S2_COUNT; i++)); do
  spawn_ue "$CURRENT_UE" 2
  CURRENT_UE=$(( CURRENT_UE + 1 ))
done

echo ""
echo "=== [4/5] Verifikasi Status Antarmuka Tunnel (oaitun_ue1) ==="
sleep 3

printf "%-5s | %-8s | %-16s | %-16s | %-12s | %-15s | %-10s\n" "UE#" "Netns" "IMSI" "Slice" "Target" "Tunnel IP" "Ping EXT-DN"
printf "%s\n" "---------------------------------------------------------------------------------------------------"

while IFS=":" read -r ue_id ns imsi slice dnn port pid; do
  tun_ip=$(sudo ip netns exec "$ns" ip -4 addr show oaitun_ue1 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "DOWN")
  ping_res="FAIL"
  if [[ "$tun_ip" != "DOWN" ]]; then
    sudo ip netns exec "$ns" ip route replace 192.168.70.0/24 dev oaitun_ue1 2>/dev/null || true
    if sudo ip netns exec "$ns" ping -I oaitun_ue1 -c 2 -W 2 "$EXT_DN_IP" >/dev/null 2>&1; then
      ping_res="OK (0% loss)"
    fi
  fi
  printf "%-5s | %-8s | %-16s | %-16s | %-12s | %-15s | %-10s\n" "$ue_id" "$ns" "$imsi" "$slice" "Port $port" "$tun_ip" "$ping_res"
done < "$STATE_FILE"

echo ""
echo "=== [5/5] Multi-UE Spawning Selesai! ==="
echo "Untuk menghentikan dan membersihkan semua UE, jalankan:"
echo "  sudo /opt/oran/ue/scripts/stop_multi_ue.sh"
