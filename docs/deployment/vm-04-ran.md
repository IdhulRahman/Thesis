# VM-4 — OAI RAN (CU + Multi-DU + E2 Agent)

This document describes the deployment of **VM-4 (`oai-ran`)**, which hosts the OpenAirInterface 5G Radio Access Network (OAI 5G RAN) configured in a **split CU / multi-DU** architecture with an integrated **O-RAN E2 Agent** and **RFsimulator (rfsim)**.

VM-4 interconnects three primary domains in the thesis platform:
1. **Core Network (VM-3):** N2 (NG-AP / SCTP) to AMF and N3 (GTP-U / UDP) to multi-slice UPFs via routed Docker bridge subnet `192.168.70.0/24`.
2. **Near-RT RIC (VM-2):** O-RAN E2 interface (E2AP over SCTP) to `ric_e2term` (`10.102.0.66:36421`).
3. **UE Emulator (VM-5):** RFsimulator channel interface for software-only over-the-air communication.

```text
               ┌────────────────────────────────────────────────────────┐
               │              VM-2 Near-RT RIC (10.102.0.66)            │
               │                   ric_e2term :36421                    │
               └───────────────────────────▲────────────────────────────┘
                                           │
                                           │ E2 (E2AP / SCTP)
                                           │
┌──────────────────────────────────────────▼────────────────────────────┐
│ VM-4 OAI RAN (10.102.0.167)                                            │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                 Centralized Unit (CU)                         │   │
│   │  - RRC / PDCP / SDAP                                          │   │
│   │  - Integrated OAI E2 Agent (points to 10.102.0.66:36421)      │   │
│   │  - N2 NG-AP (SCTP) & N3 GTP-U (UDP)                           │   │
│   └───┬───────────────────────────────────────────────────────┬───┘   │
│       │ F1-C (SCTP) / F1-U (GTP)      │ F1-C (SCTP) / F1-U (GTP)      │
│   ┌───▼───────────────────────────┐   ┌───▼───────────────────────────┐   │
│   │    Distributed Unit 1 (DU-1)  │   │    Distributed Unit 2 (DU-2)  │   │
│   │  - RLC / MAC / L1             │   │  - RLC / MAC / L1             │   │
│   │  - Cell-1 (PCI: 1, rfsim)     │   │  - Cell-2 (PCI: 2, rfsim)     │   │
│   └───┬───────────────────────────┘   └───┬───────────────────────────┘   │
└───────┼───────────────────────────────────┼───────────────────────────┘
        │ rfsim :4043                       │ rfsim :4044
        ▼                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    VM-5 OAI nrUE (10.102.0.165)                        │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| VM | VM-4 | Virtual Machine index |
| Hostname | `oai-ran` | Host identifier |
| IP address | `10.102.0.167` | Static IP on thesis research subnet |
| Subnet | `10.102.0.0/24` | Main inter-VM communication network |
| Main role | 5G RAN (CU + 2 DUs/Cells + E2 Agent) | 3GPP Split CU-DU & O-RAN E2 Node |
| Recommended resources | 8 vCPU, 16 GB RAM, 50 GB Disk | CPU cores allocated to softmodem threads |
| Target RIC endpoint | `10.102.0.66:36421/SCTP` | VM-2 Near-RT RIC `ric_e2term` |
| Target Core AMF | `192.168.70.138:38412/SCTP` | VM-3 AMF via route `192.168.70.0/24` |
| Target Core UPF-1 | `192.168.70.142:2152/UDP` | Slice 1 eMBB user-plane gateway |
| Target Core UPF-2 | `192.168.70.143:2152/UDP` | Slice 2 Low-Latency user-plane gateway |

---

## 2. Theoretical & Standardization Rationale for RAN Parameters

The parameter values selected for VM-4 are grounded in 3GPP Release 16/17 and O-RAN Alliance specifications:

### 2.1 Single Network Slice Selection Assistance Information (S-NSSAI)
- **Standard:** **3GPP TS 23.501 Clause 5.15.2** and **3GPP TS 38.413 (NGAP)**.
- **Structure:** S-NSSAI consists of an 8-bit Slice/Service Type (SST, range `0-255`) and an optional 24-bit Slice Differentiator (SD, 3 octets / 6 hexadecimal digits).
  - Standardized SSTs: `1` (eMBB), `2` (URLLC), `3` (MIoT), `4` (V2X).
  - Operator-specific SSTs: Range `128` to `255`.
- **Selected Values:**
  - **Slice 1 (Throughput-Oriented / eMBB):** `SST = 1, SD = 0x000001` (decimal `1`). Standard eMBB slice mapped to `oai-upf-slice1` (`192.168.70.142`) with DNN `default`.
  - **Slice 2 (Low-Latency / Mission-Critical):** `SST = 222 (0xDE), SD = 0x00007B` (decimal `123`). Dedicated operator-specific slice mapped to `oai-upf-slice2` (`192.168.70.143`) with DNN `lowlatency`.
- **Constraint:** Must match identically between `slicing_base_config.yaml` (AMF on VM-3), `cu_gnb.conf` / `du_gnb*.conf` (VM-4), and `oai_db2.sql` (MySQL subscriber database). Any mismatch causes AMF to reject the gNB association during `NGSetup` or reject UE PDU Session Establishment with cause `UNKNOWN_OR_UNSUPPORTED_SNSSAI`.

### 2.2 Public Land Mobile Network (PLMN Identity)
- **Standard:** **3GPP TS 38.413** and **3GPP TS 23.003**.
- **Values:** `MCC = 208` (France country code), `MNC = 95` (OpenAirInterface test network code), `MNC Length = 2`.
- **Selected Global gNB ID:** Formed by combining PLMN `208.95` and gNB ID `0xe00` (decimal `3584`), yielding `gnb_208_095_00000e00` in O-RAN E2AP messages and Near-RT RIC DBaaS inventory.
- **Constraint:** Must match the PLMN served by AMF on VM-3. If PLMN is mismatched, AMF sends `NGSetupFailure` with cause `Unknown-PLMN`.

### 2.3 Tracking Area Code (TAC)
- **Standard:** **3GPP TS 24.501** (NAS protocol) and **3GPP TS 38.413**.
- **Value:** `0xa000` (hexadecimal) = `40960` (decimal).
- **Constraint:** The TAC is broadcasted in SIB1 by both DU cells. The AMF validates whether this TAC is registered in its supported tracking area list.

### 2.4 Physical Cell ID (PCI) & NR Cell Identity
- **Standard:** **3GPP TS 38.211** (Physical Channels and Modulation) and **3GPP TS 38.300**.
- **Values:**
  - **DU-1 / Cell-1:** `PCI = 1`, `nr_cellid = 12345678L`.
  - **DU-2 / Cell-2:** `PCI = 2`, `nr_cellid = 11111111L`.
- **Rationale:** 
  - NR defines 1008 distinct PCIs ($0 \le N_{ID}^{cell} \le 1007$). Assigning distinct PCIs (`1` and `2`) prevents Primary and Secondary Synchronization Signal (PSS/SSS) interference.
  - Distinct `nr_cellid` values allow CU RRC, Core AMF, and Near-RT RIC xApps (such as Traffic Steering xApp) to unambiguously identify the source cell and target cell during handover scenarios.

### 2.5 3GPP F1 Transport & Loopback Aliasing
- **Standard:** **3GPP TS 38.470 / TS 38.473** (F1-C over SCTP port 38472) and **3GPP TS 38.474** (F1-U over GTP-U UDP port 2153).
- **Rationale:** Because CU, DU-1, and DU-2 execute as separate Linux processes on the same host (VM-4), binding all three processes to `127.0.0.1:2153` triggers a socket binding collision (`bind: Address already in use`). 
- **Solution:** Loopback IP aliasing and port differentiation:
  - CU listens on `127.0.0.1:2153`.
  - DU-1 binds F1 to `127.0.0.1:2155` (`local_n_portd = 2155`).
  - DU-2 binds F1 to `127.0.0.1:2154` (`local_n_portd = 2154`).

### 2.6 RFsimulator (rfsim) Channel Emulation
- **Mechanism:** OAI RFsimulator bypasses SDR hardware (USRP) and creates an in-memory/socket RF channel using TCP sockets.
- **Port Allocation:** DU-1 listens on TCP port `4043`; DU-2 listens on TCP port `4044`.
- **Purpose:** Enables VM-5 (`oai-nrue`) to connect multiple simulated UEs to either Cell-1 or Cell-2 over the network by specifying `--rfsimulator.serverport 4043` or `4044`.

### 2.7 O-RAN E2 Interface & FlexRIC Service Models
- **Standard:** **O-RAN.WG3.E2AP-v02.03**.
- **Service Models:** The E2 Agent embeds 8 Service Models:
  1. `kpm_sm` (E2SM-KPM v2, ID: 2) — RAN metric collection (PRB usage, throughput).
  2. `rc_sm` (E2SM-RC v1, ID: 3) — RAN Control (traffic steering, handover trigger).
  3. `slice_sm` (ID: 145) — Slicing resource quota and scheduling policy.
  4. `mac_sm` (ID: 142), `rlc_sm` (ID: 143), `pdcp_sm` (ID: 144) — Layer 2 metrics.
  5. `tc_sm` (ID: 146) — Traffic conditioning.
  6. `gtp_sm` (ID: 148) — GTP-U tunnel statistics.

---

## 3. Parameter Customization Reference Guide

Use this guide when adapting configuration parameters for custom experiments:

| Parameter | Current Value | Classification | Customization Rules & Impact |
|---|---|---|---|
| `mcc` | `208` | `[MANDATORY MATCH 5GC/UE]` | Mobile Country Code. Must match AMF `slicing_base_config.yaml` and UE SIM database. |
| `mnc` | `95` | `[MANDATORY MATCH 5GC/UE]` | Mobile Network Code. Must match AMF `slicing_base_config.yaml` and UE SIM database. |
| `tracking_area_code` | `0xa000` (40960) | `[MANDATORY MATCH 5GC]` | Tracking Area Code. Must be in AMF supported TAC list. |
| `snssaiList.sst` | `1`, `222` | `[MANDATORY MATCH 5GC/UE]` | Slice/Service Type. Must match AMF, SMF, UPF, and UE SIM profile. |
| `snssaiList.sd` | `0x000001`, `0x00007B` | `[MANDATORY MATCH 5GC/UE]` | Slice Differentiator. Must match AMF, SMF, and UE SIM profile. |
| `physCellId` | `1` (DU-1), `2` (DU-2) | `[CUSTOMIZABLE]` | Physical Cell ID (0–1007). Must remain distinct between cells in same coverage area. |
| `nr_cellid` | `12345678L`, `11111111L`| `[CUSTOMIZABLE]` | 36-bit NR Cell Identity. Must remain distinct for handover and RIC steering identification. |
| `serverport` (rfsim) | `4043` (DU-1), `4044` (DU-2) | `[CUSTOMIZABLE]` | RFsim TCP server port. Must match UE connection argument on VM-5. |
| `amf_ip_address` | `192.168.70.138` | `[CUSTOMIZABLE]` | AMF container IP reachable via static route `192.168.70.0/24 via 10.102.0.164` (or `10.102.0.164` if host port forwarding). |
| `GNB_IPV4_ADDRESS_FOR_NG_AMF` | `10.102.0.167` | `[CUSTOMIZABLE]` | VM-4 local interface IP for N2 SCTP traffic. |
| `GNB_IPV4_ADDRESS_FOR_NGU` | `10.102.0.167` | `[CUSTOMIZABLE]` | VM-4 local interface IP for N3 GTP-U traffic to UPF. |
| `near_ric_ip_addr` | `10.102.0.66` | `[CUSTOMIZABLE]` | VM-2 Near-RT RIC IP where E2Term port 36421 is reachable. |
| `local_s_portd` / `remote_s_portd` | `2153` | `[FIXED / ARCHITECTURE]` | F1-U GTP-U UDP port. Kept at 2153 per 3GPP/OAI default. |
| `GNB_PORT_FOR_S1U` | `2152` | `[FIXED / ARCHITECTURE]` | 3GPP standard N3 GTP-U port (UDP 2152). |
| `sm_dir` | `/usr/local/lib/flexric/`| `[FIXED / ARCHITECTURE]` | Path where compiled Service Model `.so` plugins are installed. |

---

## 4. Directory Layout

Working directories on VM-4:

```text
/opt/oran/ran/
├── openairinterface5g/       # Official OAI repository
└── conf/
    ├── cu_gnb.conf           # CU configuration with E2 Agent & 5GC links
    ├── du_gnb1.conf          # DU-1 (Cell-1, PCI 1, rfsim port 4043)
    └── du_gnb2.conf          # DU-2 (Cell-2, PCI 2, rfsim port 4044)
