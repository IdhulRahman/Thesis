# 5G O-RAN Telemetry Metrics Catalog & Extraction Guide

This document serves as the authoritative, peer-reviewed reference detailing all telemetry metrics extractable from the multi-slice 5G O-RAN testbed, their underlying data sources, mathematical formulations, standard mappings (3GPP / ETSI / IETF), measurement semantics, and step-by-step extraction procedures.

---

## 1. Telemetry Dataflow Architecture

Telemetry is harvested across five architectural domains at a nominal polling frequency of **1.000 Hz (1 sample per second)**:

```text
[ VM-5: nrUE (ue1 / ue2) ]     [ VM-4: Split RAN ]          [ VM-3: 5G Core ]
  (iperf3 / ping canary)         (gNB DU Scheduler Logs)      (UPF Container eth0)
        │                               │                            │
        ▼                               ▼                            ▼
  trafgen.sh                     ran_adapter.py               core_adapter.py v9
        │                               │                            │
        └───────────────────────┬───────┴────────────────────────────┘
                                │ POST :9100/report
                                ▼
                    [ VM-6: Monitoring Host ]
                      telemetry_collector.py  ──►  Prometheus (:9100/metrics)
                                │
                                ▼
                      record_dual_stream.py  ──►  telemetry_raw_<RUN_ID>.csv
```

---

## 2. Complete Metric Inventory & Semantic Definitions

> [!IMPORTANT]
> **Measurement Semantics Notice:**
> In accordance with 3GPP TS 38.314, TS 28.552, and TS 23.288, physical telemetry must strictly distinguish between instantaneous point-in-time samples, observation-interval aggregates, client-side offered load versus server-side goodput, and empirical research approximations. The table below documents the precise semantics implemented in this testbed.

