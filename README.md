# Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks

> **Thesis Research Title:**  
> *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*  
> *(Pengarahan Trafik Berbasis Identifikasi Bottleneck melalui Koordinasi O-RAN RIC–NWDAF dengan Kendali Closed-Loop pada Jaringan 5G Multi-Slice)*

This repository contains the architecture, configuration, deployment procedures, and experimental evaluation artifacts for a **software-only, cross-domain O-RAN and 5G Core experimental platform**. The platform enables empirical investigation into **closed-loop bottleneck diagnosis (RAN vs. Core user plane vs. Joint)** and adaptive traffic steering across multiple 5G network slices through coordinated interaction between an O-RAN Non-RT RIC rApp, Near-RT RIC xApp, and 3GPP NWDAF / Core user-plane adapters.

The platform is deployed entirely on virtual machines connected over a dedicated private network (`10.102.0.0/24`), requiring **no physical SDR hardware or commercial UEs**, ensuring complete reproducibility for experimental academic research.

---

## 1. System Architecture Overview

The experimental testbed implements a fully disaggregated, standards-compliant O-RAN and 3GPP Release 16/17 network divided across 6 dedicated virtual machines:

![System Architecture Overview](docs/diagram/System%20Architecture%20Overview.png)

---

## 2. Bottleneck-Aware Closed-Loop Control & Research Framework

The core contribution of this thesis is the **cross-domain closed-loop coordination mechanism** that resolves the fundamental blind spot between RAN and Core domains:

1. **The Problem of Domain Myopia:**
   - When radio resources are constrained, changing Core user-plane paths is ineffective.
   - When the Core user plane (UPF / transport) is congested, allocating additional PRBs in the RAN or triggering blind radio handovers is futile and can exacerbate ping-pong instability.
   - When both domains experience simultaneous congestion, independent uncoordinated controllers make conflicting decisions that destabilize slice SLAs.
2. **Closed-Loop MAPE-K Lifecycle:**
   - **Monitor:** Collects synchronized multi-slice telemetry from the RAN (via E2SM-KPM / E2SM-SLICE) and the 5G Core (via NWDAF / Core user-plane telemetry).
   - **Analyze (Bottleneck Diagnosis):** The rApp runs an explainable classification engine (Rule-Based / Decision Tree) to categorize system state into: `NORMAL`, `RAN_BOTTLENECK`, `CORE_BOTTLENECK`, or `JOINT_BOTTLENECK`.
   - **Plan (Action Selection):** Dispatches targeted A1 policy constraints to the Near-RT RIC xApp and/or user-plane rate-limiting/shaping constraints to the Core adapter.
   - **Execute (Actuation):** The xApp executes inter-cell traffic steering (Cell-1 $\leftrightarrow$ Cell-2) via E2SM-RC, while the Core adapter enforces user-plane conditioning.
   - **Verify (Closed-Loop Recovery):** Compares pre- and post-actuation SLA compliance ($V_s$, latency p95/p99) to confirm service recovery and prevent action churn.

---

## 3. Expected End-to-End Communication Lifecycle

The complete operational flow of the experimental testbed executes in five orchestrated phases:

