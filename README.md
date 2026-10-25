# Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks

> **Thesis Research Title:**  
> *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

This repository contains the architecture, configuration, deployment procedures, telemetry datasets, and experimental evaluation artifacts for a **software-only, cross-domain O-RAN and 5G Core experimental platform**. The platform enables empirical investigation into **closed-loop bottleneck diagnosis (RAN vs. Core user plane vs. Joint)** and adaptive traffic steering across multiple 5G network slices through coordinated interaction between an O-RAN Non-RT RIC rApp, Near-RT RIC xApp, and 3GPP NWDAF / Core user-plane adapters.

The platform is deployed entirely on virtual machines connected over a dedicated private network (`10.102.0.0/24`), requiring **no physical SDR hardware or commercial UEs**, ensuring complete reproducibility for experimental academic research.

---

## 1. System Architecture Overview

The experimental testbed implements a disaggregated O-RAN and 3GPP Release 16/17 software architecture across 6 dedicated virtual machines, aligning with normative standard interfaces where supported by open-source implementations and explicitly documenting implementation-defined bounds:

![Current System Architecture](docs/diagrams/current-system-architecture.png)

| Virtual Machine | Host IP Address | Functional Subsystem & Primary Services |
|---|---|---|
| **VM-1** (Non-RT RIC) | `10.102.0.168` | Non-RT RIC, A1 PMS v2.6.0 (`:8081`), rApp Host |
| **VM-2** (Near-RT RIC) | `10.102.0.66` | Near-RT RIC (Dawn), A1 Mediator (`:10001`), xApp Host |
| **VM-3** (5G Core & NWDAF) | `10.102.0.164` | OAI 5G Core Multi-Slice, 3GPP NWDAF (`:8080`), UPF Host |
| **VM-4** (Split RAN) | `10.102.0.167` | OAI Split RAN (CU-CP, CU-UP, DU-1, DU-2), E2 Agent |
| **VM-5** (nrUE Emulator) | `10.102.0.165` | OAI nrUE Emulator (netns: `ue1`, `ue2`), TrafGen |
| **VM-6** (Observability) | `10.102.0.67` | Telemetry Collector (`:9100`), Prometheus TSDB, Logger |

For complete architectural details, see [docs/architecture.md](docs/architecture.md).  
For the software versions, Git commits, and container image tags, see [docs/software-manifest.md](docs/software-manifest.md).

---

## 2. Research Framework & Closed-Loop Coordination

The core contribution of this thesis is the **cross-domain closed-loop coordination mechanism** that resolves the fundamental blind spot between RAN and Core domains:

1. **The Problem of Domain Myopia:**
   - **RAN Myopia:** When radio resources are constrained, modifying Core user-plane paths is ineffective.
   - **Core Myopia:** When the Core user plane (UPF / transport) is congested, allocating additional PRBs in the RAN or triggering blind radio handovers is futile and can exacerbate ping-pong instability.
   - **Uncoordinated Decoupled Controllers:** When both domains experience simultaneous congestion, independent uncoordinated controllers make conflicting decisions that destabilize slice SLAs.
2. **Closed-Loop MAPE-K Lifecycle:**
   - **Monitor:** Ingests synchronized 40-column telemetry from the RAN (MAC scheduler logs), 5G Core (UPF kernel `tc qdisc` & 3GPP NWDAF `UE_COMMUNICATION`), and UE canaries.
   - **Analyze (Bottleneck Diagnosis):** The rApp runs an explainable classification engine to categorize system state into: `NORMAL`, `RAN_BOTTLENECK`, `CORE_BOTTLENECK`, or `JOINT_BOTTLENECK`.
   - **Plan (Action Selection):** Dispatches targeted A1 policy constraints (Policy Type `20008`) to the Near-RT RIC xApp and/or user-plane rate-limiting constraints to the Core adapter.
   - **Execute (Actuation):** The xApp executes inter-cell traffic steering (Cell-1 $\leftrightarrow$ Cell-2) via E2SM-RC, while the Core adapter enforces user-plane conditioning.
   - **Verify (Closed-Loop Recovery):** Compares pre- and post-actuation SLA compliance ($V_s$, latency p95/p99) to confirm service recovery and prevent action churn.

---

## 3. Implementation Status Summary

All capabilities are classified under strict empirical evidence standards: **`Validated`**, **`Implemented`**, **`Planned`**, and **`Unsupported`**:

