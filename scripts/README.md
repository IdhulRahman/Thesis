# 5G O-RAN Thesis Testbed Scripts Repository

Collection of automation, fault injection, physical kernel telemetry, and dataset logging scripts for the thesis evaluation:
> *"Evaluating the Impact of rApp Sequential Forecasting Models on Cross-Domain Bottleneck Diagnosis and Closed-Loop SLA Recovery in O-RAN Multi-Slice Networks"*

---

## 1. Script Distribution Across Virtual Machines (VMs)

| Target VM | Domain / Component | Script | Description & Role |
|---|---|---|---|
| **VM-3** (`10.102.0.164`) | 5G Core User-Plane | [`core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py) | Host kernel telemetry adapter v9 for UPF (3GPP PM & Linux qdisc/dev), dual disk JSONL/CSV archiving, and bounded async HTTP push to `:9100/report`. |
| **VM-4** (`10.102.0.167`) | OAI Split RAN | [`start_ran.sh`](file:///d:/Idhul/Program/Thesis/scripts/start_ran.sh) | Automated background launcher for CU (N2/E2), DU-1 (Cell-1 :4043), and DU-2 (Cell-2 :4044). |
| **VM-4** (`10.102.0.167`) | OAI Split RAN | [`stop_ran.sh`](file:///d:/Idhul/Program/Thesis/scripts/stop_ran.sh) | Clean teardown script to terminate all active `nr-softmodem` processes. |
| **VM-4** (`10.102.0.167`) | OAI Split RAN | [`ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py) | Host daemon v1 extracting live MAC PRB allocation (`NPRB`) from `du1.log` & `du2.log` and pushing to VM-6 `:9100/report`. |
| **VM-5** (`10.102.0.165`) | OAI nrUE Emulator | [`spawn_multi_ue.sh`](file:///d:/Idhul/Program/Thesis/scripts/spawn_multi_ue.sh) | Multi-UE spawner featuring isolated network namespaces (`ue1`...`ueN`), veth pair & NAT setup, dynamic 3GPP config, and EXT-DN ping verification. |
| **VM-5** (`10.102.0.165`) | OAI nrUE Emulator | [`stop_multi_ue.sh`](file:///d:/Idhul/Program/Thesis/scripts/stop_multi_ue.sh) | Clean teardown utility for `nr-uesoftmodem` processes, veth interfaces, and UE namespaces. |
| **VM-5** (`10.102.0.165`) | OAI nrUE Emulator | [`trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh) | Simultaneous multi-slice traffic generator for eMBB (iperf3 UDP) and URLLC (canary ping 100 ms) with real-time reporting to VM-6 `:9100/report`. |
| **VM-5** (`10.102.0.165`) | OAI nrUE Emulator | [`enter_ue.sh`](file:///d:/Idhul/Program/Thesis/scripts/enter_ue.sh) | Interactive shell access helper into designated UE network namespaces for live diagnostics. |
| **VM-6** (`10.102.0.67`) | Monitoring Data | [`telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py) | Ingestion daemon for `:9100/report` and Prometheus Exporter `:9100/metrics` with kernel key alias synchronization (`upf_qdisc_*` $\leftrightarrow$ `upf_queue_*`). |
| **VM-6** (`10.102.0.67`) | Monitoring Data | [`record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py) | Continuous 1.000 Hz time-series telemetry logger with drift-free monotonic clock to `telemetry_raw_<RUN_ID>_<PID>.csv`. |
| **VM-6** (`10.102.0.67`) | Monitoring Data | [`log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py) | Discrete ground-truth fault scenario logger (S1–S10) appending to `experiment_events_<RUN_ID>.csv` with atomic sync to `active_event.json`. |
| **VM-6** (`10.102.0.67`) | Monitoring Data | [`analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py) | Post-experiment statistical audit script verifying PRB%, Max Backlog, Total Drops, eMBB throughput, and URLLC SLA violation ratio. |

---

## 2. Synchronization and Deployment across VMs

Each script can be copied to the target VM using `scp` or maintained directly at their designated paths:

```bash
# Example deployment to VM-3:
scp scripts/core_adapter.py five-g@10.102.0.164:/opt/oran/5gc/scripts/

# Example deployment to VM-4:
scp scripts/start_ran.sh scripts/stop_ran.sh scripts/ran_adapter.py five-g@10.102.0.167:/opt/oran/ran/scripts/

# Example deployment to VM-5:
scp scripts/spawn_multi_ue.sh scripts/stop_multi_ue.sh scripts/trafgen.sh scripts/enter_ue.sh five-g@10.102.0.165:/opt/oran/ue/scripts/

# Example deployment to VM-6:
scp scripts/telemetry_collector.py five-g@10.102.0.67:/opt/oran/monitoring/collector/
scp scripts/record_dual_stream.py scripts/log_event.py scripts/analyze_dataset.py five-g@10.102.0.67:/opt/oran/monitoring/scripts/
```

---

## 3. Core Research Telemetry Adapter (`core_adapter.py` v9) Operational Guide

The UPF host telemetry adapter operates under **3GPP TS 23.288 §6.2.3** ("Data Collection from OAM services") and 3GPP TS 32.401 / TS 28.552 PM principles:

### CLI Options Reference

| Parameter | Required / Default | Purpose |
|---|---|---|
| `--run-id <ID>` | **Mandatory** | Unique alphanumeric experiment run identifier (`[A-Za-z0-9_.-]{1,64}`). |
| `--inspect-qdiscs` | Optional flag | Read-only inspection of UPF container Linux qdiscs, returning JSON structures. |
| `--standards` | Optional flag | Dumps official 3GPP standardization references (TS 32.401, TS 28.552, etc.). |
| `--interval <SEC>` | Default: `1.0` | Target sampling cadence in seconds (research slow-loop choice). |
| `--output-dir <DIR>` | Default: `./upf-telemetry` | Directory for local JSONL and CSV run archives. |
| `--url <URL>` | Default: `http://10.102.0.67:9100/report` | Target VM-6 telemetry collector HTTP ingestion endpoint. |
| `--local-only` | Optional flag | Disables HTTP push, archiving telemetry exclusively to local disk. |
| `--once` | Optional flag | Gathers a single baseline sample for field validation. |
| `--samples <N>` | Optional integer | Stops automatically after $N$ valid samples. |

### Operational Commands (VM-3 Host)

```bash
# 1. Verify kernel qdiscs on running UPF containers:
python3 /opt/oran/5gc/scripts/core_adapter.py --inspect-qdiscs

# 2. Launch adapter daemon in background:
sudo nohup python3 -u /opt/oran/5gc/scripts/core_adapter.py \
  --run-id pilot-run-01 \
  --output-dir /opt/oran/5gc/telemetry_archive \
  --url http://10.102.0.67:9100/report \
  > /opt/oran/5gc/scripts/core_adapter.log 2>&1 &

# 3. Monitor live telemetry streaming:
tail -f /opt/oran/5gc/scripts/core_adapter.log

# 4. Stop daemon:
sudo pkill -f core_adapter.py
```
