# Experimental Scripts Inventory & Operational Reference

This directory contains the operational daemons, automation scripts, fault injection tools, and dataset recorders for the thesis:

> **Thesis Research Title:**  
> *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Script Distribution Across Virtual Machines

| Host Node | Host IP | Script File | Architectural Role | Execution Mode & Output |
|---|---|---|---|---|
| **VM-3** | `10.102.0.164` | [`core_adapter.py`](core_adapter.py) | Reads Linux kernel `tc qdisc` backlog and packet drops from UPF containers via Netlink. | Continuous daemon (1.0 Hz); pushes JSON to VM-6 `:9100/report` and archives local JSONL. |
| **VM-3** | `10.102.0.164` | [`receiver_iperf.sh`](receiver_iperf.sh) | Dedicated one-off receiver manager for `oai-ext-dn` container to capture ground-truth delivered goodput and UDP loss JSON. | Bash utility; exports to `data/raw/<RUN_ID>/receiver_goodput.json`. |
| **VM-4** | `10.102.0.167` | [`start_ran.sh`](start_ran.sh) | Orchestrates background startup of OAI gNB CU (N2/E2), DU-1 (Cell-1 `:4043`), and DU-2 (Cell-2 `:4044`). | Bash launcher; writes `cu.log`, `du1.log`, `du2.log`. |
| **VM-4** | `10.102.0.167` | [`stop_ran.sh`](stop_ran.sh) | Gracefully terminates all running OAI softmodem processes on VM-4. | Bash teardown utility; kills CU and DUs. |
| **VM-4** | `10.102.0.167` | [`ran_adapter.py`](ran_adapter.py) | Tails `du1.log` & `du2.log`, extracts live MAC PRB allocation (`NPRB / 106`), UL-SCH SNR, MCS, and BLER with file progression and staleness tracking. Formally designated as *OAI DU scheduler-log-derived telemetry (~1 Hz)*. | Continuous daemon (1.0 Hz); pushes JSON to VM-6 `:9100/report`. |
| **VM-5** | `10.102.0.165` | [`spawn_multi_ue.sh`](spawn_multi_ue.sh) | Spawns isolated UE softmodems inside Linux netns (`ue1` on Cell-1, `ue2` on Cell-2), configures veth, NAT, and verifies canary ping. | Bash automation; writes `active_ues.txt` and UE softmodem logs. |
| **VM-5** | `10.102.0.165` | [`stop_multi_ue.sh`](stop_multi_ue.sh) | Terminates UE softmodems, tears down veth interfaces, and cleans network namespaces. | Bash teardown utility. |
| **VM-5** | `10.102.0.165` | [`enter_ue.sh`](enter_ue.sh) | Interactive helper to enter a designated UE namespace (`sudo ip netns exec ue<N> bash`). | Diagnostic CLI utility. |
| **VM-5** | `10.102.0.165` | [`trafgen.sh`](trafgen.sh) | Generates UDP offered load on Slice 1 (`iperf3`) and canary probes on Slice 2 (`ping 100ms`). | Background loop (1.0 Hz); pushes throughput and RTT/loss to `:9100/report`. |
| **VM-6** | `10.102.0.67` | [`telemetry_collector.py`](telemetry_collector.py) | Ingests `/report` payloads from adapters, polls NWDAF NBI (`:8080`) with isolated run window, and exports Prometheus gauges on `:9100/metrics`. | HTTP server listening on `:9100`. |
| **VM-6** | `10.102.0.67` | [`record_dual_stream.py`](record_dual_stream.py) | Scrapes `:9100/metrics` at 1.000 Hz using monotonic time, exporting the 37-column CSV dataset directly to `data/raw/<RUN_ID>/` with `manifest.json`. | Monotonic recorder; outputs `data/raw/<RUN_ID>/telemetry_<RUN_ID>.csv`. |
| **VM-6** | `10.102.0.67` | [`log_event.py`](log_event.py) | Injects ground-truth event markers (S1, S2, S3, S6, S9, S10_A, S10_B, CLEAR) with atomic sync to `active_event.json` and writes `experiment_events_<RUN_ID>.csv`. | CLI utility; appends to per-run and root event archives. |
| **VM-6** | `10.102.0.67` | [`run_pilot_experiment.py`](run_pilot_experiment.py) | Automated orchestrator managing multi-phase pilot runs (>=60s phase duration) aligned with NWDAF URR ~30s cadence, API snapshotting, and quality audit. | Experiment runner utility. |
| **VM-6** | `10.102.0.67` | [`analyze_dataset.py`](analyze_dataset.py) | Post-experiment data auditor verifying PRB, backlog, drops, throughput, measurement coverage, and SLA violation ratios across raw run archives. | Statistical CLI auditor. |

---

## 2. Core Telemetry Adapter Reference (`core_adapter.py`)

### Role & Standards Compliance
Operates under **3GPP TS 23.288 §6.2.3** ("Data Collection from OAM services") and 3GPP PM TS 32.401 / TS 28.552 principles. It is strictly a **read-only telemetry reader**, not an actuator and not a 3GPP DCCF.

### CLI Arguments
```text
python3 core_adapter.py [OPTIONS]
  --run-id <STR>       [Required] Alphanumeric run identifier
  --interval <FLOAT>   Sampling cadence in seconds (Default: 1.0)
  --url <URL>          Target collector endpoint (Default: http://10.102.0.67:9100/report)
  --inspect-qdiscs     Inspect UPF container kernel qdiscs and exit
  --once               Capture a single sample and exit
  --local-only         Disable HTTP push, archiving only to local disk
```

---

## 3. Deployment Commands Across Nodes

Deploy scripts to their respective paths using `scp`:
```bash
# VM-3 (5G Core Host)
scp scripts/core_adapter.py five-g@10.102.0.164:/opt/oran/5gc/scripts/

# VM-4 (Split RAN Host)
scp scripts/start_ran.sh scripts/stop_ran.sh scripts/ran_adapter.py five-g@10.102.0.167:/opt/oran/ran/scripts/

# VM-5 (nrUE Host)
scp scripts/spawn_multi_ue.sh scripts/stop_multi_ue.sh scripts/trafgen.sh scripts/enter_ue.sh five-g@10.102.0.165:/opt/oran/ue/scripts/

# VM-6 (Monitoring Host)
scp scripts/telemetry_collector.py five-g@10.102.0.67:/opt/oran/monitoring/collector/
scp scripts/record_dual_stream.py scripts/log_event.py scripts/analyze_dataset.py five-g@10.102.0.67:/opt/oran/monitoring/scripts/
```
