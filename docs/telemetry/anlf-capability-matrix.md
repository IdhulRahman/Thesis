# 3GPP NWDAF AnLF & O-RAN RAN Telemetry: Capability, Provenance, and Demarcation Matrix

**Document Purpose:** Authoritative Stage-1 Technical Audit for Thesis Research  
**Research Title:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*  
**Applicable Specifications:** 3GPP TS 23.288 (v17.4.0), 3GPP TS 29.520 (v17.4.0), 3GPP TS 29.244 (v17.3.0), 3GPP TS 38.314 (v17.1.0), 3GPP TS 28.552 (v17.1.0)  
**Target Hosts:** VM-3 (5G Core & NWDAF), VM-4 (Split RAN), VM-5 (UE QoS), VM-6 (Monitoring & Analytics Collector)  
**Upstream Commit References:**
* `oai-cn5g-nwdaf`: `9d82b7547586a6e04dc0719ef18910ea01fcd9e7` (branch `develop`)
* `oai-cn5g-fed`: `v2.0.1` (Docker Compose deployment)
* `openairinterface5g`: `2026.w39` / `develop` (commit `29d5fa7d`, gNB DU/CU & nrUE)

---

## 1. Architectural Scope & Executive Principles

This document formally specifies the capabilities, data provenance, and architectural demarcation of the Core Network Analytics Logical Function (NWDAF AnLF) and Radio Access Network (RAN) telemetry utilized for cross-domain bottleneck detection in the Non-RT RIC rApp.

### Strict Scientific Guardrails
1. **Verifiable AnLF Analytics:** Core analytics consumed by the rApp must originate from the 3GPP NWDAF NBI interface (`Nnwdaf_AnalyticsInfo` / `Nnwdaf_EventsSubscription`) with end-to-end provenance. A running container or an HTTP 200 OK status alone does not constitute proof of AnLF analytic contribution.
2. **Honest RAN Demarcation:** In accordance with empirical validation, radio metrics collected on VM-4 are formally designated as:  
   $$\text{\textbf{OAI DU scheduler-log-derived telemetry, sampled by the adapter at approximately 1 Hz}}$$  
   Radio metrics are **not** claimed as Near-RT RIC E2SM-KPM indications unless an E2 subscription and indication pipeline is explicitly demonstrated.
3. **Decoupling Validation from Primary Features:** Kernel-level Linux qdisc metrics (`core_adapter.py`) and receiver-side goodput/loss (`oai-ext-dn`) serve strictly as **ground-truth validation and audit baselines**. They must never be injected as silent substitutes for NWDAF AnLF features.
4. **Distinction Between AnLF Computation and Consumer Feature Engineering:** Any mathematical transformations performed outside the NWDAF pipeline (e.g., derivative throughput rates calculated in `telemetry_collector.py` or the rApp) are formally designated as **Consumer Feature Engineering** and are never attributed as native AnLF outputs.

---

## 2. 3GPP NWDAF AnLF Capability & Event ID Audit Matrix

The table below catalogs the formal mapping between 3GPP Stage-2 / Stage-3 specifications and the deployed upstream OpenAirInterface NWDAF implementation:

| 3GPP Stage-2 Analytics ID (TS 23.288) | 3GPP Stage-3 Tabular Enum (TS 29.520 v17.6.0 §5.1.6.3.4, Table 5.1.6.3.4-1) | 3GPP Stage-3 OpenAPI Enum (TS 29.520 v17.6.0 Annex A) | Upstream OAI Engine Function & Source File | NBI Query Selector & Gateway Route | Ingestion Cadence & Data Source | Live Empirical Evidence | Operational Status in Audited Build |
|---|---|---|---|---|---|---|---|
| **Communication performance** (TS 23.288 §6.7) | **`UE_COMM`** | **`UE_COMMUNICATION`** | `ueCommunicationHandler`<br>`components/oai-nwdaf-engine/internal/engine/ue_communication.go` | `event-id=UE_COMMUNICATION`<br>`GET /nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION&ana-req={...}` | Periodic UPF Usage Reports (URR).<br>**Cadence: $\approx 30$ seconds**. | HTTP 200 OK via Kong port 8080.<br>Payload delivers dynamic `ulVol`, `dlVol`, `ulVolVariance`, and `commDur`. | **VERIFIED & OPERATIONAL (NATIVE)** |
| **Network performance** (TS 23.288 §6.6) | **`NETWORK_PERFORMANCE`** | **`NETWORK_PERFORMANCE`** | `nwPerfNumOfPdu`<br>`components/oai-nwdaf-engine/internal/engine/network_performance.go` | `event-id=NETWORK_PERFORMANCE`<br>`GET /nnwdaf-analyticsinfo/v1/analytics?event-id=NETWORK_PERFORMANCE` | Event-driven (triggered upon PDU Session Establishment). | HTTP 200 OK via Kong port 8080.<br>`absoluteNum` counted from MongoDB `testing.smf`; `relativeRatio` is an uncalculated upstream stub (`//TODO`, hardcoded 0). | **INCOMPLETE UPSTREAM**<br>*(Control Plane only; non-informative for User Plane bottlenecks)* |
| **Slice load level** / **Load level information** (TS 23.288 §6.3) | **`SLICE_LOAD_LEVEL`** | **`SLICE_LOAD_LEVEL`** | None registered in upstream OAI engine switch-case (`api_nwdaf_analytics_document_service.go`) | `event-id=SLICE_LOAD_LEVEL`<br>`GET /nnwdaf-analyticsinfo/v1/analytics?event-id=SLICE_LOAD_LEVEL` | None in audited container build. | Query returns **HTTP 400 Bad Request** (`"invalid Event Id param"`) via NBI Analytics API.<br>Unregistered subscription path `/nnwdaf-eventsubscription/v1/slice-load-level` returns **HTTP 404 Not Found** via Kong. | **UNSUPPORTED UPSTREAM**<br>*(Mapped to strict `NaN` in dataset)* |

---

## 3. End-to-End Telemetry Provenance Chains

Every variable recorded in the experiment dataset has a fully traceable provenance path:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PROVENANCE CHAIN 1: PRIMARY CORE ANALYTICS (3GPP NWDAF AnLF)                                                   │
│ [UPF-1 Container]                                                                                               │
│   │ PFCP Session Usage Reporting (TS 29.244 URR, cadence ~30s)                                                 │
│   ▼                                                                                                             │
│ [oai-smf]                                                                                                       │
│   │ SMF Event Exposure Notification (HTTP POST /test/smf)                                                       │
│   ▼                                                                                                             │
│ [oai-nwdaf-sbi]                                                                                                 │
│   │ MongoDB Driver Insert                                                                                       │
│   ▼                                                                                                             │
│ [oai-nwdaf-database (MongoDB: testing.smf)]                                                                     │
│   │ Aggregation Query: filter(startTs <= ts <= endTs)                                                          │
│   ▼                                                                                                             │
│ [oai-nwdaf-engine (ue_communication.go)]                                                                        │
│   │ Mathematical compute: ulVol, dlVol, commDur, ulVolVariance (std dev)                                        │
│   ▼                                                                                                             │
│ [oai-nwdaf-nbi-gateway (Kong Gateway :8080)]                                                                    │
│   │ HTTP GET /nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION&ana-req={...}                         │
│   ▼                                                                                                             │
│ [VM-6: telemetry_collector.py]                                                                                  │
│   │ Real-time raw poll archiving: data/raw/<RUN_ID>/nwdaf_raw_poll_responses.jsonl                               │
│   │ Prometheus Gauge exposure (nwdaf_comm_*)                                                                    │
│   ▼                                                                                                             │
│ [record_experiment.py] ──► data/raw/<RUN_ID>/telemetry_<RUN_ID>.csv (1.000 Hz Monotonic CSV)                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PROVENANCE CHAIN 2: PRIMARY RADIO METRICS (OAI DU SCHEDULER LOGS)                                               │
│ [VM-4: gNB DU-1 Process]                                                                                        │
│   │ Real-time MAC scheduler ASCII logging to /opt/oran/ran/du1.log                                              │
│   ▼                                                                                                             │
│ [VM-4: ran_adapter.py]                                                                                          │
│   │ Persistent file offset seek; Regex parser: NPRB/106, MCS, BLER, SNR                                         │
│   │ HTTP POST http://10.102.0.67:9100/report (1 Hz cadence)                                                     │
│   ▼                                                                                                             │
│ [VM-6: telemetry_collector.py] ──► Prometheus Gauge (ran_cell_*) ──► [record_experiment.py] (1.000 Hz CSV)     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PROVENANCE CHAIN 3: GROUND-TRUTH CORE VALIDATION (KERNEL / QDISC AUDIT)                                         │
│ [VM-3: UPF-1 Container Linux Network Namespace]                                                                 │
│   │ Linux Kernel Subsystems: `tc -s qdisc show dev eth0` & `/proc/net/dev`                                      │
│   ▼                                                                                                             │
│ [VM-3: core_adapter.py v9]                                                                                      │
│   │ Ingests qdisc backlog bytes, drops/sec rate, total interface bytes                                          │
│   │ HTTP POST http://10.102.0.67:9100/report (1 Hz cadence)                                                     │
│   ▼                                                                                                             │
│ [VM-6: telemetry_collector.py] ──► Prometheus Gauge (upf_queue_*, upf_packet_*) ──► [record_experiment.py]     │
│ NOTE: Strictly classified as Ground-Truth Validation / Audit; never fed into primary AnLF feature tensor.        │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PROVENANCE CHAIN 4: GROUND-TRUTH SERVICE & RECEIVER IMPACT                                                      │
│ [VM-5: nrUE uesimtun0] ────────── Offered Load (iperf3 -u) ─────────► [VM-3: oai-ext-dn Receiver :5201]        │
│                                                                               │                                 │
│                                                                               ▼                                 │
│                                                             iperf3 --one-off --logfile (receiver_iperf.sh)      │
│                                                             (Ground-Truth Delivered Goodput & UDP Loss)         │
│                                                                               │                                 │
│                                                                               ▼                                 │
│                                                             Post-Run Archived: data/raw/<RUN_ID>/receiver.json  │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Multi-Tier Dataset Architecture

