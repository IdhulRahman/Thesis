# Experimental Evaluation Methodology & Baseline Framework

**Thesis Research Title:**  
*Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Scientific Framework & Research Hypotheses

The central scientific question investigated in this research is whether **diagnosing the architectural domain of a network bottleneck (RAN vs. Core User Plane vs. Joint) prior to triggering control actions can reduce SLA violations ($V_s$), shorten recovery time ($T_{\text{rec}}$), and mitigate action churn ($C_{\text{act}}$)** compared to single-domain or decoupled control paradigms.

### 1.1 Research Hypotheses & Evaluation Questions
1. **$H_1$ (Dynamic Steering vs. Static Baseline):** Closed-loop dynamic steering is hypothesized to achieve lower SLA violation rates than static default slicing (B0) during radio degradation and core transport queuing.
2. **$H_2$ (Domain-Aware Action Selection):** Cross-domain coordination is hypothesized to achieve a lower wrong-domain actuation ratio ($W_{\text{act}}$) and reduce handover oscillation compared to single-domain RAN-only (B1) or Core-only (B2) controllers.
3. **$H_3$ (Multi-Timescale Coordination Stability):** Hierarchical coordination between a Non-RT RIC rApp (slow loop) and Near-RT RIC xApp (fast loop) is hypothesized to reduce conflicting control actions and action churn compared to uncoordinated, decoupled controllers (B3).

---

## 2. Comparative Baseline Matrix (B0 through B4 vs. Proposed)

To evaluate these hypotheses, the experimental testbed defines **five comparative baselines (B0 to B4)** alongside the **Proposed System**:

| Paradigm Tier | Baseline ID | Control Approach | Domain Awareness | Coordination Model |
|---|---|---|---|---|
| **Static Default** | **B0** | Standard 3GPP A3 Handover | Local Radio RSRP only | No RIC coordination |
| **Single-Domain** | **B1** & **B2** | Standalone xApp / Core Shaper | Isolated to RAN or Core | Single-domain visibility (RAN or Core only) |
| **Decoupled** | **B3** | Uncoordinated Dual Controllers | Both domains active | Independent uncoordinated actuation |
| **Fixed-Sequence Coordination** | **B4** | Fixed Priority Heuristic | Cross-domain aggregated | Static action sequence without root-cause diagnosis |
| **Proposed System** | **PROPOSED** | Closed-Loop MAPE-K Coordination | Cross-domain correlated | Root-cause matched steering & verification |

| Baseline ID | Control Paradigm | Decision Inputs | Actuation Mechanisms | Hypothesized Limitation / Evaluation Risk |
|---|---|---|---|---|
| **B0** | **Static 3GPP Baseline** | RSRP only (Standard A3 Event) | Autonomous gNB Handover | Operates without Core congestion visibility; does not provide dynamic slice traffic steering. |
| **B1** | **RAN-Only Control** | Radio scheduler metrics (PRB, SNR, MCS) | Inter-cell steering via Near-RT xApp | **Evaluated for Core-Blind Steering Risk:** Under Core UPF bottlenecks, risks executing unneeded inter-cell handovers or triggering handover churn without mitigating core queue saturation. |
| **B2** | **Core-Only Control** | Core telemetry (UPF queue, packet drops) | Linux `tc qdisc` rate shaping | **Evaluated for Radio-Blind Risk:** Cannot leverage alternative radio cells or radio scheduling adaptations when bottleneck originates in radio channel degradation. |
| **B3** | **Decoupled Controllers** | Both domains monitored independently | Independent xApp & Core adapters | **Evaluated for Actuation Conflict Risk:** Independent controllers risk issuing simultaneous, unaligned control actions without cross-domain arbitration, evaluated for potential SLA instability. |
| **B4** | **Fixed-Sequence Coordination** | Aggregated cross-domain telemetry | Fixed action sequence (e.g., Handover $\to$ Shape) | **Evaluated for Sequence Mismatch Risk:** Executes a predefined action sequence regardless of diagnosed root cause, evaluated for recovery delays when the initial action does not target the active bottleneck domain. |
| **PROPOSED** | **Bottleneck-Aware Closed-Loop** | Correlated RAN + Core Telemetry | Matched Action (RAN / Core / Joint) + SLA Verify | **Targeted Domain Matching & Stability Verification:** Selects actions matched to the diagnosed bottleneck domain (inter-cell radio steering for RAN, egress shaping for Core, or staged mitigation for Joint) and verifies SLA restoration over stability window $W_{\text{stab}}$ before admitting new actions. |

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

---

### 4.4 Testbed Execution Timing & RFSimulator Channel Modeling Calibration