```

---

## 5. Host Prerequisites & Routing Setup

### Step 1: Install Kernel Dependencies & Tools
```bash
sudo apt update && sudo apt install -y \
  build-essential \
  gcc-12 \
  g++-12 \
  cmake \
  ninja-build \
  git \
  libsctp-dev \
  lksctp-tools \
  iproute2 \
  net-tools \
  tshark

# Set GCC 12 as default compiler (prevents GCC 11 ICE bug with FlexRIC Service Models)
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 100 --slave /usr/bin/g++ g++ /usr/bin/g++-12
sudo update-alternatives --install /usr/bin/cc cc /usr/bin/gcc 100
sudo update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++ 100

# Ensure SCTP kernel module is loaded
sudo modprobe sctp
echo "sctp" | sudo tee -a /etc/modules-load.d/sctp.conf
```

### Step 2: Configure Static Route to VM-3 5GC Bridge Subnet
VM-4 must reach the OAI 5GC containers (`192.168.70.0/24`) hosted on VM-3 (`10.102.0.164`):

```bash
# Add route immediately (interface is auto-selected based on gateway 10.102.0.164)
sudo ip route add 192.168.70.0/24 via 10.102.0.164

# Persist route across reboots
echo "up ip route add 192.168.70.0/24 via 10.102.0.164" | sudo tee -a /etc/network/interfaces.d/5gc-route || true
```

### Step 3: Test Inter-VM Reachability
```bash
# Test reachability to VM-2 Near-RT RIC
ping -c 2 10.102.0.66

