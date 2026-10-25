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

### 2.1 Upstream Mathematical Computation Semantics & Verified Formulas
The verified mathematical formulations executed inside the official OAI NWDAF Engine (`components/oai-nwdaf-engine/internal/engine/ue_communication.go`, audited on commit `9d82b75`) are defined as follows:

1. **Cumulative User-Plane Volume Aggregation:**
   $$V_{UL} = \sum_{i=1}^{N} \text{UlVolume}_i, \quad V_{DL} = \sum_{i=1}^{N} \text{DlVolume}_i$$
   *Extracted from MongoDB session documents populated by SMF Event Exposure from UPF Usage Reports (URR).*
2. **Volume Standard Deviation ($N$-Normalized):**
   $$\bar{V}_{UL} = \frac{1}{N} \sum_{i=1}^{N} \text{UlVolume}_i, \quad \sigma_{UL} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} (\text{UlVolume}_i - \bar{V}_{UL})^2}$$
   *Computed using Go standard library `math.Sqrt` with divisor $N$ (standard deviation with $N$-normalization, rather than sample standard deviation with divisor $N-1$) and assigned to JSON output field `ueComms[0].trafChar.ulVolVariance`.*
3. **Cumulative Window Duration Accumulation:**
   $$\Delta t_{\text{accum}} = \sum_{i=1}^{N} \text{duration}_i \quad (\text{verified source operation: } \texttt{commDur += duration})$$
   *Accumulates individual report duration values directly from URR records (`commDur`). The exact relationship between report `duration` and $(\text{stopTime} - \text{startTime})$ requires additional code tracing, as the audited OAI build sums individual report duration fields directly without calculating differential timestamps; it functions as a monotonic URR event accumulation counter rather than an exact physical session wall-clock timer.*
