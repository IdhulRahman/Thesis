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
3. **Derivative vs. Cumulative Features:** Cumulative counters (`nwdaf_comm_ul_bytes`, `upf_tx_bytes_total`) are converted to first-order derivatives ($\Delta \text{bytes} / \Delta t$) before inference.
4. **Decoupling Freshness from Values:** Telemetry freshness flags (`e2e_probe_freshness`, `nwdaf_comm_freshness`) are evaluated as validity masks: when freshness is `0`, dependent telemetry is marked stale.

---

## 4. Evaluation Metrics & Statistical Validation

### 4.1 Quantitative Performance Metrics
1. **SLA Violation Ratio ($V_s$):**
   $$V_s = \frac{1}{T} \sum_{t=1}^T \mathbb{I}\left(R_t > R_{\text{thresh}} \lor L_t > L_{\text{thresh}}\right)$$
   Where $R_t$ is canary RTT, $L_t$ is packet loss, and $\mathbb{I}(\cdot)$ is the indicator function.
2. **Mean Time to Recovery ($T_{\text{rec}}$):**
   The elapsed time from fault injection ($t_{\text{fault}}$) until SLA metrics return and remain within acceptable bounds for $\ge 10$ consecutive seconds.
3. **Action Churn Rate ($C_{\text{act}}$):**
   The frequency of conflicting or reversing actuations (e.g., Cell-1 $\to$ Cell-2 followed immediately by Cell-2 $\to$ Cell-1) within an observation window.
4. **Wrong-Domain Actuation Ratio ($W_{\text{act}}$):**
   $$W_{\text{act}} = \frac{N_{\text{wrong}}}{N_{\text{total\_actions}}}$$
   Evaluates how frequently a RAN handover is triggered during a Core bottleneck, or vice versa.

### 4.2 Statistical Significance Testing
All baseline comparisons are executed across a minimum of $N \ge 10$ independent random-seeded runs per scenario. Performance differences are evaluated using the non-parametric **Wilcoxon Signed-Rank Test** (paired) or **Mann-Whitney U Test** (independent) with a significance threshold of $\alpha = 0.05$.