# Test reachability to VM-3 5GC Host
ping -c 2 10.102.0.164

# Test routed reachability to VM-3 AMF Container
ping -c 2 192.168.70.138
```

---

## 6. Obtain OAI Repository & Build with E2 Agent Support

### Step 1: Obtain the OAI Source Code

Two options are supported to download the OAI source code:

#### Option A: Shallow Git Clone
```bash
sudo mkdir -p /opt/oran/ran
sudo chown -R "$USER":"$USER" /opt/oran/ran
cd /opt/oran/ran

# Configure Git buffer and protocol settings
git config --global http.version HTTP/1.1
git config --global http.postBuffer 524288000
git config --global core.compression 0

git clone --depth 1 -b develop https://github.com/OPENAIRINTERFACE/openairinterface5g.git
cd openairinterface5g
git submodule update --init --depth 1 openair2/E2AP/flexric
```

#### Option B: Fast Tarball Download & FlexRIC Shallow Clone
If Git clone encounters TLS timeouts or network throttling, download the source tarball (~25 MB) and shallow clone FlexRIC (~8.5 MB):
```bash
sudo mkdir -p /opt/oran/ran
sudo chown -R "$USER":"$USER" /opt/oran/ran
cd /opt/oran/ran

# 1. Download and extract OAI source
wget -c https://github.com/duranta-project/openairinterface5g/archive/refs/heads/develop.tar.gz -O oai-develop.tar.gz
mkdir -p openairinterface5g
tar -xzf oai-develop.tar.gz -C openairinterface5g --strip-components=1

