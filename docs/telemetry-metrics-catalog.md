# 5G O-RAN Telemetry Metrics Catalog & Extraction Guide

This document serves as the authoritative catalog detailing all telemetry metrics extractable from the multi-slice 5G O-RAN testbed, data sources, mathematical formulations, and step-by-step procedures for both manual extraction (shell CLI) and automated collection via standard-library Python daemons.

---

## 1. Telemetry Dataflow Architecture

Telemetry is continuously harvested at a synchronized nominal frequency of **1.000 Hz (1 sample per second)** across five architectural domains:

```text
[ VM-5: nrUE ]             [ VM-4: Split RAN ]          [ VM-3: 5G Core ]
  (iperf3 / ping)            (gNB DU Scheduler)           (UPF Container)
        │                            │                            │
        ▼                            ▼                            ▼
  trafgen.sh                  ran_adapter.py               core_adapter.py
        │                            │                            │
        └────────────────────┬───────┴────────────────────────────┘
                             │ POST :9100/report
                             ▼
                 [ VM-6: Monitoring Host ]
                   telemetry_collector.py  ──►  Prometheus (:9100/metrics)
                             │
                             ▼
                   record_dual_stream.py  ──►  telemetry_raw_<RUN_ID>.csv
```

---

## 2. Complete Metric Inventory

