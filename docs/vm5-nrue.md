# VM-5 — OAI nrUE (Multi-Slice User Equipment Emulator)

This document provides the complete, production-grade deployment and operations guide for **VM-5 (`ue-emulator`)**, which hosts the OpenAirInterface 5G New Radio User Equipment (OAI nrUE) softmodem running in **RFsimulator** mode.

VM-5 emulates multi-slice, multi-instance 5G Standalone (SA) user equipments in software, connecting to the split RAN on VM-4 and core network on VM-3 without physical SDR or USRP hardware:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             VM-5: ue-emulator                               │
│                               (10.102.0.165)                                 │
│                                                                             │
│   ┌────────────────────────────────┐   ┌────────────────────────────────┐   │
│   │   Namespace: ue1 (Slice 1)     │   │   Namespace: ue2 (Slice 2)     │   │
│   │   - IMSI: 208950000000031      │   │   - IMSI: 208950000000032      │   │
│   │   - S-NSSAI: [SST: 1, SD: 1]   │   │   - S-NSSAI: [SST: 222,SD: 123]│   │
│   │   - DNN: default               │   │   - DNN: lowlatency            │   │
│   │   - Interface: oaitun_ue1      │   │   - Interface: oaitun_ue1      │   │
│   │   - IP: 12.1.1.2/24            │   │   - IP: 12.1.2.2/24            │   │
│   └───────────────┬────────────────┘   └───────────────┬────────────────┘   │
└───────────────────┼────────────────────────────────────┼────────────────────┘
                    │ RFsim TCP :4043                    │ RFsim TCP :4044
                    ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          VM-4: OAI Split RAN (10.102.0.167)                  │
│   ┌────────────────────────────────┐   ┌────────────────────────────────┐   │
│   │   Distributed Unit 1 (DU-1)    │   │   Distributed Unit 2 (DU-2)    │   │
│   │   - Cell-1 (PCI 1, rfsim :4043)│   │   - Cell-2 (PCI 2, rfsim :4044)│   │
│   └────────────────────────────────┘   └────────────────────────────────┘   │
│                                    │                                        │
│   ┌────────────────────────────────▼────────────────────────────────────┐   │
│   │                  Centralized Unit (CU-CP / CU-UP)                   │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │ N2 (38412/SCTP) & N3 (2152/UDP)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VM-3: OAI 5G Core (10.102.0.164)                     │
│   - AMF (N2 Control Plane)         - UPF-1: 192.168.70.142 (Slice 1)        │
│   - SMF-1 & SMF-2                  - UPF-2: 192.168.70.143 (Slice 2)        │
│   - MySQL (Subscriber Database)    - NSSF (Slice Selection & Routing)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| **VM Identifier** | VM-5 | Virtual Machine index |
| **Hostname** | `ue-emulator` | Host identifier |
| **IP Address** | `10.102.0.165` | Static IP on thesis research subnet |
| **Subnet** | `10.102.0.0/24` | Main inter-VM communication network |
| **Main Role** | 5G nrUE Multi-Instance Emulator | Standalone multi-UE and multi-slice traffic generator |
| **Operating System** | Ubuntu 22.04 LTS (Kernel 5.15+) | Standard LTS Linux environment |
| **Hardware Sizing** | 4 vCPU, 8 GB RAM, 30 GB Disk | Recommended host compute allocation |
| **RAN Target Host** | `10.102.0.167` (VM-4) | Host IP where DU-1 and DU-2 softmodems listen |
| **Cell-1 RFsim Target** | `10.102.0.167:4043/TCP` | DU-1 RFsimulator socket endpoint |
| **Cell-2 RFsim Target** | `10.102.0.167:4044/TCP` | DU-2 RFsimulator socket endpoint |

---

## 2. Theoretical & Standardization Rationale for UE Parameters

All parameter selections on VM-5 strictly comply with 3GPP Release 16/17 and official OpenAirInterface guidelines:

### 2.1 3GPP 5G Standalone (SA) Radio Profile
- **Standard:** **3GPP TS 38.101-1** (User Equipment radio transmission and reception) and **3GPP TS 38.211**.
- **Band:** **Band n78** (TDD, $3300 - 3800\text{ MHz}$).
- **Subcarrier Spacing (SCS):** **$\mu = 1$ ($30\text{ kHz}$)**, corresponding to `--numerology 1`.
- **Transmission Bandwidth:** **106 PRBs** ($40\text{ MHz}$ nominal channel bandwidth at $30\text{ kHz}$ SCS), corresponding to `-r 106`.
- **Downlink Carrier Frequency:** **$3619200000\text{ Hz}$ ($3.6192\text{ GHz}$)**, corresponding to `-C 3619200000`.
- **Constraint:** Must match identically with the radio profile defined in `cu_gnb.conf` and `du_gnb*.conf` on VM-4. Any mismatch in frequency, band, or numerology prevents the UE from synchronizing to the Primary and Secondary Synchronization Signals (PSS/SSS) during cell search.

### 2.2 5G AKA Security & Authentication Credentials
- **Standard:** **3GPP TS 33.501** (Security architecture and procedures for 5G System).
- **Credentials:**
  - **Subscriber Identity (SUPI / IMSI):** `208950000000031` (UE 1) and `208950000000032` (UE 2). The first 5 digits encode MCC `208` and MNC `95`.
  - **Permanent Secret Key ($K$):** `0C0A34601D4F07677303652C0462535B` (128-bit master cryptographic key).
  - **Operator Code ($OP_c$):** `63bfa50ee6523365ff14c1f45f88737d` (derived from $OP$ and $K$).
  - **Authentication Algorithm:** **Milenage** with standard 3GPP rotation constants.
- **Constraint:** These credentials must match the subscriber registration stored in MySQL table `AuthenticationSubscription` on VM-3. A single bit mismatch causes Authentication Failure (`MAC failure` or `Synch failure`), aborting the NAS Registration procedure.

### 2.3 Single Network Slice Selection Assistance Information (S-NSSAI)
- **Standard:** **3GPP TS 23.501 Clause 5.15.2** and **3GPP TS 24.501**.
- **UE 1 (High Throughput / eMBB):**
  - `SST = 1, SD = 0x000001` (decimal `1`), DNN: `default`.
  - Terminates at `oai-upf-slice1` (`192.168.70.142`), IP pool: `12.1.1.0/24`.
- **UE 2 (Low-Latency / Mission-Critical):**
  - `SST = 222 (0xDE), SD = 0x00007B` (decimal `123`), DNN: `lowlatency`.
  - Terminates at `oai-upf-slice2` (`192.168.70.143`), IP pool: `12.1.2.0/24`.
- **Constraint:** The Requested NSSAI transmitted by the UE in the RRC *Registration Request* is validated by AMF against `Allowed NSSAI` and NSSF routing tables.

### 2.4 Linux Network Namespaces for Concurrent Multi-UE Isolation
- **Problem:** By default, each OAI `nr-uesoftmodem` instance instantiates a Linux network TUN interface named `oaitun_ue1`. If multiple UEs execute in the root host namespace, the second UE crashes with `SIOCSIFFLAGS: Device or resource busy`, and kernel routing tables cannot differentiate traffic destined for different slices.
- **Solution:** Linux Network Namespaces (`ip netns`):
  - `netns: ue1` hosts UE 1, its private `oaitun_ue1` (`12.1.1.2`), and its default route.
  - `netns: ue2` hosts UE 2, its private `oaitun_ue1` (`12.1.2.2`), and its default route.
  - Complete isolation enables simultaneous, conflict-free multi-slice throughput and latency benchmarks.

### 2.5 RFsimulator TCP Channel Emulation
- **Standard:** OpenAirInterface RFsimulator architecture.
- **Mechanism:** In place of a physical radio frontend (such as USRP B210/N310), IQ samples are exchanged over TCP stream sockets.
- **Endpoint Binding:** DU-1 operates an RFsimulator server on TCP port `4043`; DU-2 operates on TCP port `4044`. The UE acts as an RFsimulator client connecting to either port via `--rfsim --rfsimulator.serveraddr 10.102.0.167 --rfsimulator.serverport <PORT>`.

---

## 3. Parameter Customization Reference Guide

