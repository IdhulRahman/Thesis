# VM-6 — Telemetry, Monitoring & Experimentation TSDB

This document provides the complete architecture, telemetry inventory, and deployment guide for **VM-6 (`monitoring-data` — `10.102.0.67`)**, which serves as the centralized observability, time-series database (TSDB), and experimentation evaluation platform for the thesis:

> **Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks**

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| **VM Identifier** | VM-6 | Virtual Machine index |
| **Hostname** | `monitoring-data` | Host identifier |
| **IP Address** | `10.102.0.67` | Static IP on thesis research subnet (`10.102.0.0/24`) |
| **Subnet Mask** | `255.255.255.0` (`/24`) | Inter-VM physical bridge network |
| **Default Gateway** | `10.102.0.1` | Gateway to hypervisor/campus routing |
| **Main Role** | Centralized Telemetry, TSDB & Experiment Logger | Cross-domain observability, SLA tracking, and visualization |
| **Core Software** | Prometheus v2.45+, Grafana v10+, Python 3.10+ | Time-series database, dashboarding, and automated scrapers |
| **Hardware Sizing** | 4 vCPU, 8 GB RAM, 40 GB Disk | Compute and persistent disk allocation |

---

## 2. End-to-End Telemetry & Data Inventory

To prove the thesis hypotheses and evaluate multi-timescale closed-loop coordination, VM-6 ingests telemetric data across all five layers of the 5G O-RAN testbed:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        CROSS-DOMAIN TELEMETRY INVENTORY (VM-6)                         │
├───────────────────┬───────────────────┬────────────────────┬───────────────────────────┤
│  5G Core (VM-3)   │     RAN (VM-4)    │    RICs (VM-1/2)   │        UE (VM-5)          │
│  - 3GPP NWDAF     │  - FlexRIC E2 KPM │  - A1 Policy (rApp)│  - End-to-End Latency     │
│  - UPF Queues     │  - PRB per Slice  │  - xApp Steering   │  - Throughput (eMBB)      │
│  - SliceLoadLevel │  - RLC Delay/CQI  │  - Action Churn    │  - Packet Loss (URLLC)    │
└───────────────────┴───────────────────┴────────────────────┴───────────────────────────┘
```

### 2.1 Domain 1: 5G Core Network & NWDAF (VM-3 — `10.102.0.164`)
Ingested via Core Research Telemetry Adapter (`core_adapter.py` v9) and 3GPP Rel-17 `Nnwdaf` REST API (`http://10.102.0.164:8080`):

> **Core Metrics Validity & Semantic Audit Note:**
> 1. Physical user-plane buffer queue dynamics and packet drops are sampled directly from the Linux kernel using `core_adapter.py` v9 (adhering to 3GPP PM TS 32.401 & TS 28.552).
> 2. Native 3GPP TS 29.520 `UE_COMMUNICATION` telemetry is polled dynamically by `telemetry_collector.py` from Kong Gateway port 8080 (`/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION`).
> 3. Upstream OAI Engine semantics: `nwdaf_comm_duration_sec` sums report elapsed durations (`commDur: 2842s`), and `nwdaf_comm_vol_std_bytes` computes sample standard deviation ($\sigma = 588\text{ B}$). In single-slice PoC (Slice 1), volume counters (`ulVol: 1680B`, `dlVol: 1680B`) match live UPF URR reports, and freshness is tracked with a 35s window.

