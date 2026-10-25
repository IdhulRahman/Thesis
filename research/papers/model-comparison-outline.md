# Draft Paper Framework & Model Comparative Study

**Working Title:**  
*Evaluating the Impact of rApp Sequential Forecasting Models on Cross-Domain Bottleneck Diagnosis and Closed-Loop SLA Recovery in O-RAN Multi-Slice Networks*  

---

## 1. Executive Summary & Research Positioning

### 1.1 The Core Scientific Question
> **Research Question (RQ):**  
> *Does a higher forecasting accuracy (lower per-feature MAE/RMSE) in Non-RT RIC rApp necessarily translate into improved cross-domain bottleneck localization, fewer wrong-domain actuations, and faster SLA recovery in multi-slice 5G networks, or does a lightweight model offer a more favorable trade-off between inference latency and closed-loop control stability?*

### 1.2 Novelty Positioning vs. State of the Art (SOTA) & Standards
While existing literature and ETSI standards (e.g., ETSI TR 104 037 on Non-RT RIC analytics exchange with 5G Core/NWDAF) discuss architectural interfaces between RIC and Core, they leave open the critical operational trade-off: **how predictive model fidelity directly governs cross-domain closed-loop actuation accuracy and stability**.

| Research Dimension | Existing SOTA (e.g., Digital Twin 2025, Slice-on-the-Fly) | Our Proposed Framework |
|---|---|---|
| **Scope of ML** | Standalone traffic / PRB forecasting | Multi-tier pipeline: Forecasting $\rightarrow$ Diagnosis $\rightarrow$ Closed-Loop Action $\rightarrow$ SLA Recovery |
| **Inference Location** | Standalone Python server or Near-RT xApp | **Locked at Non-RT RIC rApp** (multi-timescale slow loop $\ge 1\text{ s}$) |
| **Baseline Rigor** | Isolated complex models without simple baselines | **Persistence Baseline ($\hat{X}(t+H)=X(t)$)** for forecasting; **Reactive Thresholding (M0)** for control |
| **Evaluation Metrics** | Isolated ML metrics (MAE, RMSE, parameter counts) | **Multi-Tier KPIs:** Per-feature MAE/RMSE, Macro-F1, Wrong-Domain Action Rate ($W_{act}$), SLA Violation Rate ($V_s$), Recovery Time ($T_{rec}$), Action Churn ($C_{act}$) |
| **Cross-Domain Scope** | RAN-only (PRB/RSRP) | **Joint RAN (E2 KPM) + 5G Core (UPF Kernel Qdisc & 3GPP NWDAF Rel-17)** |
| **Testbed Nature** | Pure simulation (ns-3) or uncalibrated physical | **6-VM Virtualized/Emulated Testbed** with calibrated empirical radio capacity ($C_{ran}^{UL} \approx 28.4\text{ Mbps}$) |

### 1.3 Core Observability Scope, Standards Demarcation & Regulatory Context
To maintain rigorous academic honesty, avoid overclaiming, and clarify standardization vs. regulatory domains:
> *"The OAI NWDAF analytics endpoint on the testbed responds to NETWORK_PERFORMANCE requests indicating that the required data is not available. The underlying cause remains subject to confirmation via log and datastore inspection. To provide core observability, we employ a dedicated telemetry adapter that reads UPF interface counters and queue statistics. These adapter metrics are utilized in the rApp experiments. The adapter is not claimed as a standardized DCCF implementation, and its data integration with NWDAF analytics services requires separate validation."*

1. **Regulatory Governance vs. Technical Standardization Bodies:**
   - **Government Regulatory Authority (e.g., Kementerian Kominfo RI / Ditjen SDPPI):** Governs legally binding RF spectrum allocation, EIRP power radiation limits, and customer privacy protection (UU No. 36/1999). Our testbed operates in a fully enclosed, software-emulated multi-VM virtual RF environment without open public electromagnetic radiation, ensuring full compliance with national spectrum licensing regulations.
   - **Technical Standardization Consortia (3GPP & ETSI):** Define consensus engineering specifications, Performance Management (PM) architectures, and service interfaces.