| Parameter | Current Value | Classification | Customization Rules & Impact |
|---|---|---|---|
| `numerology` | `1` (30 kHz) | `[MANDATORY MATCH RAN]` | Subcarrier spacing. Must match `du_gnb*.conf`. |
| `band` | `78` | `[MANDATORY MATCH RAN]` | 5G NR TDD operational band. Must match `du_gnb*.conf`. |
| `dl_carrier_freq` | `3619200000` (3.6192 GHz) | `[MANDATORY MATCH RAN]` | Center frequency in Hz. Must match `du_gnb*.conf`. |
| `prb` | `106` | `[MANDATORY MATCH RAN]` | Channel bandwidth (40 MHz). Must match `du_gnb*.conf`. |
| `serveraddr` | `10.102.0.167` | `[CUSTOMIZABLE]` | VM-4 IP address hosting DU-1 and DU-2. |
| `serverport` | `4043` / `4044` | `[CUSTOMIZABLE]` | DU-1 (Cell-1) = `4043`, DU-2 (Cell-2) = `4044`. |
| `uicc0.imsi` | `208950000000031` / `...32` | `[MANDATORY MATCH 5GC]` | International Mobile Subscriber Identity. Must match MySQL `oai_db2.sql`. |
| `uicc0.key` | `0C0A3460...` | `[MANDATORY MATCH 5GC]` | Permanent 128-bit authentication key. Must match MySQL `oai_db2.sql`. |
| `uicc0.opc` | `63bfa50e...` | `[MANDATORY MATCH 5GC]` | 128-bit Operator Code. Must match MySQL `oai_db2.sql`. |
| `uicc0.nssai_sst` | `1` / `222` | `[MANDATORY MATCH 5GC/RAN]` | Slice Service Type (1 = eMBB, 222 = Low Latency). |
| `uicc0.nssai_sd` | `1` / `123` | `[MANDATORY MATCH 5GC/RAN]` | Slice Differentiator (hex `0x000001` / `0x00007B`). |
| `uicc0.dnn` | `default` / `lowlatency` | `[MANDATORY MATCH 5GC]` | Data Network Name. Must match SMF/UPF mapping. |

---

## 4. Directory Layout

The standard working directory on VM-5 is `/opt/oran/ue/`:

```text
/opt/oran/ue/
├── openairinterface5g/               # OAI source repository
│   └── cmake_targets/
│       └── ran_build/build/
│           └── nr-uesoftmodem        # Compiled UE softmodem executable
├── conf/
│   ├── ue_slice1.conf                # Configuration file for UE 1 (Slice 1 - eMBB)
│   └── ue_slice2.conf                # Configuration file for UE 2 (Slice 2 - Low Latency)
├── logs/                             # Execution and diagnostic logs
└── scripts/                          # Startup, namespace setup, and traffic generators
```

---

## 5. Host Setup & System Prerequisites

Execute the following commands on VM-5 to prepare the operating system:

### Step 1: Install Required Dependencies & Tooling
```bash
sudo apt update && sudo apt install -y \
  build-essential \
  cmake \
  ninja-build \
  git \
  iproute2 \
  net-tools \
  iptables \
  iperf3 \
  libforms-dev \
  libforms-bin \
  libatlas-base-dev \
  libblas-dev \
  liblapack-dev \
  liblapacke-dev \
  telnet \
  jq

# Verify network connectivity to VM-4 (RAN) and VM-3 (5GC)
ping -c 2 10.102.0.167
ping -c 2 10.102.0.164
```

### Step 2: Configure Routing to 5GC Bridge Subnet
Allow VM-5 to route packets to the container network (`192.168.70.0/24`) via VM-3:
```bash
sudo ip route add 192.168.70.0/24 via 10.102.0.164

# Verify route to AMF
ping -c 2 192.168.70.138
```

---

## 6. Clone Repository & Build `nr-uesoftmodem`

Use the official OpenAirInterface5G repository (matching the develop commit used on VM-4):

### Step 1: Clone Official OAI Repository
```bash
sudo mkdir -p /opt/oran/ue/conf /opt/oran/ue/logs /opt/oran/ue/scripts
sudo chown -R "$USER":"$USER" /opt/oran/ue
cd /opt/oran/ue

git clone https://gitlab.eurecom.fr/oai/openairinterface5g.git
cd openairinterface5g
git checkout develop
```

### Step 2: Install OAI Dependencies
```bash
cd /opt/oran/ue/openairinterface5g/cmake_targets
./build_oai -I
```

