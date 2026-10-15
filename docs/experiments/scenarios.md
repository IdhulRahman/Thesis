# Experimental Scenarios & Disturbance Registry

**Authoritative Specification:** Single Source of Truth for Fault Injection & Scenario Annotation  
**Target Nodes:** VM-5 (Traffic Generator), VM-4 (Split RAN), VM-3 (UPF Host), and VM-6 (Event Logger)  
**Historical Scenario IDs:** `CLEAR`, `S1`, `S2`, `S3`, `S6`, `S9`, `S10_A`, `S10_B`

---

## 1. Scenario Registry & Ground-Truth Label Definitions

The testbed defines discrete, repeatable fault injection scenarios to evaluate bottleneck detection across the spectrum of network conditions. Every scenario is recorded synchronously using `scripts/log_event.py` on VM-6:

| Scenario ID | Formal Scenario Identifier | Ground-Truth Domain | Physical Target Component | Injection Mechanism | Parameter Values | Expected Telemetry Signature |
|---|---|:---:|---|---|---|---|
| **`CLEAR`** | `CLEAR_FAULT` | `NORMAL` | None | Baseline quiescent state | Offered load $10\text{ Mbps}$, no shaping | PRB $\approx 15\%$, UPF backlog $0\text{ B}$, RTT $< 25\text{ ms}$, loss $0\%$. |
| **`S1`** | `S1_NORMAL_LIGHT` | `NORMAL` | None | Light baseline traffic | Offered load $10\text{ Mbps}$ ($\sim 35\% C_{\text{ran}}^{UL}$) | PRB $\approx 35\%$, UPF backlog $0\text{ B}$, RTT $< 25\text{ ms}$, loss $0\%$. |
| **`S2`** | `S2_NORMAL_HIGH` | `NORMAL` | None | High traffic without congestion | Offered load $22\text{ Mbps}$ ($\sim 80\% C_{\text{ran}}^{UL}$) | PRB $\approx 80\%$, UPF backlog $0\text{ B}$, RTT $< 30\text{ ms}$, loss $0\%$. |
| **`S3`** | `S3_RAN_OVERLOAD` | `RAN` | gNB DU-1 (Cell-1) | Radio saturation overload | Offered load $40\text{ Mbps}$ ($> 28.4\text{ Mbps}$) | PRB $= 100\%$ (106 PRB), BLER escalates, UPF backlog remains $0\text{ B}$. |
| **`S6`** | `S6_CORE_QUEUE_TBF` | `CORE` | UPF-1 (Slice 1 `eth0`) | Linux `tc qdisc` rate limiting | TBF rate $12\text{ Mbps}$, buffer $200\text{ ms}$ | UPF backlog $\approx 150 - 300\text{ KB}$, drops $>1000/\text{s}$, PRB nominal. |
| **`S9`** | `S9_JOINT_OVERLOAD` | `JOINT` | DU-1 and UPF-1 | Simultaneous RAN + Core stress | RAN load $40\text{ Mbps}$ + UPF TBF $12\text{ Mbps}$ | PRB $= 100\%$ AND UPF backlog $> 150\text{ KB}$, surge in drops and delay. |
| **`S10_A`**| `S10_A_RELEASE_RAN` | `CORE` | UPF-1 (Slice 1 `eth0`) | Staged recovery: release RAN | Load reduced to $20\text{ Mbps}$, TBF active | PRB drops to $75\%$, but UPF backlog remains saturated ($\approx 150\text{ KB}$). |
| **`S10_B`**| `S10_B_RELEASE_CORE`| `NORMAL` | None | Staged recovery: release Core | Load at $20\text{ Mbps}$, clear TBF | UPF backlog drains to $0\text{ B}$, system returns to healthy state. |

---

## 2. Multi-Slice Isolation & Cross-Slice Dynamics Notice