| Metric Name | Source NF / Method | Unit / Type | Role in Thesis Evaluation |
|---|---|---|---|
| `upf_interface_tx_mbps` | `oai-upf-slice1/2` (`/proc/net/dev`) | Derived Rate (`Mbps`) | Actual transmission throughput of the UPF interface per slice. |
| `upf_interface_rx_mbps` | `oai-upf-slice1/2` (`/proc/net/dev`) | Derived Rate (`Mbps`) | Actual reception throughput of the UPF interface per slice. |
| `upf_queue_backlog_bytes` | `oai-upf-slice1/2` (`tc -j -s qdisc`) | Instantaneous Gauge (`Bytes`) | Physical buffer queue occupancy of UPF. Early detection of Core congestion. |
| `upf_packet_drops_delta` | `oai-upf-slice1/2` (`tc -j -s qdisc`) | Rate / Delta | Physical packet drops due to buffer overflow or queue exhaustion on UPF. |
| `upf_tx_bytes_total` | `oai-upf-slice1/2` (`/proc/net/dev`) | Cumulative Counter | Cumulative egress byte volume since container startup. |
| `upf_rx_bytes_total` | `oai-upf-slice1/2` (`/proc/net/dev`) | Cumulative Counter | Cumulative ingress byte volume since container startup. |
| `nwdaf_comm_duration_sec` | OAI NWDAF NBI (`UE_COMMUNICATION`) | Seconds (`s`) | Aggregated communication duration reported by NWDAF. |
| `nwdaf_comm_ul_bytes` | OAI NWDAF NBI (`UE_COMMUNICATION`) | Bytes (`B`) | Cumulative uplink user-plane volume reported by NWDAF. |
| `nwdaf_comm_dl_bytes` | OAI NWDAF NBI (`UE_COMMUNICATION`) | Bytes (`B`) | Cumulative downlink user-plane volume reported by NWDAF. |
| `nwdaf_comm_vol_std_bytes`| OAI NWDAF NBI (`UE_COMMUNICATION`) | Bytes (`B`) | Volume variation metric (computed as standard deviation $\sigma$ upstream). |
| `nwdaf_comm_freshness` | Collector Poller (`telemetry_collector.py`)| Binary (`1/0`) | Freshness indicator for NWDAF NBI telemetry ($1$ if updated within 35s). |
| `nwdaf_network_performance` | OAI NWDAF NBI (`Nnwdaf_AnalyticsInfo`) | JSON 3GPP TS 29.520 | PDU session control analytics (`SESS_SUCC_RATIO`, static ratio `0`). |
| `amf_active_pdu_sessions` | AMF SBI (`/namf-comm`) | Counter | Ground-truth count of active PDU sessions across slices. |

### 2.2 Domain 2: OpenAirInterface Split RAN (VM-4 — `10.102.0.167`)
Ingested via O-RAN FlexRIC E2 Agent (`E2SM-KPM v2.03` over SCTP `36421`):

| Metric Name | E2 Service Model | Granularity | Role in Thesis Evaluation |
|---|---|---|---|
| `ran_cell_prb_total` | E2SM-KPM (gNB DU) | Percentage (`%`) | Overall radio resource block saturation per cell (Cell-1 :4043 vs Cell-2 :4044). |
| `ran_slice_prb_ratio` | E2SM-KPM (gNB DU) | Ratio (`0.0 - 1.0`) | Proportion of PRBs consumed by Slice 1 (eMBB) vs Slice 2 (URLLC). |
| `ran_ue_cqi` | E2SM-KPM (MAC layer) | Discrete (`0 - 15`) | Channel Quality Indicator per connected UE. Detects radio degradation. |
| `ran_ue_rsrp_dbm` | E2SM-KPM (PHY layer) | Decibel-milliwatt | Radio link strength. Used to contrast standard 3GPP A3 handover with RIC steering. |
| `ran_rlc_buffer_occupancy` | E2SM-KPM (RLC layer) | Bytes | Radio scheduling queue depth. Spikes during pure RAN bottleneck. |
| `ran_rlc_packet_delay_ms` | E2SM-KPM (RLC layer) | Milliseconds (`ms`) | Scheduling delay on the radio access link. |

### 2.3 Domain 3: O-RAN Near-RT & Non-RT RIC (VM-1 — `10.102.0.168` & VM-2 — `10.102.0.66`)
Ingested via A1 PMS REST API (`:8081`), xApp internal telemetry, and rApp decision logs:

