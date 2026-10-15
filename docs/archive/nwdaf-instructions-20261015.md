# 3GPP NWDAF Technical Specification, Integration Guidelines, and Testbed Scope

**Reference Standards:** 3GPP TS 23.288, TS 29.520, TS 28.552 (Release 19 / Release 17 Alignment)  
**Supplemental Frameworks:** ETSI, O-RAN Alliance, GSMA, ITU-T (Y.3172 / Y.3174), and UU PDP No. 27/2022  
**Target Environment:** Non-RT RIC Host (VM-1), Near-RT RIC Host (VM-2), Multi-Slice 5G Core & NWDAF (VM-3), O-RAN Split RAN (VM-4), nrUE (VM-5), and Monitoring / Telemetry Collector Host (VM-6)  
**System Role:** Authoritative Architectural Manual & Testbed Delimitation Document

---

## 1. Executive Overview

The **Network Data Analytics Function (NWDAF)** is a standardized 3GPP Network Function (NF) residing within the 5G Service-Based Architecture (SBA). Its primary role is to collect operational telemetry across the 5G System (5GS), process raw network events into descriptive statistics or predictive machine learning (ML) models, and expose standardized analytics to other Network Functions (e.g., PCF, SMF, AMF, NSSF) and management systems (OAM, RIC) to enable automated, closed-loop network optimization.

Within a 5G Standalone (5GC) deployment, NWDAF provides analytical insights into:
* Network slice and NF resource utilization.
* User Equipment (UE) mobility, dispersion, and communication dynamics.
* Quality of Service (QoS) sustainability and service experience degradation.
* User-plane and transport congestion.
* Network anomaly detection and signaling storm prediction.

> [!IMPORTANT]
> **Fundamental Design Principle:**  
> NWDAF is **not** an exhaustive, monolithic monitoring agent that automatically polls every metric and counter from all 5G network components. The telemetry accessible to an NWDAF instance is strictly constrained by:
> 1. Available standardized Network Function Services and Exposure APIs.
> 2. The specific **Analytics IDs** (Stage 2) or **Event IDs** (Stage 3) requested by consumers.
> 3. Supported 3GPP Release features (e.g., Release 15/16 baseline vs. Release 17/18/19 enhancements).
> 4. Physical deployment architecture and vendor/open-source implementation boundaries.

---

## 2. Authoritative Specification Hierarchy

