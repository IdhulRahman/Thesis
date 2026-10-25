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
│   │   - IP: 12.1.1.2/24            │   │   - IP: 12.2.1.2/24            │   │
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

> [!WARNING]
> **UE 2 MySQL Subscriber Profile must be verified before launch.** When spawning multi-UE via `spawn_multi_ue.sh` (Section 8 below), UE 1 is dynamically assigned IMSI `208950000000001` and UE 2 is assigned `208950000000002` from the VM-3 pre-provisioned pool (while Section 7 above shows the legacy static fallback template `...031`/`...032`).
>
> A known issue was encountered where `SessionManagementSubscriptionData` for IMSI `208950000000002` had an incorrect S-NSSAI (`sd: 000001` pointing to Slice 1 instead of `sd: 00007B` for Slice 2). This caused `FGS_PDU_SESSION_ESTABLISHMENT_REJ` immediately after attach.
>
> Verify and fix on VM-3 before spawning UE 2:
> ```sql
> sudo docker exec -it mysql mysql -u root -plinux oai_db
> SELECT ueid, sst, sd FROM SessionManagementSubscriptionData WHERE ueid = '208950000000002';
> -- Expected: sst=222, sd='00007B'
> -- If wrong, run:
> UPDATE SessionManagementSubscriptionData SET singleNssai = '{"sst":222,"sd":"00007B"}' WHERE ueid = '208950000000002' AND sst = 222;
> ```
> After correcting, restart `oai-amf` and `oai-smf-slice2` on VM-3 to flush stale state.
> See [Troubleshooting Case 49](../troubleshooting/ran-ue.md#case-49) for full root-cause analysis.

---

## 8. Dynamic Multi-Instance Execution via Linux Network Namespaces

To evaluate multi-slice QoS and traffic steering without interface collisions or routing ambiguity, VM-5 provides dynamic multi-UE automation scripts managed in [`scripts/`](../../scripts):

### Step 1: Dynamic Multi-UE Spawner Script (`spawn_multi_ue.sh`)

Automated script to create isolated network namespaces (`ue1`...`ueN`), configure veth pairs & NAT, and dynamically initialize OAI 5G nrUE connections is managed at:
* **Source:** [`scripts/spawn_multi_ue.sh`](../../scripts/spawn_multi_ue.sh)
* **Path on VM-5:** `/opt/oran/ue/scripts/spawn_multi_ue.sh`

#### Execution Commands on VM-5 (`five-g@nrue`):
```bash
# Launch 1 eMBB UE (Cell-1 :4043) and 1 URLLC UE (Cell-2 :4044):
sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1

# Or run interactively:
sudo /opt/oran/ue/scripts/spawn_multi_ue.sh
```

#### Post-Spawn Verification:
```bash
# Verify UE 1 tunnel interface is UP inside its namespace:
sudo ip netns exec ue1 ip -4 addr show oaitun_ue1
# Expected: inet 12.1.1.X/24 scope global oaitun_ue1

# Verify UE 2 tunnel interface is UP inside its namespace:
sudo ip netns exec ue2 ip -4 addr show oaitun_ue1
# Expected: inet 12.2.1.X/24 scope global oaitun_ue1

# Quick end-to-end ping test from UE 1 to External DN:
sudo ip netns exec ue1 ping -c 5 192.168.70.145
```

If UE 2 does NOT obtain `oaitun_ue1`, check for `FGS_PDU_SESSION_ESTABLISHMENT_REJ` in `/opt/oran/ue/logs/ue2.log` — most likely cause is the MySQL subscriber profile mismatch (see warning above).

---

### Step 2: Automated Multi-UE Teardown Script (`stop_multi_ue.sh`)

Clean teardown script to terminate all UE softmodem processes, veth interfaces, and network namespaces is managed at:
* **Source:** [`scripts/stop_multi_ue.sh`](../../scripts/stop_multi_ue.sh)
* **Path on VM-5:** `/opt/oran/ue/scripts/stop_multi_ue.sh`

#### Execution Commands on VM-5 (`five-g@nrue`):
```bash
sudo /opt/oran/ue/scripts/stop_multi_ue.sh
```

---

### Step 3: Automated Multi-Slice Traffic Generator (`trafgen.sh`)

Integrated multi-slice traffic generator (iperf3 UDP eMBB on UE1 and precision URLLC latency probing on UE2 with automated metric reporting to VM-6 `:9100/report`) is managed at:
* **Source:** [`scripts/trafgen.sh`](../../scripts/trafgen.sh)
* **Path on VM-5:** `/opt/oran/ue/scripts/trafgen.sh`

#### Usage Commands on VM-5 (`five-g@nrue`):
```bash
# 1. Quick connectivity check to External DN (192.168.70.145):
sudo /opt/oran/ue/scripts/trafgen.sh ping

# 2. Run simultaneous benchmark (e.g., 80 seconds, 18 Mbps eMBB):
sudo /opt/oran/ue/scripts/trafgen.sh run 80 18

# 3. Check status of running traffic tests:
sudo /opt/oran/ue/scripts/trafgen.sh status

# 4. Forcibly terminate all traffic:
sudo /opt/oran/ue/scripts/trafgen.sh stop
```

---

### Step 4: Interactive CLI Shell / Terminal Access (`enter_ue.sh`)

For direct inspection or troubleshooting within a specific UE network namespace:
* **Source:** [`scripts/enter_ue.sh`](../../scripts/enter_ue.sh)
* **Path on VM-5:** `/opt/oran/ue/scripts/enter_ue.sh`

#### Execution Commands on VM-5 (`five-g@nrue`):
```bash
# Enter UE-1 namespace:
sudo /opt/oran/ue/scripts/enter_ue.sh ue1

# Enter UE-2 namespace:
sudo /opt/oran/ue/scripts/enter_ue.sh ue2
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

## 10. Interactive RF Impairment SOP (RFsimulator Channel Modeling)

The OAI RFsimulator provides an interactive Telnet interface (`--telnetsrv` on port `9090`) to dynamically modify channel propagation parameters during experiments without restarting softmodem processes.

> [!CAUTION]
> **Mathematical Semantics of `path_loss_dB` in OAI RFsimulator:**
> In upstream OAI `apply_channelmod.c` (commit `29d5fa7d`, lines 218–225):
> $$\text{amplitude\_multiplier} = 10^{\frac{\text{path\_loss\_dB}}{20.0}}$$
> The internal `path_loss_dB` parameter functions as a **total path gain (amplification factor)** rather than positive mathematical attenuation:
> * Baseline value configured in `du_gnb1.conf`: **`20.0 dB`**.
> * Modifying `ploss` from `20` to `35` **amplifies** the signal by $+15\text{ dB}$, improving channel quality.
> * To induce signal **degradation / attenuation**, `path_loss_dB` must be **decreased** (e.g., from `20.0` down to `10.0` or `5.0 dB`).

> [!IMPORTANT]
> **Channel Direction Demarcation (Downlink vs. Uplink):**
> In this testbed's `du_gnb1.conf` model descriptors (see [Troubleshooting Case #51](../troubleshooting/ran-ue.md#case-51)):
> * **Channel ID 0 (`rfsimu_channel_enB0`):** Downlink channel (gNB TX $\to$ UE RX).
> * **Channel ID 1 (`rfsimu_channel_ue0`):** Uplink channel (UE TX $\to$ gNB RX).
> Because `ran_adapter.py` monitors the **Uplink Shared Channel (`ulsch`)** scheduler metrics on gNB, channel impairment aimed at degrading `ran_snr_cell1`, `ran_mcs_cell1`, and elevating `ran_bler_cell1` must explicitly target **Channel 1**.

### Recommended Impairment Procedure (`rfsim_channel_control.py`)
To prevent syntax errors, Telnet IAC escaping issues, or unverified channel changes, use the validated Python controller script:

```bash
# 1. Query active channel parameters on DU-1 (port 9090)
python3 /opt/oran/ran/scripts/rfsim_channel_control.py show --port 9090

# 2. Inject 10.0 dB attenuation on Uplink (Channel 1)
# (Reduces path_loss_dB from baseline 20.0 dB down to 10.0 dB)
python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 10.0 --channel-id 1 --port 9090

# 3. Monitor observed telemetry response in ran_adapter / record_experiment.py:
# Typical observed response under channel attenuation: downward pressure on ran_snr_cell1,
# downward link adaptation on ran_mcs_cell1, and potential HARQ retransmission bursts
# reflected in ran_bler_cell1 (magnitude depends on baseline calibration and link state)

# 4. Restore baseline channel conditions after experiment run
python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
```

> [!NOTE]
> **Handover Execution Boundary:**
> In the current baseline testbed, UE-1 (port `4043`) and UE-2 (port `4044`) are statically attached to distinct RFsim DU instances. Channel attenuation on Cell-1 isolates radio bottleneck conditions for classifier evaluation; dynamic inter-cell handover execution via E2SM-RC remains a planned Phase B capability.

---

## 11. Multi-Slice SLA Evaluation Workloads

To measure end-to-end SLA satisfaction and evaluate baseline recovery times from the actual user perspective, VM-5 runs synchronized traffic generators across the distinct slice network namespaces using `scripts/trafgen.sh` (or standalone invocations per namespace).

### 11.1 Workload Generator Profiles

```bash
# Terminal 1: Slice 1 (Throughput / eMBB) - Goodput saturation and 5 Hz canary probe
sudo ip netns exec ue1 iperf3 -c 192.168.70.145 -u -b 25M -t 60 -i 1
sudo ip netns exec ue1 ping -D -O -I oaitun_ue1 -i 0.2 -c 325 192.168.70.145

# Terminal 2: Slice 2 (Low Latency / URLLC) - High-frequency 10 Hz canary latency probe
sudo ip netns exec ue2 ping -D -O -I oaitun_ue1 -i 0.1 -c 650 192.168.70.145
```

Or execute automated multi-slice orchestration via `trafgen.sh`:
```bash
# Syntax: ./trafgen.sh start <duration_sec> <embb_mbps>
./trafgen.sh start 60 25
```

### 11.2 Ground-Truth SLA Evaluation Contract
During each observation window $k$, SLA compliance is evaluated at VM-5:
- **Slice 1 (eMBB) SLA Contract:** Evaluated relative to offered workload: user goodput $T_{\text{eMBB}} \ge 20.0\text{ Mbps}$ under saturation stress ($\ge 25\text{ Mbps}$ offered load), or $\ge 85\%$ of offered demand when operating below capacity. *(Note: Recorded in CSV via `e2e_slice1_tput_mbps` from sender-side iperf3 client; receiver goodput validation at EXT-DN requires offline extraction from server logs).*
- **Slice 2 (URLLC) SLA Contract:** End-to-End Round-Trip Time $RTT \le 20.0\text{ ms}$ (measured to EXT-DN `192.168.70.145`) and packet loss $\le 1.0\%$.

> [!NOTE]
> **Scope & Standards Demarcation:**  
> 3GPP TS 23.501 Table 5.7.4-1 defines standard Packet Delay Budget (PDB) between UE and N6-terminating UPF per standardized 5QI (e.g., 5QI 82 = 10 ms, 5QI 85 = 5 ms). Standard PDB is a single-hop UE–UPF radio/core transit budget, distinct from end-to-end round-trip latency to an external Data Network (DN). In this testbed, the evaluated metric is **End-to-End ICMP RTT** measured between VM-5 namespace `ue2` and EXT-DN `192.168.70.145`. The $20.0\text{ ms}$ threshold is a research evaluation choice accounting for virtualization overhead, Linux network stack transit, and virtual RFsim socket loopbacks.

SLA compliance is evaluated per slice ($V_{s,\text{eMBB}}$, $V_{s,\text{URLLC}}$) and jointly across slices ($V_{s,\text{joint}}$):
$$V_{s,i} = \frac{\sum_{k=1}^K \mathbb{I}(\text{SLA Violated}_{i,k})}{K} \times 100\%, \quad V_{s,\text{joint}} = \frac{\sum_{k=1}^K \mathbb{I}(\text{SLA}_{\text{eMBB}}(k) \lor \text{SLA}_{\text{URLLC}}(k))}{K} \times 100\%$$
Windows with active probe timeout / link drops are logged as Violated; pre-experiment warmup intervals are excluded from denominator $K$.

---

## References
- 3GPP TS 38.101-1: NR; User Equipment (UE) radio transmission and reception
- 3GPP TS 38.211: NR; Physical channels and modulation
- 3GPP TS 38.300 / TS 38.331: NR; Radio Resource Control (RRC) protocol specification
- 3GPP TS 33.501: Security architecture and procedures for 5G System
- 3GPP TS 23.501: System architecture for the 5G System (Clause 5.15 Network Slicing)
- OpenAirInterface5G Documentation: https://gitlab.eurecom.fr/oai/openairinterface5g
- OAI RFsimulator Documentation: https://gitlab.eurecom.fr/oai/openairinterface5g/-/blob/develop/radio/rfsimulator/README.md