# 2. Shallow clone FlexRIC submodule for E2 Agent support
git clone --depth 1 https://gitlab.eurecom.fr/mosaic5g/flexric.git openairinterface5g/openair2/E2AP/flexric
```

### Step 2: Install OAI Dependencies
```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets
./build_oai -I
```

> [!TIP]
> **SIMDe Header Verification:**  
> If `build_helper` encounters a timeout (`curl 28`) when cloning `simde-no-tests`, install the SIMDe header files manually (SIMDe is a header-only library):
> ```bash
> sudo apt install -y libsimde-dev || {
>   sudo rm -rf /tmp/simde
>   git clone --depth 1 https://github.com/simd-everywhere/simde-no-tests.git /tmp/simde
>   sudo cp -r /tmp/simde/simde /usr/include/
> }
> ls -d /usr/include/simde
> ```

### Step 3: Build gNB Softmodem with E2 Agent and RFsimulator

> [!WARNING]
> **GCC 11 Internal Compiler Error with FlexRIC `kpm_sm`:**  
> The default `gcc-11` on Ubuntu 22.04 crashes with a segmentation fault (`internal compiler error: Segmentation fault in kpm_dec_generic.h`) when compiling the KPM Service Model due to an RTL expansion bug with C11 `_Generic`.  
> Upgrade to `gcc-12` before building the Service Models (see [Troubleshooting Case 27](../troubleshooting/ran-ue.md#case-27-gcc-11-internal-compiler-error-segmentation-fault-on-flexric-kpm_sm-_generic-macro)):
> ```bash
> sudo apt update && sudo apt install -y gcc-12 g++-12
> sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 100 --slave /usr/bin/g++ g++ /usr/bin/g++-12
> sudo update-alternatives --install /usr/bin/cc cc /usr/bin/gcc 100
> sudo update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++ 100
> gcc --version
> ```

Compile `nr-softmodem` with O-RAN E2 Agent support (`--build-e2`) and RFsimulator (`-w SIMU`):

```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets
./build_oai -w SIMU --gNB --build-e2 --ninja
```

Compile and install FlexRIC Service Models (SM) shared libraries:
```bash
# Build all Service Model shared libraries
ninja -C /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build mac_sm rlc_sm pdcp_sm slice_sm kpm_sm rc_sm gtp_sm tc_sm

# Install Service Models to /usr/local/lib/flexric/
sudo mkdir -p /usr/local/lib/flexric
sudo cp $(find /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build -name "*_sm.so") /usr/local/lib/flexric/

# Verify installed Service Models
ls -la /usr/local/lib/flexric/
```

Verify the compiled binary exists:
```bash
ls -la /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build/nr-softmodem
```

---

## 7. Configuration Files Setup

Create the configuration directory:
```bash
mkdir -p /opt/oran/ran/conf
```

### 1. Centralized Unit (CU) Configuration (`cu_gnb.conf`)

Save this file to `/opt/oran/ran/conf/cu_gnb.conf`:

```hcl
Active_gNBs = ("gNB-CU");
Asn1_verbosity = "none";

