# Multi-Timescale QoS-Aware Traffic Steering in Multi-Slice O-RAN

> **Research title:**  
> *Development of a Multi-Timescale QoS-Aware Traffic Steering Mechanism for rApp and xApp Coordination in Multi-Slice O-RAN*

This repository contains the implementation, configuration, and deployment documentation for a **software-only O-RAN experimental platform** used to study coordination between a Non-RT RIC rApp and a Near-RT RIC xApp operating at different control timescales.

The main objective is to evaluate QoS-aware traffic steering across multiple O-RAN slices, where:

- the **rApp** performs long-timescale QoS policy adaptation;
- policies are delivered through the **A1 interface**;
- the **xApp** performs near-real-time traffic steering;
- the **E2 interface** is used for RAN telemetry and control;
- the RAN and UE environment is fully emulated using **OpenAirInterface (OAI)**.

---

## Architecture Overview

```text
                       ┌─────────────────────────────┐
                       │          VM-1               │
                       │       Non-RT RIC            │
                       │                             │
                       │  Custom rApp                │
                       │      │                      │
                       │      ▼                      │
                       │  A1 Policy Management       │
                       │  Service                    │
                       └─────────────┬───────────────┘
                                     │
                                     │ A1
                                     ▼
                       ┌─────────────────────────────┐
                       │          VM-2               │
                       │       Near-RT RIC           │
                       │                             │
                       │  A1 Mediator                │
                       │      │                      │
                       │      ▼                      │
                       │  Traffic-Steering xApp      │
                       │      │                      │
                       │      ▼                      │
                       │  E2Term / E2Mgr / SubMgr    │
                       └─────────────┬───────────────┘
                                     │
                                     │ E2
                                     ▼
                       ┌─────────────────────────────┐
                       │          VM-4               │
                       │          OAI RAN            │
                       │                             │
                       │  CU + DU-1 + DU-2           │
                       │  E2 Agent                   │
                       └─────────────┬───────────────┘
                                     │
                                     │ RFsim / F1
                                     ▼
                       ┌─────────────────────────────┐
                       │          VM-5               │
                       │        OAI nrUE(s)           │
                       └─────────────────────────────┘

          ┌──────────────────────┐       ┌──────────────────────┐
          │        VM-3          │       │        VM-6          │
          │      OAI 5GC         │       │ Monitoring & Data    │
          │ NSSF / PCF / UPF ... │       │ Prometheus / DB      │
          └──────────────────────┘       └──────────────────────┘
```

---

## VM Deployment

The experimental environment uses six virtual machines connected through the `10.10.10.0/24` subnet.

| VM | Hostname | IP Address | Main Role |
|---|---|---:|---|
| VM-1 | `nonrt-ric` | `10.10.10.11` | Non-RT RIC, A1 PMS, custom rApp |
| VM-2 | `near-rt-ric` | `10.10.10.12` | Near-RT RIC, A1 Mediator, xApp |
| VM-3 | `oai-5gc` | `10.10.10.13` | OAI 5G Core |
| VM-4 | `oai-ran` | `10.10.10.14` | OAI CU, two DUs/cells, E2 Agent |
| VM-5 | `ue-emulator` | `10.10.10.15` | OAI nrUE emulator |
| VM-6 | `monitoring-data` | `10.10.10.16` | Monitoring, logging, experiment data |

---

## Framework

The platform is built around the following components:

### Non-RT RIC

- O-RAN SC A1 Policy Management Service
- Custom QoS-aware rApp
- Long-timescale QoS policy adaptation

### Near-RT RIC

- Minimal O-RAN SC Near-RT RIC deployment
- E2Term
- E2Mgr
- Subscription Manager
- App Manager
- DBaaS
- RMR
- A1 Mediator
- Python xApp runtime

### RAN and Core

- OpenAirInterface 5G Core
- OpenAirInterface CU/DU split RAN
- One logical gNB
- Two DUs / two cells
- OAI E2 Agent
- OAI RFsimulator
- OAI nrUE

### Monitoring and Experiment Data

- Prometheus
- Grafana
- Experiment logger
- Database for QoS, policy, steering, and training data

---

## Control Loops

The proposed system uses two control timescales.

### Long-Timescale Control

```text
Network QoS history
        │
        ▼
      rApp
        │
        ▼
Adaptive QoS policy
        │
        ▼
       A1
```

The rApp evaluates longer-term network conditions and updates QoS policy constraints.

### Near-Real-Time Control

```text
E2 telemetry
     │
     ▼
    xApp
     │
     ▼
Traffic-steering decision
     │
     ▼
E2 control
```

The xApp performs near-real-time traffic steering while respecting the policy constraints received from the rApp.

---

## Repository Structure

