# 3GPP NWDAF Integration, Native Telemetry Pipeline, and Scope Delimitation

**Authoritative Specification:** Single Source of Truth for NWDAF Integration  
**Standard References:** 3GPP TS 23.288, TS 29.520, TS 28.552 (Release 17 Baseline / Release 19 Context)  
**Target Environment:** VM-3 (`oai-core`: 5G Core & NWDAF Host) and VM-6 (`monitoring-data`: Telemetry Collector)  
**System Role:** Service-Based Analytics Exposure & Native User-Plane Telemetry Ingestion

---

## 1. Architectural Scope & Standards Demarcation

The **Network Data Analytics Function (NWDAF)** is a standardized 3GPP Network Function within the 5G Service-Based Architecture (SBA). In our multi-slice experimental testbed:

* **Logical Function Role:**  
  The deployed OpenAirInterface (OAI) `cn5g-nwdaf` microservice stack operates strictly as an **AnLF (Analytics Logical Function)**. It ingests standardized event exposure notifications, aggregates historical records in a MongoDB datastore, and exposes analytical endpoints over a Northbound API (NBI).
* **Demarcation of Machine Learning (MTLF):**  
  > [!NOTE]
  > Under 3GPP TS 23.288, the Model Training Logical Function (MTLF) is an internal NWDAF sub-function. In our research testbed, **offline model training and predictive anomaly classification are executed externally within the O-RAN Non-RT RIC rApp on VM-1 (`10.102.0.168`)**. The rApp acts as an analytics consumer of NWDAF and OAM data, representing an O-RAN data science workflow rather than a 3GPP internal MTLF.
* **Dual-Track Telemetry Decoupling:**  
  NWDAF is **not** an all-inclusive monitoring agent for low-level OS counters. High-frequency 1.0 Hz Linux kernel socket queue backlogs (`tc qdisc`) and packet drops are extracted directly by `core_adapter.py` v9 on VM-3 and streamed to VM-6, completely decoupled from the 5GC control-plane HTTP/2 stack.

---

## 2. 5-Layer Native 3GPP User-Plane Telemetry Chain (Channel E)

The testbed implements and empirically validates the complete native 3GPP telemetry propagation chain under Control and User Plane Separation (CUPS):

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      5-Layer Native 3GPP User-Plane Telemetry Chain                    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Layer 1: UPF Datapath Accumulation                                                    │
│  • oai-upf-slice1 (simpleswitch datapath) accumulates bytes and packets                │
│  • URR ID 1 bound to PDR 1 with Periodic Reporting enabled                             │
│                                │                                                       │
│                                ▼ (N4 Session Report Request: msg type 56, 109 bytes)   │
│  Layer 2: PFCP N4 Transport                                                            │
│  • UPF usage_report_loop() transmits periodic reports over UDP :8805                   │
│  • Includes IE Type 62 (Measurement Method) and volume octets                          │
│                                │                                                       │
│                                ▼ (Nsmf_EventExposure: Event 98 QOS_MON)                │
│  Layer 3: SMF Ingestion & Exposure                                                     │
│  • oai-smf-slice1 extracts UL/DL bytes and dispatches HTTP/2 notifications             │
│                                │                                                       │
│                                ▼ (POST /nnwdaf-sbi/v1/notification)                    │
│  Layer 4: NWDAF SBI Ingestion & Storage                                                │
│  • oai-nwdaf-sbi receives notification and pushes CustomUsageReport                    │
│  • MongoDB testing.smf appends records into qosmonlist array                           │
│                                │                                                       │
│                                ▼ (Internal MongoDB Query)                              │
│  Layer 5: NWDAF Engine & Northbound REST API                                           │
│  • oai-nwdaf-engine aggregates qosmonlist records                                      │
│  • Kong API Gateway (:8080) exposes GET /nnwdaf-analyticsinfo/v1/analytics             │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Analytics Capabilities & Semantic Limitations

### 3.1 `UE_COMMUNICATION` (3GPP TS 29.520 §5.1.6.3.2) — **Validated**
* **NBI Endpoint:** `GET http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION`
* **Query Parameters:** URL-encoded `ana-req` with `startTs` and `endTs` ISO-8601 timestamps.
* **Payload Structure:**
  ```json
  {
    "anaMetaInfo": {
      "dataWindow": { "startTime": "2026-10-01T00:00:00Z", "stopTime": "2026-10-31T23:59:59Z" }
    },
    "ueComms": [
      {
        "commDur": 10585,
        "ulVol": 2688,
        "dlVol": 2688
      }
    ]
  }
  ```