> [!IMPORTANT]
> **Slice Independence Principle:**  
> In our dual-slice testbed:
> * **Slice 1 (eMBB):** Anchored on UPF-1 (`oai-upf-slice1`), connected to Cell-1 (Port `4043`).
> * **Slice 2 (URLLC):** Anchored on UPF-2 (`oai-upf-slice2`), connected to Cell-2 (Port `4044`).
>
> Fault injections targeted at Slice 1 (such as `tc qdisc` rate shaping on UPF-1 `eth0` in **S6**) **do not automatically cause queue accumulation or packet drops on Slice 2**. Slice 2 operates over an independent physical container network stack and serving cell. Slice 2 canaries will only experience degradation under:
> 1. Explicit cross-slice resource contention (e.g., co-locating UE-2 onto Cell-1 or co-locating UPF-2 onto the same congested link).
> 2. Host CPU/Memory starvation affecting the underlying hypervisor.

---

## 3. Step-by-Step Injection & Verification Procedures

### 3.1 Scenario S1 & S2 — Normal Baselines
1. **VM-6 (Annotate):**
   ```bash
   python3 /opt/oran/monitoring/scripts/log_event.py S1 "Starting Light Normal Baseline"
   ```
2. **VM-5 (Inject Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 10
   ```
3. **Disturbance Confirmation:**  
   Verify on VM-6 (`curl -s http://localhost:9100/metrics`): `e2e_slice1_tput_mbps` $\approx 10.0$, `upf_queue_backlog_bytes` $= 0$, `ran_prb_cell1` $\le 40\%$.

### 3.2 Scenario S3 — RAN Radio Overload
1. **VM-6 (Annotate):**
   ```bash
   python3 /opt/oran/monitoring/scripts/log_event.py S3 "Injecting RAN Overload (40 Mbps)"
   ```
2. **VM-5 (Inject Overload Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 40
   ```
3. **Disturbance Confirmation:**  
   `ran_prb_cell1` reaches $100\%$ ($106/106$ PRBs), while `upf_backlog_bytes_embb` remains $0\text{ B}$.

### 3.3 Scenario S6 — Core Transport Queuing via TBF
1. **VM-6 (Annotate):**
   ```bash
   python3 /opt/oran/monitoring/scripts/log_event.py S6 "Injecting Core TBF Shaper (12 Mbps)"
   ```
2. **VM-3 (Apply Token Bucket Filter on UPF-1):**
   ```bash
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf \
     rate 12mbit burst 32kbit latency 200ms
   ```
3. **VM-5 (Inject Saturated Traffic):**
   ```bash
   sudo /opt/oran/ue/scripts/trafgen.sh start 20
   ```
4. **Disturbance Confirmation:**  
   `upf_backlog_bytes_embb` accumulates to $\ge 150\text{ KB}$, `upf_drops_embb` $> 0$, while `ran_prb_cell1` remains $< 80\%$.

### 3.4 Scenario S9 — Joint RAN & Core Overload
1. **VM-6 (Annotate):**
   ```bash
   python3 /opt/oran/monitoring/scripts/log_event.py S9 "Injecting Joint Overload"
   ```
2. **VM-3 & VM-5 (Apply Simultaneous Stress):**
   * On VM-3: Apply TBF ($12\text{ Mbps}$, latency $200\text{ ms}$) on `oai-upf-slice1`.
   * On VM-5: Launch traffic at $40\text{ Mbps}$.
3. **Disturbance Confirmation:**  
   Both `ran_prb_cell1` $= 100\%$ AND `upf_backlog_bytes_embb` $> 150\text{ KB}$ simultaneously.

### 3.5 Scenario S10_A & S10_B — Staged Recovery
1. **S10_A (Release RAN):** Reduce traffic to $20\text{ Mbps}$ on VM-5. Annotate `python3 log_event.py S10_A`. Confirm PRB drops while UPF queue persists.
2. **S10_B (Release Core):** Remove TBF on VM-3:
   ```bash
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
   Annotate `python3 log_event.py S10_B`. Confirm UPF queue backlog drains to $0\text{ B}$.
3. **Clear All:**
   ```bash
   python3 /opt/oran/monitoring/scripts/log_event.py CLEAR "Experiment Completed"
   ```
