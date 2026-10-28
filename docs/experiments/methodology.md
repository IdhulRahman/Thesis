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

### 4.4 Testbed Execution Timing & RFSimulator Channel Modeling Specification

#### 4.4.1 RFSimulator Channel Modeling Architecture (`chanmod`) & Research Rationale
In virtualized 5G experimentation, OpenAirInterface RFSimulator provides two distinct operational modes:
* **Ideal Propagation Mode (`options = ();`):** By default, RFSimulator behaves as an ideal, distortion-free communication medium ("pure pipe") without signal path loss, thermal noise, Doppler shift, or multipath fading.
* **Realistic Propagation Mode (`options = ("chanmod");`):** Activating software channel modeling introduces physical wireless propagation characteristics, dynamically calculating large-scale path loss (`ploss_dB`), thermal noise floor (`noise_power_dB`), and multi-tap Rayleigh/Rician fading matrices.

**Critical Necessity for Machine Learning / NWDAF Telemetry:**
In this thesis research, dynamic channel modeling is fundamental for training explainable Machine Learning classifiers (NWDAF AnLF and Near-RT RIC xApps). Under an ideal channel, radio telemetry is sterile and invariant:
* Block Error Rate (BLER) remains identically $0.0\%$.
* Modulation and Coding Scheme (MCS) is locked permanently at the highest index (MCS 28).
* Channel Quality Indicator (CQI) remains pegged at 15.

Without radio variance, machine learning models exhibit **shortcut learning**, relying disproportionately on Core UPF queue metrics and failing to differentiate between:
1. **Radio Resource Saturation (Congestion Bottleneck):** High PRB demand under pristine channel conditions (high SNR $> 25\text{ dB}$, high MCS 28, minimal BLER).
2. **Channel Coverage Degradation (Radio Impairment Bottleneck):** Moderate PRB demand accompanied by degrading link conditions (falling SNR $\to$ link adaptation drops MCS $\to$ BLER escalates $\to$ RLC retransmissions surge).