```mermaid
sequenceDiagram
    autonumber
    participant Core as VM-3: OAI 5GC + NWDAF
    participant RAN as VM-4: OAI RAN (CU/DUs)
    participant RIC as VM-2: Near-RT RIC (xApp)
    participant NonRT as VM-1: Non-RT RIC (rApp)
    participant UE as VM-5: OAI nrUE
    participant Mon as VM-6: Telemetry/DB

    Note over Core,RAN: Phase 1: Core & RAN Initialization
    RAN->>Core: N2 NGSetupRequest (PLMN: 208.95, TAC: 0xa000, Slices: [1:1, 222:123])
    Core-->>RAN: N2 NGSetupResponse (AMF Associated)
    RAN->>RAN: F1 Setup DU-1 (PCI 1, Port 4043) & DU-2 (PCI 2, Port 4044)

    Note over RAN,RIC: Phase 2: O-RAN E2 Setup Procedure
    RAN->>RIC: E2SetupRequest (Global gNB ID: gnb_208_095_00000e00, 8x SMs)
    RIC->>RIC: DBaaS RNIB Node Registration (Status: CONNECTED)
    RIC-->>RAN: E2SetupResponse (Global RIC ID: AACCE)

    Note over NonRT,RIC: Phase 3: A1 Policy Synchronization & Baseline Distribution
    NonRT->>RIC: PUT /A1-P/v2/policytypes/20008/policies/ts-pol-01 (Thresholds & SLA Bounds)
    RIC->>RIC: A1 Mediator forwards policy via RMR (mtype 20010) to xApp
    RIC-->>NonRT: Policy Accepted & Status ENFORCED (mtype 20011 RTS)

    Note over UE,Core: Phase 4: Multi-UE Sliced PDU Session Establishment
    UE->>RAN: Attach over RFsimulator (Cell-1 :4043)
    UE->>Core: NAS Registration & PDU Session 1 (S-NSSAI: 1:1, DNN: default)
    Core-->>UE: PDU Session Established (UPF-1: 192.168.70.142)
    UE->>Core: PDU Session 2 (S-NSSAI: 222:123, DNN: lowlatency)
    Core-->>UE: PDU Session Established (UPF-2: 192.168.70.143)

    Note over Core,NonRT: Phase 5: Cross-Domain Closed-Loop Diagnosis, Steering & Verification
    RIC->>RAN: E2 Subscription Request (E2SM-KPM ID: 2, Interval: 100ms)
    RAN-->>RIC: Periodic E2SM-KPM Telemetry (PRB usage per slice, CQI, packet delay)
    Core-->>NonRT: NWDAF / Core Telemetry (SliceLoadLevel, UPF queuing delay, packet loss)
    NonRT->>NonRT: rApp classifies bottleneck location (RAN vs Core vs Joint)
    NonRT->>RIC: Update A1 Policy (Targeted steering constraints & slice weights)
    RIC->>RAN: E2 Control Request (E2SM-RC ID: 3: Handover UE to Cell-2 if RAN bottleneck)
    RAN->>UE: RRC Reconfiguration (Handover to Cell-2 PCI 2 :4044)
    NonRT->>NonRT: Verify SLA recovery; suppress ineffective action churn
    RAN-->>Mon: Stream radio telemetry to Prometheus
    Core-->>Mon: Stream core user-plane metrics to Prometheus
    RIC-->>Mon: Log closed-loop decisions and SLA recovery timestamps
```

---

## 4. Virtual Machine Specifications & Topology

All virtual machines run on Ubuntu 22.04 LTS interconnected via static IP assignments:

| VM | Hostname | IP Address | vCPU | RAM | Disk | Key Assigned Services |
|---|---|---|:---:|:---:|:---:|---|
<<<<<<< HEAD
| **VM-1** | `nonrt-ric` | `10.102.0.168` | 4 | 8 GB | 30 GB | Non-RT RIC, A1 PMS v2.6.0, Bottleneck-Aware Coordinator rApp |
| **VM-2** | `near-rt-ric` | `10.102.0.66` | 6 | 12 GB | 40 GB | Minimal Near-RT RIC, A1 Mediator, xApp, E2Term, E2Mgr, DBaaS Redis 5.0.9 |
| **VM-3** | `oai-5gc` | `10.102.0.164` | 4 | 8 GB | 30 GB | OAI 5GC Multi-Slice (AMF, SMF-1/2, UPF-1/2, NRF, UDM, MySQL) + NWDAF / Core Adapter |
| **VM-4** | `oai-ran` | `10.102.0.167` | 8 | 16 GB | 50 GB | OAI 5G RAN (CU + DU-1 + DU-2 + FlexRIC E2 Agent + RFsim :4043/:4044) |
| **VM-5** | `ue-emulator` | `10.102.0.165` | 4 | 8 GB | 30 GB | OAI nrUE Multi-Instance Emulator (rfsim client) |
| **VM-6** | `monitoring-data` | `10.102.0.67` | 4 | 8 GB | 40 GB | Prometheus TSDB, Grafana Dashboards, Telemetry Collector |
=======
| **VM-1** | `nonrt-ric` | `10.10.10.11` | 4 | 4 GB | 60 GB | Non-RT RIC, A1 PMS v2.6.0, Custom QoS rApp |
| **VM-2** | `near-rt-ric` | `10.10.10.12` | 4 | 4 GB | 60 GB | Minimal Near-RT RIC, A1 Mediator, xApp, E2Term, E2Mgr, DBaaS Redis 5.0.9 |
| **VM-3** | `oai-5gc` | `10.10.10.13` | 4 | 4 GB | 60 GB | OAI 5GC v2.1.0 Multi-Slice (AMF, SMF-1/2, UPF-1/2, NRF, UDM, MySQL) |
| **VM-4** | `oai-ran` | `10.10.10.14` | 4 | 4 GB | 60 GB | OAI 5G RAN (CU + DU-1 + DU-2 + FlexRIC E2 Agent + RFsim :4043/:4044) |
| **VM-5** | `ue-emulator` | `10.10.10.15` | 4 | 4 GB | 60 GB | OAI nrUE Multi-Instance Emulator (rfsim client) |
| **VM-6** | `monitoring-data` | `10.10.10.16` | 4 | 4 GB | 60 GB | Prometheus TSDB, Grafana Dashboards, Telemetry Collector |
>>>>>>> 89e2253a8557676afd4d0a3744f6b652e29a909d