```text
.
├── README.md
├── LICENSE
├── .gitignore
│
├── docs/
│   ├── architecture.md
│   ├── vm1-nonrt-ric.md
│   ├── vm2-nearrt-ric.md
│   ├── vm3-oai-5gc.md
│   ├── vm4-oai-ran.md
│   ├── vm5-ue-emulator.md
│   ├── vm6-monitoring.md
│   ├── a1-integration.md
│   ├── e2-integration.md
│   ├── handover-and-slicing.md
│   └── troubleshooting.md
│
└── configs/
    ├── vm1/
    ├── vm2/
    ├── vm3/
    ├── vm4/
    ├── vm5/
    └── vm6/
```

`docs/` contains deployment and integration documentation, while `configs/` contains configuration files used by each VM.

---

## Installation Guides

Follow the installation guides in VM order.

| VM | Installation Guide |
|---|---|
| VM-1 — Non-RT RIC | [docs/vm1-nonrt-ric.md](docs/vm1-nonrt-ric.md) |
| VM-2 — Near-RT RIC | [docs/vm2-nearrt-ric.md](docs/vm2-nearrt-ric.md) |
| VM-3 — OAI 5GC | [docs/vm3-oai-5gc.md](docs/vm3-oai-5gc.md) |
| VM-4 — OAI RAN | [docs/vm4-oai-ran.md](docs/vm4-oai-ran.md) |
| VM-5 — UE Emulator | [docs/vm5-ue-emulator.md](docs/vm5-ue-emulator.md) |
| VM-6 — Monitoring and Data | [docs/vm6-monitoring.md](docs/vm6-monitoring.md) |

---

## Integration Guides

- [A1 Integration](docs/a1-integration.md)
- [E2 Integration](docs/e2-integration.md)
- [Handover and Slicing](docs/handover-and-slicing.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## Current Implementation Status

| Component | Status |
|---|---|
| VM-1 Non-RT RIC | ✅ Completed |
| A1 Policy Management Service | ✅ Completed |
| VM-2 Near-RT RIC | ✅ Completed |
| A1 Mediator | ✅ Completed |
| A1 PMS ↔ A1 Mediator integration | ✅ Completed |
| A1 policy type `20008` synchronization | ✅ Completed |
| A1 → RMR → xApp policy delivery | ✅ Completed |
| xApp policy acknowledgement | ✅ Completed |
| OAI 5GC | ⏳ Planned |
| OAI RAN | ⏳ Planned |
| E2 setup | ⏳ Planned |
| E2SM-KPM | ⏳ Planned |
| E2SM-RC | ⏳ Planned |
| OAI nrUE | ⏳ Planned |
| F1 handover | ⏳ Planned |
| QoS / network slicing | ⏳ Planned |
| DRL integration | ⏳ Planned |
| Monitoring and experiment pipeline | ⏳ Planned |

---

## A1 Integration Status

The current A1 path has been validated end-to-end:

```text
A1 PMS
   │
   ▼
OSC A1 Client
   │
   ▼
A1 Compatibility Shim
   │
   ▼
A1 Mediator
   │
   │ RMR 20010
   ▼
Traffic-Steering xApp
   │
   │ RMR 20011
   ▼
A1 Mediator
```

The current baseline policy type is:

```text
Policy Type ID: 20008
```

with a simple traffic-steering parameter:

```json
{
  "threshold": 5
}
```

This policy type is used as the initial A1 traffic-steering baseline before introducing the adaptive QoS policy mechanism proposed in this research.

---

## Research Scope

The implementation focuses on:

- multi-timescale rApp and xApp coordination;
- QoS-aware traffic steering;
- multiple O-RAN slices;
- dynamic A1 policy adaptation;
- policy-constrained near-real-time control;
- steering stability and ping-pong reduction;
- software-only handover and traffic experiments.

The platform is intentionally designed without SDR hardware or commercial UEs so experiments can be reproduced using virtual machines.

---

## Experimental Baselines

The planned evaluation includes:

- conventional RAN handover;
- O-RAN traffic-steering logic with static policy;
- xApp-only traffic steering;
- proposed coordinated rApp + xApp traffic steering.

All baselines will use the same emulated infrastructure and comparable network conditions.

---

## Documentation Philosophy

This repository separates:

```text
docs/     → how the system is installed, integrated, and validated
configs/  → configuration files actually used by the deployment
```

The goal is to keep the repository simple while preserving enough information to reproduce the experimental platform.

---

## References

The implementation follows official documentation and reference implementations from:

- O-RAN Software Community
- OpenAirInterface
- srsRAN minimal O-RAN SC RIC packaging
- Docker

Detailed references are provided in the corresponding files under `docs/`.

---

## License

See [LICENSE](LICENSE).