gNBs =
(
 {
    # [CUSTOMIZABLE] Node identifier (0xe00 = decimal 3584)
    gNB_ID = 0xe00;
    # [CUSTOMIZABLE] Human-readable CU name
    gNB_name = "gNB-CU";

    # [MANDATORY MATCH 5GC] Tracking Area Code (0xa000 = decimal 40960)
    tracking_area_code = 0xa000;

    # [MANDATORY MATCH 5GC] PLMN identity and supported slices
    plmn_list = ({
      mcc = 208;                          # [MANDATORY MATCH 5GC] MCC
      mnc = 95;                           # [MANDATORY MATCH 5GC] MNC
      mnc_length = 2;                     # [MANDATORY MATCH 5GC] MNC length
      snssaiList = (
        { sst = 1; sd = 0x000001; },      # [MANDATORY MATCH 5GC] Slice 1: eMBB
        { sst = 222; sd = 0x00007B; }     # [MANDATORY MATCH 5GC] Slice 2: Low Latency
      );
    });

    # [CUSTOMIZABLE] NR Cell Identity for Serving Cell
    nr_cellid = 12345678L;

    # [FIXED / ARCHITECTURE] 3GPP F1 transport configuration
    tr_s_preference  = "f1";
    local_s_address  = "127.0.0.3";       # [FIXED] CU F1 listening IP
    remote_s_address = "0.0.0.0";         # [FIXED] Accept F1 from any DU
    local_s_portd    = 2153;              # [FIXED] F1-U listening UDP port
    remote_s_portd   = 2153;

    SCTP :
    {
        SCTP_INSTREAMS  = 2;
        SCTP_OUTSTREAMS = 2;
    };

    # [CUSTOMIZABLE] AMF IPv4 endpoint (direct container IP via route 192.168.70.0/24 or host IP 10.102.0.164)
    amf_ip_address = ({ ipv4 = "192.168.70.138"; });

    # [CUSTOMIZABLE] Network interfaces for N2 (AMF) and N3 (UPF)
    NETWORK_INTERFACES =
    {
        GNB_IPV4_ADDRESS_FOR_NG_AMF = "10.102.0.167";  # [CUSTOMIZABLE] VM-4 IP for N2
        GNB_IPV4_ADDRESS_FOR_NGU    = "10.102.0.167";  # [CUSTOMIZABLE] VM-4 IP for N3
        GNB_PORT_FOR_S1U            = 2152;           # [FIXED] 3GPP standard N3 port
    };
 }
);

security = {
  ciphering_algorithms = ( "nea0" );
  integrity_algorithms = ( "nia2", "nia0" );
  drb_ciphering = "yes";
  drb_integrity = "no";
};

log_config :
{
  # [CUSTOMIZABLE] Log verbosity: "none", "error", "warn", "info", "debug", "trace"
  global_log_level = "info";
  pdcp_log_level   = "info";
  rrc_log_level    = "info";
  f1ap_log_level   = "info";
  ngap_log_level   = "info";
};

# [MANDATORY MATCH RIC] O-RAN E2 Agent pointing to VM-2 Near-RT RIC
e2_agent = {
  near_ric_ip_addr = "10.102.0.66";              # [CUSTOMIZABLE] VM-2 Near-RT RIC IP
  sm_dir = "/usr/local/lib/flexric/";            # [FIXED] Service Model directory
};
```

---

### 2. Distributed Unit 1 Configuration (`du_gnb1.conf`) — Cell-1

Save this file to `/opt/oran/ran/conf/du_gnb1.conf` (derived from `gnb-du.sa.band78.106prb.rfsim.conf`):

```hcl
Active_gNBs = ( "du-rfsim1");
Asn1_verbosity = "none";

gNBs =
(
 {
    # [CUSTOMIZABLE] DU Identifier (0xe01 = decimal 3585)
    gNB_DU_ID = 0xe01;
    # [CUSTOMIZABLE] DU name
    gNB_name = "du-rfsim1";

    # [MANDATORY MATCH 5GC] Tracking Area Code
    tracking_area_code = 0xa000;

    # [MANDATORY MATCH 5GC] PLMN identity and supported slices
    plmn_list = ({
      mcc = 208;
      mnc = 95;
      mnc_length = 2;
      snssaiList = (
        { sst = 1; sd = 0x000001; },
        { sst = 222; sd = 0x00007B; }
      );
    });

    # [CUSTOMIZABLE] NR Cell Identity (Cell-1)
    nr_cellid = 12345678L;
    # [CUSTOMIZABLE] Physical Cell ID (PCI: 1)
    physCellId = 1;

    # [FIXED / ARCHITECTURE] 3GPP F1 transport configuration
    tr_s_preference  = "f1";
    local_n_address  = "127.0.0.4";       # [FIXED] Local DU-1 F1 IP
    remote_n_address = "127.0.0.3";       # [FIXED] Remote CU F1 IP
    local_n_portd    = 2153;              # [FIXED] Standard F1-U port (differentiated by IP alias)
    remote_n_portd   = 2153;              # [FIXED] Remote CU F1-U UDP port
 }
);