2. **Telemetry Performance Management Principles (3GPP TS 32.401 & TS 28.552):**
   - OAI NWDAF v2.1.0 natively covers control plane signaling analytics (`NETWORK_PERFORMANCE` for PDU session and UE counts from AMF/SMF event exposure, with relative ratios hardcoded to `0` with `//TODO` comments).
   - Real-time user-plane queue statistics from the C-based UPF are collected via a host telemetry adapter (`core_adapter.py` v9) following standardized 3GPP PM classifications:
     - **Cumulative Counters:** `upf_tx_bytes_total`, `upf_rx_bytes_total`, `upf_packet_drops_total` (TS 32.401).
     - **Instantaneous Gauge:** `upf_queue_backlog_bytes` (instantaneous buffer occupancy).
     - **Derived Rates:** `upf_interface_tx_mbps`, `upf_interface_rx_mbps`, `upf_packet_drops_delta` (computed over monotonic $\Delta t$).
   - A 1-second sampling cadence is selected specifically for the Non-RT RIC rApp closed-loop control requirement on the testbed, distinguished from 5–15 minute periodic OAM reporting.
   - The deep learning forecasting models (MLP, LSTM, GRU) are trained directly on **raw physical metrics**, while composite congestion scores remain strictly documented as optional research heuristics.

---

## 2. Experimental Model Candidates & Forecasting Baselines

To ensure fair scientific evaluation, all candidates receive **identical historical information**:
- **Recurrent Candidates (LSTM, GRU):** Ingest input tensor of shape $(T_{obs}, F)$.
- **Feedforward Candidate (MLP):** Ingests flattened tensor of shape $(T_{obs} \times F)$, ensuring identical historical context.
- **Persistence Baseline:** Predicts $\hat{X}(t+H) = X(t)$ without parametric learning to verify whether deep learning adds operational value.
- **Reactive Control Baseline (M0):** Operates on instantaneous observation $X(t)$ via static thresholding (evaluated strictly in Control Stage, not in MAE forecasting).

| Candidate ID | Model Architecture | Role in Comparison | Input Representation | Implementation Note |
|---|---|---|---|---|
| **Base-P** | **Persistence Baseline** | Naive Forecasting Baseline | $\hat{X}(t+H) = X(t)$ | Zero-parameter benchmark. Verifies DL utility. |
| **M0** | **Reactive Heuristic** | Control Baseline (No Forecast) | Instantaneous $X(t)$ | Static thresholding. Excluded from forecasting MAE. |
| **M1** | **Multilayer Perceptron (MLP)** | Non-Recurrent Neural Baseline | Flattened vector $\in \mathbb{R}^{T_{obs} \times F}$ | Dense feedforward network with ReLU & Dropout. |
| **M2** | **Long Short-Term Memory (LSTM)** | Benchmark Recurrent Candidate | Sequential tensor $\in \mathbb{R}^{T_{obs} \times F}$ | 3-gate recurrent architecture (Input, Forget, Output). |
| **M3** | **Gated Recurrent Unit (GRU)** | Candidate Recurrent Model | Sequential tensor $\in \mathbb{R}^{T_{obs} \times F}$ | 2-gate recurrent architecture (Reset, Update). |

> *Note on Neutrality:* No model is pre-declared as the preferred winner. The comparison empirically determines whether recurrent gating justifies its computational and parameter overhead over MLP or Persistence.

---

## 3. Four-Stage Comparative Study Design

The evaluation is structured into four sequential, hypothesis-driven comparative stages:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STAGE A: FORECASTING FIDELITY & FOOTPRINT                 │
│   Candidates: Persistence, MLP, LSTM, GRU                                    │
│   Metrics: Per-feature MAE & RMSE, p95 Inference Latency, Params, RSS Memory │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STAGE B: BOTTLENECK DIAGNOSTIC LOCALIZATION               │
│   Input: Forecast state X_hat(t+H) fed into identical diagnostic engine      │
│   Classes: {NORMAL (0), RAN (1), CORE (2), JOINT (3)}                        │
│   Metrics: Macro-F1, Per-class Precision/Recall, 4x4 Confusion Matrix        │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STAGE C: CLOSED-LOOP SLA RECOVERY & ACTION STABILITY      │
│   Comparison: Reactive (M0) vs. Predictive Control (MLP, LSTM, GRU)          │
│   Metrics: SLA Violation Rate (V_s), Recovery Time (T_rec),                   │
│            Wrong-Domain Action Rate (W_act), Handover Churn, Core Churn      │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STAGE D: CROSS-DOMAIN INFORMATION ABLATION                │
│   Configurations: RAN-only vs. Core-only vs. Joint RAN+Core (selected model) │
│   Purpose: Empirically evaluate the contribution of cross-domain RIC-NWDAF telemetry │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Multi-Tier Evaluation Metrics Formulation

To prevent conflating disparate units, all errors are computed and reported in their authentic physical dimensions:

### Tier 1: Machine Learning & Computational Metrics
1. **Per-Feature Mean Absolute Error ($\text{MAE}_f$) and RMSE ($\text{RMSE}_f$):**
   $$\text{MAE}_f = \frac{1}{N} \sum_{i=1}^{N} |x_{f}^{(i)} - \hat{x}_{f}^{(i)}|, \quad \text{reported in: } [\% \text{ PRB}, \text{Bytes backlog}, \text{Mbps throughput}, \dots]$$