The technical foundation of NWDAF is governed by three primary, complementary 3GPP specifications published through ETSI:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   3GPP TS 23.288 (Stage 2)                              │
│   Architecture Enhancements for 5GS to Support Network Data Analytics  │
│   • Functional entities (AnLF, MTLF, DCCF, ADRF, MFAF)                 │
│   • Data collection mechanisms, input NF services, & Analytics IDs     │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│       3GPP TS 29.520 (Stage 3)       │  │   3GPP TS 28.552 (OAM / PM)   │
│   Network Data Analytics Services    │  │   5G Performance Measurements │
│   • OpenAPI REST specifications      │  │   • Standardized PM counters  │
│   • Nnwdaf_AnalyticsInfo (HTTP GET)  │  │   • AMF, SMF, UPF, & gNB      │
│   • Nnwdaf_EventsSubscription (POST) │  │     performance indicators    │
│   • JSON schemas & error definitions │  │   • Management plane inputs   │
└──────────────────────────────────────┘  └──────────────────────────────┘
```

### 2.1 Specification Role Matrix

| Specification | Primary Scope | Core Clauses & References | Critical Architectural Question Answered |
|---|---|---|---|
| **3GPP TS 23.288**<br>*(ETSI TS 123 288)* | System Architecture & Analytics Capabilities (Stage 2) | Clauses 4, 5, 6.1–6.25, and Clause 7 (Table 7.1-2) | *How does NWDAF coordinate data collection, what inputs are required, and what analytics are generated?* |
| **3GPP TS 29.520**<br>*(ETSI TS 129 520)* | Protocol & API Implementation (Stage 3) | Clauses 4, 5.1, 5.2, and Annex A (OpenAPI Schemas) | *How do consumer NFs request, subscribe, and receive analytics payloads over HTTP/2 REST APIs?* |
| **3GPP TS 28.552**<br>*(ETSI TS 128 552)* | 5G Performance Measurements & PM Counters | Clauses 5.1–5.18 (gNB and 5GC NF counters) | *What physical performance counters and metrics are standardized across AMF, SMF, UPF, and RAN?* |

---

## 3. NWDAF Architecture & Operational Workflow

### 3.1 Logical Functions Decomposition

In 3GPP specifications (TS 23.288 Clauses 4–5), NWDAF functionality is decomposed into discrete logical functions:

* **AnLF (Analytics Logical Function):**  
  Responsible for computing descriptive statistics, ingesting historical telemetry, running inference against trained models, and serving analytics to consumers via Service-Based Interfaces (SBI).
* **MTLF (Model Training Logical Function):**  
  Responsible for training, validating, and updating machine learning models based on historical datasets, and exposing trained model artifacts to the AnLF.
* **DCCF (Data Collection Coordination Function):**  
  Coordinates multi-source data collection across NFs and OAM, preventing redundant subscriptions and duplicate network queries.
* **ADRF (Analytics Data Repository Function):**  
  Serves as the persistent storage layer for historical training datasets, raw telemetry records, and trained ML models.
* **MFAF (Messaging Framework Adaptation Function):**  
  Translates and adapts high-volume telemetry streams across messaging brokers (e.g., Kafka, AMQP) into standardized 3GPP notifications.

> [!NOTE]
> **Normative Boundary of MTLF:**  
> According to 3GPP TS 23.288, the MTLF is an internal logical function of the NWDAF. External data science pipelines or offline machine learning engines (such as models trained for an O-RAN Non-RT RIC rApp) do **not** automatically constitute a 3GPP MTLF, but rather represent external analytical consumers or independent management-plane intelligence.

```mermaid
flowchart TD
    subgraph Data Sources
        UPF["UPF (N4 / PFCP)"]
        SMF["SMF (Nsmf_EventExposure)"]
        AMF["AMF (Namf_EventExposure)"]
        OAM["OAM / Management Plane"]
        RAN["O-RAN / gNB (via OAM)"]
    end

    subgraph 3GPP TS 23.288 NWDAF Architecture
        DCCF["DCCF (Data Coordination)"]
        ADRF["ADRF (Historical Repository)"]
        MTLF["MTLF (Model Training)"]
        AnLF["AnLF (Analytics Engine & NBI)"]
    end

    subgraph Consumer NFs / Optimization
        PCF["PCF (Policy Control)"]
        SMF_C["SMF (Session / UPF Selection)"]
        RIC["O-RAN Non-RT RIC rApp (VM-1)"]
    end

    UPF -->|URR / QoS Mon| SMF
    SMF -->|SBI Event Exposure| DCCF
    AMF -->|SBI Event Exposure| DCCF
    OAM -->|PM Counters| DCCF
    RAN -->|PM / Telemetry| OAM

    DCCF --> ADRF
    DCCF --> AnLF
    ADRF --> MTLF
    MTLF -->|Trained Models| AnLF

    AnLF -->|Nnwdaf_AnalyticsInfo| PCF
    AnLF -->|Nnwdaf_EventsSubscription| SMF_C
    AnLF -->|Northbound 3GPP REST API| RIC
