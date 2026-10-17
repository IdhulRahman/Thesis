# Experimental Scenarios & Disturbance Registry

**Authoritative Specification:** Single Source of Truth for Fault Injection & Scenario Annotation  
**Target Nodes:** VM-5 (Traffic Generator), VM-4 (Split RAN), VM-3 (UPF Host), and VM-6 (Telemetry Recorder)  
**Canonical Scenario IDs:** `S1`, `S2`, `S3`, `S6`, `S9`, `S10_A`, `S10_B`, `CLEAR`

---

## 1. Scenario Registry & Ground-Truth Label Definitions

The testbed defines discrete, repeatable fault injection scenarios to evaluate bottleneck detection across the spectrum of network conditions. Every scenario is recorded directly using `scripts/record_experiment.py` on VM-6:

| Scenario ID | Formal Scenario Identifier | Ground-Truth Domain | Physical Target Component | Injection Mechanism | Parameter Values | Expected Telemetry Signature |
|---|---|:---:|---|---|---|---|
| **`CLEAR`** | `CLEAR_FAULT` | `NORMAL` | None | Baseline quiescent state | Offered load $10\text{ Mbps}$, no shaping | PRB $\approx 15\%$, UPF backlog $0\text{ B}$, RTT $< 25\text{ ms}$, loss $0\%$. |
| **`S1`** | `S1_NORMAL_LIGHT` | `NORMAL` | None | Light baseline traffic | Offered load $10\text{ Mbps}$ ($\sim 35\% C_{\text{ran}}^{UL}$) | PRB $\approx 35\%$, UPF backlog $0\text{ B}$, RTT $< 25\text{ ms}$, loss $0\%$. |
| **`S2`** | `S2_NORMAL_HIGH` | `NORMAL` | None | High traffic without congestion | Offered load $22\text{ Mbps}$ ($\sim 80\% C_{\text{ran}}^{UL}$) | PRB $\approx 80\%$, UPF backlog $0\text{ B}$, RTT $< 30\text{ ms}$, loss $0\%$. |
| **`S3`** | `S3_RAN_OVERLOAD` | `RAN` | gNB DU-1 (Cell-1) | Radio saturation overload | Offered load $40\text{ Mbps}$ (or candidate $80\text{ Mbps}$) | PRB peaks, BLER escalates, UPF backlog remains $0\text{ B}$. |
| **`S6`** | `S6_CORE_QUEUE_TBF` | `CORE` | UPF-1 (Slice 1 `eth0`) | Linux `tc qdisc` rate limiting | TBF rate $12\text{ Mbps}$, buffer $200\text{ ms}$ | UPF backlog $\approx 150 - 300\text{ KB}$, drops $>1000/\text{s}$, PRB nominal. |
| **`S9`** | `S9_JOINT_OVERLOAD` | `JOINT` | DU-1 and UPF-1 | Simultaneous RAN + Core stress | RAN load $40\text{ Mbps}$ + UPF TBF $12\text{ Mbps}$ | PRB elevated AND UPF backlog $> 150\text{ KB}$, surge in drops and delay. |
| **`S10_A`**| `S10_A_RELEASE_RAN` | `CORE` | UPF-1 (Slice 1 `eth0`) | Staged recovery: release RAN | Load reduced to $20\text{ Mbps}$, TBF active | PRB drops to nominal, but UPF backlog remains saturated ($\approx 150\text{ KB}$). |
| **`S10_B`**| `S10_B_RELEASE_CORE`| `NORMAL` | None | Staged recovery: release Core | Load at $20\text{ Mbps}$, clear TBF | UPF backlog drains to $0\text{ B}$, system returns to healthy state. |

---

## 2. Multi-Slice Isolation & Cross-Slice Dynamics Notice

> [!IMPORTANT]
> **Slice Independence Principle:**  
> In our dual-slice testbed:
> * **Slice 1 (eMBB):** Anchored on UPF-1 (`oai-upf-slice1`), connected to Cell-1 (Port `4043`).
> * **Slice 2 (URLLC):** Anchored on UPF-2 (`oai-upf-slice2`), connected to Cell-2 (Port `4044`).
>
> Fault injections targeted at Slice 1 (such as `tc qdisc` rate shaping on UPF-1 `eth0` in **S6**) **do not automatically cause queue accumulation or packet drops on Slice 2**. Slice 2 operates over an independent physical container network stack and serving cell. Slice 2 canaries will only experience degradation under explicit cross-slice resource contention or hypervisor CPU starvation.

---

## 3. Step-by-Step Injection & Recording Procedures

Each scenario session is recorded independently via `record_experiment.py`.

### 3.1 Scenario S1 & S2 — Normal Baselines
1. **VM-5 (Inject Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 65 10
   ```
2. **VM-6 (Record Scenario):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 60 --notes "Light Normal Baseline"
   ```

### 3.2 Scenario S3 — RAN Radio Overload
1. **VM-5 (Inject Overload Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 65 80
   ```
2. **VM-6 (Record Scenario):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 60 --notes "RAN Overload candidate 80M"
   ```

### 3.3 Scenario S6 — Core Transport Queuing via TBF
1. **VM-3 (Apply Token Bucket Filter on UPF-1):**
   ```bash
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 12mbit burst 10kb latency 200ms
   ```
2. **VM-5 (Inject Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 65 20
   ```
3. **VM-6 (Record Scenario):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 60 --notes "Core TBF 12Mbit on UPF-1"
   ```

### 3.4 Scenario S9 — Joint RAN & Core Overload
1. **VM-3 & VM-5 (Apply Simultaneous Stress):**
   * On VM-3: Apply TBF ($12\text{ Mbps}$, latency $200\text{ ms}$) on `oai-upf-slice1`.
   * On VM-5: Launch traffic at $80\text{ Mbps}$.
2. **VM-6 (Record Scenario):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S9 --duration 60 --notes "Simultaneous RAN and Core stress"
   ```

### 3.5 Cleanup / Baseline Recovery
1. **VM-3 (Remove TBF on UPF-1):**
   ```bash
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
2. **VM-5 (Reset Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 65 10
   ```
3. **VM-6 (Record Baseline State):**
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py CLEAR --duration 30 --notes "Quiescent Baseline Recovery"
   ```