# [CUSTOMIZABLE] RFsimulator TCP server listening port for Cell-1
rfsimulator :
{
    serverport = 4043;                    # [CUSTOMIZABLE] VM-5 nrUE connects here
};
```

---

### 3. Distributed Unit 2 Configuration (`du_gnb2.conf`) — Cell-2

Save this file to `/opt/oran/ran/conf/du_gnb2.conf`:

```hcl
Active_gNBs = ( "du-rfsim2");
Asn1_verbosity = "none";

gNBs =
(
 {
    # [CUSTOMIZABLE] DU Identifier (0xe02 = decimal 3586)
    gNB_DU_ID = 0xe02;
    # [CUSTOMIZABLE] DU name
    gNB_name = "du-rfsim2";

    # [MANDATORY MATCH 5GC] Tracking Area Code
    tracking_area_code = 0xa000;

    # [MANDATORY MATCH 5GC] PLMN identity and supported slices
    plmn_list = ({
      mcc = 208;
      mnc = 95;
      mnc_length = 2;
      snssaiList = (
        { sst = 1; sd = 0x000001; },
        { sst = 222; sd = 0x00007B; }
      );
    });

    # [CUSTOMIZABLE] NR Cell Identity (Cell-2, target for handover)
    nr_cellid = 11111111L;
    # [CUSTOMIZABLE] Physical Cell ID (PCI: 2)
    physCellId = 2;

    # [FIXED / ARCHITECTURE] 3GPP F1 transport configuration
    tr_s_preference  = "f1";
    local_n_address  = "127.0.0.1";       # [FIXED] Local DU F1 IP
    remote_n_address = "127.0.0.1";       # [FIXED] Remote CU F1 IP
    local_n_portd    = 2154;              # [FIXED] Port differentiation to avoid collision
    remote_n_portd   = 2153;              # [FIXED] Remote CU F1-U UDP port
 }
);

# [CUSTOMIZABLE] RFsimulator TCP server listening port for Cell-2
rfsimulator :
{
    serverport = 4044;                    # [CUSTOMIZABLE] Target cell for Traffic Steering
};
```

---

## 8. Automated Script to Generate `du_gnb1.conf` and `du_gnb2.conf`

To generate exact configuration files directly from the OAI template:

```bash
python3 - << 'EOF'
with open("/opt/oran/ran/openairinterface5g/ci-scripts/conf_files/gnb-du.sa.band78.106prb.rfsim.conf") as f:
    tpl = f.read()

# DU-1 (Cell-1, PCI 1, RFsim port 4043)
du1 = tpl.replace('"du-rfsim"', '"du-rfsim1"')
du1 = du1.replace('gNB_DU_ID = 0xe00;', 'gNB_DU_ID = 0xe01;')
du1 = du1.replace('physCellId                                                    = 0;', 'physCellId                                                    = 1;')
du1 = du1.replace('tracking_area_code  =  1;', 'tracking_area_code  =  0xa000;')
du1 = du1.replace('plmn_list = ({ mcc = 208; mnc = 99; mnc_length = 2; snssaiList = ({ sst = 1 }, { sst = 2 }, { sst = 3 } ) });',
                  'plmn_list = ({ mcc = 208; mnc = 95; mnc_length = 2; snssaiList = ({ sst = 1, sd = 0x000001 }, { sst = 222, sd = 0x00007B }) });')
du1 = du1.replace('local_n_address = "192.168.71.171";', 'local_n_address = "127.0.0.4";')
du1 = du1.replace('remote_n_address = "192.168.71.150";', 'remote_n_address = "127.0.0.3";')
du1 = du1.replace('local_n_portd   = 2153;', 'local_n_portd   = 2153;')
du1 = du1.replace('remote_n_portd  = 2153;', 'remote_n_portd  = 2153;')
du1 = du1.replace('serverport = 4043;', 'serverport = 4043;')

with open("/opt/oran/ran/conf/du_gnb1.conf", "w") as f:
    f.write(du1)

# DU-2 (Cell-2, PCI 2, RFsim port 4044)
du2 = tpl.replace('"du-rfsim"', '"du-rfsim2"')
du2 = du2.replace('gNB_DU_ID = 0xe00;', 'gNB_DU_ID = 0xe02;')
du2 = du2.replace('nr_cellid = 12345678L;', 'nr_cellid = 11111111L;')
du2 = du2.replace('physCellId                                                    = 0;', 'physCellId                                                    = 2;')
du2 = du2.replace('tracking_area_code  =  1;', 'tracking_area_code  =  0xa000;')
du2 = du2.replace('plmn_list = ({ mcc = 208; mnc = 99; mnc_length = 2; snssaiList = ({ sst = 1 }, { sst = 2 }, { sst = 3 } ) });',
                  'plmn_list = ({ mcc = 208; mnc = 95; mnc_length = 2; snssaiList = ({ sst = 1, sd = 0x000001 }, { sst = 222, sd = 0x00007B }) });')