```

### 3.2 Standard Operational Workflow

1. **Analytics Request / Subscription:**  
   A consumer (e.g., PCF, SMF, or external controller) issues a request or establishes an event subscription specifying a target `EventId` (Stage 3) or `Analytics ID` (Stage 2), target UE identifier (`tgt-ue`), network slice (`s-nssai`), DNN, and time window (`ana-req`).
2. **NF Discovery & Data Source Identification:**  
   NWDAF identifies relevant data producers by querying the Network Repository Function (NRF) for registered NF instances (AMF, SMF, UDM).
3. **Data Ingestion:**  
   NWDAF initiates event subscriptions via NF Service-Based Interfaces (Channel E) or requests performance management counters via OAM interfaces (Channel O).
4. **Data Normalization & Correlation:**  
   Raw events from disparate NFs are temporally and contextually aligned using common dimension keys (Timestamp, SUPI, S-NSSAI, DNN, Cell ID/TAI, QFI).
5. **Analytics Inference / Calculation:**  
   The AnLF computes statistical aggregations or executes model inference using weights provided by the MTLF.
6. **Payload Exposure:**  
   The resulting analytics payload is delivered to the consumer either synchronously (Request/Response) or asynchronously (Subscribe/Notify).
7. **Closed-Loop Action:**  
   The consumer NF consumes the analytics to execute network actions (e.g., PCF updates QoS parameters, SMF reselects an optimal UPF, or RIC triggers traffic steering).

---

## 4. Standardized Analytics Capabilities (Stage 2 vs. Stage 3 Mapping)

In 3GPP specifications, a distinction exists between **Stage 2 conceptual capability names** (TS 23.288 Table 7.1-2) and **Stage 3 protocol enumeration identifiers** (TS 29.520):

* In **TS 29.520 Release 17**, slice load information is exposed under the `EventId` enumeration `LOAD_LEVEL_INFORMATION` (yielding `SliceLoadLevelInformation`) or `NSI_LOAD_LEVEL`, whereas `UE_COMMUNICATION` and `NETWORK_PERFORMANCE` share identical naming across Stage 2 and Stage 3.
* In **TS 23.288 / TS 29.520 Release 19**, additional event enumerations and enhanced analytics types are formalized.

The table below catalogs standardized capabilities, classified into **Descriptive**, **Predictive**, and **Decision Support**:

| Analytics Category | Stage 2 Capability (TS 23.288) | Stage 3 EventId (TS 29.520 Rel-17/19) | Output Semantics & Analytical Scope | Classification |
|---|---|---|---|---|
| **Load & Capacity** | Slice load level | `LOAD_LEVEL_INFORMATION` / `NSI_LOAD_LEVEL` | Current and predicted load level for a target S-NSSAI based on active sessions and resource limits. | Descriptive / Predictive |
| | NF load | `NF_LOAD` | Resource utilization (CPU, memory, storage) and traffic load of specific NF instances. | Descriptive / Predictive |
| | Network performance | `NETWORK_PERFORMANCE` | Aggregated network health, session establishment success ratios (`SESS_SUCC_RATIO`), and failure distributions. | Descriptive / Predictive |
| **User Mobility** | UE mobility | `UE_MOBILITY` | Historical trajectories, duration of stay within target cells/TAIs, and predicted future locations. | Descriptive / Predictive |
| | UE communication | `UE_COMMUNICATION` | Cumulative uplink/downlink volume, communication duration, periodic intervals, and volume variance. | Descriptive / Predictive |
| | User data congestion | `USER_DATA_CONGESTION` | User-plane buffer backlog, packet discard rates, and RAN/Core congestion level indices. | Descriptive / Predictive |
| **Quality of Service** | Service experience | `SERVICE_EXPERIENCE` | Observed MOS (Mean Opinion Score), application latency, and perceived end-user service quality. | Descriptive / Predictive |
| | QoS sustainability | `QOS_SUSTAINABILITY` | Probability of QoS degradation below guaranteed thresholds (GBR) within a defined geographic area. | Predictive / Decision Support |
| **Anomalies & Security**| Abnormal behaviour | `ABNORMAL_BEHAVIOUR` | Deviations from expected UE behavioral profiles (e.g., unexpected mobility, abnormal uplink volume). | Descriptive / Predictive |
| | Signalling storm | `SIGNALLING_STORM` | Detection and forecasting of massive, synchronized signaling surges (e.g., IoT reconnection bursts).| Predictive |

---

## 5. Multi-Domain Telemetry Ingestion Channels (E, O, V)

To prevent data misattribution, 3GPP and ETSI categorize telemetry sources into three distinct ingestion channels:

* **Channel E (Standardized Exposure API):**  
  Data and asynchronous events acquired directly from standardized NF Service-Based Interfaces (TS 23.288 §6.2.2).
* **Channel O (OAM / Performance Management):**  
  Standardized performance counters, system alarms, and management records provided through Element Management / Network Management systems (TS 28.552).
* **Channel V (Vendor / System Implementation):**  
  Operating system-level telemetry, kernel socket queues, and vendor-proprietary instrumentation that are not exposed over standard 3GPP SBIs.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Ingestion Channels Matrix                       │
├──────────────────┬──────────────────┬──────────────────────────────────┤
│ Channel E        │ Channel O        │ Channel V                        │
│ Standard SBI     │ OAM / PM Counters│ Host / Kernel Telemetry          │
│ (3GPP TS 23.288) │ (3GPP TS 28.552) │ (Linux / eBPF / Socket API)      │
├──────────────────┼──────────────────┼──────────────────────────────────┤
│ • Namf_EventExp  │ • PRB Utilization│ • Linux tc qdisc buffer backlog  │
│ • Nsmf_EventExp  │ • Active PDU Sess│ • Egress kernel drops (skb drop) │
│ • Nudm_EventExp  │ • GTP RTT / Loss │ • Socket buffer unallocated bytes│
│ • Npcf_EventExp  │ • CPU/RAM util   │ • Hardware MAC ring descriptors  │
└──────────────────┴──────────────────┴──────────────────────────────────┘
```