| No | CSV Column Name | Prometheus Metric Identifier | Domain | Source Component | Unit / Type | Exact Measurement Semantics & Scientific Scope |
|---|---|---|---|---|---|---|
| 1 | `timestamp_utc` | *(Row Metadata)* | Pipeline | Host Clock UTC | ISO-8601 | Microsecond-accurate UTC timestamp for cross-VM time alignment. |
| 2 | `elapsed_sec` | *(Row Metadata)* | Pipeline | Monotonic Clock | Seconds | Monotonic float (`time.monotonic()`) with zero wall-clock drift. |
| 3 | `run_id` | *(Row Metadata)* | Pipeline | Session Argument | String | Unique experiment identifier (e.g., `PILOT_TEST`, `RUN_01_TRAIN`). |
| 4 | `scrape_ok` | *(Internal Logger)* | Pipeline | HTTP Scraper | Boolean (0/1) | Indicates whether the 1 Hz HTTP scrape to `:9100/metrics` succeeded. |
| 5 | `scrape_latency_ms` | *(Internal Logger)* | Pipeline | HTTP Scraper | ms | Duration taken by the scraper to ingest Prometheus metrics. |
| 6 | `e2e_slice1_tput_mbps` | `e2e_slice1_throughput_mbps` | UE Experience | VM-5 `ue1` ns | Mbps | **Sender-side offered load** reported by `iperf3 -u` client. Receiver goodput requires EXT-DN server telemetry. |
| 7 | `e2e_slice1_jitter_ms` | `e2e_slice1_jitter_ms` | UE Experience | VM-5 `ue1` ns | ms | **Unmeasured in UDP Sender Mode** (`NaN`). RFC 3550 transit jitter is measured at the receiver (`iperf3 -s` on EXT-DN). CLI jitter represents probe latency deviation. |
| 8 | `e2e_slice2_rtt_ms` | `e2e_slice2_latency_rtt_ms` | UE Experience | VM-5 `ue2` ns | ms | **Latest ICMP Canary RTT** to EXT-DN (`192.168.70.145`). Represents the most recent probe reply in the 1-second window. |
| 9 | `e2e_slice2_loss_pct` | `e2e_slice2_packet_loss_pct` | UE Experience | VM-5 `ue2` ns | % | **Sequence-Matched Canary Loss Ratio**: Computed via continuous `icmp_seq` window tracking with a 200 ms grace period, eliminating false drops from delayed packets. Decays to `NaN` when probe stream stops. |
| 10 | `e2e_probe_freshness` | `e2e_probe_freshness` | UE Experience | VM-5 `ue1`/`ue2` | Boolean (0/1) | **UE Canary Probe Freshness Indicator**: `1` when active reports received within 3.5s; decays to `0` when probe stream stops, preventing stale telemetry from being misinterpreted as healthy. |
| 11 | `nwdaf_load_embb` | `nwdaf_slice_load_level{snssai="01000001"}` | 5G Core / NWDAF | VM-3 NWDAF :8080 | % (0–100) | **Standard 3GPP TS 23.288 Slice Load Level**: Polled from Rel-17 Nnwdaf endpoint. Emits `NaN` when the external NWDAF NF is inactive. Decoupled from heuristic estimates. |
| 12 | `nwdaf_load_urllc` | `nwdaf_slice_load_level{snssai="de00007b"}` | 5G Core / NWDAF | VM-3 NWDAF :8080 | % (0–100) | **Standard 3GPP TS 23.288 Slice Load Level**: Polled from Rel-17 Nnwdaf endpoint. Emits `NaN` when the external NWDAF NF is inactive. Decoupled from heuristic estimates. |
| 13 | `estimated_load_embb` | `estimated_slice_load_level{snssai="01000001"}` | 5G Core UPF | VM-3 UPF-1 / VM-6 | % (0–100) | **Research Interface Utilization Estimate** ($\min(100, \max(5, \frac{\text{Tx}}{25.0} \times 100))$). Empirical load proxy derived from UPF egress throughput. |
| 14 | `estimated_load_urllc` | `estimated_slice_load_level{snssai="de00007b"}` | 5G Core UPF | VM-3 UPF-2 / VM-6 | % (0–100) | **Research Interface Utilization Estimate** ($\min(100, \max(5, \frac{\text{Tx}}{5.0} \times 100))$). Empirical load proxy derived from UPF egress throughput. |
| 15 | `upf_backlog_bytes_embb` | `upf_queue_backlog_bytes{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Bytes | **UPF Container Interface Egress Qdisc Backlog** on `eth0`. Decays to `NaN` after 3.5s if core report is interrupted or null. |
| 16 | `upf_backlog_bytes_urllc`| `upf_queue_backlog_bytes{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Bytes | **UPF Container Interface Egress Qdisc Backlog** on `eth0`. Decays to `NaN` after 3.5s if core report is interrupted or null. |
| 17 | `upf_drops_embb` | `upf_packet_drops{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Drops / s | **UPF Egress Qdisc Packet Drop Rate** ($\Delta \text{drops} / \Delta t$). Strictly decoupled from integer drop counts (`upf_packet_drops_delta`). |
| 18 | `upf_drops_urllc` | `upf_packet_drops{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Drops / s | **UPF Egress Qdisc Packet Drop Rate** ($\Delta \text{drops} / \Delta t$). Strictly decoupled from integer drop counts (`upf_packet_drops_delta`). |
| 19 | `ran_prb_cell1` | `ran_cell_prb_utilization{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | % (0–100) | **Instantaneous MAC Slot PRB Allocation Ratio** ($(NPRB / 106) \times 100\%$) from latest DU log entry, not TS 38.314 time-integrated cell usage. |
| 20 | `ran_prb_cell2` | `ran_cell_prb_utilization{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | % (0–100) | **Instantaneous MAC Slot PRB Allocation Ratio** ($(NPRB / 106) \times 100\%$) from latest DU log entry, not TS 38.314 time-integrated cell usage. |
| 21 | `ran_mcs_cell1` | `ran_cell_mcs{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Index (0–28) | Latest UL-SCH Modulation & Coding Scheme allocated to the active UE in Cell-1. `NaN` when unallocated. |
| 22 | `ran_mcs_cell2` | `ran_cell_mcs{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Index (0–28) | Latest UL-SCH Modulation & Coding Scheme allocated to the active UE in Cell-2. `NaN` when unallocated. |
| 23 | `ran_bler_cell1` | `ran_cell_bler{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Ratio (0.0–1.0) | Latest Block Error Rate on UL-SCH transport blocks in Cell-1. `NaN` when unallocated. |
| 24 | `ran_bler_cell2` | `ran_cell_bler{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Ratio (0.0–1.0) | Latest Block Error Rate on UL-SCH transport blocks in Cell-2. `NaN` when unallocated. |
| 25 | `ran_snr_cell1` | `ran_cell_snr_db{cell_id="1"}` | Split RAN L1/L2 | VM-4 DU-1 (:4043) | dB | Latest Uplink Signal-to-Noise Ratio (SNR) measured at gNB receiver for Cell-1. `NaN` when unallocated. |
| 26 | `ran_snr_cell2` | `ran_cell_snr_db{cell_id="2"}` | Split RAN L1/L2 | VM-4 DU-2 (:4044) | dB | Latest Uplink Signal-to-Noise Ratio (SNR) measured at gNB receiver for Cell-2. `NaN` when unallocated. |
| 27 | *(Prometheus Gauge)* | `ran_cell_rssi_dbm{cell_id="X"}` | Split RAN L1 | VM-4 DU-X | dBm | Received Signal Strength Indicator (RSSI) at gNB receiver. `NaN` when unallocated. |
| 28 | *(Prometheus Gauge)* | `ran_cell_ulsch_errors{cell_id="X"}` | Split RAN L2 | VM-4 DU-X | Counter | Cumulative MAC layer UL-SCH CRC decode failures count. |
| 29 | `rapp_diagnosed_bottleneck`| `rapp_diagnosed_bottleneck` | RIC Intelligence | VM-1 / VM-2 RIC | Enum (-1–3) | rApp diagnosis: `-1=UNINITIALIZED`, `0=NORMAL`, `1=RAN`, `2=CORE`, `3=JOINT`. |
| 30 | `rapp_confidence` | `rapp_confidence` | RIC Intelligence | VM-1 / VM-2 RIC | Score (0.0–1.0)| Diagnostic model confidence score. Initialized to `0.0` until active model inference runs. |
| 31 | *(Prometheus Gauge)* | `a1_policy_threshold` | RIC Intelligence | VM-1 Non-RT RIC | ms | URLLC latency SLA constraint communicated via A1 Policy Type 20008. |
| 32 | `event_scenario` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Operator-injected scenario identifier (`S1`, `S2`, `S3`, `S6`, `S9`, `CLEAR`). |
| 33 | `event_domain` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Intended target failure domain (`BASELINE`, `RAN`, `CORE`, `JOINT`). |
| 34 | `event_component` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Intended target failure entity (`NONE`, `DU-1_Cell-1`, `UPF-1_Slice-1`, etc.). |

---

## 3. In-Depth Domain Telemetry & Extraction Procedures

---

### Domain 1: End-to-End UE QoS Experience (VM-5 `oai-ue`)

#### 1.1 Architectural Context & Standards Notes
* **Sender vs. Receiver Throughput (RFC 2544 / iperf3 Docs):**
  In `iperf3 -u` (UDP client mode), the client log reports the **sender-side offered bitrate**. If packets are dropped downstream at the gNB or UPF, the client is unaware unless bidirectional control packets or receiver-side logs (`iperf3 -s` at EXT-DN) are captured. Consequently, `e2e_slice1_tput_mbps` represents offered load at the UE ingress.
* **Canary Latency, Age & Freshness Decay (RFC 2681):**
  `e2e_slice2_rtt_ms` samples the latest ICMP echo reply from a continuous 100 ms canary probe stream directed at EXT-DN (`192.168.70.145`). If ping halts while `trafgen.sh` continues running, `trafgen.sh` detects zero new replies in the evaluation interval, increments measurement age (`reply_age_sec`), computes 100% loss for expected probes, and pushes `rtt_ms: null`. The collector exports `e2e_slice2_latency_rtt_ms NaN` and resets `e2e_probe_freshness = 0`, ensuring freshness measures actual measurement vitality rather than mere HTTP daemon reporting vitality. Auxiliary Prometheus metrics `e2e_slice2_reply_age_sec` and `e2e_slice2_last_seq` track probe age and sequence continuity. 

#### 1.2 Manual Shell Extraction Procedure (VM-5)
```bash
# Execute Slice 1 (eMBB) UDP offered load test inside the ue1 namespace:
sudo ip netns exec ue1 iperf3 -c 192.168.70.145 -u -b 25M -t 5 -i 1

# Execute Slice 2 (URLLC) ICMP canary probe inside the ue2 namespace:
sudo ip netns exec ue2 ping -I oaitun_ue1 -c 10 -i 0.1 192.168.70.145
```

#### 1.3 Automated Extraction Implementation
Executed by [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh):
```bash
cd /opt/oran/ue/scripts
sudo ./trafgen.sh start 30 25
```
*Telemetry Push Payload to `:9100/report`:*
```json
{
  "slice": 1,
  "throughput_mbps": 24.8,
  "jitter_ms": 0.0
}
```
```json
{
  "slice": 2,
  "rtt_ms": 14.2,
  "packet_loss_pct": 0.0
}
```

---

### Domain 2: Split-RAN Radio & MAC Layer (VM-4 `oai-ran`)

#### 2.1 Architectural Context & Standards Notes (3GPP TS 38.314 §4.2.1.6)
* **Standard Definition:** TS 38.314 §4.2.1.6 defines cell PRB utilization as the total number of resource blocks and symbols allocated divided by total available resource block symbols over an observation period $T$.
* **Implementation Scope:** In `ran_adapter.py`, the script parses the most recent MAC scheduler line from `du1.log` / `du2.log` printed by OAI gNB DU. The metric represents the **instantaneous MAC slot allocation ratio** allocated to the active UE:
  $$\text{PRB Ratio} = \frac{\text{NPRB}}{106.0} \times 100\%$$
* **Radio Quality Diagnostics (3GPP TS 23.288 §6.8.2):**
  When traffic is absent or no matching UE scheduling line is found, the parser emits `NaN` (or `valid: false`), avoiding synthetic "healthy" fallbacks (e.g., hardcoded 25 dB) that would corrupt statistical audits.

#### 2.2 Manual Shell Extraction Procedure (VM-4)
```bash
# Inspect the latest MAC scheduler lines on Cell-1 (DU-1, port :4043):
grep "NPRB" /opt/oran/ran/du1.log | tail -n 5

# Verbatim OAI DU scheduler log format:
# UE 82c3: ulsch_rounds 3455040/0/0/0, ulsch_errors 0, ulsch_DTX 0, BLER 0.00000 MCS (0) 14 (Qm 4 deltaMCS 0) NPRB 51 SNR 25.7 (+2.7) RSSI -42.0 CCE fail 0
```

#### 2.3 Automated Extraction Implementation
Executed by host daemon [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py):
* Execution:
```bash
cd /opt/oran/ran/scripts
python3 ran_adapter.py > ran_adapter.log 2>&1 &
```
*Telemetry Payload to `:9100/report`:*
```json
{
  "ran_cell_prb_utilization": {"1": 48.72, "2": 4.72},
  "ran_cell_radio_stats": {
    "1": {"nprb": 51, "mcs": 14, "bler": 0.0, "snr_db": 25.7, "rssi_dbm": -42.0, "ulsch_errors": 0},
    "2": {"nprb": 5, "mcs": 0, "bler": 0.0, "snr_db": 25.0, "rssi_dbm": -42.0, "ulsch_errors": 0}
  }
}
```

---

### Domain 3: 5G Core User-Plane & NWDAF (VM-3 `oai-core`)

#### 3.1 Architectural Context & Standards Notes (3GPP TS 28.552 / TS 23.288)
* **Qdisc Backlog Scope:** `upf_backlog_bytes` captures the Linux kernel traffic control (`tc`) egress queue depth on the container network interface (`eth0`). It specifically measures the bytes waiting inside the egress qdisc (e.g., TBF or pfifo_fast) before delivery to the bridge, not internal C-based OAI UPF ring buffers. If reporting from the UPF is interrupted or if a sample returns `null`, the collector immediately marks the metric as `NaN` (and auto-resets stale values after 3.5s) to prevent retaining old values.
* **Drops Decoupling:** In compliance with PM principles (TS 32.401), drops are strictly decoupled into instantaneous rates (`upf_packet_drops` in packets/sec) and observation delta counts (`upf_packet_drops_delta` in packets), preventing unit confusion.
* **NWDAF Load Level vs. Research Estimate:** As documented in [`docs/vm/vm3-oai-5gc.md`](file:///d:/Idhul/Program/Thesis/docs/vm/vm3-oai-5gc.md#L529-L565), OAI NWDAF v2.1.0 does not implement user-plane performance analytics. The collector exposes `estimated_slice_load_level` as an **empirical research proxy** based on interface throughput against provisioned slice capacity (25 Mbps eMBB, 5 Mbps URLLC), reserving `nwdaf_slice_load_level` for authentic 3GPP TS 23.288 Nnwdaf analytics when the external NF is responding. Both metrics are strictly decoupled into separate Prometheus identifiers (`nwdaf_slice_load_level` vs `estimated_slice_load_level`) and distinct CSV columns (`nwdaf_load_*` vs `estimated_load_*`), preventing overwriting regardless of ingestion or scrape order.

#### 3.2 Manual Shell Extraction Procedure (VM-3)
```bash
# 1. Inspect UPF Slice 1 Linux interface byte counters:
docker exec oai-upf-slice1 cat /proc/net/dev | grep eth0

# 2. Inspect root qdisc queue discipline, buffer occupancy, and drop counters:
docker exec oai-upf-slice1 tc -j -s qdisc show dev eth0
```

#### 3.3 Automated Extraction Implementation
Executed by [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py) v9:
* Samples interface counters with monotonic timestamp bracketing.
* Archives locally to `./upf-telemetry/<RUN_ID>/telemetry.jsonl` and `./telemetry.csv`.
* Asynchronously delivers reports to `http://10.102.0.67:9100/report`.
```bash
cd /opt/oran/5gc/scripts
python3 core_adapter.py --run-id PILOT_TEST > core_adapter.log 2>&1 &
```

---

### Domain 4: O-RAN RIC Intelligence & Control Loop (VM-1 / VM-2)

#### 4.1 Architectural Context
* **Inference State Tracking:** In training and data generation runs, `rapp_diagnosed_bottleneck` is initialized to `-1` (`UNINITIALIZED`) with `confidence = 0.0`. When an active rApp model executes inference in closed-loop evaluation runs, it publishes classifications `0` (NORMAL), `1` (RAN), `2` (CORE), or `3` (JOINT).
* **A1 Policy Constraints (O-RAN.WG2.A1AP):** The Non-RT RIC dispatches A1 Policy Type 20008 (`urllc_sla_latency_threshold_ms: 20.0`) to constrain Near-RT RIC traffic steering.

#### 4.2 Manual Query Procedure (VM-1)
```bash
# Query active A1 policies on Non-RT RIC:
curl -s http://10.102.0.166:8080/A1-P/v2/policytypes/20008/policies
```

---

### Domain 5: Telemetry Aggregation, Exporter & Dataset Logger (VM-6 `monitor`)

#### 5.1 Telemetry Aggregator ([`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py))
* `POST /report`: Ingests JSON reports from VM-3, VM-4, and VM-5.
* `GET /metrics`: Exposes standardized Prometheus format on port `:9100`.

#### 5.2 High-Precision Dataset Logger ([`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py))
* Scrapes `:9100/metrics` at an exact 1.000 Hz interval using zero-drift monotonic timing.
* Flushes synchronized rows directly to `/opt/oran/monitoring/data/telemetry_raw_<RUN_ID>_<PID>.csv`.

#### 5.3 Ground-Truth Event Logger ([`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py))
* Records intended operator fault injection events (`S1`–`S10`) to `active_event.json` and `experiment_events_<RUN_ID>.csv`.

#### 5.4 Automated Statistical Auditor ([`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py))
* Audits the latest recorded CSV dataset (sorted by modification time `mtime`):
```bash
cd /opt/oran/monitoring/scripts
python3 analyze_dataset.py
```

---

## 4. Cross-Domain Bottleneck Diagnostic Signature Matrix

> [!NOTE]
> **Corrected Diagnostic Decision Logic:**
> 1. **RAN Overload:** Characterized by sustained PRB saturation ($\approx 100\%$) and offered load exceeding radio capacity (28.4 Mbps), resulting in throughput plateauing. Under clean RF conditions, MCS remains high and BLER remains near zero; depressed MCS and elevated BLER specifically indicate radio channel degradation or interference.
> 2. **Core Bottleneck:** Characterized by sustained UPF egress buffer buildup (`upf_backlog_bytes > 0`) and positive queue packet drops on the affected slice (Slice 1). PRB on the RAN does not need to be low; it simply matches whatever traffic the throttled UPF can egress.
> 3. **Joint Bottleneck:** Confirmed physical bottleneck signatures on **both** RAN (sustained PRB saturation) **and** Core (sustained UPF buffer backlog and packet drops) concurrently.
> 4. **Normal Baseline:** Delivered throughput matches offered load, UPF buffer backlog is zero, packet drops are zero, and URLLC latency satisfies SLA constraints ($< 20\text{ ms}$).

| Network State | Class Label | PRB C1 (`ran_prb`) | Radio MCS (`ran_mcs`) | Radio BLER (`ran_bler`) | UPF Buffer (`upf_backlog`) | UPF Drops (`upf_drops`) | URLLC RTT (`e2e_rtt`) | Primary Bottleneck Proof |
|---|---|---|---|---|---|---|---|---|
| **Normal Light** (`S1`) | `NORMAL` (0) | $\approx 48\%$ | Healthy ($\ge 14$) | $\approx 0.0000$ | **`0 B`** | **`0`** | $< 15\text{ ms}$ (Compliant) | Offload matches demand, zero queuing. |
| **Normal High** (`S2`) | `NORMAL` (0) | $\approx 67\%$ | Healthy ($\ge 14$) | $\approx 0.0000$ | **`0 B`** | **`0`** | $\approx 20\text{ ms}$ (Near SLA boundary) | High goodput without queuing or loss. |
| **RAN Overload** (`S3`) | `RAN` (1) | **Saturated ($\approx 100\%$)** | High (if clean RF) / Depressed (if degraded) | Low (if clean RF) / Elevated (if degraded) | **`0 B`** | **`0`** | $> 25\text{ ms}$ (SLA Violated) | Radio scheduler capacity exhaustion; Core buffer empty. |
| **Core TBF Congestion** (`S6`) | `CORE` (2) | Dependent on UPF egress rate | Normal | $\approx 0.0000$ | **Elevated ($> 100\text{ KB}$)** | **Positive ($> 0$)** | Variable (Cross-slice isolation observation) | UPF egress qdisc buffer exhaustion and packet drops. |
| **Joint Overload** (`S9`) | `JOINT` (3) | **Saturated ($\approx 100\%$)** | Variable | Variable | **Elevated ($> 100\text{ KB}$)** | **Positive ($> 0$)** | $> 35\text{ ms}$ (Critical SLA Violation) | Simultaneous saturation of radio PRBs and Core UPF buffers. |

---

## 5. Repository File Locations Reference

* RAN Telemetry Adapter: [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py)
* Core UPF Telemetry Adapter: [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py)
* UE Multi-Slice Traffic Generator: [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh)
* Telemetry Collector & Exporter: [`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py)
* Monotonic CSV Dataset Logger: [`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py)
* Ground-Truth Event Logger: [`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py)
* Dataset Statistical Auditor: [`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py)