| No | CSV Column Name | Prometheus Metric Identifier | Domain | Host / Process Source | Unit / Type | Description & Standards Mapping |
|---|---|---|---|---|---|---|
| 1 | `timestamp_utc` | *(Row Metadata)* | Pipeline | System Clock UTC | ISO-8601 | Microsecond-accurate UTC timestamp for cross-VM synchronization. |
| 2 | `elapsed_sec` | *(Row Metadata)* | Pipeline | Monotonic Clock | Seconds | Monotonic float (zero wall-clock drift) since run initialization. |
| 3 | `run_id` | *(Row Metadata)* | Pipeline | CLI Session / Argument| String | Unique experiment session identifier (e.g., `PILOT_TEST`). |
| 4 | `scrape_ok` | *(Internal Logger)* | Pipeline | HTTP Status :9100 | Boolean (0/1) | Prometheus scrape success status indicator. |
| 5 | `scrape_latency_ms` | *(Internal Logger)* | Pipeline | Scrape Duration | ms | End-to-end HTTP request duration to scrape `:9100/metrics`. |
| 6 | `e2e_slice1_tput_mbps` | `e2e_slice1_throughput_mbps` | UE Experience | VM-5 `ue1` ns | Mbps | Slice 1 (eMBB) user goodput delivered to EXT-DN via `iperf3`. |
| 7 | `e2e_slice1_jitter_ms` | `e2e_slice1_jitter_ms` | UE Experience | VM-5 `ue1` ns | ms | Slice 1 (eMBB) UDP packet delay variation / jitter. |
| 8 | `e2e_slice2_rtt_ms` | `e2e_slice2_latency_rtt_ms` | UE Experience | VM-5 `ue2` ns | ms | Slice 2 (URLLC) precision Round-Trip Time (ICMP canary to EXT-DN). |
| 9 | `e2e_slice2_loss_pct` | `e2e_slice2_packet_loss_pct` | UE Experience | VM-5 `ue2` ns | % | Slice 2 (URLLC) packet loss ratio (URLLC SLA reliability probe). |
| 10 | `nwdaf_load_embb` | `nwdaf_slice_load_level{snssai="01000001"}` | 5G Core / NWDAF | VM-3 5GC / UPF | % (0–100) | Slice load level per 3GPP TS 23.288 §6.3 (Nnwdaf API or UPF dynamic fallback). |
| 11 | `nwdaf_load_urllc` | `nwdaf_slice_load_level{snssai="de00007b"}` | 5G Core / NWDAF | VM-3 5GC / UPF | % (0–100) | Slice load level per 3GPP TS 23.288 §6.3 (Nnwdaf API or UPF dynamic fallback). |
| 12 | `upf_backlog_bytes_embb` | `upf_queue_backlog_bytes{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Bytes | Kernel egress qdisc buffer occupancy on Slice 1 UPF interface. |
| 13 | `upf_backlog_bytes_urllc`| `upf_queue_backlog_bytes{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Bytes | Kernel egress qdisc buffer occupancy on Slice 2 UPF interface. |
| 14 | `upf_drops_embb` | `upf_packet_drops{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Drops / s | Instantaneous packet drop rate from UPF buffer overflow or TBF shaping. |
| 15 | `upf_drops_urllc` | `upf_packet_drops{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Drops / s | Instantaneous packet drop rate from UPF buffer overflow or TBF shaping. |
| 16 | `ran_prb_cell1` | `ran_cell_prb_utilization{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | % (0–100) | Cell-1 Physical Resource Block (PRB) allocation ratio $(NPRB / 106) \times 100\%$. |
| 17 | `ran_prb_cell2` | `ran_cell_prb_utilization{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | % (0–100) | Cell-2 Physical Resource Block (PRB) allocation ratio $(NPRB / 106) \times 100\%$. |
| 18 | `ran_mcs_cell1` | `ran_cell_mcs{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Index (0–28) | Cell-1 Modulation & Coding Scheme (MCS) reflecting physical link adaptation. |
| 19 | `ran_mcs_cell2` | `ran_cell_mcs{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Index (0–28) | Cell-2 Modulation & Coding Scheme (MCS) reflecting physical link adaptation. |
| 20 | `ran_bler_cell1` | `ran_cell_bler{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Ratio (0.0–1.0) | Cell-1 UL-SCH MAC Block Error Rate (CRC failures ratio). |
| 21 | `ran_bler_cell2` | `ran_cell_bler{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Ratio (0.0–1.0) | Cell-2 UL-SCH MAC Block Error Rate (CRC failures ratio). |
| 22 | `ran_snr_cell1` | `ran_cell_snr_db{cell_id="1"}` | Split RAN L1/L2 | VM-4 DU-1 (:4043) | dB | Cell-1 Uplink Signal-to-Noise Ratio (SNR) measured at gNB receiver. |
| 23 | `ran_snr_cell2` | `ran_cell_snr_db{cell_id="2"}` | Split RAN L1/L2 | VM-4 DU-2 (:4044) | dB | Cell-2 Uplink Signal-to-Noise Ratio (SNR) measured at gNB receiver. |
| 24 | *(Prometheus Gauge)* | `ran_cell_rssi_dbm{cell_id="X"}` | Split RAN L1 | VM-4 DU-X | dBm | Received Signal Strength Indicator (RSSI) at gNB receiver. |
| 25 | *(Prometheus Gauge)* | `ran_cell_ulsch_errors{cell_id="X"}` | Split RAN L2 | VM-4 DU-X | Counter | Cumulative MAC layer UL-SCH decoding errors count. |
| 26 | `rapp_diagnosed_bottleneck`| `rapp_diagnosed_bottleneck` | RIC Intelligence | VM-1 / VM-2 RIC | Enum (0–3) | rApp sequential bottleneck diagnosis: `0=NORMAL`, `1=RAN`, `2=CORE`, `3=JOINT`. |
| 27 | `rapp_confidence` | `rapp_confidence` | RIC Intelligence | VM-1 / VM-2 RIC | Score (0.0–1.0)| Probabilistic diagnostic confidence score emitted by the rApp. |
| 28 | *(Prometheus Gauge)* | `a1_policy_threshold` | RIC Intelligence | VM-1 Non-RT RIC | ms | URLLC latency SLA threshold enforced via A1 Policy Type 20008. |
| 29 | `event_scenario` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Ground-truth injected scenario ID (`S1`, `S2`, `S3`, `S6`, `S9`, etc.). |
| 30 | `event_domain` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Target failure domain (`BASELINE`, `RAN`, `CORE`, `JOINT`). |
| 31 | `event_component` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum | Target network component (`NONE`, `DU-1_Cell-1`, `UPF-1_Slice-1`, etc.). |

---

## 3. In-Depth Domain Telemetry & Extraction Procedures

---

### Domain 1: End-to-End UE QoS Experience (VM-5 `oai-ue`)

#### 1.1 Available Metrics
1. **`e2e_slice1_tput_mbps`**: Actual UDP application goodput delivered from UE1 to the external data network (EXT-DN).
2. **`e2e_slice1_jitter_ms`**: End-to-end packet delay variation / jitter on Slice 1.
3. **`e2e_slice2_rtt_ms`**: Precision Round-Trip Time latency from UE2 to EXT-DN (`192.168.70.145`).
4. **`e2e_slice2_loss_pct`**: Packet loss percentage on Slice 2 probe packets.

#### 1.2 Manual Shell Extraction Procedure (VM-5)
Each UE is isolated inside its designated network namespace (`ue1` for eMBB and `ue2` for URLLC):
```bash
# Test Slice 1 (eMBB) UDP throughput via iperf3 in the ue1 namespace:
sudo ip netns exec ue1 iperf3 -c 192.168.70.145 -u -b 25M -t 5 -i 1

# Test Slice 2 (URLLC) latency via ICMP Canary in the ue2 namespace:
sudo ip netns exec ue2 ping -I oaitun_ue1 -c 4 -i 0.2 192.168.70.145
```

#### 1.3 Automated Extraction via Script
Executed by [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh):
```bash
# Launch simultaneous multi-slice traffic benchmark (30s duration, 25 Mbps eMBB load):
cd /opt/oran/ue/scripts
sudo ./trafgen.sh start 30 25
```
*Telemetry Push Mechanism:* In the background, `trafgen.sh` parses live log outputs and executes asynchronous HTTP POSTs to the VM-6 collector:
```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"slice": 1, "throughput_mbps": 23.4, "jitter_ms": 1.25}' \
  http://10.102.0.67:9100/report
```

---

### Domain 2: Split-RAN Radio & MAC Layer (VM-4 `oai-ran`)

#### 2.1 Available Metrics
1. **`ran_cell_prb_utilization`**: MAC scheduler Physical Resource Block utilization percentage:
   $$\text{PRB Utilization (\%)} = \frac{\text{NPRB}}{106.0} \times 100\%$$
   *(106 PRB represents the full channel capacity for 40 MHz bandwidth at 30 kHz Subcarrier Spacing).*
2. **`ran_cell_mcs`**: Active Modulation and Coding Scheme index (0 to 28) allocated by the scheduler per UE.
3. **`ran_cell_bler`**: Block Error Rate (0.00000 to 1.00000) on the UL-SCH physical transport block.
4. **`ran_cell_snr_db`**: Signal-to-Noise Ratio (in dB) measured at the gNB antenna receiver.
5. **`ran_cell_rssi_dbm`**: Received Signal Strength Indicator (in dBm).
6. **`ran_cell_ulsch_errors`**: Cumulative count of failed MAC layer CRC decodes.

#### 2.2 Manual Shell Extraction Procedure (VM-4)
Both OAI DU instances (`du1` on port `:4043` and `du2` on port `:4044`) continuously print scheduler statistics to their respective log files:
```bash
# Inspect latest radio link scheduler output on Cell-1 (DU-1):
grep "NPRB" /opt/oran/ran/du1.log | tail -n 5

# Verbatim OAI DU scheduler format:
# UE 82c3: ulsch_rounds 3455040/0/0/0, ulsch_errors 0, ulsch_DTX 0, BLER 0.00000 MCS (0) 14 (Qm 4 deltaMCS 0) NPRB 51 SNR 25.7 (+2.7) RSSI -42.0 CCE fail 0
```

#### 2.3 Automated Extraction via Script
Executed by the host daemon [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py):
* Continuously tails `du1.log` and `du2.log` via standard-library subprocess regex matching:
```python
RADIO_STATS_PATTERN = re.compile(
    r'ulsch_errors\s+(?P<errors>\d+).*?'
    r'BLER\s+(?P<bler>[0-9.]+).*?'
    r'MCS\s*(?:\([^)]*\))?\s*(?P<mcs>\d+).*?'
    r'NPRB\s+(?P<nprb>\d+).*?'
    r'SNR\s+(?P<snr>[-0-9.]+).*?'
    r'RSSI\s+(?P<rssi>[-0-9.]+)'
)
```
*Execution command on VM-4:*
```bash
cd /opt/oran/ran/scripts
python3 ran_adapter.py > ran_adapter.log 2>&1 &
```
*Report payload sent to `:9100/report`:*
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

#### 3.1 Available Metrics
1. **`upf_interface_tx_mbps` / `rx_mbps`**: Layer-3 IP interface throughput on UPF instances per slice.
2. **`upf_bytes_sent`**: Cumulative egress byte counter (compliant with 3GPP TS 28.552).
3. **`upf_queue_backlog_bytes`**: Kernel egress qdisc buffer occupancy on the UPF interface (in bytes).
4. **`upf_packet_drops`**: Packet drop rate resulting from queue buffer saturation or TBF rate-limiting (drops/s).
5. **`nwdaf_slice_load_level`**: Slice resource load index (0–100%) per 3GPP TS 23.288 §6.3.

#### 3.2 Manual Shell Extraction Procedure (VM-3)
```bash
# 1. Read interface packet and byte counters inside the Slice 1 UPF container:
docker exec oai-upf-slice1 cat /proc/net/dev | grep eth0

# 2. Inspect root qdisc queue discipline, buffer backlog, and drop counters:
docker exec oai-upf-slice1 tc -j -s qdisc show dev eth0
```
*Sample JSON output from `tc -j -s qdisc show`:*
```json
[
  {
    "kind": "tbf",
    "handle": "1:",
    "root": true,
    "bytes": 2854910,
    "packets": 1952,
    "drops": 145,
    "backlog": 124500,
    "qlen": 83
  }
]
```

#### 3.3 Automated Extraction via Script
Executed by the host daemon [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py) v9:
* Samples counters within high-precision monotonic timing brackets.
* Computes rates via differential observation:
  $$\Delta \text{rate} = \frac{\text{counter}_t - \text{counter}_{t-1}}{\Delta t_{\text{monotonic}}}$$
* Archives locally to `./upf-telemetry/<RUN_ID>/telemetry.jsonl` and `./telemetry.csv`.
* Asynchronously delivers reports to `http://10.102.0.67:9100/report`.

*Execution command on VM-3:*
```bash
cd /opt/oran/5gc/scripts
python3 core_adapter.py --run-id PILOT_TEST > core_adapter.log 2>&1 &
```

---

### Domain 4: O-RAN RIC Intelligence & Control Loop (VM-1 / VM-2)

#### 4.1 Available Metrics
1. **`rapp_diagnosed_bottleneck`**: Classification state generated by the Non-RT RIC rApp sequential diagnosis engine:
   * `0`: **NORMAL** (Healthy network state, SLA fully met).
   * `1`: **RAN Bottleneck** (Radio access saturation or channel degradation).
   * `2`: **CORE Bottleneck** (UPF buffer queue buildup or shaping drops).
   * `3`: **JOINT Bottleneck** (Simultaneous congestion across both RAN and Core).
2. **`rapp_confidence`**: Model classification probability score (0.00 to 1.00).
3. **`a1_policy_threshold`**: URLLC latency SLA constraint communicated via A1 Policy Type 20008 (ms).

#### 4.2 Manual Query Procedure (VM-1 / VM-2)
```bash
# Query active A1 policies from Non-RT RIC (VM-1):
curl -s http://10.102.0.166:8080/A1-P/v2/policytypes/20008/policies

# Sample A1 Policy response:
# {
#   "policy_ratio_id": "slice-steering-policy-01",
#   "urllc_sla_latency_threshold_ms": 20.0,
#   "target_cell_id": "Cell-1"
# }
```

---

### Domain 5: Telemetry Aggregation, Exporter & Dataset Logger (VM-6 `monitor`)

#### 5.1 Telemetry Aggregator ([`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py))
Runs on port `:9100`:
* Ingestion Endpoint: `POST http://10.102.0.67:9100/report` (Ingests JSON reports from VM-3, VM-4, and VM-5).
* Exporter Endpoint: `GET http://10.102.0.67:9100/metrics` (Exposes standardized Prometheus metrics).

*Live Verification Commands on VM-6:*
```bash
# Verify live radio link metrics:
curl -s http://127.0.0.1:9100/metrics | grep ran_cell

# Verify live Core UPF and NWDAF metrics:
curl -s http://127.0.0.1:9100/metrics | grep -E "upf_|nwdaf_"

# Verify live End-to-End UE QoS metrics:
curl -s http://127.0.0.1:9100/metrics | grep e2e_slice
```

#### 5.2 High-Precision Dataset Logger ([`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py))
* Scrapes `http://127.0.0.1:9100/metrics` at an exact 1.000 Hz interval using `time.monotonic()` (zero drift).
* Synchronizes active fault annotations from `/opt/oran/monitoring/data/active_event.json`.
* Flushes records instantaneously to `/opt/oran/monitoring/data/telemetry_raw_<RUN_ID>_<PID>.csv`.

*Execution Command:*
```bash
cd /opt/oran/monitoring/scripts
python3 record_dual_stream.py RUN_01_TRAIN
```

#### 5.3 Ground-Truth Event Logger ([`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py))
* Atomically logs ground-truth labels during live fault injection runs:
```bash
python3 log_event.py S1 "Normal Light Load Baseline"
python3 log_event.py S3 "Inject RAN Overload 40 Mbps"
python3 log_event.py S6 "Inject Core TBF Rate Limit 12 Mbps"
python3 log_event.py CLEAR "Clear All Injections"
```

#### 5.4 Automated Statistical Auditor ([`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py))
* Audits the latest recorded CSV dataset (sorted by modification time `mtime`):
```bash
python3 analyze_dataset.py
```

---

## 4. Cross-Domain Bottleneck Signature Matrix

The following matrix defines the physical signatures distinguishing each bottleneck class based on the extracted metrics:

| Network State | Class Label | PRB C1 (`ran_prb`) | Radio MCS (`ran_mcs`) | Radio BLER (`ran_bler`) | UPF Buffer (`upf_backlog`) | UPF Drops (`upf_drops`) | URLLC RTT (`e2e_rtt`) |
|---|---|---|---|---|---|---|---|
| **Normal Light** (`S1`) | `NORMAL` (0) | $\approx 48\%$ | High ($\ge 14$) | $\approx 0.0000$ | **`0 B`** | **`0`** | $< 15\text{ ms}$ (Compliant) |
| **Normal High** (`S2`) | `NORMAL` (0) | $\approx 67\%$ | High ($\ge 14$) | $\approx 0.0000$ | **`0 B`** | **`0`** | $\approx 20\text{ ms}$ (Near SLA boundary) |
| **RAN Overload** (`S3`) | `RAN` (1) | **Saturated ($\approx 100\%$)** | Depressed | Positive / Errors | **`0 B`** | **`0`** | $> 25\text{ ms}$ (SLA Violated) |
| **Core TBF Congestion** (`S6`) | `CORE` (2) | Low ($< 25\%$) | Normal | $\approx 0.0000$ | **Elevated ($> 100\text{ KB}$)** | **Positive ($> 0$)** | $> 25\text{ ms}$ (SLA Violated) |
| **Joint Overload** (`S9`) | `JOINT` (3) | **Saturated ($\approx 100\%$)** | Depressed | Positive | **Elevated ($> 100\text{ KB}$)** | **Positive ($> 0$)** | $> 35\text{ ms}$ (Critical SLA Violation) |

---

## 5. Repository File Locations Reference

* RAN Telemetry Adapter: [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py)
* Core UPF Telemetry Adapter: [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py)
* UE Multi-Slice Traffic Generator: [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh)
* Telemetry Collector & Exporter: [`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py)
* Monotonic CSV Dataset Logger: [`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py)
* Ground-Truth Event Logger: [`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py)
* Dataset Statistical Auditor: [`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py)