### 5.1 Telemetry Matrix by Network Function

| Network Function | Standardized Metrics & Event Types | Ingestion Channel | Standard Source Reference |
|---|---|---|---|
| **AMF** *(Access & Mobility)* | Registration attempts/successes, paging events, UE TAI/Cell location updates, connection state transitions. | **E, O** | TS 23.288 §6.2.2.1 / TS 28.552 §5.2 |
| **SMF** *(Session Management)* | Active PDU sessions, establishment/modification attempts, QoS Flow allocations, S-NSSAI/DNN mappings. | **E, O** | TS 23.288 §6.2.2.1 / TS 28.552 §5.3 |
| **UPF** *(User Plane Function)* | Uplink/Downlink octets and packets, GTP-U round-trip time, packet loss count, PFCP Usage Reports (URR). | **E (via SMF N4), O** | TS 29.244 / TS 28.552 §5.4 |
| **PCF** *(Policy Control)* | Policy association events, rule update successes/failures, QoS rule trigger notifications. | **E, O** | TS 23.288 §6.2.2.1 / TS 28.552 §5.5 |
| **NRF** *(Repository Function)* | NF instance registrations, heartbeat statuses, registered NF profiles, dynamic NF load attributes. | **E, O** | TS 29.510 / TS 28.552 |
| **gNB / NG-RAN** | Physical Resource Block (PRB) utilization, RRC connection counts, ULSCH/DLSCH SNR, MCS, BLER, handover metrics. | **O (via OAM / RIC)** | TS 38.314 / TS 28.552 §5.1 |
| **Host Kernel (UPF Host)** | Socket buffer backlogs (`tc qdisc`), network interface transmit drops, memory and vCPU saturation. | **V / OAM Host Adapter** | Linux Netlink / `rtnetlink(7)` |

> [!NOTE]
> **Radio Access Network Separation:**  
> A gNB is not a part of the 5G Core. NWDAF has **no native SBI** connecting directly to base stations. All radio telemetry must be ingested either through the OAM Performance Management framework (Channel O) or through standardized RIC–NWDAF interworking interfaces.

---

## 6. Standardized Service-Based Interfaces (TS 29.520)

Communication with NWDAF occurs via HTTP/2 utilizing JSON payloads compliant with OpenAPI 3.0 schemas defined in 3GPP TS 29.520 Annex A:

### 6.1 `Nnwdaf_AnalyticsInfo` (Synchronous Query)
* **HTTP Method:** `GET`
* **Resource Path:** `/nnwdaf-analyticsinfo/v1/analytics`
* **Query Parameters:**
  * `event-id`: Required 3GPP `EventId` enumeration (e.g., `UE_COMMUNICATION`, `NETWORK_PERFORMANCE`).
  * `ana-req`: JSON-encoded analytics request parameters, containing `startTs` and `endTs` ISO-8601 timestamps.
  * `event-filter`: Filtering criteria specifying target `snssais`, `dnns`, or `anyUeInd`.
  * `tgt-ue`: Target UE identity filter (e.g., `supi` or `gpsi`).

### 6.2 `Nnwdaf_EventsSubscription` (Asynchronous Notification)
* **HTTP Method:** `POST`
* **Resource Path:** `/nnwdaf-eventssubscription/v1/subscriptions`
* **Request Body:** Contains subscription criteria, target event identifiers, sampling intervals, and the callback URI (`notificationURI`) where NWDAF publishes notification webhooks.

---

## 7. Supplemental Standards & Indonesian Regulatory Framework

1. **ITU-T Recommendation Y.3172 & Y.3174:**  
   Establishes the architectural framework for machine learning pipelines in telecommunications networks, including Data Brokers, Machine Learning Functions (MLFO), and sandbox environments.
2. **O-RAN Alliance / ETSI TR 104 037:**  
   Defines coordination models between 5G Core NWDAF and O-RAN Near-RT / Non-RT RIC. While NWDAF manages core-side slice and session analytics ($> 100\text{ ms}$ timescale), the Near-RT RIC executes real-time radio resource control ($10 - 100\text{ ms}$ timescale).
3. **GSMA 5G Intelligent Packet Core:**  
   Documents industry best practices for deploying NWDAF to achieve zero-touch closed-loop experience assurance and automated user-plane traffic steering.
4. **Indonesian Regulatory Compliance (UU No. 27 Tahun 2022 - Pelindungan Data Pribadi / PDP):**  
   Whenever NWDAF processes individual subscriber identifiers (SUPI, IMSI, GPSI, or granular cell location trajectories), the system must enforce strict pseudonymization, role-based access control, and telemetry aggregation to maintain full compliance with Indonesian personal data protection statutes.

---

## 8. Specific Testbed Implementation Scope & Delimitation (Repository Baseline)

To maintain scientific integrity in our research (*"Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks"*), the testbed implementation establishes explicit boundaries and decoupling between standardized 3GPP NWDAF endpoints and empirical host telemetry.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Testbed Telemetry & Dataflow Architecture                       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   [ VM-4: Split RAN ]                      [ VM-3: 5G Core & NWDAF ]                   │
│   • OAI DU1 / DU2 Scheduler Logs           • UPF simpleswitch (URR via N4 PFCP)        │
│   • Instantaneous NPRB, SNR, MCS, BLER     • SMF-1 (Nsmf_EventExposure QOS_MON)        │
│          │                                 • oai-cn5g-nwdaf Stack (AnLF)               │
│          │                                 • UPF eth0 tc qdisc backlog & drops         │
│          │                                        │                   │                │
│          │ (Channel O/V: POST :9100/report)       │                   │                │
│          ▼                                        ▼                   ▼                │
│   ran_adapter.py                         core_adapter.py v9    Kong API Gateway        │
│          │                                        │            (:8080 NBI REST)        │
│          │                                        │                   │                │
│          │ (POST :9100/report)                    │ (POST :9100/report)│ (HTTP GET)     │
│          └───────────────────────┬────────────────┘                   │                │
│                                  │                                    │                │
│                                  ▼                                    ▼                │
│                   [ VM-6: Monitoring Host / Telemetry Collector ]                      │
│                   • telemetry_collector.py (Ingests Adapter JSON & Polls NWDAF API)    │
│                   • Prometheus TSDB (:9100/metrics)                                    │
│                   • record_dual_stream.py (Exports 37-Column CSV)                      │
│                                  │                                                     │
│                                  ▼ (Telemetry Sync)                                    │
│                   [ VM-1: O-RAN Non-RT RIC & SMO Host ]                                │
│                   • Closed-Loop rApp Steering Engine (MAPE-K Cycle)                    │
│                   • Offline Trained ML Models (Decision Tree / Bottleneck Classifier)  │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.1 Architectural Role: AnLF vs. Offline rApp Model Training
* **Deployed OAI NWDAF Microservice Stack (VM-3):**  
  As verified in our system audit, the 8 active containers on VM-3 (`10.102.0.164`) comprise:
  1. `oai-nwdaf-nbi-gateway` (Kong API Gateway, port 80/8080/8001)
  2. `oai-nwdaf-nbi-analytics` (Analytics NBI document service, port 6059)
  3. `oai-nwdaf-nbi-events` (Events subscription service, port 6060)
  4. `oai-nwdaf-nbi-ml` (ML NBI service, port 6061)
  5. `oai-nwdaf-engine` (Internal analytics computation engine, port 6063)
  6. `oai-nwdaf-engine-ads` (Anomaly Detection Service container)
  7. `oai-nwdaf-sbi` (Service-Based Interface for NF notification ingestion, port 6062)
  8. `oai-nwdaf-database` (MongoDB instance storing `testing.smf` collections, port 27017)