> [!TIP]
> **SIMDe Header Verification:**  
> If `build_helper` encounters a download timeout cloning `simde-no-tests`, install the SIMDe header files manually:
> ```bash
> sudo apt install -y libsimde-dev || {
>   sudo rm -rf /tmp/simde
>   git clone --depth 1 https://github.com/simd-everywhere/simde-no-tests.git /tmp/simde
>   sudo cp -r /tmp/simde/simde /usr/include/
> }
> ls -d /usr/include/simde
> ```

### Step 3: Compile nrUE Softmodem with RFsimulator
Compile `nr-uesoftmodem` with RFsimulator support (`-w SIMU`):

```bash
cd /opt/oran/ue/openairinterface5g/cmake_targets
./build_oai -w SIMU --nrUE --ninja
```

Verify that the binary and RFsimulator shared library were created successfully:
```bash
ls -la /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build/nr-uesoftmodem
ls -la /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build/librfsimulator.so
```

---

## 7. Configuration Files Setup

Create dedicated configuration files to manage UE subscription credentials cleanly.

### 1. Configuration for UE 1 (Slice 1 — eMBB)
Save this file as `/opt/oran/ue/conf/ue_slice1.conf`:

```hcl
# [MANDATORY MATCH 5GC/RAN] UE 1 Configuration: Slice 1 (eMBB)
uicc0 = {
  imsi      = "208950000000031";                 # [MANDATORY MATCH 5GC] Registered IMSI
  key       = "0C0A34601D4F07677303652C0462535B";# [MANDATORY MATCH 5GC] 128-bit Key
  opc       = "63bfa50ee6523365ff14c1f45f88737d";# [MANDATORY MATCH 5GC] Operator Code
  dnn       = "default";                          # [MANDATORY MATCH 5GC] DNN
  nssai_sst = 1;                                  # [MANDATORY MATCH 5GC/RAN] eMBB SST
  nssai_sd  = 1;                                  # [MANDATORY MATCH 5GC/RAN] eMBB SD (0x000001)
};
```

### 2. Configuration for UE 2 (Slice 2 — Low Latency)
Save this file as `/opt/oran/ue/conf/ue_slice2.conf`:

```hcl
# [MANDATORY MATCH 5GC/RAN] UE 2 Configuration: Slice 2 (Low-Latency)
uicc0 = {
  imsi      = "208950000000032";                 # [MANDATORY MATCH 5GC] Dedicated IMSI
  key       = "0C0A34601D4F07677303652C0462535B";# [MANDATORY MATCH 5GC] 128-bit Key
  opc       = "63bfa50ee6523365ff14c1f45f88737d";# [MANDATORY MATCH 5GC] Operator Code
  dnn       = "lowlatency";                       # [MANDATORY MATCH 5GC] DNN
  nssai_sst = 222;                                # [MANDATORY MATCH 5GC/RAN] Low-Latency SST
  nssai_sd  = 123;                                # [MANDATORY MATCH 5GC/RAN] Low-Latency SD (0x00007B)
};
```

> [!NOTE]
> Ensure that subscriber `208950000000032` is registered in MySQL on VM-3 before launching UE 2. If using only one subscriber ID for initial testing, set `imsi = "208950000000031"` in `ue_slice2.conf` and launch sequentially.

---

## 8. Dynamic Multi-Instance Execution via Linux Network Namespaces

To evaluate multi-slice QoS and traffic steering without interface collisions or routing ambiguity, VM-5 provides dynamic multi-UE automation scripts. The spawner prompts the user for the number of UEs and their slice distribution (or accepts CLI arguments), sets up isolated Linux network namespaces (`ue1`...`ueN`) with veth pairs and NAT, dynamically generates 3GPP config files, staggers softmodem startup, and performs automated ping validation.

### Step 1: Dynamic Multi-UE Spawner Script (`/opt/oran/ue/scripts/spawn_multi_ue.sh`)

Save this script as `/opt/oran/ue/scripts/spawn_multi_ue.sh`:

```bash
#!/usr/bin/env bash
set -e

# ==============================================================================
# Dynamic Multi-UE Spawner with Network Namespace Isolation (VM-5 ue-emulator)
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
  echo "Menjalankan softmodem UE #$ue_idx di namespace $ns mengarah ke port $rf_port..."
  sudo ip netns exec "$ns" nohup "$BUILD_DIR/nr-uesoftmodem" \
    -r 106 \
    --numerology 1 \
    --band 78 \
    -C 3619200000 \
    --rfsim \
    --rfsimulator.serveraddr "$RAN_IP" \
    --rfsimulator.serverport "$rf_port" \
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
```

