# Experimental Evaluation Methodology & Baseline Framework

**Thesis Research Title:**  
*Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Scientific Framework & Core Hypotheses

The central scientific premise of this thesis is that **diagnosing the exact architectural domain of a network bottleneck (RAN vs. Core User Plane vs. Joint) prior to triggering control actions significantly reduces SLA violations ($V_s$), minimizes recovery time ($T_{\text{rec}}$), and eliminates action churn ($C_{\text{act}}$)** compared to single-domain or uncoordinated control paradigms.

### 1.1 Core Hypotheses
1. **$H_1$ (Superiority over Static Default):** Closed-loop dynamic steering achieves significantly lower SLA violation rates compared to standard static 3GPP slicing (B0) during both radio degradation and core transport queuing.
2. **$H_2$ (Mitigation of Domain Myopia):** A bottleneck-aware coordinator achieves a lower wrong-domain actuation rate ($W_{\text{act}} \to 0$) and avoids ping-pong handover instability compared to RAN-only (B1) or Core-only (B2) controllers.
3. **$H_3$ (Coordination Stability):** Hierarchical multi-timescale coordination (slow loop ~30s on rApp, fast loop on xApp) eliminates actuation thrashing observed in decoupled independent controllers (B3).

---

## 2. Comparative Baseline Matrix (B0 through B4 vs. Proposed)

To validate the hypotheses, the experimental testbed executes **five comparative baselines (B0 to B4)** alongside the **Proposed System**:

| Paradigm Tier | Baseline ID | Control Approach | Domain Awareness | Coordination Model |
|---|---|---|---|---|
| **Static Default** | **B0** | Standard 3GPP A3 Handover | Local Radio RSRP only | No RIC coordination |
| **Single-Domain** | **B1** & **B2** | Standalone xApp / Core Shaper | Isolated to RAN or Core | Blind to cross-domain congestion |
| **Decoupled** | **B3** | Uncoordinated Dual Controllers | Both domains active | Independent / Conflicting actuation |
| **Naive Coordination** | **B4** | Fixed Priority Heuristic | Cross-domain aggregated | Static action sequence (No root diagnosis) |
| **Proposed System** | **PROPOSED** | Closed-Loop MAPE-K Coordination | Cross-domain correlated | Root-cause matched steering & verification |

| Baseline ID | Control Paradigm | Decision Inputs | Actuation Mechanisms | Expected Failure Mode / Behavioral Limitation |
|---|---|---|---|---|
| **B0** | **Static 3GPP Baseline** | RSRP only (Standard A3 Event) | Autonomous gNB Handover | Completely blind to Core congestion; no dynamic slice traffic steering. |
| **B1** | **RAN-Only Control** | Radio scheduler metrics (PRB, SNR, MCS) | Inter-cell steering via Near-RT xApp | **Core-Blind:** When Core UPF is congested, triggers futile inter-cell handovers and ping-pong churn. |
| **B2** | **Core-Only Control** | Core telemetry (UPF queue, packet drops) | Linux `tc qdisc` rate shaping | **Radio-Blind:** Cannot leverage alternative radio cells when radio channel collapses. |
| **B3** | **Decoupled Controllers** | Both domains monitored independently | Independent xApp & Core adapters | **Conflicting Actions:** Both controllers act simultaneously without cross-domain coordination, destabilizing SLAs. |
| **B4** | **Coordinated (Fixed Heuristic)**| Aggregated cross-domain telemetry | Fixed action sequence (e.g., Handover $\to$ Shape) | **Suboptimal Recovery:** Executes wrong action first when bottleneck cause does not match fixed priority. |
| **PROPOSED** | **Bottleneck-Aware Closed-Loop** | Correlated RAN + Core Telemetry | Matched Action (RAN / Core / Joint) + SLA Verify | **Optimal Recovery:** Acts strictly on diagnosed root-cause domain; suppresses churn via closed-loop verification. |

---

## 3. Dataset Partitioning & Data Processing Rules

### 3.1 Data Splitting Strategy
Experimental datasets recorded via `record_experiment.py` are partitioned temporally across contiguous scenario executions:
* **Training Set ($60\%$):** Contiguous scenario blocks used for offline feature normalization and classifier training.
* **Validation Set ($20\%$):** Independent experiment runs used for hyperparameter tuning and decision threshold calibration.
* **Testing Set ($20\%$):** Unseen experiment runs evaluated under continuous closed-loop execution.