| Metric Name | Source Component | Data Type | Role in Thesis Evaluation |
|---|---|---|---|
| `rapp_diagnosed_bottleneck` | rApp Classifier (VM-1) | Enum (`0:NORMAL, 1:RAN, 2:CORE, 3:JOINT`) | Ground-truth classification of bottleneck origin. Core novelty metric. |
| `rapp_classifier_confidence` | rApp Classifier (VM-1) | Float (`0.0 - 1.0`) | AI/heuristic confidence score for root-cause diagnosis. |
| `a1_policy_threshold` | A1 PMS (VM-1 / VM-2) | Numeric (Type 20008) | Active steering threshold enforced from Non-RT to Near-RT RIC. |
| `xapp_steering_decision` | xApp (VM-2) | Enum (`KEEP, CELL_1, CELL_2`) | Real-time traffic steering action dispatched via E2SM-RC. |
| `xapp_action_churn_count` | xApp / rApp | Counter (actions/min) | Handover frequency. Evaluates steering stability and ping-pong avoidance. |
| `xapp_inference_time_ms` | xApp (VM-2) | Milliseconds (`ms`) | Execution time of the near-RT control loop (fast loop latency). |

### 2.4 Domain 4: End-to-End User Experience (VM-5 — `10.102.0.165`)
Ingested directly from the automated multi-slice traffic generator (`trafgen.sh`):

| Metric Name | Workload Generator | Sampling | Role in Thesis Evaluation |
|---|---|---|---|
| `e2e_slice1_throughput_mbps` | `iperf3` (Slice 1 eMBB) | 1.0 second | Ground-truth user-plane throughput delivered across Slice 1. |
| `e2e_slice2_latency_rtt_ms` | Precision Ping (Slice 2 URLLC) | 100 ms | Ground-truth end-to-end RTT latency (min, avg, max, mdev, p95, p99). |
| `e2e_slice2_packet_loss_pct` | Precision Ping (Slice 2 URLLC) | Cumulative (`%`) | SLA violation indicator for mission-critical slice. Must remain 0%. |
| `e2e_sla_violation_status` | SLA Monitor | Binary (`0: OK, 1: VIOLATED`) | Evaluates SLA violation rate ($V_s$) and recovery time ($T_{rec}$). |

---

## 3. High-Level Monitoring Architecture

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              VM-6: monitoring-data (10.102.0.67)                       │
│                                                                                        │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         Unified Grafana Dashboard (:3000)                      │   │
│   │   [Panel 1: NWDAF Slice Load]      [Panel 2: RAN PRB Saturation Cell-1 vs 2]   │   │
│   │   [Panel 3: Bottleneck Diagnosis]  [Panel 4: E2E URLLC Latency vs eMBB Tput]   │   │
│   │   [Panel 5: A1 Policy & Actions]   [Panel 6: SLA Recovery Time (Trec)]         │   │
│   └───────────────────────────────────────▲────────────────────────────────────────┘   │
│                                           │ PromQL Queries                             │
│   ┌───────────────────────────────────────┴────────────────────────────────────────┐   │
│   │                       Prometheus Time-Series Database (:9090)                  │   │
│   │                  Storage: TSDB with 15-day retention (1s scrape)               │   │
│   └───────────────────────────────────────▲────────────────────────────────────────┘   │
│                                           │ Scrape Targets (:9100, :9101, :9102, :9103)│
│   ┌───────────────────────────────────────┴────────────────────────────────────────┐   │
│   │                     Multi-Domain Telemetry Collectors & Exporters              │   │
│   │   - core_nwdaf_exporter.py    -> Polls VM-3 Kong API (:8080) & UPF stats       │   │
│   │   - ran_e2_exporter.py        -> Reads VM-4 FlexRIC KPM telemetry             │   │
│   │   - ric_coordinator_exporter  -> Polls VM-1 A1 PMS (:8081) & rApp decisions    │   │
│   │   - ue_qos_exporter.py        -> Reads VM-5 trafgen logs (iperf3 & ping)       │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Formal Research Evaluation Metrics

Data ingested into VM-6 directly feeds the mathematical formulations required for thesis evaluation (Section 5 of [Methodology](../experiments/methodology.md)):

1. **SLA Violation Rate ($V_s$):**
   $$V_s = \frac{\sum_{k=1}^{K} \mathbb{I}(\text{SLA violated in window } k)}{K} \times 100\%$$
2. **Recovery Time ($T_{rec}$):**
   $$T_{rec} = t_{recover} - t_{inject}$$
   *Evaluates how quickly each baseline restores URLLC latency $<20\text{ ms}$ after a bottleneck injection.*