2. **Inference Latency ($L_{inf}$):** 95th-percentile execution latency of `model.predict()` in milliseconds ($<10\text{ ms}$ target on rApp).
3. **Computational Footprint:** Parameter count, floating-point operations (FLOPs), and Resident Set Size (RSS in MB).

### Tier 2: Diagnostic Localization Metrics
1. **Macro-Averaged F1 Score:**
   $$\text{Macro-F1} = \frac{1}{|C|} \sum_{c \in C} \frac{2 \cdot P_c \cdot R_c}{P_c + R_c}, \quad C = \{\text{NORMAL}, \text{RAN}, \text{CORE}, \text{JOINT}\}$$
2. **Per-Class Precision ($P_c$) & Recall ($R_c$):** Explicitly tracking cross-domain confusion (e.g., misclassifying Core congestion as RAN).
3. **Diagnostic Lead Time / Latency ($T_{det}$):** Time elapsed between physical fault onset and correct state classification.

### Tier 3: Closed-Loop Network System Metrics
1. **Wrong-Domain Action Ratio ($W_{act}$):**
   $$W_{act} = \frac{N_{\text{wrong}}}{N_{\text{total\_actions}}} \times 100\%$$
   Measures the proportion of dispatched control actions targeted at the incorrect domain (action-level domain fidelity).
2. **Per-Window Policy Recall ($R_{window}$):**
   $$R_{window} = \frac{N_{\text{windows with correct intervention}}}{N_{\text{fault windows requiring intervention}}} \times 100\%$$
   Evaluates the proportion of fault windows requiring intervention that successfully receive a timely, correct-domain control action. A window receiving conflicting actions (e.g., correct radio action plus erroneous core throttling) is scored as non-compliant ($0$) to penalize control ambiguity. A fault window with zero dispatched actions is scored as a missed intervention ($0$). Normal non-fault windows are excluded from the denominator.
3. **Window Evaluation States & Coverage:**
   Offline evaluation classifies each window into **`Compliant`** (healthy scrape and SLA met), **`Violated`** (verified probe delivery failure, loss $> 1.0\%$, or active timeout), or **`Unknown / Unmeasured`** (scrape failed, daemon stalled, or telemetry pipeline unmeasured). Every KPI report must explicitly include **Measurement Coverage**:
   $$\text{Coverage}_i = \frac{K_{\text{measured},i}}{K_{\text{total}}} \times 100\%, \quad K_{\text{measured},i} = K_{\text{compliant},i} + K_{\text{violated},i}$$
4. **Per-Slice SLA Violation Ratio ($V_{s,i}$):**
   $$V_{s,\text{URLLC}} = \frac{K_{\text{violated},\text{URLLC}}}{K_{\text{measured},\text{URLLC}}} \times 100\%$$
   Where URLLC SLA requires $RTT \le 20.0\text{ ms}$ and loss $\le 1.0\%$. *(Note: `e2e_slice1_tput_mbps` strictly measures sender-side offered rate; eMBB goodput SLA cannot be evaluated on CSV data alone and is reported as Unmeasured pending receiver goodput logs from EXT-DN).*
5. **Joint SLA Violation Ratio ($V_{s,\text{joint}}$):**
   $$V_{s,\text{joint}} = \frac{1}{K_{\text{joint\_measured}}} \sum_{k=1}^{K_{\text{joint\_measured}}} \mathbb{I}\left(\text{SLA}_{\text{eMBB}}(k) = \text{Violated} \lor \text{SLA}_{\text{URLLC}}(k) = \text{Violated}\right) \times 100\%$$
   Evaluated strictly over windows where verified receiver goodput evidence is available for eMBB alongside URLLC probe evidence.
6. **SLA Recovery Time ($T_{rec}$):**
   $$T_{rec} = t_{\text{restored}} - t_{\text{violation}}$$
   Elapsed time from first SLA violation onset following fault injection until slice SLAs return and remain continuously compliant for a **consecutive stability window of $W_{\text{stab}} \ge 10\text{ seconds}$**. Runs where SLA fails to recover within the experiment duration are explicitly recorded and reported as **Unrecovered** ($T_{rec} = \text{Unrecovered} \ (|T_{\text{exp}} - t_{\text{violation}}|)$), rather than omitted. Multi-slice recovery is conditional on receiver goodput availability; when evaluating URLLC only, reported as $T_{rec,\text{URLLC}}$.
