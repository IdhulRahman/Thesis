# System Architecture

This document describes the high-level architecture of the experimental platform used for:

> **Development of a Multi-Timescale QoS-Aware Traffic Steering Mechanism for rApp and xApp Coordination in Multi-Slice O-RAN**

The platform is designed as a **software-only O-RAN testbed** using six virtual machines. The architecture separates long-timescale policy adaptation from near-real-time traffic steering so that both control loops can be evaluated independently and jointly.

---

## 1. Architecture Goals

The platform is designed to support the following research goals:

- coordination between an rApp and an xApp operating at different timescales;
- QoS-aware traffic steering across multiple O-RAN slices;
- dynamic policy delivery through A1;
- near-real-time telemetry and control through E2;
- software-only mobility and handover experiments;
- repeatable experiments without SDR hardware;
- logging of QoS, policy, steering, and control decisions for later analysis.

The main research idea is:

```text
Long-timescale QoS adaptation
            │
            ▼
           rApp
            │
            │ A1 policy
            ▼
           xApp
            │
            │ E2 control
            ▼
            RAN
            │
            ▼
          UE(s)
```

---

## 2. High-Level Topology

![High-Level System Architecture Overview](diagram/High-Level%20System%20Architecture%20Overview.png)

---

## 3. VM Mapping

The platform uses the subnet:

```text
10.10.10.0/24
```

| VM | Hostname | IP Address | Role |
|---|---|---:|---|
| VM-1 | `nonrt-ric` | `10.10.10.11` | Non-RT RIC, A1 PMS, rApp |
| VM-2 | `near-rt-ric` | `10.10.10.12` | Near-RT RIC, A1 Mediator, xApp |
| VM-3 | `oai-5gc` | `10.10.10.13` | OAI 5G Core |
| VM-4 | `oai-ran` | `10.10.10.14` | OAI CU, two DUs/cells, E2 Agent |
| VM-5 | `ue-emulator` | `10.10.10.15` | OAI nrUE |
| VM-6 | `monitoring-data` | `10.10.10.16` | Monitoring, logging, experiment data |

The IP assignments are static so that component configuration remains reproducible across experiment runs.

## 4. Non-RT Control Layer

VM-1 represents the Non-RT side of the control architecture.

Main components:

```text
Custom rApp
    │
    ▼
A1 Policy Management Service
```

The rApp is responsible for long-timescale adaptation.

Its planned role is to:

- observe historical QoS and network behavior;
- evaluate slice-level QoS conditions;
- update long-term policy constraints;
- send updated policy information through A1.

The initial control period is approximately:

```text
~30 seconds
```

This value is an experimental starting point and can be adjusted during evaluation.

The rApp does not directly perform per-second handover or steering decisions.

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
10.10.10.12:36421/SCTP
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

## 17. Main Evaluation Objectives

The architecture supports evaluation of three main hypotheses.

### H1

Coordinated rApp + xApp control reduces QoS violations compared with xApp-only control.

### H2

Policy constraints from the rApp improve QoS satisfaction compared with unconstrained DRL control.

### H3

Multi-timescale coordination improves steering stability and reduces ping-pong behavior while maintaining QoS.

---

## 18. Main Experiment Flow

A complete experiment is expected to follow this sequence:

```text
1. Start OAI 5GC
        │
        ▼
2. Start OAI CU + DU-1 + DU-2
        │
        ▼
3. Establish E2 connection to Near-RT RIC
        │
        ▼
4. Start OAI nrUE
        │
        ▼
5. Generate traffic
        │
        ▼
6. Collect E2 KPI
        │
        ▼
7. xApp evaluates steering
        │
        ▼
8. rApp periodically updates QoS policy
        │
        ▼
9. xApp applies policy-constrained action
        │
        ▼
10. Log QoS and mobility result
```

---

## 19. Network Interfaces

The main interfaces are:

| Interface | From | To | Role |
|---|---|---|---|
| A1 | VM-1 | VM-2 | Long-timescale policy |
| RMR | A1 Mediator | xApp | Internal Near-RT RIC messaging |
| E2 | VM-2 | VM-4 | KPI and RAN control |
| N2/N3 | VM-4 | VM-3 | RAN to 5GC |
| F1 | CU | DUs | CU/DU split |
| RFsim | VM-4 | VM-5 | Software-only radio simulation |
| Monitoring | VM-1..5 | VM-6 | Experiment metrics and logs |

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

VM-3 OAI 5GC                 ✅
VM-4 OAI RAN (CU + 2 DUs)    ✅
E2 integration (E2AP/SCTP)   ✅
E2SM-KPM (ID: 2)             ✅
E2SM-RC (ID: 3)              ✅
FlexRIC Service Models (8 SM)✅

VM-5 OAI nrUE (Multi-UE)     ⏳ (Next Phase)
F1 handover                  ⏳
QoS / slicing                ⏳
DRL integration              ⏳
VM-6 monitoring              ⏳
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