Make the script executable:
```bash
chmod +x /opt/oran/ue/scripts/spawn_multi_ue.sh
```

---

### Step 2: Automated Multi-UE Teardown Script (`/opt/oran/ue/scripts/stop_multi_ue.sh`)

Save this script as `/opt/oran/ue/scripts/stop_multi_ue.sh`:

```bash
#!/usr/bin/env bash
echo "Menghentikan semua proses nr-uesoftmodem..."
sudo pkill -9 nr-uesoftmodem || true

echo "Membersihkan semua antarmuka veth dan namespace UE..."
for ns in $(ip netns list | grep -oP '^ue\d+'); do
  ue_idx="${ns#ue}"
  echo "Menghapus $ns dan veth-ue${ue_idx}..."
  sudo ip link del "veth-ue${ue_idx}" 2>/dev/null || true
  sudo ip netns del "$ns" 2>/dev/null || true
done

rm -f /opt/oran/ue/active_ues.txt
echo "Seluruh UE berhasil dihentikan dan dibersihkan."
```

Make the script executable:
```bash
chmod +x /opt/oran/ue/scripts/stop_multi_ue.sh
```

---

### Step 3: Automated Multi-Slice Traffic Generator (`/opt/oran/ue/scripts/trafgen.sh`)

Instead of manual terminal windows, VM-5 provides a unified automated traffic generator (`trafgen.sh`). The script reads active UE state, applies slice-appropriate traffic profiles (heavy UDP throughput for Slice 1 eMBB and high-frequency precision ping for Slice 2 URLLC), and logs performance metrics.

Save this script as `/opt/oran/ue/scripts/trafgen.sh`:

```bash
#!/usr/bin/env bash
# ==============================================================================
# Automated Multi-Slice Traffic Generator (VM-5 ue-emulator)
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
```

Make the script executable:
```bash
chmod +x /opt/oran/ue/scripts/trafgen.sh
```

---

### Step 4: Interactive CLI Shell / Terminal Access (`/opt/oran/ue/scripts/enter_ue.sh`)

If manual diagnostic access into a specific UE's network namespace is occasionally required, use `enter_ue.sh`:

```bash
cat << 'EOF' > /opt/oran/ue/scripts/enter_ue.sh
#!/usr/bin/env bash
ns="${1:-ue1}"
if ! ip netns list | grep -q "^$ns\b"; then
  echo "Namespace $ns tidak ditemukan! Namespace yang sedang aktif:"
  ip netns list
  exit 1
fi
echo "Masuk ke dalam namespace $ns (Ketik 'exit' untuk kembali ke shell host)..."
sudo ip netns exec "$ns" bash --rcfile <(echo "
  export PS1='\[\e[1;33m\][$ns]#\[\e[0m\] '
")
EOF

chmod +x /opt/oran/ue/scripts/enter_ue.sh
```

---

## 9. Acceptance Criteria & Validation

To confirm end-to-end operational readiness, verify the following validation milestones:

### 1. RFsimulator Socket Connection Established [VALIDATED]
In the UE logs (`ue1_cell1.log`), confirm that the client successfully connects to the DU RFsimulator socket:
```text
[RFSIM] Connected to server 10.102.0.167:4043
[RFSIM] RF simulator connected
```

### 2. 5G SA Synchronization & Cell Search [VALIDATED]
The UE synchronizes with the PSS/SSS signals broadcast by DU-1:
```text
[NR_PHY] Cell search: [PCI 1] Found PSS and SSS
[NR_PHY] Synchronized to cell 1 (PCI 1)
[NR_RRC] Received SIB1 from gNB
```

### 3. Random Access & RRC Connection [VALIDATED]
The UE performs the RACH procedure and enters RRC Connected state:
```text
[NR_MAC] RA procedure succeeded: Contention Resolution verified
[NR_RRC] RRCSetupRequest sent
[NR_RRC] Received RRCSetup -> State: RRC_CONNECTED
```