### 3.2 Data Processing & Feature Engineering Rules
1. **Zero Artificial Imputation:** Unsupported metrics (such as `nwdaf_load_embb`) or unmeasured values emit strict **`NaN`**. They must **not** be filled with synthetic constants (e.g., $0$ or $-42\text{ dBm}$) during training.
2. **Monotonic Elapsed Timing:** Temporal feature alignment strictly uses `elapsed_sec` derived from `time.monotonic()` to eliminate leap-second or NTP wall-clock adjustments.
3. **Derivative vs. Cumulative Features:** Cumulative counters (`nwdaf_comm_ul_bytes`, `nwdaf_comm_dl_bytes`) update in step functions every $\approx 30\text{ s}$ governed by UPF periodic URR reports. Direct 1 Hz differentiation ($\Delta V / \Delta t$) yields zero-delta plateaus with 30-second burst spikes. For model evaluation, cumulative counters are either ingested directly as monotonic volume totals, or transformed using causal windowed averaging ($\frac{V_t - V_{t-W}}{W}$ where $W \ge 30\text{ s}$) with declared reset/epoch boundaries. Instantaneous 1 Hz differentiation must not be conflated with physical real-time line rate.
4. **Quality & Freshness Indicators (Not Deletion Filters):** Telemetry freshness indicators (`nwdaf_comm_freshness` at 45s and `e2e_probe_freshness` at 3.5s) function as telemetry health diagnostics, NOT blanket raw data validity masks. A value of `nwdaf_comm_freshness = 0` occurs legitimately during periods of stable zero-traffic or reporting stalls; recorder daemons strictly record all observations without row deletion. Downstream filtering, imputation, or masking policies are explicit analyst decisions that must be declared and tested for sensitivity during offline evaluation.

---

## 4. Evaluation Metrics & Statistical Validation

### 4.1 Unified SLA Evaluation Contract
To maintain consistency across all analysis and baseline evaluations, SLA satisfaction is defined per slice relative to workload demand:

1. **Slice 1 (eMBB) SLA Contract:**
   * **Offered Load Sensitivity:** Measured throughput must be evaluated relative to offered workload demand. Low throughput during low-demand scenarios (e.g., Scenario S1 with offered load of 10 Mbps) is **not** an SLA violation.
   * **SLA Threshold:** Under saturation stress (offered load $\ge 25\text{ Mbps}$), Slice 1 SLA requires user goodput $T_{\text{eMBB}} \ge 20.0\text{ Mbps}$ (or $\ge 85\%$ of offered demand when below capacity).
2. **Slice 2 (URLLC) SLA Contract:**
   * **End-to-End Latency Target:** Canary ICMP round-trip time $RTT \le 20.0\text{ ms}$ and sequence loss percentage $\le 1.0\%$.
   * **Scope & Standards Demarcation:** 3GPP TS 23.501 Table 5.7.4-1 defines standard Packet Delay Budget (PDB) between UE and N6-terminating UPF (e.g., 5 ms for URLLC QCI). In this testbed, the metric is **End-to-End ICMP RTT** measured between VM-5 namespace `ue2` and EXT-DN `192.168.70.145`. The $20.0\text{ ms}$ threshold is a calibrated end-to-end research SLA accounting for virtualization overhead, Linux network scheduling, and RFsim socket loopback transit.

### 4.2 Quantitative Performance Metrics
1. **SLA Violation Ratio ($V_s$):**
   $$V_s = \frac{1}{T} \sum_{t=1}^T \mathbb{I}\left(\text{SLA}_{\text{eMBB}}(t) = \text{Violated} \lor \text{SLA}_{\text{URLLC}}(t) = \text{Violated}\right) \times 100\%$$
   Where $T$ is total scenario duration and $\mathbb{I}(\cdot)$ is the indicator function.
2. **SLA Recovery Time ($T_{\text{rec}}$):**
   $$T_{\text{rec}} = t_{\text{restored}} - t_{\text{violation}}$$
   Measured from the timestamp of first SLA violation onset ($t_{\text{violation}}$) following fault injection until both slice SLAs return to compliance and remain continuously compliant for a **consecutive stability window of $W_{\text{stab}} \ge 10\text{ seconds}$**. Runs where SLA fails to recover within the experiment duration are explicitly recorded and reported as **Unrecovered** ($T_{\text{rec}} = \text{Unrecovered} \ (|T_{\text{exp}} - t_{\text{violation}}|)$), rather than omitted.
3. **Wrong-Domain Actuation Ratio ($W_{\text{act}}$):**
   Evaluated under two formal denominators depending on evaluation objective:
   * *Per-Action Precision:* $W_{\text{act,action}} = \frac{N_{\text{wrong}}}{N_{\text{total\_actions}}}$ (evaluates whether dispatched actions match ground-truth bottleneck domain).
   * *Per-Window Policy Recall:* $W_{\text{act,window}} = \frac{N_{\text{wrong\_actions}} + N_{\text{missed\_interventions}}}{N_{\text{fault\_windows}}}$ (evaluates end-to-end intervention timeliness across all fault windows).
4. **Action Churn Rate ($C_{\text{act}}$):**
   The frequency of reversing or oscillating control actions (e.g., Cell-1 $\to$ Cell-2 $\to$ Cell-1) per observation epoch, disaggregated into Radio Handover Churn and Core Shaping Churn.

### 4.3 Statistical Significance Testing
All baseline comparisons are executed across a minimum of $N \ge 10$ independent random-seeded runs per scenario. Performance differences are evaluated using the non-parametric **Wilcoxon Signed-Rank Test** (paired) or **Mann-Whitney U Test** (independent) with a significance threshold of $\alpha = 0.05$.