---

## 5. Network Slicing & Cellular Radio Profile

| Parameter | Slice 1 (Throughput) | Slice 2 (Low-Latency) | Standardization & Compliance |
|---|---|---|---|
| **Service Role** | High Throughput / Bulk Data (eMBB) | Ultra-Reliable Low-Latency / Mission-Critical | 3GPP TS 23.501 Clause 5.15 |
| **SST** | `1` (Standard eMBB) | `222` (`0xDE`, Operator-Specific) | 3GPP TS 23.501 Table 5.15.2.2-1 |
| **SD** | `0x000001` (decimal `1`) | `0x00007B` (decimal `123`) | 24-bit Slice Differentiator |
| **Default DNN** | `default` | `lowlatency` | Data Network Name mapping |
| **UPF Endpoint** | `192.168.70.142:2152/UDP` | `192.168.70.143:2152/UDP` | Multi-UPF routed via Docker bridge |
| **PLMN Identity** | `MCC = 208, MNC = 95` | `MCC = 208, MNC = 95` | 3GPP TS 38.413 / TS 23.003 |
| **Tracking Area** | `TAC = 0xa000` (`40960`) | `TAC = 0xa000` (`40960`) | 3GPP TS 24.501 |
| **Cell Allocation** | Cell-1 (DU-1, PCI 1, rfsim :4043) | Cell-2 (DU-2, PCI 2, rfsim :4044) | 3GPP TS 38.211 (PCI 0–1007) |

### 5.1 Extension Guide: How to Add a New Network Slice

The experimental platform is architected to scale beyond the initial 2 slices (e.g., adding **Slice 3 — Massive IoT / Custom**, with `SST = 3`, `SD = 0x000003` / decimal `3`, and `DNN = iot`). Because network slicing spans the end-to-end 3GPP protocol stack, adding a slice requires synchronized configuration across all system layers:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ VM-3 (5G Core)                                                         │
│  1. MySQL: Provision subscriber (IMSI, SST, SD, DNN)                   │
│  2. AMF: Expose supported SST/SD via docker-compose environment        │
│  3. NSSF: Register S-NSSAI to SMF/UPF mapping profile                  │
│  4. SMF/UPF: Spawn oai_smf_slice3 & oai_upf_slice3 on 192.168.70.0/24   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ N2 / N3
┌───────────────────────────────────▼────────────────────────────────────┐
│ VM-4 (OAI RAN)                                                         │
│  5. cu_gnb.conf: Append { sst = 3; sd = 0x000003; } to snssaiList      │
│  6. du_gnb*.conf: Append { sst = 3; sd = 0x000003; } to cell slice list │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ RFsim (:4043/:4044)
┌───────────────────────────────────▼────────────────────────────────────┐
│ VM-5 (OAI nrUE)                                                        │
│  7. Launch UE with --uicc0.nssai_sst 3 --uicc0.nssai_sd 3 --dnn iot    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ E2 / A1
┌───────────────────────────────────▼────────────────────────────────────┐
│ VM-2 (Near-RT RIC) & VM-1 (Non-RT RIC)                                 │
│  8. E2SM-SLICE / E2SM-KPM: Collect Slice-3 PRB usage and delay         │
│  9. rApp / xApp: Apply traffic steering policy targeting Slice-3 SLA   │
└────────────────────────────────────────────────────────────────────────┘
```

#### Step 1: Provision Subscriber in 5GC MySQL Database (VM-3)
Register the new S-NSSAI for the target UE identity (e.g., IMSI `208950000000033` or additional slice for `208950000000031`) in MySQL (`database/oai_db2.sql` or live container):
```sql
-- Connect to MySQL container
docker exec -it mysql mysql -uroot -plinux -D oai_db