du2 = du2.replace('local_n_address = "192.168.71.171";', 'local_n_address = "127.0.0.5";')
du2 = du2.replace('remote_n_address = "192.168.71.150";', 'remote_n_address = "127.0.0.3";')
du2 = du2.replace('local_n_portd   = 2153;', 'local_n_portd   = 2153;')
du2 = du2.replace('remote_n_portd  = 2153;', 'remote_n_portd  = 2153;')
du2 = du2.replace('serverport = 4043;', 'serverport = 4044;')

with open("/opt/oran/ran/conf/du_gnb2.conf", "w") as f:
    f.write(du2)
print("Configuration files du_gnb1.conf and du_gnb2.conf generated successfully.")
EOF
```

---

## 9. Execution Order & Service Startup

Start the components in sequence:

### Step 1: Start Centralized Unit (CU)
```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf \
  --e2_agent.near_ric_ip_addr 10.102.0.66 \
  --e2_agent.sm_dir /usr/local/lib/flexric/ \
  2>&1 | tee /opt/oran/ran/cu.log
```

### Step 2: Start Distributed Unit 1 (DU-1 / Cell-1)
```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-softmodem -O /opt/oran/ran/conf/du_gnb1.conf --rfsim 2>&1 | tee /opt/oran/ran/du1.log
```

### Step 3: Start Distributed Unit 2 (DU-2 / Cell-2)
```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-softmodem -O /opt/oran/ran/conf/du_gnb2.conf --rfsim 2>&1 | tee /opt/oran/ran/du2.log
```

---

### 9.1 Automated Background Daemon Scripts (`start_ran.sh` & `stop_ran.sh`)

To execute the Split RAN components cleanly and automatically in the background without maintaining multiple interactive terminal sessions, use the automation scripts managed in [`scripts/`](../../scripts):

* **Launcher Script:** [`scripts/start_ran.sh`](../../scripts/start_ran.sh) (deployed on VM-4 at `/opt/oran/ran/start_ran.sh`)
* **Stopper Script:** [`scripts/stop_ran.sh`](../../scripts/stop_ran.sh) (deployed on VM-4 at `/opt/oran/ran/stop_ran.sh`)

#### Execution Commands on VM-4 (`five-g@oai-ran`):
```bash
# 1. Start all RAN components (CU, DU-1, DU-2) staged sequentially in the background:
/opt/oran/ran/start_ran.sh

# 2. Terminate all running RAN processes:
/opt/oran/ran/stop_ran.sh

# 3. Monitor real-time component logs:
tail -f /opt/oran/ran/cu.log
tail -f /opt/oran/ran/du1.log
tail -f /opt/oran/ran/du2.log
```

---

## 10. Acceptance Criteria & Validation

All acceptance criteria have been verified on VM-4:

1. **Routing to VM-3 5GC Bridge Subnet [VALIDATED]:**
   ```bash
   ping -c 2 192.168.70.138
   # Output: 2 packets transmitted, 2 received, 0% packet loss
   ```

2. **NGAP (N2) Association with AMF Established [VALIDATED]:**
   ```bash
   grep -E "NGSetupResponse|associated AMF" /opt/oran/ran/cu.log
   # Output:
   # [NGAP]   Received NGSetupResponse from AMF
   # [GNB_APP] [gNB 0] Received NGAP_REGISTER_GNB_CNF: associated AMF 1
   ```

3. **Dual-Cell F1 Associations Active & In Service [VALIDATED]:**
   ```bash
   grep -E "Added cell|is in service" /opt/oran/ran/cu.log
   # Output:
   # [NR_RRC] Added cell 12345678 to DU cells array (total cells = 1)
   # [NR_RRC] cell PLMN 208.95 Cell ID 12345678 is in service
   # [NR_RRC] Added cell 11111111 to DU cells array (total cells = 2)
   # [NR_RRC] cell PLMN 208.95 Cell ID 11111111 is in service
   ```

4. **E2 Connection to Near-RT RIC Established [VALIDATED]:**
   Querying the Near-RT RIC E2 inventory on VM-2 (`10.102.0.66`):
   ```bash
   curl -s http://10.0.2.11:3800/v1/e2t/list | jq .
   # Output:
   # [
   #   {
   #     "e2tAddress": "10.0.2.10:38000",
   #     "ranNames": [
   #       "gnb_208_095_00000e00"
   #     ]
   #   }
   # ]
   ```
   And checking `ric_e2mgr` connection status:
   ```text
   #RanConnectStatusChangeManager.ChangeStatus - RAN name: gnb_208_095_00000e00, currentStatus: UNKNOWN_CONNECTION_STATUS, nextStatus: CONNECTED
   #ranListManagerInstance.AddNbIdentity - RAN name: gnb_208_095_00000e00 - Successfully added nodeb identity
   ```

5. **RFsimulator Server Ports Listening [VALIDATED]:**
   - DU-1 (Cell-1, PCI 1): listening on TCP port `4043`.
   - DU-2 (Cell-2, PCI 2): listening on TCP port `4044`.
   Ready for multi-UE attachment from VM-5 (`oai-nrue`).

---

## 11. Extension Guide: Adding a New Network Slice to RAN (CU/DU)

To configure CU and DUs to advertise and support an additional slice (e.g., **Slice 3 — Massive IoT**, `SST = 3`, `SD = 0x000003`):

### Step 1: Update CU Configuration (`/opt/oran/ran/conf/cu_gnb.conf`)
Under `gNBs.plmn_list[0].snssaiList`, append the new S-NSSAI:
```hcl
      snssaiList = (
        { sst = 1; sd = 0x000001; },      # Slice 1: eMBB
        { sst = 222; sd = 0x00007B; },    # Slice 2: Low Latency
        { sst = 3; sd = 0x000003; }       # Slice 3: IoT / Custom [NEW]
      );
