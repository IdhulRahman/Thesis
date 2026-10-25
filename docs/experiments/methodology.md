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
   * **Offered Load vs. Receiver Goodput Demarcation:** In the recorded 40-column CSV dataset, `e2e_slice1_tput_mbps` strictly measures the client-side offered transmission rate ($T_{\text{offered}}$) generated by `iperf3 -u` at VM-5 (`ue1`). True eMBB user-plane goodput ($T_{\text{goodput}}$) is measured at the receiver endpoint (EXT-DN). In intervals where receiver-side logs (`/opt/oran/5gc/ext-dn/iperf_server.log`) are uningested, **eMBB goodput SLA cannot be conclusively evaluated** and is categorized as **`Unmeasured / Pending Receiver Evidence`**.
   * **Conditional Joint SLA & Recovery Scope:** Because eMBB goodput SLA evaluation is pending receiver log cross-validation, the evaluation of Joint SLA Violation Ratio ($V_{s,\text{joint}}$) and Two-Slice Recovery Time ($T_{\text{rec}}$) is conditional on the availability of verified receiver goodput evidence. When evaluations are restricted strictly to the streaming 40-column CSV, SLA evaluation is performed unambiguously on Slice 2 (URLLC), while eMBB compliance is reported as unmeasured goodput.
   * **SLA Threshold (When Receiver Data Available):** Under saturation stress (offered load $\ge 25\text{ Mbps}$), Slice 1 SLA requires receiver goodput $T_{\text{goodput}} \ge 20.0\text{ Mbps}$ (or $\ge 85\%$ of offered demand when operating below capacity).
2. **Slice 2 (URLLC) SLA Contract:**
   * **End-to-End Latency Target:** Canary ICMP round-trip time $RTT \le 20.0\text{ ms}$ and sequence loss percentage $\le 1.0\%$.
   * **Scope & Standards Demarcation:** 3GPP TS 23.501 Table 5.7.4-1 defines standard Packet Delay Budget (PDB) as a delay bound across the **one-way UE–UPF segment terminating at the N6 reference point** according to specific standardized 5QI values (e.g., 5QI 82 = 10 ms, 5QI 83 = 10 ms, 5QI 84 = 30 ms, 5QI 85 = 5 ms for delay-critical GBR). Standard PDB is an endpoint-to-endpoint delay bound, distinct from end-to-end round-trip latency to an external Data Network (DN). In this testbed, the metric is **End-to-End ICMP RTT** measured between VM-5 namespace `ue2` and EXT-DN `192.168.70.145`. The $20.0\text{ ms}$ threshold is a research evaluation choice accounting for virtualization overhead, Linux network scheduling, and virtual RFsim socket loopbacks.

### 4.2 Quantitative Performance Metrics

1. **Window Evaluation States & Coverage:**
   During offline analysis, each observation window $k$ is categorized into one of three mutually exclusive measurement states:
   * **`Compliant`:** Telemetry pipeline is healthy (`scrape_ok = 1`, `e2e_probe_freshness = 1`) and valid probe measurements satisfy the SLA bound ($RTT \le 20.0\text{ ms}$, loss $\le 1.0\%$).
   * **`Violated`:** Telemetry evidence confirms probe transmission but delivery failed or degraded (e.g., echo request sequence sent with observed loss $> 1.0\%$ or timeout, while scrape and collector pipeline remained operational with `scrape_ok = 1`).
   * **`Unknown / Unmeasured`:** Telemetry observation pipeline failed or probe evidence is absent (e.g., scrape failed `scrape_ok = 0`, collector daemon halted, or `rtt = NaN` without active sequence counter advancement).
   
   To maintain empirical rigor, every SLA evaluation must explicitly report **Measurement Coverage**:
   $$\text{Coverage}_i = \frac{K_{\text{measured},i}}{K_{\text{total}}} \times 100\%, \quad \text{where } K_{\text{measured},i} = K_{\text{compliant},i} + K_{\text{violated},i}$$
   Windows scored as `Unknown / Unmeasured` are excluded from the denominator $K_{\text{measured},i}$ rather than assumed compliant or penalized as outages.