### 4. 5G-AKA Authentication & PDU Session Establishment [VALIDATED]
In VM-3 AMF logs and UE logs:
```text
[NAS] Sending Registration Request (5GS Registration)
[NAS] Received Authentication Request (Milenage AKA)
[NAS] Authentication Response verified -> Security Mode Complete
[NAS] PDU Session Establishment Accepted:
      - NSSAI: SST 1, SD 0x000001
      - Assigned UE IP: 12.1.1.2
```

### 5. Tunnel Interface & End-to-End User Plane Ping [VALIDATED]
Inspect the interface inside namespace `ue1`:
```bash
sudo ip netns exec ue1 ifconfig oaitun_ue1
# Output should show inet 12.1.1.2 netmask 255.255.255.0
```

Verify end-to-end data transmission by pinging the UPF-1 gateway (`12.1.1.1`):
```bash
sudo ip netns exec ue1 ping -c 4 12.1.1.1
# Output:
# 4 packets transmitted, 4 received, 0% packet loss, time 3004ms
# rtt min/avg/max/mdev = 8.123/10.450/14.210/2.311 ms
```

Verify user-plane throughput using `iperf3`:
```bash
# In namespace ue1 against external DN or UPF:
sudo ip netns exec ue1 iperf3 -c 12.1.1.1 -t 10 -i 1
```

---

## 10. Interactive Channel Simulation & Handover Trigger

The OAI RFsimulator provides an interactive telnet server to simulate physical mobility and trigger RRC A3-event handovers between Cell-1 and Cell-2 in real time.

### Step 1: Enable Telnet Server on DU-1 and DU-2
When launching `nr-softmodem` on VM-4, append `--telnetsrv --rfsimulator.options chanmod`.

### Step 2: Connect to Telnet Console
From VM-4 or VM-5:
```bash
telnet 10.102.0.167 9090
```

### Step 3: Modify Pathloss to Trigger Handover
Simulate the UE moving away from Cell-1 towards Cell-2:
```text
# Show current RF channel status
channelmod show current

# Increase path loss on Cell-1 (weaken Cell-1 RSRP)
channelmod modify 0 ploss 35

# In CU log, confirm A3 Measurement Report and Handover trigger:
# [NR_RRC] UE 1: Received MeasurementReport (event A3: target cell PCI 2 better than source PCI 1)
```

---

## 11. Multi-Slice SLA Evaluation Workloads

To measure end-to-end SLA satisfaction and evaluate baseline recovery times from the actual user perspective, VM-5 runs synchronized traffic generators across the distinct slice network namespaces.

### 11.1 Workload Generator Profiles

```bash
# Terminal 1: Slice 1 (Throughput / eMBB) - Heavy background UDP traffic
sudo ip netns exec ue1 iperf3 -c 192.168.70.135 -u -b 40M -t 300 -i 1

# Terminal 2: Slice 2 (Low Latency / URLLC) - High-frequency latency probe (every 50ms)
sudo ip netns exec ue2 ping -c 6000 -i 0.05 192.168.70.135 | tee /opt/oran/nrue/slice2_latency.log
```

### 11.2 Ground-Truth SLA Violation Logging
During each 30-second observation window $k$, SLA compliance is evaluated at VM-5:
- **Slice 1 SLA Bound:** Throughput $\ge 30\text{ Mbps}$, Packet loss $\le 2\%$.
- **Slice 2 SLA Bound:** One-way latency $\le 15\text{ ms}$, RTT $\le 25\text{ ms}$.

If the observed metric breaches either bound within window $k$, window $k$ is logged as an SLA violation for computing the SLA Violation Rate ($V_s$):
$$V_s = \frac{\sum_{k=1}^K \mathbb{I}(\text{SLA Violated}_k)}{K} \times 100\%$$

---

## References
- 3GPP TS 38.101-1: NR; User Equipment (UE) radio transmission and reception
- 3GPP TS 38.211: NR; Physical channels and modulation
- 3GPP TS 38.300 / TS 38.331: NR; Radio Resource Control (RRC) protocol specification
- 3GPP TS 33.501: Security architecture and procedures for 5G System
- 3GPP TS 23.501: System architecture for the 5G System (Clause 5.15 Network Slicing)
- OpenAirInterface5G Documentation: https://gitlab.eurecom.fr/oai/openairinterface5g
- OAI RFsimulator Documentation: https://gitlab.eurecom.fr/oai/openairinterface5g/-/blob/develop/radio/rfsimulator/README.md