```

### Step 2: Update DU Configurations (`/opt/oran/ran/conf/du_gnb1.conf` & `du_gnb2.conf`)
Append the slice to `snssaiList` in `du_gnb1.conf` (for Cell-1) and/or `du_gnb2.conf` (for Cell-2):
```hcl
    plmn_list = ({
      mcc = 208;
      mnc = 95;
      mnc_length = 2;
      snssaiList = (
        { sst = 1, sd = 0x000001 },
        { sst = 222, sd = 0x00007B },
        { sst = 3, sd = 0x000003 }        # Slice 3: IoT / Custom [NEW]
      );
    });
```

### Step 3: Restart Services & Verify NGAP Association
Restart CU and DUs in sequence:
```bash
# In CU terminal
sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf 2>&1 | tee /opt/oran/ran/cu.log

# In DU-1 and DU-2 terminals
sudo ./nr-softmodem -O /opt/oran/ran/conf/du_gnb1.conf --rfsim 2>&1 | tee /opt/oran/ran/du1.log
sudo ./nr-softmodem -O /opt/oran/ran/conf/du_gnb2.conf --rfsim 2>&1 | tee /opt/oran/ran/du2.log
```
*Verification:* Inspect `/opt/oran/ran/cu.log` to confirm that `NGSetupResponse` from AMF acknowledges all three slices without rejection.

---

## 12. RAN Fault Injection & Baseline Handover Modes

VM-4 hosts the dual-cell radio environment (DU-1 on PCI 1 and DU-2 on PCI 2) used to simulate radio congestion and evaluate inter-cell traffic steering.

### 12.1 Radio Bottleneck Injection Procedure
To simulate a pure RAN radio bottleneck during baseline experiments:

```bash
# Inject 80 Mbps UDP saturation load on Cell-1 (DU-1 port 4043)
# This forces DU-1 PRB utilization to exceed 90% while Cell-2 remains idle (<15%)
iperf3 -u -c 12.1.1.2 -b 80M -t 120
```

*Verification:* In Near-RT RIC telemetry (E2SM-KPM / Prometheus), observe:
- `cell1_prb_utilization` > 0.90
- `cell2_prb_utilization` < 0.15
- Slice 1 packet delay at MAC layer increases significantly.

### 12.2 Handover Execution Modes per Baseline

| Baseline ID | Handover Mechanism | Control Entity | E2SM-RC Involvement |
|---|---|---|---|
| **B0** | Standard 3GPP RRC A3 Event | Internal OAI CU RRC logic | Disabled (RIC does not issue E2 control). Handover triggers only if RSRP delta exceeds `handover_margin`. |
| **B1** | Dynamic Radio Handover | Near-RT RIC xApp | Enabled. xApp issues E2SM-RC Handover to Cell-2 when Cell-1 PRB > 80%. |
| **B2** | Prohibited | N/A | Disabled. UEs remain anchored on Cell-1. |
| **B3** | Uncoordinated Handover | Independent xApp | Enabled. Disregards Core congestion state. |
| **B4** | Fixed Priority Handover | rApp-directed xApp | Enabled. Triggered as primary step regardless of bottleneck origin. |
| **Proposed** | Bottleneck-Aware Handover | rApp-constrained xApp | **Selectively Enabled.** Executed only when `RAN_BOTTLENECK` is diagnosed. Inhibited during `CORE_BOTTLENECK`. |

---

## References
- 3GPP TS 23.501: System architecture for the 5G System (Stage 2)
- 3GPP TS 38.413: NG-RAN; NG Application Protocol (NGAP)
- 3GPP TS 38.470 / TS 38.473: NG-RAN; F1 general aspects, principles, and F1AP
- 3GPP TS 38.211: NR; Physical channels and modulation (PCI)
- O-RAN WG3: E2 Application Protocol (E2AP) v02.03 & E2SM-RC v01.03
- OpenAirInterface 5G RAN Repository: https://gitlab.eurecom.fr/oai/openairinterface5g