3. **Macro-F1 Diagnosis Score:**
   $$\text{Macro-F1} = \frac{1}{|C|} \sum_{c \in C} \frac{2 \cdot P_c \cdot R_c}{P_c + R_c}, \quad C = \{\text{NORMAL}, \text{RAN}, \text{CORE}, \text{JOINT}\}$$
4. **Action Churn Rate ($C_{act}$):**
   $$C_{act} = \frac{N_{act}}{T_{\text{minutes}}}$$
   *Measures steering stability and verifies suppression of futile handovers.*

---

## 5. Deployment Guide on VM-6 (`10.102.0.67`)

### Step 1: Docker Compose Stack Setup

Save `/opt/oran/monitoring/docker-compose.yml`:

```yaml
services:
  prometheus:
    image: prom/prometheus:v2.47.0
    container_name: monitoring-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./data/prometheus:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:10.1.0
    container_name: monitoring-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_DASHBOARDS_MIN_REFRESH_INTERVAL=1s
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./data/grafana:/var/lib/grafana
    depends_on:
      - prometheus
```

### Step 2: Prometheus Scrape & Grafana Datasource Configuration

Configure scrape target in `/opt/oran/monitoring/prometheus/prometheus.yml`:
```yaml
global:
  scrape_interval: 1s
  evaluation_interval: 1s

scrape_configs:
  - job_name: 'thesis_telemetry_collector'
    static_configs:
      - targets: ['10.102.0.67:9100']
```

Automate Prometheus datasource in `/opt/oran/monitoring/grafana/provisioning/datasources/prometheus.yml`:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

### Step 3: Automate Dashboard Provisioning & Dashboard JSON

1. Configure Dashboard Provisioning (`/opt/oran/monitoring/grafana/provisioning/dashboards/dashboards.yml`):
```yaml
apiVersion: 1
providers:
  - name: 'Thesis Closed-Loop Dashboards'
    orgId: 1
    folder: 'O-RAN 5G'
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

2. Save Pre-Configured Dashboard JSON (`/opt/oran/monitoring/grafana/provisioning/dashboards/thesis_dashboard.json`):
```json
{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": true,
  "panels": [
    {
      "id": 1,
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
      "type": "timeseries",
      "title": "End-to-End Latency (Slice 2 URLLC)",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "ms",
          "color": { "mode": "palette-classic" },
          "custom": { "fillOpacity": 15, "lineWidth": 2 },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 20 }
            ]
          }
        }
      },
      "targets": [
        { "expr": "e2e_slice2_latency_rtt_ms", "legendFormat": "URLLC RTT (ms)", "refId": "A" }
      ]
    },
    {
      "id": 2,
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
      "type": "timeseries",
      "title": "End-to-End Throughput (Slice 1 eMBB)",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "Mbps",
          "color": { "fixedColor": "#73BF69", "mode": "fixed" },
          "custom": { "fillOpacity": 20, "lineWidth": 2 }
        }
      },
      "targets": [
        { "expr": "e2e_slice1_throughput_mbps", "legendFormat": "eMBB Throughput", "refId": "A" }
      ]
    },
    {
      "id": 3,
      "gridPos": { "h": 6, "w": 8, "x": 0, "y": 8 },
      "type": "stat",
      "title": "URLLC Packet Loss Rate",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 1 }
            ]
          }
        }
      },
      "targets": [
        { "expr": "e2e_slice2_packet_loss_pct", "refId": "A" }
      ]
    },
    {
      "id": 4,
      "gridPos": { "h": 6, "w": 8, "x": 8, "y": 8 },
      "type": "stat",
      "title": "Bottleneck Diagnosis (rApp)",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": { "text": "NORMAL", "color": "green" },
                "1": { "text": "RAN BOTTLENECK", "color": "yellow" },
                "2": { "text": "CORE BOTTLENECK", "color": "orange" },
                "3": { "text": "JOINT BOTTLENECK", "color": "red" }
              }
            }
          ]
        }
      },
      "targets": [
        { "expr": "rapp_diagnosed_bottleneck", "refId": "A" }
      ]
    },
    {
      "id": 5,
      "gridPos": { "h": 6, "w": 8, "x": 16, "y": 8 },
      "type": "timeseries",
      "title": "NWDAF Core Slice Load Level",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "custom": { "fillOpacity": 15, "lineWidth": 2 }
        }
      },
      "targets": [
        { "expr": "nwdaf_slice_load_level", "legendFormat": "Slice {{snssai}}", "refId": "A" }
      ]
    },
    {
      "id": 6,
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 14 },
      "type": "timeseries",
      "title": "RAN Radio Resource Saturation (Cell-1 vs Cell-2 PRB)",
      "datasource": { "type": "prometheus", "uid": "Prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "custom": { "fillOpacity": 15, "lineWidth": 2 }
        }
      },
      "targets": [
        { "expr": "ran_cell_prb_utilization", "legendFormat": "Cell {{cell_id}} PRB", "refId": "A" }
      ]
    }
  ],
  "refresh": "1s",
  "schemaVersion": 38,
  "style": "dark",
  "tags": ["5g", "oran", "thesis", "ric", "nwdaf"],
  "time": { "from": "now-5m", "to": "now" },
  "timezone": "browser",
  "title": "5G O-RAN RIC-NWDAF Closed-Loop & Bottleneck Telemetry",
  "uid": "oran-thesis-dashboard",
  "version": 1
}
```

3. Restart Grafana to load dashboard:
```bash
docker compose restart grafana
```

---

### Step 4: Run the Telemetry Collector & Experiment Suite

All telemetry and experimental suite scripts on VM-6 are centrally managed in repository directory [`scripts/`](../../scripts):

1. **Telemetry Collector & Exporter Daemon:** [`scripts/telemetry_collector.py`](../../scripts/telemetry_collector.py)
   * *Path on VM-6:* `/opt/oran/monitoring/collector/telemetry_collector.py`
   * *Function:* Ingests physical Core UPF metrics pushed from VM-3 (`/report`), polls NWDAF (`:8080`), ingests UE QoS metrics from VM-5, and exposes Prometheus-formatted multi-domain metrics at `http://10.102.0.67:9100/metrics`.
   ```bash
   # Run collector daemon in background:
   nohup python3 /opt/oran/monitoring/collector/telemetry_collector.py > /opt/oran/monitoring/collector/collector.log 2>&1 &
   ```