* **Dataset Metrics Mapped:**
  * `nwdaf_comm_ul_bytes`: Cumulative uplink user-plane volume in bytes.
  * `nwdaf_comm_dl_bytes`: Cumulative downlink user-plane volume in bytes.
  * `nwdaf_comm_vol_std_bytes`: Standard deviation of report volumes computed by upstream engine.
  * `nwdaf_comm_freshness`: Binary indicator (`1` = source URR volume changed $\le 45\text{ s}$, `0` = stale/idle).
* **Semantic Limitation of `nwdaf_comm_duration_sec`:**  
  > [!WARNING]
  > In the upstream OAI engine (`internal/engine/ue_communication.go`), `commDur` is calculated via `totalDuration += report.Duration` across all reports in the query window. Because reports are emitted periodically every 30 seconds, this sums overlapping intervals over extended runs (e.g., >8000s). Thus, `nwdaf_comm_duration_sec` serves as a **monotonic URR event-accumulation counter**, rather than an exact physical session elapsed time.

### 3.2 `NETWORK_PERFORMANCE` (3GPP TS 29.520 §5.1.6.3.10) — **Validated with Upstream Limitation**
* **NBI Endpoint:** `GET http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=NETWORK_PERFORMANCE`
* **Query Filters:** Requires `event-filter` containing `snssais`, `dnns`, and `nwPerfTypes` set to `["SESS_SUCC_RATIO"]`.
* **Observed Response:** Returns HTTP 200 with dynamic `absoluteNum: 1` reflecting actual PDU session document counts from MongoDB `testing.smf`.
* **Upstream Code Limitation (`network_performance.go`):**  
  Source code audit of `components/oai-nwdaf-engine/internal/engine/network_performance.go` confirms that `relativeRatio` and `confidence` are hardcoded to `0` with an uncompleted `//TODO` upstream:
  ```go
  // Relative ratio and confidence remain //TODO upstream:
  relativeRatio, confidence := int32(0), int32(0)
  ```
  Consequently, `relativeRatio` does not compute dynamic load ratios.

### 3.3 `SLICE_LOAD_LEVEL` (3GPP TS 23.288 §6.3 / TS 29.520) — **Unsupported**
* **Audit Finding:**  
  In the OAI NWDAF NBI service (`api_nwdaf_analytics_document_service.go`), the request dispatcher switch case strictly handles only three event IDs: `NETWORK_PERFORMANCE`, `UE_COMMUNICATION`, and `UE_MOBILITY`.
* **Handling in Dataset:**  
  Any query for `SLICE_LOAD_LEVEL` or `LOAD_LEVEL_INFORMATION` returns HTTP 400 (`"invalid Event Id param"`). To avoid data falsification, `nwdaf_load_embb` and `nwdaf_load_urllc` are explicitly set to **`NaN`** in the dataset. Slice load is monitored using empirical interface proxies (`estimated_load_embb`, `estimated_load_urllc`).

---

## 4. Verification & Diagnostic Procedures

### 4.1 Live NBI Verification (from VM-3 or VM-6)
Execute an HTTP GET query through the Kong API Gateway:
```bash
curl -s -G "http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics" \
  --data-urlencode "event-id=UE_COMMUNICATION" \
  --data-urlencode 'ana-req={"startTs":"2026-10-01T00:00:00Z","endTs":"2026-10-31T23:59:59Z"}' | jq .
```
**Expected Output:** HTTP 200 OK with populated `ueComms` array containing `commDur`, `ulVol`, and `dlVol`.

### 4.2 MongoDB Ingestion Inspection
Inspect the underlying MongoDB datastore on VM-3:
```bash
sudo docker exec -it oai-nwdaf-database mongo testing --eval \
  'db.smf.find({}, {"qosmonlist": 1, "supi": 1, "pduSessionId": 1}).pretty()'
```
**Expected Output:** MongoDB document under `testing.smf` containing array `qosmonlist` with multiple `CustomUsageReport` entries populated with live volume and duration counters.

### 4.3 Container Stack Health
Confirm all 8 NWDAF microservices on VM-3 are healthy:
```bash
sudo docker ps --filter "name=oai-nwdaf" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
The active microservices must include:
1. `oai-nwdaf-nbi-gateway` (Kong port 80, 8080, 8001)
2. `oai-nwdaf-nbi-analytics` (Port 6059)
3. `oai-nwdaf-nbi-events` (Port 6060)
4. `oai-nwdaf-nbi-ml` (Port 6061)
5. `oai-nwdaf-engine` (Port 6063)
6. `oai-nwdaf-engine-ads`
7. `oai-nwdaf-sbi` (Port 6062)
8. `oai-nwdaf-database` (MongoDB port 27017)