4. **Control-Plane Network Performance Stub (`network_performance.go`):**
   $$\text{absoluteNum} = \text{collection.CountDocuments}(\dots), \quad \text{relativeRatio} = 0 \quad (\text{hardcoded //TODO in audited build})$$

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

To maintain scientific rigor, all telemetry recorded during experiments is strictly partitioned into three independent tiers:

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
  * *Note on Volume Rate Derivatives:* Upstream NWDAF cumulative volume counters (`nwdaf_comm_ul_bytes`, `nwdaf_comm_dl_bytes`) update in step functions every $\approx 30\text{ s}$ governed by periodic UPF URR reports. Direct 1 Hz differentiation ($\Delta V / \Delta t$) produces intermittent zero-delta plateaus with 30-second burst spikes. If rate derivatives are computed for inference, they require causal windowed aggregation ($\frac{V_t - V_{t-W}}{W}$ where $W \ge 30\text{ s}$) with explicit reset/epoch boundaries; raw 1 Hz instantaneous differentiation does not represent physical instantaneous line-rate throughput.

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
* `nwdaf_comm_freshness` (NWDAF value-change heuristic indicator: 1 if reported user-plane volume tuple updated within 45s, else 0. Operates as a reporting-cadence heuristic, NOT a raw data validity mask; unchanged values occur legitimately during stable zero-traffic periods and must not trigger automatic row deletion)
* `e2e_probe_freshness` (Canary reply arrival indicator: 1 if active ICMP echo reply received from UE-2 within 3.5s, else 0; drops to 0 during link collapse, severe buffer drops, or radio link failure)

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

To evaluate the true contribution of NWDAF AnLF analytics, the research protocol enforces identical conditions across three defined experimental models:

| Study Configuration | Input Feature Vector | Evaluation Objective |
|---|---|---|
| **Model A: RAN-Only Baseline** | $\mathbf{x}_{\text{RAN}} = [\text{PRB}_1, \text{PRB}_2, \text{MCS}_1, \text{MCS}_2, \text{BLER}_1, \text{BLER}_2, \text{SNR}_1, \text{SNR}_2]$ | Establish diagnostic accuracy baseline without Core visibility (O-RAN Near-RT RIC radio visibility only). |
| **Model B: RAN + Standard NWDAF AnLF** | $\mathbf{x}_{\text{NWDAF}} = [\mathbf{x}_{\text{RAN}}, V_{UL}, V_{DL}, \Delta t_{\text{accum}}, \sigma_{UL}]$ *(with optional causal windowed derivative $\frac{V_t - V_{t-W}}{W}, W \ge 30\text{s}$ evaluated separately)* | Measure the quantifiable diagnostic gain (F1-score, localization latency) provided strictly by standardized 3GPP Rel-17 NWDAF AnLF analytics. |
| **Model C: Multi-Domain OAM Reference** | $\mathbf{x}_{\text{OAM}} = [\mathbf{x}_{\text{NWDAF}}, \text{Backlog}_{\text{eMBB}}, \text{Backlog}_{\text{URLLC}}, \text{Drops}_{\text{eMBB}}, \text{Drops}_{\text{URLLC}}, \text{EstLoad}_{\text{eMBB}}, \text{EstLoad}_{\text{URLLC}}]$ | Serve as an extended cross-domain observability reference utilizing host Linux kernel queue/drop counters from `core_adapter.py` and collector-derived load proxies (strictly reported as an OAM diagnostic reference, separated from standard 3GPP AnLF claims; additional sensors provide richer input but do not automatically guarantee an upper bound on performance). |

### 7.1 Telemetry Data Sources, Synchronization, and KPI Availability
To support empirical reproducibility, all feature vectors and KPI evaluations map to declared physical collection points:
1. **CSV Feature Alignment:** Every feature included in $\mathbf{x}_{\text{RAN}}$, $\mathbf{x}_{\text{NWDAF}}$, and $\mathbf{x}_{\text{OAM}}$ corresponds directly to columns in the active 40-column dataset logged by `record_experiment.py` at 1.000 Hz.
2. **Throughput Evaluation Source & Scope Boundary:** In the recorded CSV, `e2e_slice1_tput_mbps` strictly reflects client-side offered transmission rate generated by `iperf3 -u` on VM-5 (namespace `ue1`). True user-plane goodput is measured at the receiver endpoint (EXT-DN). In intervals where receiver-side logs (`/opt/oran/5gc/ext-dn/iperf_server.log`) are uningested, eMBB goodput SLA cannot be conclusively evaluated and is designated as `Unmeasured / Pending Receiver Evidence`. Joint SLA and two-slice recovery time ($T_{\text{rec}}$) evaluations are likewise conditional on the presence of verified receiver goodput evidence.
3. **Temporal Alignment & Cross-VM Clock Synchronization (System Prerequisite):**
   * *Local Monotonic Elapsed Timing:* On VM-6, `record_experiment.py` uses Python `time.monotonic()` strictly to compute local elapsed experiment duration (`elapsed_sec = time.monotonic() - t_start`). This provides local elapsed timing without backwards steps or forward leaps caused by NTP step adjustments or leap seconds. However, `time.monotonic()` is strictly host-local: it provides no cross-VM alignment, and it does not guarantee uniform sampling intervals ($\Delta t$), as loop cadence remains subject to operating system process scheduling latency and Python runtime overhead.
   * *Cross-VM Wall-Clock Synchronization Prerequisite:* Correlating telemetry events across distinct physical virtual machines (such as aligning client transmission timestamps on VM-5 with receiver arrival timestamps on VM-3 EXT-DN) requires disciplined inter-host clock synchronization. An authoritative upstream NTP reference server has not yet been formally established or verified in the testbed manifest. Therefore, configuring and verifying an authoritative time source across all six virtual machines (`VM-1` to `VM-6`) is documented as a mandatory **Deployment Prerequisite** (avoiding unverified assignment to subnet gateway `10.102.0.1` or VM-3 `10.102.0.164`).
   * *Synchronization Verification Commands & Distinct Outputs:* Testbed operators must inspect synchronization health using the tool corresponding to the active daemon:
     * *General system clock status:*
       ```bash
       timedatectl status
       # Evaluates: "System clock synchronized: yes" and "NTP service: active"
       ```
     * *Specific diagnostics for systemd-timesyncd:*
       ```bash
       timedatectl timesync-status
       # Reports distinct daemon metrics: Server, Poll interval, Offset, Delay, and Jitter
       ```
     * *Specific diagnostics for chrony:*
       ```bash
       chronyc tracking
       # Reports distinct RFC 5905 metrics: Reference ID, Stratum, Last offset, RMS offset, Root delay, and Root dispersion
       ```
   * *Target Acceptance vs. Measured Uncertainty:* Setting an operational target (such as RMS offset $< 5\text{ ms}$ and root dispersion $< 10\text{ ms}$) defines an acceptance threshold for admitting correlated test runs, but does not prove an inter-host jitter of $\pm 5\text{ ms}$. In experimental evaluations that require multi-VM log alignment, the actual measured offset, root delay, and root dispersion from `chronyc tracking` (or offset and jitter from `timedatectl timesync-status`) must be recorded during the trial and reported as the empirical time uncertainty budget, rather than stated as a constant assumption.
