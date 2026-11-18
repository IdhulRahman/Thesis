# Operational Standard Operating Procedures (SOP) & Pre-Flight Checklists

**Document Purpose:** Mandatory operational protocol to guarantee end-to-end telemetry integrity across all experiment scenarios.  
**Applicability:** VM-1 through VM-6 (Non-RT RIC, Near-RT RIC, 5G Core, Split RAN, UE, Monitoring).  
**Zero-Tolerance Policy:** No recording session ($\ge 1800\text{ s}$) shall be initiated without successfully passing the **Mandatory Pre-Flight Telemetry Gate Check**.

---

## 1. Component Inter-Dependency & Cascading Restart Matrix

In a virtualized multi-VM 5G testbed, restarting an upstream component invalidates in-memory state, subscriptions, or file descriptors in downstream components. Whenever a component is restarted, all dependent components listed below **MUST** be restarted in strict order:

| Trigger Event (Component Restarted) | Host | Dependent Components That MUST Be Restarted | Reason & Failure Mode if Omitted |
|---|---|---|---|
| **`oai-smf-slice1` / `oai-smf-slice2`** | VM-3 | **`oai-nwdaf-sbi`**, **`oai-nwdaf-engine`** | **CRITICAL:** SMF wipes in-memory `Nsmf_EventExposure` subscriptions upon restart. `oai-nwdaf-sbi` only subscribes on initialization. Failure to restart NWDAF SBI causes SMF to drop URR reports (`No subscription available`), resulting in **permanent `ulVol: 0` in telemetry**. |
| **`oai-upf-slice1` / `oai-upf-slice2`** | VM-3 | **`core_adapter.py`**, **SMF PDU Association** | UPF restart destroys existing PFCP sessions and kernel `qdisc` handles. |
| **gNB DU-1 / DU-2 (`nr-softmodem`)** | VM-4 | **`ran_adapter.py`**, **RFsim attenuation reset (0.0 dB)** | DU restart recreates `/opt/oran/ran/du1.log`. `ran_adapter.py` must re-seek the file from line 0. Channel attenuation must be 0.0 dB for UE initial synchronization. |
| **gNB CU (`nr-softmodem`)** | VM-4 | **DU-1, DU-2**, **E2 Agent (`ric_e2term`)** | CU restart severs F1-C and E2AP SCTP connections. |
| **`nrUE` Softmodem (VM-5)** | VM-5 | **Verify `oaitun_ue1` active in `ue1` and `ue2`** | Spawning UE without cleanup causes tun device collisions and `DOWN` interfaces. |

### Canonical Core Restart Sequence
Whenever the 5G Core control plane or user plane must be restarted, the following unified sequence must be executed on **VM-3**:
```bash
# 1. Restart Core Network Functions
sudo docker restart oai-nrf-slice12 oai-nssf oai-amf oai-smf-slice1 oai-smf-slice2 oai-upf-slice1 oai-upf-slice2

# 2. MANDATORY: Concurrently restart NWDAF SBI and Engine to re-establish Nsmf subscriptions
sudo docker restart oai-nwdaf-sbi oai-nwdaf-engine

# 3. Verify N11 subscription state in SMF logs
sudo docker logs --tail 20 oai-smf-slice1 | grep -i "subscription"
```

---

## 2. Mandatory Pre-Flight Telemetry Gate Check (The 60-Second Rule)

Before launching any long-duration experiment session (Training 3600s, Validation 1800s, Testing 1800s), an operator **MUST execute a 30-second verification probe** and confirm that all four telemetry pillars are actively producing valid, non-zero metrics.

### Step 1: Start Canary Traffic Probe on VM-5 (30 Seconds)
```bash
sudo /opt/oran/ue/scripts/trafgen.sh start 30 10
```

### Step 2: Execute Pre-Flight Probe Query on VM-6
While traffic is actively transmitting (around second 10–20), run the gate check on **VM-6**:
```bash
curl -s http://127.0.0.1:9100/metrics | grep -E "(nwdaf_comm_ul_bytes|nwdaf_api_status|ran_cell_prb_utilization\{cell_id=\"1\"\}|ran_cell_bler\{cell_id=\"1\"\}|upf_queue_backlog_bytes\{snssai=\"01000001\"\})"
```

### Step 3: Evaluate Pass / Fail Criteria

| Pillar | Metric Identifier | Required Pre-Flight Condition | Action if FAILED |
|---|---|---|---|
| **1. RAN Scheduler** | `ran_cell_prb_utilization{cell_id="1"}` | $\mathbf{> 0.0\%}$ (Typically $30\text{–}100\%$) | Restart `ran_adapter.py` on VM-4. Check `du1.log`. |
| **2. RAN BLER** | `ran_cell_bler{cell_id="1"}` | **Numeric ($\ge 0.0000$)** | Verify DU-1 log output in `/opt/oran/ran/du1.log`. |
| **3. Core UPF** | `upf_queue_backlog_bytes{snssai="01000001"}` | **Numeric ($\ge 0\text{ B}$)** | Restart `core_adapter.py` on VM-3. Verify `tc qdisc`. |
| **4. Core NWDAF API** | `nwdaf_api_status` | **Strictly `1`** | Check Kong Gateway (`:8080`) and NWDAF containers on VM-3. |
| **5. Core NWDAF Volume** | `nwdaf_comm_ul_bytes` | **Strictly $> 0$** (Increments across 30s) | **HALT!** Run `sudo docker restart oai-nwdaf-sbi oai-nwdaf-engine` on VM-3. |

> [!CAUTION]
> **GATE FAILURE RULE:**  
> If **ANY** of the five criteria above fails, **DO NOT START `record_experiment.py`!**  
> Resolve the specific failed pillar first, re-run the 30-second probe, and proceed only when all five criteria return **PASS**.

---

## 3. Scenario Transition Procedure

When transitioning between scenarios (e.g., S9 $\to$ S8 $\to$ S4 $\to$ S3):

1. **Stop Traffic Generator on VM-5:**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh stop
   ```
2. **Apply Domain Impairments:**
   * **RAN (VM-4):** Set calibrated attenuation via `rfsim_channel_control.py`
     - Clean Baseline (S1, S2, S5, S6, S7): `reset` (0.0 dB)
     - Soft Degradation (S3, S8): `set-attenuation 15.0 --channel-id 1 --port 9090`
     - Hard Degradation (S4, S9): `set-attenuation 18.0 --channel-id 1 --port 9090`
   * **Core (VM-3):** Set kernel `tc qdisc` on `oai-upf-slice1`
     - Clean Baseline (S1, S2, S3, S4, S5): `tc qdisc del dev eth0 root 2>/dev/null || true`
     - Soft Core TBF (S6, S8): `tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms`
     - Hard Core TBF (S7, S9): `tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms`
3. **Run Mandatory 60-Second Gate Check (§2).**
4. **Launch Long Recording Session (`record_experiment.py`) only after Gate Check PASS.**