* **Functional Delimitation:**  
  The deployed NWDAF acts strictly as an **AnLF (Analytics Logical Function)**. The open-source OAI NWDAF codebase does not implement an autonomous 3GPP-standard MTLF, DCCF, or ADRF.
* **Separation of rApp Machine Learning:**  
  All predictive machine learning models, statistical threshold classifiers, and multi-slice traffic steering policies reside in the **O-RAN Non-RT RIC rApp on VM-1 (`10.102.0.168`)**. Model training is conducted offline using experimental dataset runs, representing an external O-RAN data science workflow rather than an internal 3GPP NWDAF MTLF.

### 8.2 Standard Exposure (Channel E): `UE_COMMUNICATION` Active
* **Native Ingestion Chain:**  
  The 5-layer native 3GPP telemetry chain is fully active and verified:
  1. *UPF Datapath:* URR 1 bound to PDR 1 accumulates datapath octets and packets on `simpleswitch`.
  2. *PFCP N4:* UPF emits periodic N4 Session Report Requests.
  3. *SMF Exposure:* SMF-1 extracts counters and fires `Nsmf_EventExposure` (`QOS_MON`, Event 98) HTTP/2 notifications.
  4. *NWDAF SBI:* `oai-nwdaf-sbi` receives notifications and stores `CustomUsageReport` records in MongoDB `testing.smf` under `qosmonlist`.
  5. *NWDAF Engine & NBI:* `oai-nwdaf-engine` aggregates records, exposing them via Kong Gateway at `http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION`.
* **Standard Telemetry Columns in Dataset:**
  * `nwdaf_comm_ul_bytes`: Standard cumulative uplink user-plane volume in bytes.
  * `nwdaf_comm_dl_bytes`: Standard cumulative downlink user-plane volume in bytes.
  * `nwdaf_comm_vol_std_bytes`: Uplink/downlink traffic volume standard deviation across ingested URR reports.
  * `nwdaf_comm_freshness`: Telemetry freshness indicator (1 = updated within 45s, 0 = stale).
  * `nwdaf_api_status`: Northbound HTTP 200 health indicator (1 = healthy, 0 = unreachable).
* **Semantic Limitation of `nwdaf_comm_duration_sec`:**  
  > [!WARNING]
  > In the upstream OAI NWDAF engine (`internal/engine/ue_communication.go`), `commDur` is computed by cumulatively summing the durations of all ingested URR reports falling within the query window (`totalDuration += report.Duration`). Because reports arrive periodically every 30 seconds, this calculation accumulates overlapping time windows over prolonged runs (e.g., >8000s), functioning as a **monotonic event-accumulation indicator** rather than an accurate physical session elapsed time.