2. **Single-Scenario Telemetry Recorder:** [`scripts/record_experiment.py`](../../scripts/record_experiment.py)
   * *Path on VM-6:* `/opt/oran/monitoring/scripts/record_experiment.py`
   * *Function:* Unified 1.000 Hz monotonic telemetry recorder that records a single scenario per session directly into `/opt/oran/monitoring/data/raw/<RUN_ID>/` with `manifest.json`.
   ```bash
   # Run telemetry dataset recorder for an experiment scenario:
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 60 --notes "Baseline normal 10M"
   ```

3. **Statistical Dataset Audit & SLA Validator:** [`scripts/analyze_dataset.py`](../../scripts/analyze_dataset.py)
   * *Path on VM-6:* `/opt/oran/monitoring/scripts/analyze_dataset.py`
   * *Function:* Audits dataset integrity post-run (PRB%, maximum buffer backlog, total packet drops, throughput, and URLLC latency SLA violation rates).
   ```bash
   # Audit and analyze recorded experiment dataset:
   python3 /opt/oran/monitoring/scripts/analyze_dataset.py /opt/oran/monitoring/data/raw/<RUN_ID>/telemetry_<RUN_ID>.csv
   ```

---

### Step 5: Verification & Access
1. **Collector Health Check:**
   ```bash
   curl http://10.102.0.67:9100/health
   curl http://10.102.0.67:9100/metrics
   ```
2. **Prometheus Targets Status:**
   - URL: `http://10.102.0.67:9090/targets`
   - State for `thesis_telemetry_collector` should be **UP** (1/1 up).
3. **Access Grafana Dashboard:**
   - URL: `http://10.102.0.67:3000`
   - Credentials: `admin` / `admin`
   - Folder: `O-RAN 5G` -> Dashboard: **"5G O-RAN RIC-NWDAF Closed-Loop & Bottleneck Telemetry"**