-- Add Session Management Subscription for Slice 3
INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `sequenceNumber`, `sst`, `sd`, `dnisArray`)
VALUES ('208950000000033', '20895', 1, 3, '000003', '{"iot":{"dnn": "iot"}}');

-- (Optional) If using a new IMSI, insert authentication credentials:
INSERT INTO `AuthenticationSubscription` (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`)
VALUES ('208950000000033', '5G_AKA', '0C0A34601D4F07677303652C0462535B', '0C0A34601D4F07677303652C0462535B', '000000000000', '8000', 'milenage', '63bfa50ee6523365ff14c1f45f88737d', NULL, 0);
```

#### Step 2: Register Slice in Core Network Functions (VM-3)
Edit `/opt/oran/5gc/oai-cn5g-fed/docker-compose/docker-compose-slicing-basic-nrf.yaml`:

1. **AMF Configuration:** Append Slice 3 to supported S-NSSAI environment variables:
   ```yaml
   oai_amf:
     environment:
       # Existing Slice 0 & 1 variables...
       - SST_2=3                     # [MANDATORY MATCH RAN/UE] Slice 3 SST
       - SD_2=3                      # [MANDATORY MATCH RAN/UE] Slice 3 SD
       - SERVED_GUAMI_SST_2=3
       - SERVED_GUAMI_SD_2=3
       - PLMN_SUPPORT_SST_2=3
       - PLMN_SUPPORT_SD_2=3
   ```

2. **NSSF Configuration (`conf/nssf_slice_config.yaml`):** Register S-NSSAI `[SST: 3, SD: 3]` so NSSF selects candidate SMF/UPF instances upon PDU Session Establishment.

3. **Deploy Dedicated SMF & UPF Instances:**
   Add `oai_smf_slice3` and `oai_upf_slice3` container definitions:
   - Dedicated UPF IP on Docker bridge: `192.168.70.144:2152`
   - Dedicated UE IPv4 Subnet Pool: `12.1.3.0/24`
   - Data Network Name (DNN): `iot`
   - Add routing and NAT masquerade rule in `oai_ext_dn` for subnet `12.1.3.0/24`.

4. **Restart 5GC stack:**
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
   ```

#### Step 3: Advertise Supported Slice in RAN CU & DU (VM-4)
1. **Update CU Configuration (`/opt/oran/ran/conf/cu_gnb.conf`):**
   Append Slice 3 under `plmn_list[0].snssaiList`:
   ```hcl
   snssaiList = (
     { sst = 1; sd = 0x000001; },      # Slice 1: eMBB
     { sst = 222; sd = 0x00007B; },    # Slice 2: Low Latency
     { sst = 3; sd = 0x000003; }       # Slice 3: IoT / Custom [NEW]
   );
   ```

2. **Update DU Configurations (`/opt/oran/ran/conf/du_gnb1.conf` & `du_gnb2.conf`):**
   Add `{ sst = 3; sd = 0x000003; }` to `snssaiList` for any cell (Cell-1, Cell-2, or both) designated to host Slice 3.

3. **Restart CU and DUs:**
   ```bash
   # Restart CU and DU softmodems
   # CU sends NGSetupRequest to AMF; AMF validates SST=1, 222, 3 against its configured list.
   ```
   *Validation:* In CU log, confirm: `[NGAP] Received NGSetupResponse with 3 supported slices`.

#### Step 4: Attach nrUE on the New Slice (VM-5)
Launch the simulated UE requesting the new S-NSSAI:
```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-uesoftmodem -r 106 --numerology 1 --band 78 -C 3619200000 \
  --rfsim --rfsimulator.serveraddr 10.102.0.167 --rfsimulator.serverport 4043 \
  --uicc0.imsi 208950000000033 \
  --uicc0.nssai_sst 3 \
  --uicc0.nssai_sd 3 \
  --uicc0.dnn iot
```
*Validation:* Confirm tunnel `oaitun_ue1` receives an IP from `12.1.3.0/24` (e.g., `12.1.3.2`) and can reach `12.1.3.1`.

#### Step 5: Incorporate into O-RAN RIC Telemetry & Steering (VM-2 & VM-1)
1. **VM-2 (Near-RT RIC xApp):** The FlexRIC E2 Agent (`slice_sm`) on VM-4 automatically exposes metrics tagged with `sst: 3, sd: 3`. The xApp can now read Slice 3 PRB utilization and apply slice-differentiated handover decisions.
2. **VM-1 (Non-RT RIC rApp):** In A1 Policy Management Service, define policy instances targeting `sst: 3, sd: 3` to enforce distinct SLA bounds (e.g., maximum delay, throughput floors, or target DU preference).

---

## 6. Implementation & Validation Status

| Milestone / Component | Target VM | Current Status | Verification Evidence / Reference |
|---|---|:---:|---|
| **VM-1: Non-RT RIC & A1 PMS** | VM-1 | ✅ Complete | Healthcheck `200 OK`, live OpenAPI schema exposed on port 8081. |
| **VM-2: Near-RT RIC Platform** | VM-2 | ✅ Complete | Minimal O-RAN SC (E2Term, E2Mgr, DBaaS, SubMgr) healthy. |
| **A1 Interface Integration** | VM-1 $\leftrightarrow$ VM-2 | ✅ Complete | A1 PMS $\leftrightarrow$ A1 Shim $\leftrightarrow$ A1 Mediator $\leftrightarrow$ xApp validated. |
| **VM-3: OAI 5G Core Multi-Slice** | VM-3 | ✅ Complete | 12 containers running; dual UPFs active; N2 exposed on port 38412. |
| **VM-4: OAI RAN Split CU/DU** | VM-4 | ✅ Complete | CU and Dual DUs compiled; F1-C/F1-U active; Cell 1 & 2 in service. |
| **O-RAN E2 Interface Integration** | VM-4 $\leftrightarrow$ VM-2 | ✅ Complete | Node `gnb_208_095_00000e00` connected; 8 Service Models registered. |
| **VM-5: OAI nrUE Multi-UE** | VM-5 | ⏳ Next Phase | Dual-slice multi-UE connection via RFsimulator TCP sockets. |
| **F1 Handover Execution** | VM-4 / VM-5 | ⏳ Next Phase | Inter-cell handover between DU-1 (:4043) and DU-2 (:4044). |
| **Coordinated rApp + xApp Steering** | VM-1 / VM-2 | ⏳ Planned | Thesis evaluation: QoS-aware DRL traffic steering mechanism. |
| **Telemetry & Experiment Pipeline** | VM-6 | ⏳ Planned | Automated logging of throughput, latency, loss, and handover signaling. |

---

## 7. Experimental Baselines for Thesis Evaluation

To rigorously prove the scientific hypothesis, the thesis evaluates **five standard comparative baselines (B0 to B4)** against the **Proposed System**. Each baseline reflects standard operational paradigms in cellular and O-RAN deployments:

| Baseline ID | Baseline Paradigm | Description & Behavioral Policy | Operational Procedure (What We Configure) |
|---|---|---|---|
| **B0** | **Static 3GPP Baseline (Standard Default)** | Static slicing reservations and standard 3GPP RRC A3 event-triggered handover based purely on RSRP. No dynamic RIC steering and no Core adaptation. | • Disable xApp control logic (monitor-only mode via E2).<br>• Disable rApp policy updates (static A1 dummy policy).<br>• Fixed PRB allocation per slice; static UPF queues. |
| **B1** | **RAN-Only Control (Standalone xApp)** | Near-RT xApp autonomously triggers inter-cell steering based solely on radio metrics (RSRP/CQI/PRB). Blind to 5G Core congestion and UPF bottlenecks. | • Enable xApp steering via E2SM-RC.<br>• Disable NWDAF integration on rApp.<br>• rApp dispatches static A1 threshold bounds. |
| **B2** | **Core-Only Control (NWDAF / User-Plane Adaptation)** | Core user-plane adapter dynamically adapts rate limits or queue parameters based on NWDAF metrics. Blind to radio link conditions and cell loads. | • Disable xApp handover steering (UE stays on attached cell).<br>• Enable Core adapter on VM-3 to shape/rate-limit UPF queues upon congestion detection. |
| **B3** | **Decoupled / Separate Controllers (Uncoordinated)** | RAN xApp and Core adapter operate concurrently and independently without an overarching coordinator. Vulnerable to conflicting actions and oscillation. | • Enable xApp steering independently on VM-2.<br>• Enable Core adapter independently on VM-3.<br>• Disable cross-domain correlation in rApp (no shared policy constraints). |
| **B4** | **Coordinated without Bottleneck Diagnosis (Fixed Heuristic)** | rApp aggregates telemetry from both domains, but applies a fixed, naive action sequence (e.g., always attempt handover first, then Core shaping) without diagnosing the bottleneck root cause. | • Enable rApp coordination over A1 and Core adapter.<br>• Configure decision engine to follow a static, hardcoded action priority list regardless of telemetry origin. |
| **Proposed** | **Bottleneck-Aware Closed-Loop Coordination** | rApp diagnoses the bottleneck root cause (`NORMAL`, `RAN`, `CORE`, `JOINT`), selects domain-matched actions, and verifies SLA recovery in a closed loop. | • Enable full rApp Bottleneck Classifier + Action Selector.<br>• Dynamic A1 policy updates to xApp + matched Core adapter control.<br>• Enable post-actuation SLA verification and churn suppression. |

### Evaluation Metrics & Validation Objectives:
1. **SLA Violation Rate ($V_s$):** Percentage of evaluation time windows where slice SLA bounds (delay, throughput) are violated.
2. **Recovery Time ($T_{rec}$):** Duration from bottleneck injection to full SLA restoration across consecutive evaluation windows.
3. **Macro-F1 Diagnosis Score:** Classification accuracy of the bottleneck identification engine across all four system states.
4. **Action Churn Rate:** Number of policy/handover oscillations per minute to evaluate control stability.

---

## 8. Repository Structure & Documentation Index

```text
Thesis/
├── README.md                          # Repository overview, architecture, and research framework
├── docs/
│   ├── architecture.md                # In-depth architectural design, layers, and interfaces
│   ├── bottleneck-methodology.md      # Baseline matrix (B0-B4), failure injection, and metrics
│   ├── vm1-nonrt-ric.md               # Step-by-step deployment guide for VM-1 (Non-RT RIC)
│   ├── vm2-nearrt-ric.md               # Step-by-step deployment guide for VM-2 (Near-RT RIC)
│   ├── vm3-oai-5gc.md                 # Deployment & slicing guide for VM-3 (OAI 5GC)
│   ├── vm4-oai-ran.md                 # Build & deployment guide for VM-4 (OAI Split RAN)
│   ├── vm5-nrue.md                    # Build & multi-UE deployment guide for VM-5 (OAI nrUE)
│   ├── a1-integration.md              # Complete A1 integration guide (VM-1 to VM-2)
│   ├── e2-integration.md              # Complete E2 integration guide (VM-4 to VM-2)
│   └── troubleshooting.md             # Solutions for 29+ validated operational failure modes
└── configs/                           # Deployment manifests and configuration files
```

### Direct Links to Detailed Guides:
- **Architecture Specification:** [docs/architecture.md](docs/architecture.md)
- **Baseline & Methodology Guide:** [docs/bottleneck-methodology.md](docs/bottleneck-methodology.md)
- **Node Installation Guides:**
  - [VM-1: Non-RT RIC Installation Guide](docs/vm1-nonrt-ric.md)
  - [VM-2: Near-RT RIC Installation Guide](docs/vm2-nearrt-ric.md)
  - [VM-3: OAI 5G Core Installation Guide](docs/vm3-oai-5gc.md)
  - [VM-4: OAI RAN CU/DU Installation Guide](docs/vm4-oai-ran.md)
  - [VM-5: OAI nrUE Emulator Installation Guide](docs/vm5-nrue.md)
- **Interface Integration Guides:**
  - [A1 Integration Guide (Non-RT to Near-RT)](docs/a1-integration.md)
  - [E2 Integration Guide (RAN to Near-RT)](docs/e2-integration.md)
- **Troubleshooting Manual:** [docs/troubleshooting.md](docs/troubleshooting.md)

---

## 9. References & Standards Compliance
- **O-RAN WG1:** O-RAN Architecture Description v07.00
- **O-RAN WG2:** A1 Interface: General Aspects and Principles v03.01
- **O-RAN WG3:** E2 Application Protocol (E2AP) v02.03
- **3GPP TS 23.501:** System Architecture for the 5G System (Release 17)
- **3GPP TS 38.413:** NG-RAN; NG Application Protocol (NGAP)
- **3GPP TS 38.470 / TS 38.473:** NG-RAN; F1 Application Protocol (F1AP)
- **OpenAirInterface:** https://gitlab.eurecom.fr/oai/openairinterface5g
- **O-RAN Software Community:** https://wiki.o-ran-sc.org/