2. **Per-Slice SLA Violation Ratio ($V_{s,i}$):**
   Evaluates SLA compliance strictly over verified measured windows:
   $$V_{s,\text{URLLC}} = \frac{K_{\text{violated},\text{URLLC}}}{K_{\text{measured},\text{URLLC}}} \times 100\%$$
   *(eMBB violation ratio $V_{s,\text{eMBB}}$ is reported when receiver-side goodput logs are available; otherwise designated as Unmeasured).*

3. **Joint SLA Violation Ratio ($V_{s,\text{joint}}$):**
   Evaluates multi-slice system degradation over windows where both slices have valid measurement evidence:
   $$V_{s,\text{joint}} = \frac{1}{K_{\text{joint\_measured}}} \sum_{k=1}^{K_{\text{joint\_measured}}} \mathbb{I}\left(\text{SLA}_{\text{eMBB}}(k) = \text{Violated} \lor \text{SLA}_{\text{URLLC}}(k) = \text{Violated}\right) \times 100\%$$

4. **Wrong-Domain Action Ratio ($W_{\text{act}}$):**
   $$W_{\text{act}} = \frac{N_{\text{wrong}}}{N_{\text{total\_actions}}} \times 100\%$$
   Measures the proportion of dispatched control actions targeted at the incorrect domain (e.g., executing radio cell handover when the bottleneck resides in the UPF transport queue, or applying core shaping when the bottleneck is radio attenuation).

5. **Per-Window Policy Recall ($R_{\text{window}}$):**
   $$R_{\text{window}} = \frac{N_{\text{windows with correct intervention}}}{N_{\text{fault windows requiring intervention}}} \times 100\%$$
   Measures the proportion of fault windows requiring intervention that successfully receive a timely, correct-domain control action.
   * *Multi-Action Windows:* If a fault window receives multiple conflicting actions (e.g., a correct radio action accompanied by an erroneous core throttling action, or rapid oscillating commands), the window is scored as **failed / non-compliant ($0$)** to penalize control ambiguity.
   * *No-Action Windows:* A fault window with zero dispatched actions ($N_{\text{actions}} = 0$) is scored as a **missed intervention ($0$)**.
   * *Normal Windows:* Windows under normal operating conditions where no fault is injected are excluded from the denominator.

6. **SLA Recovery Time ($T_{\text{rec}}$):**
   $$T_{\text{rec}} = t_{\text{restored}} - t_{\text{violation}}$$
   Measured from the timestamp of first SLA violation onset ($t_{\text{violation}}$) following fault injection until slice SLAs return to compliance and remain continuously compliant for a **consecutive stability window of $W_{\text{stab}} \ge 10\text{ seconds}$**. Runs where SLA fails to recover within the experiment duration are explicitly recorded and reported as **Unrecovered** ($T_{\text{rec}} = \text{Unrecovered} \ (|T_{\text{exp}} - t_{\text{violation}}|)$), rather than omitted. *(Multi-slice recovery requires verified receiver goodput evidence for eMBB; when evaluating URLLC only, reported as $T_{\text{rec,URLLC}}$).*

7. **Action Churn Rate ($C_{\text{act}}$):**
   The frequency of reversing or oscillating control actions (e.g., Cell-1 $\to$ Cell-2 $\to$ Cell-1) per observation epoch, disaggregated into Radio Handover Churn and Core Shaping Churn.

### 4.3 Statistical Significance Testing
All baseline comparisons are executed across a minimum of $N \ge 10$ independent random-seeded runs per scenario. Performance differences are evaluated using the non-parametric **Wilcoxon Signed-Rank Test** (paired) or **Mann-Whitney U Test** (independent) with a significance threshold of $\alpha = 0.05$.