**Computational Bottleneck Analysis in Source Code:**
Inspection of OAI source code (commit [`29d5fa7d`](https://github.com/OPENAIRINTERFACE/openairinterface5g/tree/29d5fa7d38bb1ee8935ef7ae30a396d53772ea4f), file `radio/rfsimulator/apply_channelmod.c` at `rxAddInput()`):
```c
// Invoked 2x per I/Q sample across all subcarriers and antenna ports
out_ptr->r += ... + noise_per_sample * gaussZiggurat(0.0, 1.0);
out_ptr->i += ... + noise_per_sample * gaussZiggurat(0.0, 1.0);
```
Even with unity gain (`ploss_dB = 0.0`) and low noise floor (`noise_power_dB = -100.0`), `gaussZiggurat(0.0, 1.0)` executes per-sample floating-point random generation and channel matrix convolutions. At 106 PRBs full sampling ($61.44\text{ Msps}$), this generates over **$122.8\text{ million}$** random number calls per second on a single thread (`ru_thread`), inducing severe CPU saturation that dilates the simulated radio clock to $\approx 0.42\times - 0.44\times$ real-time ([Case 55](../troubleshooting/ran-ue.md#case-55)).

---

#### 4.4.2 3GPP Bandwidth Mapping & Three-Quarter Sampling (`-E`)
To eliminate simulator computational dilation while preserving active channel modeling, the testbed leverages 3GPP bandwidth downscaling paired with OAI Three-Quarter Sampling (`-E`):

**1. Frequency Domain Processing & FFT Sizing:**
OFDM signals are processed in the frequency domain via Fast Fourier Transform (FFT). Standard Cooley-Tukey FFT architectures require transform sizes of power-of-two ($2^N$). Standard 3GPP transmission bandwidth configurations (3GPP TS 38.104 Table 5.3.2-1), however, rarely align with power-of-two boundaries:
* **106 PRBs ($40\text{ MHz}$, SCS $30\text{ kHz}$):** $106 \times 12 = 1272\text{ active subcarriers}$. The next power-of-two FFT is **2048 points** ($61.44\text{ Msps}$), leaving $2048 - 1272 = 776$ unused guard-band subcarriers that the CPU is forced to compute.
* **Three-Quarter Sampling (`-E`):** OAI implements an alternative sampling rate using $\frac{3}{4} \times 2^N$. For 106 PRBs, FFT size scales to $\frac{3}{4} \times 2048 = 1536\text{ points}$ ($46.08\text{ Msps}$). Because $1536 \ge 1272$, all 106 PRBs are accommodated without frequency truncation, reducing computational load by $25\%$.
* **51 PRBs ($20\text{ MHz}$, SCS $30\text{ kHz}$):** $51 \times 12 = 612\text{ active subcarriers}$. The power-of-two size is 1024. With `-E`, the transform size reduces to:
  $$\text{FFT} = 1024 \times \frac{3}{4} = 768\text{ points} \quad (23.04\text{ Msps})$$
  Because $768 \ge 612$, all 51 PRBs fit completely without spectral distortion, reducing computational sample volume by **$62.5\%$** relative to unscaled 106 PRBs.

**2. Source Code Implementation in OpenAirInterface:**
* **CLI Parameter Declaration (`executables/softmodem-common.h` line 141):**
  ```c
  {"E", CONFIG_HLP_TQFS, PARAMFLAG_BOOL, .iptr=&softmodem_params.threequarter_fs, .defintval=0, TYPE_INT, 0},
  ```
* **UE Frame Config Propagation (`executables/nr-uesoftmodem.c` line 242):**
  ```c
  fp->threequarter_fs = get_softmodem_params()->threequarter_fs;
  ```
* **Transform Sizing Logic (`openair1/PHY/INIT/nr_parms.c` lines 97–116):**
  ```c
  fp->ofdm_symbol_size = 512;
  while(fp->ofdm_symbol_size < N_RB_DL * NR_NB_SC_PER_RB)
      fp->ofdm_symbol_size <<= 1;

  if (fp->threequarter_fs) {
      const uint16_t threeq_fft_size = fp->ofdm_symbol_size * 3 / 4;
      if (threeq_fft_size < (N_RB_DL * NR_NB_SC_PER_RB)) {
          warn_higher_threequarter_fs(N_RB_DL, fp->numerology_index);
          fp->ofdm_symbol_size = threeq_fft_size << 1;
      } else {
          fp->ofdm_symbol_size = threeq_fft_size;
      }
  }
  ```
* **Sampling Rate Mapping (`common/utils/nr/nr_common.c` lines 809–902):**
  ```c
  case 51:
    if (threequarter_fs) {
      *sampling_rate = 23040000;  // 23.04 Msps
      *bandwidth = 20e6;          // 20 MHz
    }
  ```
* **SSB Carrier Scan for 51 PRBs (`--ue-scan-carrier`):**
  In carrier bandwidths of 51 PRBs ($612$ subcarriers), the hardcoded default SSB subcarrier offset of 516 falls outside the carrier bandwidth ($516 + 240 = 756 > 612$), causing synchronization failure (`synch Failed`). Passing `--ue-scan-carrier` enables dynamic GSCN carrier scanning via `get_scan_ssb_first_sc()` (`openair1/PHY/NR_UE_TRANSPORT/nr_initial_sync.c`), achieving synchronization to GSCN 7923 ($3610.56\text{ MHz}$) in 1 frame.

---

#### 4.4.3 Calibrated Operational Profiles & Performance Matrix
The testbed formally defines three operational profiles to support distinct evaluation objectives:

```
+---------------------------------------------------------------------------------------------------------+
| Profile 1: Calibrated Real-Time Slicing Profile (Default Recommendation for ML / NWDAF Telemetry)       |
| DU-1: 51 PRB, SCS 30 kHz, -E (23.04 Msps), chanmod ACTIVE, unity gain (0.0 dB), noise -100.0 dB        |
| UE-1: -r 51, -C 3609120000, -E, --ue-scan-carrier                                                      |
| DU-2 / UE-2: 106 PRB Baseline (Port 4044, 61.44 Msps)                                                   |
| Verified Behavior: SFN progress 1.05x - 1.09x real-time; physical PUSCH capacity 16.6 Mbps             |
| Documentation: Case 56 in docs/troubleshooting/ran-ue.md#case-56                                        |
+---------------------------------------------------------------------------------------------------------+
| Profile 2: High-Throughput Wire-Speed Baseline (Pure Clean Pipe, No Channel Variation)                  |
| DU-1: 106 PRB, SCS 30 kHz, no -E (61.44 Msps), options = (); (chanmod DISABLED)                        |
| UE-1: -r 106, -C 3619200000, timing-correction-disable                                                 |
| DU-2 / UE-2: 106 PRB Baseline (Port 4044)                                                               |
| Verified Behavior: 20.0 Mbps wire-speed (20.03s duration), SFN progress 1.02x real-time                 |
| Documentation: Case 55 (Resolution) in docs/troubleshooting/ran-ue.md#case-55                           |
+---------------------------------------------------------------------------------------------------------+
| Profile 3: Historical Full-Bandwidth Impairment Profile (Reference Benchmark - Dilation Mode)           |
| DU-1: 106 PRB, SCS 30 kHz, no -E (61.44 Msps), options = ("chanmod"); noise_power_dB = -2.0 dB       |
| Verified Behavior: Clock progress dilates to 0.44x, throughput capped at ~13 Mbps (artificial queue)   |
| Documentation: Case 55 (Symptom) in docs/troubleshooting/ran-ue.md#case-55                              |
+---------------------------------------------------------------------------------------------------------+
```

**Multi-Step Empirical Load Characterization under Profile 1 (60-second test runs):**

| Offered Load (UDP) | SFN Clock Ratio | Receiver Throughput | Packet Loss | Duration Delta | Mean RTT (Slice 2 Co-run) | Status |
|---|---|---|---|---|---|---|
| **5.0 Mbps** | $1.09\times$ (Real-time) | **$5.00\text{ Mbps}$** | **0.0%** (0/25,897) | $+0.05\text{ s}$ | $18.9\text{ ms}$ | Healthy Normal |
| **10.0 Mbps** | $1.08\times$ (Real-time) | **$9.99\text{ Mbps}$** | **0.0%** (0/51,795) | $+0.05\text{ s}$ | $17.4\text{ ms}$ | Healthy Normal |
| **15.0 Mbps** | $1.06\times$ (Real-time) | **$15.0\text{ Mbps}$** | **0.0%** (0/77,694) | $+0.05\text{ s}$ | $15.1\text{ ms}$ | Healthy Normal |
| **20.0 Mbps** | $1.05\times$ (Real-time) | **$16.6\text{ Mbps}$** (Capacity)| **0.0%** (0/103,592)| $+12.45\text{ s}$ (Drainage) | $20.2\text{ ms}$ | RAN Capacity Backlog |

---

#### 4.4.4 Disaggregation of Bottleneck Domains: Computational vs. Physical Channel Saturation
A paramount scientific outcome of this calibration is disaggregating simulation software artifacts from physical communication constraints:

$$\text{Total Observed Latency/Backlog} = \Delta t_{\text{sim\_dilation}} + \Delta t_{\text{phy\_backlog}}$$

1. **Elimination of Computational Dilation ($\Delta t_{\text{sim\_dilation}} = 0$):**
   Under Profile 1, the SFN radio clock advances at **$1.05\times - 1.09\times$ real-time** across all offered loads. Computational time dilation is completely eliminated.
2. **Isolation of Physical TDD Capacity Bound:**
   Under 3GPP Band 78 TDD frame structure with $\mu = 1$ ($30\text{ kHz}$ SCS) and $5\text{ ms}$ periodicity ($10\text{ slots}$), the frame pattern allocates:
   * 7 Downlink slots, 2 Uplink slots, and 1 Mixed slot $\implies 20\%$ to $25\%$ of radio frame time dedicated to PUSCH transmission.
   * At 51 PRBs, the theoretical uplink physical limit is **$16.6\text{ Mbps}$**.
3. **Mathematical Queue Backlog Verification:**
   When offered $20.0\text{ Mbps}$ UDP load against a $16.6\text{ Mbps}$ physical channel:
   * Excess load generation rate: $\Delta R = 20.0 - 16.6 = 3.4\text{ Mbps}$.
   * Total excess volume generated over 60 seconds: $3.4\text{ Mbps} \times 60\text{ s} = 204\text{ Mbit}$.
   * Theoretical buffer drainage duration:
     $$\Delta t_{\text{drainage}} = \frac{204\text{ Mbit}}{16.6\text{ Mbps}} = \mathbf{12.28\text{ seconds}}$$
   * Measured receiver reporting duration delta: $72.45\text{ s} - 60.00\text{ s} = \mathbf{12.45\text{ seconds}}$.
   * **Calculated vs. measured error is less than $1.4\%$**, rigorously proving that the delay observed under 20 Mbps is authentic socket/RLC queue drainage rather than CPU clock throttling.