To guarantee scientific rigor, all telemetry recorded during experiments is strictly partitioned into three independent tiers:

### Tier 1: Primary Feature Tensor (Inputs to Cross-Domain Diagnosis Model)
* **RAN Features (OAI DU Scheduler-Derived):**
  * `ran_prb_cell1`, `ran_prb_cell2` (PRB utilization percentage: $\frac{NPRB}{106} \times 100$)
  * `ran_mcs_cell1`, `ran_mcs_cell2` (Modulation and Coding Scheme index, 0–28)
  * `ran_bler_cell1`, `ran_bler_cell2` (Transport block BLER, 0.0–1.0)
  * `ran_snr_cell1`, `ran_snr_cell2` (Uplink SNR, dB)
* **Core NWDAF Features (3GPP TS 29.520 AnLF Native):**
  * `nwdaf_comm_ul_bytes` (Cumulative uplink user-plane volume)
  * `nwdaf_comm_dl_bytes` (Cumulative downlink user-plane volume)
  * `nwdaf_comm_duration_sec` (Cumulative URR report window duration)
  * `nwdaf_comm_vol_std_bytes` (Volume standard deviation across session records)
  * *Note on Rate Derivatives:* Throughput rate estimation from gauge volume metrics (`rate()`) is deferred pending verification of volume report interval semantics and source timestamps.

### Tier 2: Ground-Truth Validation & Reference Data (Excluded from Model Input)
* **Core Kernel Validation:**
  * `upf_backlog_bytes_embb`, `upf_backlog_bytes_urllc` (Linux qdisc queue depth)
  * `upf_drops_embb`, `upf_drops_urllc` (Linux qdisc packet drop rate)
  * `estimated_load_embb`, `estimated_load_urllc` (Interface empirical proxy)
* **End-to-End Service Validation:**
  * EXT-DN receiver-side goodput (Mbps) and UDP packet loss (%)
  * `e2e_slice2_rtt_ms` (Canary ICMP round-trip latency)
  * `e2e_slice2_loss_pct` (Canary sequence-matched loss percentage)

