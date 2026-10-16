# System Capability Implementation Status & Empirical Evidence

This document establishes the authoritative, peer-reviewed capability matrix of the 6-VM testbed. Every architectural component, interface, and telemetry metric is classified under strict, unambiguous status categories based on verifiable empirical evidence.

---

## 1. Formal Status Classification Taxonomy

* **`Validated`**: The capability, interface, or protocol has been verified on the testbed with passing empirical evidence (live logs, packet captures, HTTP 200 responses, or passing ping/traffic canaries). Test parameters and evidence links are provided.
* **`Implemented`**: The code, container, daemon, or configuration is deployed and actively executing, but lacks complete closed-loop end-to-end verification.
* **`Planned`**: The capability is formalized in the research design and architectural specifications, but has not yet been deployed or evaluated in live experiments.
* **`Unsupported`**: The feature is not implemented by the upstream open-source codebase or hardware environment; any related metrics are explicitly handled (e.g., mapped to `NaN`) to prevent data contamination.
* **`Historical`**: A prior implementation state, bug investigation, or preliminary workaround that has been superseded by a permanent fix.

---

## 2. End-to-End System Capability Matrix

| System Domain | Interface / Capability | Status | Exact Scope & Verification Procedure | Baseline Date & Commit | Concrete Evidence Source |
|---|---|:---:|---|---|---|
| **5G Core CP** | AMF N2 Association & Registration | **`Validated`** | OAI gNB CU establishes SCTP association on port `38412`. AMF successfully registers against NRF-12 with dynamic UUID. | 2026-10-14 (`9ce3aee`) | [`troubleshooting/5g-core.md#case-51`](troubleshooting/5g-core.md#case-51) |
| **5G Core CP** | Multi-Slice SMF N4 Association | **`Validated`** | Bidirectional PFCP Association Setup between `oai-smf-slice1` / `oai-smf-slice2` and UPF-1 / UPF-2 with 10s heartbeats. | 2026-10-14 (`9ce3aee`) | [`troubleshooting/5g-core.md#case-50`](troubleshooting/5g-core.md#case-50) |
| **5G Core UP** | Native PFCP URR & N4 Periodic Reporting | **`Validated`** | UPF `simpleswitch` accumulates user-plane octets via URR 1 and emits periodic PFCP Session Report Requests (`msg type 56`) over N4 to SMF-1. | 2026-10-15 (`13f8f73`) | [`integration/nwdaf-integration.md#4-verification--diagnostic-procedures`](integration/nwdaf-integration.md#4-verification--diagnostic-procedures) |
| **5G Core UP** | SMF $\to$ NWDAF Event Exposure (`QOS_MON`) | **`Validated`** | SMF-1 receives N4 usage reports, maps them to `Nsmf_EventExposure` (`QOS_MON`, Event 98), and dispatches HTTP/2 notifications to `oai-nwdaf-sbi`. | 2026-10-15 (`13f8f73`) | [`troubleshooting/nwdaf.md#case-47`](troubleshooting/nwdaf.md#case-47) |
| **NWDAF** | Native Storage Ingestion (`qosmonlist`) | **`Validated`** | `oai-nwdaf-sbi` receives SMF notifications and persists `CustomUsageReport` objects into MongoDB `testing.smf` under `qosmonlist`. | 2026-10-15 (`13f8f73`) | [`integration/nwdaf-integration.md#4-verification--diagnostic-procedures`](integration/nwdaf-integration.md#4-verification--diagnostic-procedures) |
| **NWDAF** | NBI REST API: `UE_COMMUNICATION` | **`Validated`** | Kong API Gateway (`:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION`) returns HTTP 200 with dynamic `ulVol`, `dlVol`, and `commDur`. | 2026-10-15 (`43f50d8`) | Verified via live curl query; matches ingested URR volume |
| **NWDAF** | NBI REST API: `NETWORK_PERFORMANCE` | **`Validated`** | Kong API Gateway returns HTTP 200 with dynamic `absoluteNum` (counted from MongoDB `testing.smf`). `relativeRatio` remains `0` (upstream `//TODO`). | 2026-10-14 (`9ce3aee`) | [`troubleshooting/nwdaf.md#case-48`](troubleshooting/nwdaf.md#case-48) |
| **NWDAF** | NBI REST API: `SLICE_LOAD_LEVEL` | **`Unsupported`** | Not implemented in OAI NBI switch case (`api_nwdaf_analytics_document_service.go`). Queries return HTTP 400. Mapped to `NaN` in dataset. | Upstream OAI Rel-17 | [`integration/nwdaf-integration.md#33-slice_load_level-3gpp-ts-23288-63--ts-29520--unsupported`](integration/nwdaf-integration.md#33-slice_load_level-3gpp-ts-23288-63--ts-29520--unsupported) |
| **Core Telemetry**| UPF Host Kernel Telemetry (`core_adapter.py`) | **`Validated`** | Ingests `tc qdisc` queue backlog bytes and packet drops on `eth0` from UPF containers via Netlink, posting to VM-6 `:9100/report` at 1.0 Hz. | 2026-10-15 (`fd6b1f3`) | Active daemon (PID 1123653), logs streaming to VM-6 |
| **Split RAN** | Split CU-CP/CU-UP & Dual DU Architecture | **`Validated`** | Native OAI softmodem runs CU-CP/UP on VM-4; DU-1 (Cell-1, PCI 1, `:4043`) and DU-2 (Cell-2, PCI 2, `:4044`) connect via F1-C/F1-U. | 2026-10-14 (`9ce3aee`) | [`deployment/vm-04-ran.md`](deployment/vm-04-ran.md) |
| **Split RAN** | RAN Telemetry Extraction (`ran_adapter.py`) | **`Validated`** | Tails `du1.log` & `du2.log` live, extracts instantaneous UL-SCH PRB allocation, SNR, MCS, and BLER without synthetic fallbacks, posting at 1.0 Hz. | 2026-10-15 (`fd6b1f3`) | Active daemon (PID 355971), verified live values |
| **O-RAN E2** | E2 Setup Handshake (CU E2 Agent $\to$ E2Term) | **`Validated`** | FlexRIC E2 Agent in CU softmodem connects over SCTP port `36421` to VM-2 E2Term; node registered in DBaaS with Global gNB ID `gnb_208_095_00000e00`. | 2026-10-12 (`348f047`) | [`integration/e2-integration.md`](integration/e2-integration.md) |
| **O-RAN E2** | E2SM-KPM Telemetry Indications | **`Historical`** | Tested with standalone FlexRIC nearRT-RIC; for current testbed 1 Hz logging, RAN scheduler metrics are reliably ingested via `ran_adapter.py`. | 2026-09-30 | Documented in [`integration/e2-integration.md`](integration/e2-integration.md) |
| **O-RAN E2** | E2SM-RC Handover Control Actuation | **`Planned`** | xApp dispatches E2 Control messages to trigger inter-cell handover (Cell-1 $\leftrightarrow$ Cell-2) via OAI CU RRC Reconfiguration. | Research Phase B | Under active implementation for closed-loop execution |
| **O-RAN A1** | A1 Policy Management Service (VM-1 $\to$ VM-2) | **`Validated`** | VM-1 A1 PMS v2.6.0 establishes REST connection to VM-2 A1 Mediator (`:10001`), successfully executing PUT and GET for Policy Type `20008`. | 2026-10-11 (`1e579ab`) | [`integration/a1-integration.md`](integration/a1-integration.md) |
| **O-RAN A1** | xApp RMR Policy Delivery (A1 Mediator $\to$ xApp) | **`Validated`** | A1 Mediator forwards policy via RMR message type `20010` to `a1_policy_xapp.py`; xApp responds with `20011` (`ENFORCED`). | 2026-10-11 (`1e579ab`) | [`troubleshooting/ric-a1.md#case-14`](troubleshooting/ric-a1.md#case-14) |
| **Multi-UE** | Multi-Namespace nrUE Attachment & Ping Canary | **`Validated`** | UE 1 attaches to Cell-1 (eMBB, `12.1.1.0/24`) and UE 2 attaches to Cell-2 (URLLC, `12.1.2.0/24`); ping canary to EXT-DN achieves 0% loss. | 2026-10-15 (`fd6b1f3`) | Active processes PID 147281 (UE1) and PID 147363 (UE2) |
| **Telemetry** | Monotonic Synchronized 38-Column CSV Logging | **`Validated`** | `record_dual_stream.py` scrapes `:9100/metrics` at 1.000 Hz, recording microsecond UTC timestamps, monotonic elapsed time, exact `event_phase_id`, and 38 clean columns. | 2026-10-16 | Verified via `tests/test_quality_gates.py` |
| **Non-RT RIC** | Offline Model Training for Bottleneck Classifier | **`Planned`** | Offline training pipeline (Decision Tree, Random Forest, MLP) designed on collected 37-column telemetry datasets to classify bottleneck state into NORMAL, RAN_BOTTLENECK, CORE_BOTTLENECK, JOINT_BOTTLENECK; execution and artifact generation awaiting full multi-scenario dataset collection (`compare_models.ipynb` currently unexecuted). | Planned | [`research/papers/model-comparison-outline.md`](../research/papers/model-comparison-outline.md) |
| **Non-RT RIC** | Autonomous Closed-Loop Steering rApp | **`Planned`** | Fully autonomous MAPE-K control loop running on VM-1 ingesting live telemetry from VM-6 and dispatching A1 policies to VM-2. | Research Phase B | Designed and specified in [`architecture.md`](architecture.md) |

---

## 3. Delimitation Notice: Differentiating Implemented Telemetry from Planned Closed-Loop Control

> [!IMPORTANT]
> **Scientific Integrity & Evidence Boundary:**
> 1. **Telemetry & Monitoring Layer:** The cross-domain observability pipeline (RAN scheduler logs + UPF kernel qdisc backlog/drops + native 3GPP NWDAF URR telemetry + UE experience canaries) is **fully implemented, empirically validated, and actively operating at 1.000 Hz**.
> 2. **A1 / E2 Infrastructure Layer:** A1 Policy Management Service (VM-1) and E2 Setup / SCTP connection (VM-4 to VM-2) are **fully operational and verified**.
> 3. **Closed-Loop Actuation Layer:** The automated execution of inter-cell handover via E2SM-RC control based on real-time rApp inference is **planned research work**. Testbed evaluations currently execute controlled baseline experiments to validate diagnostic accuracy prior to enabling autonomous actuation.
