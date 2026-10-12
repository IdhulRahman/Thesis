# System Architecture

This document describes the high-level architecture of the cross-domain experimental platform used for:

> **Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks**

The platform is designed as a **software-only cross-domain testbed** using six virtual machines. The architecture unifies O-RAN radio control loops with 5G Core user-plane analytics (NWDAF / Core Adapter) so that bottleneck identification and traffic steering can be evaluated across multiple operational baselines and experimental failure modes.

---

## 1. Architecture Goals

The platform is designed to support the following research goals:

- **Bottleneck Diagnosis:** Differentiating between RAN radio congestion, Core user-plane congestion (UPF/transport), and Joint congestion per network slice;
- **Closed-Loop Action Selection:** Selecting matched control actions (RAN inter-cell handover via xApp, Core user-plane conditioning, or coordinated joint control) based on diagnosed bottleneck location;
- **Comparative Baseline Evaluation:** Enabling empirical comparison across standard baseline modes: B0 (Static 3GPP), B1 (RAN-only), B2 (Core-only), B3 (Decoupled), B4 (Coordinated without diagnosis), and the Proposed System;
- **Hierarchical Timescale Decoupling:** Long-timescale (~30s) bottleneck analysis and policy generation in the rApp, combined with near-real-time (<1s) radio actuation in the xApp;
- **SLA Recovery Verification:** Verifying post-actuation SLA restoration ($V_s$ and latency percentiles) to prevent action churn;
- **Hardware-Free Reproducibility:** Entirely software-based execution without physical SDR hardware or commercial UEs.

The cross-domain research paradigm is:

```text
  5G Core Domain (VM-3)                 O-RAN Domain (VM-4 & VM-2)
  [UPF-1 & UPF-2 Telemetry]             [E2SM-KPM & E2SM-SLICE]
              │                                      │
              └───────────────┬──────────────────────┘
                              ▼
               Non-RT RIC rApp (VM-1)
               [Bottleneck Diagnosis Engine]
               (NORMAL | RAN | CORE | JOINT)
                              │
               Action Selector & SLA Verifier
                              │
              ┌───────────────┴──────────────────────┐
              ▼                                      ▼
       Core Adapter (VM-3)                    A1 Policy to Near-RT
   [User-Plane Conditioning]                  xApp in Near-RT RIC (VM-2)
                                                     │
                                                     ▼ E2SM-RC
                                              OAI RAN CU/DUs (VM-4)
                                              [Cell-1 <-> Cell-2 Handover]
```

---

## 2. High-Level Topology

![High-Level System Architecture Overview](diagram/High-Level%20System%20Architecture%20Overview.png)

---

## 3. VM Mapping

The platform uses the subnet:

```text
10.102.0.0/24
```

| VM | Hostname | IP Address | Role |
|---|---|---:|---|
| VM-1 | `nonrt-ric` | `10.102.0.168` | Non-RT RIC, A1 PMS v2.6.0, Bottleneck-Aware rApp |
| VM-2 | `near-rt-ric` | `10.102.0.66` | Near-RT RIC, A1 Mediator, xApp, E2Term, E2Mgr, DBaaS |
| VM-3 | `oai-core` | `10.102.0.164` | OAI 5G Core Multi-Slice (v2.1.0) + Native OAI NWDAF (8 microservices) |
| VM-4 | `oai-ran` | `10.102.0.167` | OAI CU, two DUs/cells (DU-1 :4043 / DU-2 :4044), E2 Agent (FlexRIC) |
| VM-5 | `ue-emulator` | `10.102.0.165` | OAI nrUE multi-instance (RFsimulator client, `ue1` & `ue2` netns) |
| VM-6 | `monitoring-data` | `10.102.0.67` | Prometheus TSDB, Grafana, Telemetry Collector |

The IP assignments are static so that component configuration remains reproducible across experiment runs.

### 3.1 Validated Golden Software Stack Specification

To ensure cross-domain compatibility, repeatability, and bug-free operation across all thesis experiments, the platform is standardized on the following **Golden Stack**:

| Layer / Domain | Software Framework | Version / Branch | Deployment Mode & Image Source | Role in Thesis Platform |
|---|---|---|---|---|
| **5G Core Network NFs** | OpenAirInterface 5G Core (`oai-cn5g-fed`) | **`v2.1.0`** (3GPP Rel-16/17 SA) | Docker Compose (`oaisoftwarealliance/oai-*:v2.1.0`) | AMF, SMF-1/2/3, UPF-1/2, VPP-UPF-3, NRF-12/3, UDM, UDR, AUSF, NSSF |
| **Core Analytics (NWDAF)** | OpenAirInterface NWDAF (`oai-cn5g-nwdaf`) | **`develop / v2.0.0`** (3GPP Rel-17) | 8 Docker microservices + Kong API Gateway (`:8080`) + MongoDB | Exposes `Nnwdaf_AnalyticsInfo` (`NETWORK_PERFORMANCE`) to rApp |
| **Centralized Unit (CU)** | OpenAirInterface5G (`openairinterface5g`) | **`develop` branch** | Native C softmodem with FlexRIC submodule | CU-CP / CU-UP with E2 Agent (SCTP :36421 to VM-2) |
| **Distributed Units (DU)** | OpenAirInterface5G (`openairinterface5g`) | **`develop` branch** | Native C softmodem (F1-U :2155/:2154, RFsim :4043/:4044) | DU-1 (Cell-1, PCI 1) and DU-2 (Cell-2, PCI 2) |
| **Near-RT RIC** | O-RAN Software Community (O-RAN SC) | **Dawn Release** | Docker Compose (7 platform containers) | E2Term, E2Mgr, Subscription Manager, A1 Mediator, DBaaS Redis 5.0.9, Traffic Steering xApp |
| **Non-RT RIC** | O-RAN SC Non-RT RIC | **A1 PMS v2.6.0** | Spring Boot / Java 17 container (:8081) | Manages A1 Policy Types (Type 20008) and synchronizes with A1 Mediator |
| **User Equipment (UE)** | OpenAirInterface5G (`nr-uesoftmodem`) | **`develop` branch** | Native executable in Linux `ip netns` (`ue1` & `ue2`) | Emulates multi-slice UEs (Slice 1: SST 1 SD 1, Slice 2: SST 222 SD 123) |

## 4. Non-RT Control Layer & Bottleneck Classifier

VM-1 represents the Non-RT coordinator of the architecture.

Main functional blocks inside the rApp:

```text
┌────────────────────────────────────────────────────────┐
│               rApp Coordinator (VM-1)                  │
│                                                        │
│  1. Cross-Domain Telemetry Aggregator                  │
│     ├── Ingests E2SM-KPM / Prometheus RAN metrics      │
│     └── Ingests NWDAF / Core Adapter Nnwdaf metrics    │
│                                                        │
│  2. Bottleneck Classification Engine                   │
│     └── Rule-Based / Decision Tree Classifier          │
│         States: NORMAL, RAN, CORE, JOINT, UNCERTAIN    │
│                                                        │
│  3. Action Selector & A1 Policy Generator              │
│     ├── Dispatches A1 Policy Type 20008 to xApp        │
│     └── Emits Core shaping targets to Core Adapter     │
│                                                        │
│  4. Closed-Loop SLA Verifier                           │
│     └── Compares pre- vs post-action window metrics    │
└────────────────────────────────────────────────────────┘
```

The rApp operates on a periodic cycle:

```text
~30 seconds
```

This timescale matches standard 3GPP NWDAF reporting windows and avoids interfering with the Near-RT RIC's fast radio loop.

---

## 5. Near-RT Control Layer

VM-2 represents the Near-RT control layer.

Main components:

```text
A1 Mediator
A1 Compatibility Shim
Python xApp
E2Term
E2Mgr
SubMgr
AppMgr
DBaaS
RMR
```

The xApp performs near-real-time traffic-steering decisions.

The initial xApp control period is approximately:

```text
~1 second
```

The planned action space is:

```text
Keep
Cell_1
Cell_2
```

The xApp receives:

```text
A1 policy constraints
+
E2 telemetry
```

and produces:

```text
traffic-steering decisions
```

that are later applied through E2 control.

---

## 6. Multi-Timescale Coordination