#### 4.4.1 Radio Clock Progress vs. Wall-Clock Alignment
In virtualized OAI RFSimulator testbeds, radio frame scheduling adheres strictly to 3GPP TS 38.211 ($10\text{ ms}$ per radio frame). However, software simulator execution speed varies relative to host wall-clock time depending on PHY-layer computational intensity:
* **Computational Dilation Under Active Channel Modeling:** In our experimental testbed at 106 PRBs (Band 78, Numerology 1, SCS 30 kHz), active channel modeling (`options = ("chanmod");`) was empirically localized as the primary computational constraint, reducing radio progress to $\approx 0.42\times - 0.44\times$ real-time. Per-sample calculations in `apply_channelmod.c` (such as `gaussZiggurat()` noise calls and multipath matrix convolutions) serve as primary candidates for detailed profiling. This artificial time dilation limits the rate at which wall-clock application packets can be consumed by the radio stack to $\approx 13 - 14\text{ Mbps}$, inducing secondary bufferbloat and cross-instance scheduling contention.
* **Real-Time Baseline Alignment:** Deactivating `chanmod` on DU-1 (`options = ();`) verified operation near real-time ($\approx 0.91\times - 1.08\times$ during load) for the evaluated dual-slice 20 Mbps session, completing in $20.03\text{ s}$ receiver reporting duration with $0\%$ receiver-reported UDP packet loss (see [Case 55](../troubleshooting/ran-ue.md#case-55)).

#### 4.4.2 RAN Telemetry Metric Dynamics & Machine Learning Considerations
A primary evaluation goal of this thesis is benchmarking machine learning algorithms (e.g., NWDAF AnLF and Near-RT RIC xApps) for **Root Cause Analysis (RCA) and Bottleneck Domain Localization** (RAN vs. Core vs. Joint):
* **Channel Metric Dynamics & Shortcut Learning Risks:** Operating without active channel modeling reduces error rates and stabilizes channel metrics (testbed traces show MCS adapting to link state and CQI occasionally reporting N/A). When evaluated for bottleneck classification, a lack of radio channel variance poses an experimental risk of shortcut learning, where an ML model might disproportionately rely on dynamic Core telemetry while under-utilizing radio features. This represents a research risk to be systematically evaluated during offline training rather than a foregone conclusion based purely on feature counts.
* **Disaggregating Saturation from Coverage Degradation:** Realistic bottleneck detection requires distinguishing between:
  1. **Radio Resource Saturation:** High PRB demand under clean channel conditions (high MCS, minimal BLER).
  2. **Channel Coverage Degradation:** Low/moderate PRB demand accompanied by poor radio channel conditions (declining SNR $\to$ link adaptation drops MCS $\to$ BLER escalates $\to$ RLC retransmissions surge).
  Dynamic channel metrics (BLER, MCS, CQI, SNR) are required to realistically represent coverage degradation states in the training dataset.

#### 4.4.3 Calibrated Operational Profiles & Empirical Resolution Roadmap
To balance computational stability with metric richness for machine learning, our experimental campaign empirically evaluated three operational profiles (see [Case 55](../troubleshooting/ran-ue.md#case-55) and [Case 56](../troubleshooting/ran-ue.md#case-56)):
1. **Profile 1: Calibrated Real-Time Slicing Profile (51 PRB + `-E` + `chanmod` Active — Recommended):**
   * **PHY Parameterization:** Band 78 ($\mu = 1$, SCS 30 kHz), Point A ARFCN `639996` ($3599.94\text{ MHz}$), SSB ARFCN `640704` ($3610.56\text{ MHz}$), BWP RIV `13750` ($51\text{ PRB}$), nrUE center frequency $3609.12\text{ MHz}$ (`3609120000`).
   * **Sampling & Transform:** Three-quarter sampling (`-E`) reduces FFT size to 768 ($23.04\text{ Msps}$ per `get_samplerate_and_bw()` in OAI `nr_common.c`), cutting sample volume by $50\%$ relative to 106 PRB `-E` and $62.5\%$ relative to unscaled full sampling.
   * **Runtime Performance:** Sustains **$1.05\times - 1.09\times$ real-time radio progress** under full load with software channel modeling active (`ploss_dB = 0.0`, `noise_power_dB = -100.0`). Physical uplink capacity is bounded at **$16.6\text{ Mbps}$** by TDD slot allocations (2 UL slots per 5 ms), allowing healthy multi-slice traffic at 5, 10, and 15 Mbps with zero queuing delay ($+0.05\text{ s}$ duration delta) and clean buffer backlog accumulation at 20 Mbps ($12.45\text{ s}$ queue drainage).
2. **Profile 2: Full-Bandwidth Wire-Speed Baseline (106 PRB, no `-E`, `options = ();`):**
   * Disables software channel modeling overhead to evaluate physical upper-bound throughput at $20.0\text{ Mbps}$ line-rate ($20.03\text{ s}$ receiver duration, SFN ratio $\approx 1.02\times$).
3. **Profile 3: Historical Full-Bandwidth Impairment Reference (106 PRB + `chanmod`, no `-E`):**
   * Retained as a documented historical benchmark demonstrating the $0.44\times$ clock dilation ceiling ($\approx 13\text{ Mbps}$ wall-clock absorption limit).

