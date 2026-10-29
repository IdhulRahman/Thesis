# Experimental Scripts Inventory & Operational Reference

This directory contains the operational daemons, automation scripts, fault injection tools, and dataset recorders for the thesis:

> **Thesis Research Title:**  
> *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Script Distribution Across Virtual Machines

| Host Node | Host IP | Script File | Architectural Role | Execution Mode & Output |
|---|---|---|---|---|
| **VM-3** | `10.102.0.164` | [`core_adapter.py`](core_adapter.py) | Reads Linux kernel `tc qdisc` backlog and packet drops from UPF containers via Netlink. | Continuous daemon (1.0 Hz); pushes JSON to VM-6 `:9100/report` and archives local JSONL. |
| **VM-3** | `10.102.0.164` | [`receiver_iperf.sh`](receiver_iperf.sh) | Dedicated one-off receiver manager for `oai-ext-dn` container to capture ground-truth delivered goodput and UDP loss JSON. | Bash utility; exports to `data/raw/<RUN_ID>/receiver_<SESSION_ID>.json`. |
| **VM-4** | `10.102.0.167` | [`start_ran.sh`](start_ran.sh) | Orchestrates background startup of OAI gNB CU (N2/E2), DU-1 (Cell-1 `:4043` with `-E` three-quarter sampling), and DU-2 (Cell-2 `:4044`). | Bash launcher; writes `cu.log`, `du1.log`, `du2.log`. |
| **VM-4** | `10.102.0.167` | [`stop_ran.sh`](stop_ran.sh) | Gracefully terminates all running OAI softmodem processes on VM-4. | Bash teardown utility; kills CU and DUs. |
| **VM-4** | `10.102.0.167` | [`rfsim_channel_control.py`](rfsim_channel_control.py) | Dynamic RF channel impairment controller over OAI softmodem Telnet (`:9090`). Controls UL/DL path loss and attenuation without restarting gNB processes. | Python CLI utility; supports `show`, `set-attenuation`, `set-raw-ploss`, `reset`, `sweep`. |
| **VM-4** | `10.102.0.167` | [`ran_adapter.py`](ran_adapter.py) | Tails `du1.log` & `du2.log`, extracts live MAC PRB allocation (normalized per cell: 51 PRBs for Cell-1, 106 PRBs for Cell-2, with auto-detection from `du_gnb*.conf`), UL-SCH SNR, MCS, and BLER with file progression and staleness tracking. Formally designated as *OAI DU scheduler-log-derived telemetry (~1 Hz)*. | Continuous daemon (1.0 Hz); pushes JSON to VM-6 `:9100/report`. |
| **VM-4** | `10.102.0.167` | [`measure_sfn_clock.py`](measure_sfn_clock.py) | Audits OAI gNB DU SFN (System Frame Number) radio progression against host monotonic wall clock to detect simulator clock dilation. | Python CLI utility; outputs live frame progress, radio/wall ratio, and session summary. |
| **VM-5** | `10.102.0.165` | [`spawn_multi_ue.sh`](spawn_multi_ue.sh) | Spawns isolated UE softmodems inside Linux netns (`ue1` on Cell-1 with 51 PRB / 3609.12 MHz / `-E` / `--ue-scan-carrier`, `ue2` on Cell-2 with 106 PRB / 3619.20 MHz), configures veth, NAT, and verifies canary ping. | Bash automation; writes `active_ues.txt` and UE softmodem logs. |
| **VM-5** | `10.102.0.165` | [`stop_multi_ue.sh`](stop_multi_ue.sh) | Terminates UE softmodems, tears down veth interfaces, and cleans network namespaces. | Bash teardown utility. |
| **VM-5** | `10.102.0.165` | [`enter_ue.sh`](enter_ue.sh) | Interactive helper to enter a designated UE namespace (`sudo ip netns exec ue<N> bash`). | Diagnostic CLI utility. |
| **VM-5** | `10.102.0.165` | [`trafgen.sh`](trafgen.sh) | Generates UDP offered load on Slice 1 (`iperf3`) and canary probes on Slice 2 (`ping 100ms`). | Background loop (1.0 Hz); pushes throughput and RTT/loss to `:9100/report`. |
| **VM-6** | `10.102.0.67` | [`telemetry_collector.py`](telemetry_collector.py) | Ingests `/report` payloads from adapters, polls NWDAF NBI (`:8080`) with isolated run window, and exports Prometheus gauges on `:9100/metrics`. | HTTP server listening on `:9100`. |
| **VM-6** | `10.102.0.67` | [`record_experiment.py`](record_experiment.py) | Single-scenario telemetry recorder scraping `:9100/metrics` at 1.000 Hz monotonic cadence, exporting the 40-column CSV dataset directly to `data/raw/<RUN_ID>/` with `manifest.json`. | Monotonic recorder; outputs `data/raw/<RUN_ID>/telemetry_<RUN_ID>.csv`. |
| **VM-6** | `10.102.0.67` | [`analyze_dataset.py`](analyze_dataset.py) | Post-experiment data auditor calculating statistical distributions (PRB, backlog, drops, goodput, SLA violation ratios) from recorded CSV archives. | Statistical CLI auditor. |

---

## 2. Telemetry Recording Operational Guide (`record_experiment.py`)

### Usage Modes

1. **Interactive Prompt:**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py
   ```
   *Asks for scenario name (default `S1`), duration in seconds (default `60`), and optional notes.*

2. **Direct CLI Execution:**
   ```bash
   # Record S1 Baseline (60s)
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 60 --notes "Baseline normal 10M"

   # Record S3 RAN Overload (60s)
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 60 --notes "Kandidat overload 80M"

   # Record S6 Core Bottleneck (60s)
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 60 --notes "Kandidat TBF Core 12M"
   ```

3. **Manual Stop Mode (`Ctrl+C`):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 0
   ```
   *Runs continuously until operator presses `Ctrl+C`. Safely flushes and closes CSV and writes manifest.*

### Post-Recording Statistical Analysis
To inspect statistical distributions of the recorded run:
```bash
python3 /opt/oran/monitoring/scripts/analyze_dataset.py /opt/oran/monitoring/data/raw/<RUN_ID>/telemetry_<RUN_ID>.csv
```

---

## 3. SFN Radio Clock Audit Guide (`measure_sfn_clock.py`)

To verify whether RFSimulator executes in real-time or suffers CPU-induced time dilation (see [Case 55](../docs/troubleshooting/ran-ue.md#case-55)):

```bash
# Monitor Cell-1 (DU-1) live progression
python3 /opt/oran/ran/scripts/measure_sfn_clock.py --log /opt/oran/ran/du1.log

# Monitor Cell-2 (DU-2) reporting every 128 frames (1.28s)
python3 /opt/oran/ran/scripts/measure_sfn_clock.py --log /opt/oran/ran/du2.log --step 128

# Audit an existing log file from the beginning and exit after 10 samples
python3 /opt/oran/ran/scripts/measure_sfn_clock.py --log /opt/oran/ran/du1.log --from-start --max-samples 10
```

* **Interpretation:**
  * Ratio $\ge 0.95\times$: Real-time execution (no simulator dilation).
  * Ratio $0.70\times - 0.95\times$: Moderate dilation / high CPU load.
  * Ratio $< 0.70\times$: Severe software simulator bottleneck (e.g. 106 PRB full sampling `chanmod`).