The central research mechanism is the interaction between two different control loops.

### Slow Loop

```text
QoS history
    │
    ▼
   rApp
    │
    ▼
A1 policy update
    │
    ▼
   xApp
```

Typical function:

```text
adapt long-term QoS constraints
```

Initial timescale:

```text
~30 s
```

### Fast Loop

```text
RAN KPI
   │
   ▼
  xApp
   │
   ▼
steering decision
   │
   ▼
 RAN control
```

Typical function:

```text
near-real-time traffic steering
```

Initial timescale:

```text
~1 s
```

The proposed architecture therefore separates:

```text
policy adaptation
```

from:

```text
steering execution
```

---

## 7. A1 Control Path

The validated A1 path is:

```text
VM-1
Custom rApp / client
        │
        ▼
A1 PMS :8081
        │
        │ OscA1Client
        ▼
VM-2
A1 Compatibility Shim :10001
        │
        ▼
A1 Mediator :10000
        │
        │ RMR 20010
        ▼
Traffic-Steering xApp
        │
        │ RMR RTS 20011
        ▼
A1 Mediator
```

The current baseline policy type is:

```text
20008
```

with a simple parameter:

```json
{
  "threshold": 5
}
```

This baseline is used to validate the communication path before the final adaptive QoS policy format is introduced.

Detailed setup:

[A1 Integration](a1-integration.md)

---

## 8. E2 Control Path

The planned E2 path is:

```text
Traffic-Steering xApp
        │
        ▼
Near-RT RIC
        │
        │ E2
        ▼
OAI E2 Agent
        │
        ▼
CU / DU
```

VM-2 exposes:

```text
10.102.0.66:36421/SCTP
```

for E2 connectivity.

Two E2 service-model roles are planned:

```text
E2SM-KPM
```

for KPI collection, and:

```text
E2SM-RC
```

for RAN control.

The exact OAI service-model configuration will be frozen after VM-4 integration is completed.

---

## 9. RAN Architecture

The planned RAN architecture uses:

```text
1 logical gNB
1 CU
2 DUs
2 cells
```

Conceptually:

```text
                 CU
               /    \
              /      \
           DU-1      DU-2
            │          │
          Cell-1     Cell-2
              \      /
               \    /
                nrUE
```

This structure is selected so that the UE can be steered between two cells while keeping the environment software-only.

The target mobility mechanism is:

```text
F1-based handover
```

between:

```text
Cell-1
↔
Cell-2
```

---

## 10. 5G Core Architecture

VM-3 hosts the OAI 5G Core.

The deployment is expected to include the core functions required by the experimental setup, including:

```text
AMF
SMF
UPF
NRF
UDM
UDR
AUSF
NSSF
PCF
```

NSSF and PCF are particularly relevant for the planned slice and QoS configuration.

The 5GC is kept on a separate VM so that core-network issues can be isolated from RAN and RIC issues during troubleshooting.

---

## 11. UE Architecture

VM-5 hosts software-based OAI nrUE instances.

The platform intentionally avoids:

```text
SDR
USRP
physical UE
```

The UE environment is used to generate repeatable software-only experiments for:

- attachment;
- traffic generation;
- QoS measurement;
- mobility;
- handover;
- multi-cell steering.

---

## 12. Slice Model

The initial research setup uses two logical slices.

### Slice 1

Primary objective:

```text
throughput-oriented service
```

Typical metric emphasis:

```text
throughput
resource utilization
```

### Slice 2

Primary objective:

```text
low-latency service
```

Typical metric emphasis:

```text
latency
QoS violations
```

The low-latency slice should not be presented as a full standards-compliant URLLC implementation unless the final configuration and experiment explicitly demonstrate that capability.

---

## 13. Traffic-Steering Decision Model

The initial steering action space is:

```text
A = {
    Keep,
    Cell_1,
    Cell_2
}
```

The xApp will combine:

```text
RAN state
+
QoS state
+
A1 policy constraints
```

to select an action.

Conceptually:

```text
State
  │
  ├── radio measurements
  ├── load
  ├── slice QoS
  ├── latency
  ├── throughput
  └── current serving cell
  │
  ▼
Policy-constrained xApp logic
  │
  ▼
Action
  │
  ├── Keep
  ├── Cell_1
  └── Cell_2
```