### 8.3 Handling of Upstream Code Limitations & Unsupported Event IDs
* **Upstream Code Audit (`network_performance.go`):**  
  Audit of the pinned OAI NWDAF engine codebase (`components/oai-nwdaf-engine/internal/engine/network_performance.go`) reveals that under `nwPerfNumOfPdu`, `relativeRatio` and `confidence` remain hardcoded to constant `0` with an uncompleted `//TODO` upstream:
  ```go
  // Relative ratio and confidence remain //TODO upstream:
  relativeRatio, confidence := int32(0), int32(0)
  ```
  `absoluteNum` dynamically reports active PDU sessions counted from MongoDB, but `relativeRatio` does not compute true resource ratios.
* **Stage 3 Event ID Restriction:**  
  Inspection of `api_nwdaf_analytics_document_service.go` shows that the NBI switch case strictly supports only three event identifiers: `NETWORK_PERFORMANCE`, `UE_COMMUNICATION`, and `UE_MOBILITY`. Queries for other 3GPP event identifiers (such as `LOAD_LEVEL_INFORMATION`, `NSI_LOAD_LEVEL`, or `QOS_SUSTAINABILITY`) return HTTP 400 (`"invalid Event Id param"`).
* **Preserving Scientific Integrity:**  
  Because slice load percentages are not calculated by the upstream engine, the testbed pipeline explicitly assigns `nwdaf_load_embb` and `nwdaf_load_urllc` as **`NaN`** in the dataset. Slice load is instead monitored using empirical interface utilization proxies (`estimated_load_embb`, `estimated_load_urllc`) derived from UPF egress throughput.

### 8.4 High-Frequency Channel O & Channel V Decoupling
* **Decoupled Architecture:**  
  High-frequency kernel transport queues (`upf_queue_backlog_bytes` on `eth0`) and hardware/kernel drops (`upf_drops_embb`, `upf_drops_urllc`) are sampled at **1.0 Hz** directly via `core_adapter.py` v9 on VM-3. Physical gNB radio metrics (`ran_prb_cell1`, `ran_mcs_cell1`, `ran_bler_cell1`, `ran_snr_cell1`, `ran_rssi_cell1`) are parsed live from MAC scheduler logs on VM-4 via `ran_adapter.py`.
* **Rationale & Sampling Behavior:**  
  The 30-second reporting cadence observed on our NWDAF datapath is an artifact of the UPF's periodic URR reporting configuration (`PERIODIC_REPORT_TIME`) and SMF notification batching, rather than a normative 3GPP prohibition against 1 Hz sampling. However, polling high-frequency kernel socket queues directly via lightweight host adapters provides instantaneous 1-second visibility into transport queue backlogs without imposing excessive HTTP/2 polling overhead on the 5G Core control plane.

---

## 9. Practical Guidelines for Dataset Generation & Research Verification

Following the best-practice methodology outlined in 3GPP and ETSI research literature, researchers and thesis evaluators should follow these operational steps:

1. **Focus on Verified Analytics IDs:**  
   Do not attempt to poll unsupported Analytics IDs from the open-source core. Rely on `UE_COMMUNICATION` for native 3GPP user-plane validation.
2. **Execute Pre-Flight Validation:**  
   Before recording experimental runs, execute the 4-point audit:
   * Verify UE connectivity and ping canaries on VM-5 (`10.102.0.165` / `10.102.0.166`).
   * Verify UPF container qdisc and active sessions on VM-3 (`10.102.0.164`).
   * Verify NWDAF NBI HTTP 200 response on `http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics`.
   * Verify 37 active metrics on VM-6 (`curl -s http://localhost:9100/metrics`).
3. **Multi-Domain Data Alignment:**  
   Utilize `scripts/record_dual_stream.py` on VM-6 to record cross-domain observations synchronized with UTC and monotonic timestamps.
4. **Transparent Academic Reporting:**  
   In thesis publications, cite 3GPP TS 23.288 and TS 29.520 for the AnLF interface, while explicitly documenting that model training is executed offline on the Non-RT RIC host (VM-1) for rApp deployment, clearly distinguished from internal 3GPP NWDAF MTLF routines.