7. **Action Churn ($C_{act}$):**
   The frequency of reversing or oscillating control actions per observation epoch, disaggregated into **Radio Handover Churn** (handovers per minute) and **Core Shaping Churn** (rate policy alterations per minute) to isolate control instability.

---

## 5. Controlled Fault Injection Scenarios & Physical Ground Truth

Experiments run on the **6-VM virtualized/emulated testbed** with verified physical constraints ($C_{ran}^{UL} \approx 28.4\text{ Mbps}$):

| Scenario ID | Injected Fault Mechanism | Target Component | Ground Truth Label | Ideal Closed-Loop Action |
|---|---|---|---|---|
| **S1** | Normal Light Load (10 Mbps $\approx 35\% C_{ran}^{UL}$) | None (Baseline) | `NORMAL` | No action (Maintain current binding) |
| **S2** | Normal High Load (22 Mbps $\approx 80\% C_{ran}^{UL}$) | None (High Healthy) | `NORMAL` | No action (Zero Churn) |
| **S3** | Radio Uplink Overload (40 Mbps $> 140\% C_{ran}^{UL}$) | DU-1 Cell-1 | `RAN_BOTTLENECK` | Inter-cell steering of UE to Cell-2 |
| **S6** | Core Queue Limitation (`tbf rate 12mbit burst 32k latency 200ms`) | UPF-1 (Slice-1) | `CORE_BOTTLENECK` | Radio handover **prohibited**; Core traffic shaping applied |
| **S9** | Radio Overload (40M) + Core Limit (12M TBF) | Cell-1 + UPF-1 | `JOINT_BOTTLENECK` | Coordinated inter-cell steering + user-plane shaping |
| **S10** | Stepwise Decoupling: Phase 1 (Joint) $\rightarrow$ Phase 2 (Core only) $\rightarrow$ Drain | Cell-1 $\rightarrow$ UPF-1 | Multi-phase | Decoupled sequential action and restoration |

---

## 6. Leakage-Free Dataset Partitioning Protocol

To satisfy rigorous machine learning standards (preventing artificial score inflation):
1. **Independent Run Separation:** The dataset consists of independent experimental runs (Run 1, Run 2, Run 3) recorded under randomized traffic sequences and varied fault durations.
2. **No Overlapping Window Leakage:** Data is partitioned at the **Run level** (e.g., Run 1 for Training, Run 2 for Validation, Run 3 for Testing). Under no circumstances are overlapping sliding windows randomly shuffled between splits.
3. **Isolated Preprocessing:** Feature scaling parameters (Min-Max/StandardScaler) and diagnostic thresholds are fitted **strictly on the Training Run** and frozen prior to evaluation on the Test Run.
4. **Timestamp Ground-Truth Alignment:**
   - Multi-step forecasting at $t+H$ is evaluated against ground truth at $t+H$.
   - Instantaneous diagnosis at $t$ is evaluated against ground truth at $t$.
   - Unforeseen step faults with zero precursor dynamics are reported with realistic lead-time limits.

---

## 7. Paper Section Outline

- **Section I: Introduction**
  - Multi-slicing challenges and domain silos between O-RAN Near-RT RIC and 5G Core.
  - The Core Question: Does forecasting accuracy translate into closed-loop SLA stability?
- **Section II: Related Work & Standards Context**
  - Traffic forecasting in O-RAN (MLP, LSTM, GRU).
  - Cross-domain coordination in ETSI TR 104 037 and 3GPP NWDAF Rel-17.
- **Section III: Testbed Architecture & Multi-Timescale Control**
  - 6-VM virtualized campus testbed topology.
  - Slow-loop Non-RT RIC rApp vs. Fast-loop Near-RT RIC xApp interaction.
- **Section IV: Multi-Tier Decision Pipeline**
  - Mathematical formulation of Candidates (Persistence, MLP, LSTM, GRU).
  - Diagnostic localization engine and custom A1 policy definition.
- **Section V: Experimental Evaluation & Comparative Results**
  - *Part A:* Forecasting fidelity (per-feature MAE/RMSE, inference latency, memory).
  - *Part B:* Diagnostic accuracy (Macro-F1, precision/recall, 4x4 confusion matrix).
  - *Part C:* Closed-loop network KPIs ($W_{act}$, $V_s$, $T_{rec}$, disaggregated churn).
  - *Part D:* Cross-domain ablation (RAN-only vs Core-only vs Joint telemetry).
- **Section VI: Discussion & Engineering Insights**
  - The accuracy-latency-stability Pareto frontier.
  - When deep sequential modeling provides genuine operational value over simple heuristics.
- **Section VII: Conclusion**