---

## 14. DRL Integration

DRL training is planned to be performed outside VM-2, primarily on a laptop or training environment.

The runtime separation is:

```text
Training environment
        │
        │ trained model
        ▼
VM-2 xApp
        │
        ▼
PyTorch inference only
```

VM-2 is therefore not intended to perform heavy model training.

The training dataset can be produced from experiment data exported from VM-6.

---

## 15. Monitoring and Data Flow

VM-6 is dedicated to monitoring and experiment data.

Planned data flow:

```text
VM-1 rApp metrics ───────┐
                         │
VM-2 xApp / RIC metrics ─┤
                         │
VM-3 5GC metrics ────────┤
                         ├──► VM-6
VM-4 RAN metrics ────────┤
                         │
VM-5 UE metrics ─────────┘
```

The monitoring layer is intended to record:

- RAN KPI;
- slice-level QoS;
- throughput;
- latency;
- packet loss if applicable;
- policy updates;
- xApp actions;
- handover events;
- steering changes;
- QoS violations;
- ping-pong events;
- experiment timestamps.

This allows the control decisions to be correlated with network outcomes.

---

## 16. Experimental Baselines

The architecture is designed so that all baselines can use the same infrastructure.

### B0 — Conventional RAN Handover

```text
No rApp control
No DRL steering
RAN mobility logic only
```

### B1 — Static O-RAN Traffic-Steering Policy

```text
Static A1 policy
+
traffic-steering xApp logic
```

Policy type `20008` provides the initial baseline concept.

### B2 — Optional O-RAN SC Baseline

Optional comparison using available O-RAN SC anomaly-detection / QoE-prediction / traffic-steering logic where practical.

### B3 — xApp-Only DRL

```text
fixed QoS configuration
+
DRL xApp
+
no adaptive rApp policy
```

### Proposed Method

```text
adaptive rApp
+
dynamic A1 QoS policy
+
policy-constrained DRL xApp
+
stability mechanism
```

---

## 17. Main Evaluation Hypotheses & Baseline Modes

The architecture evaluates four concrete scientific hypotheses across five standard baselines:

### Hypotheses:
- **H1 (Benefit of Coordination):** Bottleneck-aware coordination yields significantly lower SLA violation rates ($V_s$) than uncoordinated controllers under shifting bottleneck conditions.
- **H2 (Benefit of Diagnosis):** Diagnosing bottleneck locations prior to actuation recovers SLAs faster ($T_{rec}$) than naive, fixed-order action heuristics (B4).
- **H3 (Cross-Slice Isolation):** Coordination with slice-differentiated resource boundaries prevents priority slice recovery from starving subordinate slices.
- **H4 (Telemetry Staleness Resilience):** Telemetry timestamp filtering prevents ineffective actuation when reports are delayed or out of sync.

### Comparative Baseline Modes:
1. **B0 (Static 3GPP Default):** Fixed PRBs, static UPF queues, standard RRC A3 handover (xApp and rApp control disabled).
2. **B1 (RAN-Only Control):** Standalone xApp triggers steering based on radio metrics; blind to Core UPF congestion.
3. **B2 (Core-Only Control):** Core adapter shapes UPF traffic based on NWDAF; blind to radio channel and cell loads.
4. **B3 (Decoupled Controllers):** xApp and Core adapter operate independently without cross-domain coordination.
5. **B4 (Coordinated without Diagnosis):** rApp coordinates both domains but applies a fixed, hardcoded action sequence.
6. **Proposed System:** Bottleneck diagnosis $\rightarrow$ domain-matched action $\rightarrow$ closed-loop SLA verification.

---

## 18. Main Experiment Flow

A complete experimental cycle executes as follows:

```text
1. Start OAI 5GC & NWDAF / Core Adapter (VM-3)
        │
        ▼
2. Start OAI Split RAN (CU + DU-1 + DU-2) (VM-4)
        │
        ▼
3. Establish E2AP association to Near-RT RIC (VM-2)
        │
        ▼
4. Attach OAI nrUE instances on Slice 1 & Slice 2 (VM-5)
        │
        ▼
5. Inject controlled workload / congestion (RAN radio vs Core UPF)
        │
        ▼
6. Stream telemetry (E2SM-KPM from RAN + Nnwdaf from Core)
        │
        ▼
7. rApp classifies bottleneck location (NORMAL, RAN, CORE, JOINT)
        │
        ▼
8. rApp generates domain-matched action (A1 Policy to xApp and/or Core target)
        │
        ▼
9. xApp executes inter-cell steering via E2SM-RC; Core adapter applies shaping
        │
        ▼
10. rApp verifies SLA recovery; logs metrics ($V_s$, $T_{rec}$, churn) to VM-6 TSDB
```

---

## 19. Network Interfaces

The complete cross-domain interface map:

| Interface | From | To | Protocol / Transport | Role |
|---|---|---|---|---|
| A1 | VM-1 | VM-2 | HTTP REST (Port 10001) | Policy guidance & SLA bounds |
| Nnwdaf / Core Adapter | VM-1 | VM-3 | HTTP/2 REST (Port 8080) | Core slice load & delay telemetry |
| RMR | A1 Mediator | xApp | TCP RMR (Port 4560) | Internal Near-RT RIC messaging |
| E2 | VM-2 | VM-4 | E2AP over SCTP (Port 36421) | E2SM-KPM telemetry & E2SM-RC actuation |
| N2 | VM-4 | VM-3 | NGAP over SCTP (Port 38412) | RAN to AMF control plane |
| N3 | VM-4 | VM-3 | GTP-U over UDP (Port 2152) | Dual-UPF user plane routing |
| F1 | CU | DUs | F1-C (38472/SCTP) & F1-U (2153-2155/UDP) | CU/DU disaggregation |
| RFsim | VM-4 | VM-5 | TCP Sockets (:4043/:4044) | Software-only RF emulation |
| Monitoring | All VMs | VM-6 | HTTP REST / Prometheus Pull | Experiment metrics & telemetry |

---

## 20. Implementation Status

Current status:

```text
VM-1 Non-RT RIC              ✅
A1 PMS                        ✅
VM-2 Near-RT RIC             ✅
A1 Mediator                   ✅
A1 compatibility shim        ✅
A1 policy type 20008          ✅
A1 PMS → xApp delivery        ✅
RMR 20010 / 20011             ✅

VM-3 OAI 5GC (12 Containers) ✅
VM-4 OAI RAN (CU + 2 DUs)    ✅
E2 integration (E2AP/SCTP)   ✅
E2SM-KPM (ID: 2)             ✅
E2SM-RC (ID: 3)              ✅
FlexRIC Service Models (8 SM)✅
VM-5 OAI nrUE (Multi-UE)     ✅
VM-6 monitoring (TSDB/Logger)✅
QoS / multi-slicing (dual UPF) ✅

Native NWDAF (oai-nwdaf)     ⏳ (Bypassed via Core Adapter v9)
F1 handover (E2SM-RC / RRC)  ⏳ (In Progress)
DRL / ML model integration   ⏳ (In Progress)
```

---

## 21. Architecture Boundaries

The following are intentionally outside the current scope:

- SDR hardware;
- USRP;
- commercial UE testing;
- production-grade orchestration;
- Kubernetes-based cloud deployment;
- carrier-grade high availability.

The platform is an experimental research environment focused on reproducibility and control-loop evaluation.

---

## 22. Design Principle

The architecture follows one simple separation:

```text
rApp
=
slow policy adaptation
```

```text
xApp
=
fast steering execution
```

with:

```text
A1
=
coordination between control timescales
```

and:

```text
E2
=
near-real-time observation and RAN control
```

This separation is the core architectural basis of the proposed multi-timescale traffic-steering mechanism.

---

## Related Documentation

- [VM-1 — Non-RT RIC](vm1-nonrt-ric.md)
- [VM-2 — Near-RT RIC](vm2-nearrt-ric.md)
- [A1 Integration](a1-integration.md)
- [E2 Integration](e2-integration.md)
- [Handover and Slicing](handover-and-slicing.md)