| System Capability | Implementation Scope | Status | Validation Evidence |
|---|---|:---:|---|
| **5GC Multi-Slice Control Plane** | AMF N2 (:38412), SMF-1/2 N4 PFCP | **`Validated`** | Tested with dynamic NRF registration ([Case #51](docs/troubleshooting/5g-core.md#case-51)) |
| **5GC Native User-Plane URR** | UPF simpleswitch URR $\to$ SMF $\to$ NWDAF | **`Validated`** | Verified periodic N4 Session Reports (msg 56) & live `qosmonlist` ([Doc](docs/integration/nwdaf-integration.md)) |
| **3GPP NWDAF NBI Analytics** | `UE_COMMUNICATION` over Kong :8080 | **`Validated`** | HTTP 200 with dynamic volume/duration ([Doc](docs/integration/nwdaf-integration.md)) |
| **NWDAF Slice Load Level** | Upstream code `relativeRatio` //TODO | **`Unsupported`** | Mapped to `NaN` in dataset to avoid false data ([Doc](docs/integration/nwdaf-integration.md)) |
| **Core Host Telemetry Adapter** | UPF container kernel `tc qdisc` & drops | **`Validated`** | Daemon `core_adapter.py` streaming at 1.0 Hz to VM-6 ([Doc](docs/deployment/vm-03-5g-core.md)) |
| **Split RAN (CU + Dual DU)** | CU-CP/UP, DU-1 (:4043), DU-2 (:4044) | **`Validated`** | Both cells in service, F1-C/F1-U active ([Doc](docs/deployment/vm-04-ran.md)) |
| **RAN Telemetry Extraction** | Physical MAC scheduler log parsing | **`Validated`** | Daemon `ran_adapter.py` streaming PRB%, SNR, MCS, BLER ([Doc](docs/deployment/vm-04-ran.md)) |
| **O-RAN E2 Setup Handshake** | CU FlexRIC Agent $\to$ VM-2 E2Term | **`Validated`** | Node `gnb_208_095_00000e00` connected over SCTP :36421 ([Doc](docs/integration/e2-integration.md)) |
| **O-RAN A1 Policy Interface** | VM-1 A1 PMS $\to$ VM-2 A1 Mediator $\to$ xApp | **`Validated`** | Policy Type 20008 PUT/GET passed, status `ENFORCED` ([Doc](docs/integration/a1-integration.md)) |
| **Multi-UE Namespaces & Traffic** | `ue1` (eMBB), `ue2` (URLLC), Canary Ping | **`Validated`** | 0% ping loss to EXT-DN, 1 Hz telemetry push ([Doc](docs/deployment/vm-05-ue.md)) |
| **40-Column Monotonic Recorder** | Single-scenario 1.000 Hz CSV dataset recorder | **`Validated`** | `record_experiment.py` verified with local monotonic elapsed logging at 1.000 Hz target cadence ([Doc](docs/telemetry/metric-catalog.md)) |
| **Closed-Loop Steering Actuation** | E2SM-RC Handover & Core Shaping Loop | **`Planned`** | Research Phase B active implementation ([Doc](docs/architecture.md)) |

For the complete capability matrix, test procedures, and dates, see the [Implementation Status Matrix](docs/implementation-status.md).

---

## 4. Documentation Sitemap & Directory Structure

The repository documentation is modularized into discrete functional categories:

| Documentation Directory | Description & Primary References |
|---|---|
| **[docs/](docs/README.md)** | Master documentation sitemap, reading order, and architecture guides. |
| **[docs/deployment/](docs/deployment/README.md)** | Step-by-step installation, bring-up, and operational guides for all 6 VMs. |
| **[docs/integration/](docs/integration/README.md)** | Cross-VM protocol contracts: A1 interface, E2 interface, and native 3GPP NWDAF pipeline. |
| **[docs/telemetry/](docs/telemetry/metric-catalog.md)** | Single authoritative metric dictionary for the 40-column dataset and Prometheus metrics. |
| **[docs/experiments/](docs/experiments/methodology.md)** | Comparative baseline methodology (B0–B4 vs Proposed) and scenario registry (S1–S10). |
| **[docs/references/](docs/references/standards.md)** | Standards claim mapping table (3GPP/ETSI/O-RAN) and bottleneck taxonomy. |
| **[docs/troubleshooting/](docs/troubleshooting/README.md)** | Domain-separated troubleshooting guides with complete historical case mapping. |
| **[docs/diagrams/](docs/diagrams/current-system-architecture.mmd)** | Source Mermaid files and high-resolution rendered architectural diagrams. |
| **[docs/archive/](docs/archive/README.md)** | Historical technical snapshots, investigation reports, and pre-refactor audits. |
| **[research/papers/](research/papers/model-comparison-outline.md)** | Academic draft paper outline, model comparison hypotheses, and mapping templates. |
| **[scripts/](scripts/README.md)** | Multi-VM automation, daemon execution reference, and telemetry recorder tools. |

---

## 5. Quick-Start Deployment Sequence

To bring up the multi-slice 5G O-RAN platform in correct dependency order, follow the 6-step sequence:

```bash
# Step 1: Start 5G Core & NWDAF on VM-3 (10.102.0.164)
# (Follow docs/deployment/vm-03-5g-core.md)

# Step 2: Start Split RAN on VM-4 (10.102.0.167)
sudo /opt/oran/ran/start_ran.sh
sudo nohup python3 -u /opt/oran/ran/scripts/ran_adapter.py > /dev/null 2>&1 &

# Step 3: Start Non-RT RIC on VM-1 (10.102.0.168)
# (Follow docs/deployment/vm-01-non-rt-ric.md)

# Step 4: Start Near-RT RIC on VM-2 (10.102.0.66)
# (Follow docs/deployment/vm-02-near-rt-ric.md)

# Step 5: Spawn UEs and Traffic on VM-5 (10.102.0.165)
sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
sudo nohup /opt/oran/ue/scripts/trafgen.sh start 60 25 > /dev/null 2>&1 &

# Step 6: Launch Collector & Logger on VM-6 (10.102.0.67)
python3 /opt/oran/monitoring/collector/telemetry_collector.py &
python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 60
```

---

## 6. Normative Standards Compliance

* **3GPP TS 23.501 / TS 23.502:** System Architecture & Procedures for the 5G System (Release 17).
* **3GPP TS 23.288:** Architecture Enhancements for 5GS to Support Network Data Analytics Services (Release 17).
* **3GPP TS 29.520:** 5G System; Network Data Analytics Services; Stage 3 (Release 17).
* **3GPP TS 28.552 / TS 32.401:** 5G Performance Measurements & Performance Management Principles.
* **3GPP TS 38.314:** NR; Layer 2 Measurements.
* **O-RAN WG1 / WG2 / WG3:** Architecture Description, A1 Interface Specification, and E2AP Specification.
* **ETSI TR 104 037:** O-RAN Use Cases and Non-RT RIC Analytics Exchange with 5G Core.