### Tier 3: Metadata, Annotations, and Quality Indicators
* `timestamp_utc`, `elapsed_sec`, `run_id`
* `event_phase_id`, `event_scenario`, `event_domain`, `event_component` (Operator-assigned labels from `record_experiment.py`)
* `nwdaf_api_status` (HTTP connectivity status to Kong Gateway :8080)
* `nwdaf_comm_freshness` (NWDAF value-change heuristic indicator: 1 if reported user-plane volume tuple updated within 45s, else 0; operates independently of `nwdaf_api_status`)
* `e2e_probe_freshness` (Canary reply arrival freshness indicator: 1 if active ICMP echo reply received from UE-2 within 3.5s, else 0; valid measurement indicator even when measured RTT values remain numerically stable)

---

## 5. Gateway Route & Protocol Error Demarcation

To eliminate ambiguity between network routing errors and application-level errors, HTTP responses from Kong Gateway (:8080) are classified as follows:

| HTTP Status | Triggering Condition | Diagnostic Interpretation | System Handling |
|---|---|---|---|
| **`HTTP 200 OK`** | Request matches a registered Kong route and the backend microservice executes successfully. | Target microservice operational; data returned in JSON payload. | Collector parses JSON payload and extracts telemetry. |
| **`HTTP 400 Bad Request`** | Kong route matched, but query parameters or requested `event-id` are malformed or unsupported by backend engine. | Microservice alive, but requested analytics or parameters are invalid. | Collector logs error; sets `nwdaf_api_status = 0`. |
| **`HTTP 404 Not Found`** | Requested URL path is not registered in Kong Gateway routes (e.g., `/nnwdaf-eventsubscription/v1/slice-load-level`). | API route not mapped in gateway configuration. | Collector catches exception; metrics remain strict `NaN`. |
| **`HTTP 500 / 502 / 504`** | Backend microservice (`oai-nwdaf-engine` or `oai-nwdaf-nbi-analytics`) crashed, unresponsive, or MongoDB unreachable. | Microservice pipeline failure. | Collector sets `nwdaf_api_status = 0`; retains previous valid or `NaN`. |

---

## 6. Multi-Slice Operational Scope & Boundary

The current testbed implementation establishes the following slice boundaries:

1. **Slice-1 (eMBB — SST: 1, SD: 000001):**
   * Handled by `oai-upf-slice1` (PoC UPF container).
   * PFCP Usage Reporting (URR) is actively enabled.
   * URR reports flow through SMF to `oai-nwdaf-sbi` and are stored in MongoDB `testing.smf`.
   * **Audited Status: Operational for `UE_COMMUNICATION` AnLF analytics.**
2. **Slice-2 (URLLC — SST: 222, SD: 00007b):**
   * Handled by `oai-upf-slice2` (Baseline UPF container).
   * Dedicated to high-priority low-latency canary traffic (10 Hz ping).
   * PFCP URR reporting is currently not ingested into MongoDB for Slice-2.
   * **Audited Status: Excluded from Core AnLF volume reporting; validated exclusively via E2E probe metrics (`e2e_slice2_rtt_ms`).**

---

## 7. Comparative Ablation Study Protocol

To evaluate the true contribution of NWDAF AnLF analytics, the research protocol enforces identical conditions across two primary experimental models:

| Study Configuration | Input Feature Vector | Evaluation Objective |
|---|---|---|
| **Model A: RAN-Only Baseline** | $\mathbf{x}_{\text{RAN}} = [\text{PRB}_1, \text{PRB}_2, \text{MCS}_1, \text{MCS}_2, \text{BLER}_1, \text{BLER}_2, \text{SNR}_1, \text{SNR}_2]$ | Establish diagnostic accuracy baseline without Core visibility. |
| **Model B: RAN + NWDAF AnLF** | $\mathbf{x}_{\text{FUSED}} = [\mathbf{x}_{\text{RAN}}, V_{UL}, V_{DL}, \Delta t, \sigma_{UL}, \Delta V_{UL}/\Delta t]$ | Measure the quantifiable diagnostic gain (F1-score, localization latency) provided by standard 3GPP AnLF analytics. |
| **Model C: RAN + Kernel Telemetry (Optional Reference)** | $\mathbf{x}_{\text{KERNEL}} = [\mathbf{x}_{\text{RAN}}, \text{Backlog}_{\text{UPF}}, \text{Drops}_{\text{UPF}}]$ | Serve as an upper-bound observability reference using host kernel sensors (reported separately, never conflated with 3GPP AnLF). |
