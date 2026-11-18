# Experimental Scenarios & Disturbance Registry

> **See also:** [RF Attenuation Calibration (2026-11-17)](rf-attenuation-calibration.md) for empirical sweep results and scenario dB candidates.

**Authoritative Specification:** Single Source of Truth for Scenario Definitions, Treatment Parameters, and Response Hypotheses  
**Target Architecture:** VM-5 (UE Emulation), VM-4 (Split RAN), VM-3 (UPF Core Host), VM-6 (Telemetry Collector & Recorder)  
**Classification Target Classes:** `BASELINE`, `RAN`, `CORE`, `JOINT`  
**Treatment Scenario Identifiers:** `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, `S9`

---

> [!IMPORTANT]
> **Status Notice on Parameters & Execution Scope:**
> * All numeric parameter values listed herein (offered loads, attenuation levels, TBF rates, durations) represent **candidates for upcoming calibration**, NOT final static constants, standard mandates, or newly verified runtime measurements.
> * Operational commands are documented strictly as **planned procedures for future execution** following calibration. No experiments, traffic runs, or runtime VM alterations are performed during this documentation revision.
> * Four epistemic categories must be maintained without conflation:
>   1. **Committed Configurations:** Formally recorded in repository files (Profile 1: 51 PRBs, SCS 30 kHz, `-E`, `chanmod`, unity gain 0.0 dB, noise -100.0 dB; Profile 2: 106 PRBs baseline comparator).
>   2. **Historical Empirical Evidence:** Supported by documented test sessions (e.g., Case 55 dilation on 106 PRBs, Case 56 real-time calibration on 51 PRBs).
>   3. **Proposed Parameters:** Candidates awaiting experimental calibration (e.g., noise grid -40 to -20 dB, S5 load 15–20 Mbps, S7 TBF 5–6 Mbps).
>   4. **Runtime Conditions:** Live state of VM processes, softmodems, and network links requiring verification at the time of execution.

---

## 1. Classification Targets vs. Experimental Treatment Identifiers

In this research, machine learning models (NWDAF AnLF and Near-RT RIC xApp) are trained to classify the network state into four discrete operational classes:

$$\mathcal{C} = \{\text{BASELINE}, \text{RAN}, \text{CORE}, \text{JOINT}\}$$

The experimental Scenario IDs serve as **treatment scenario identifiers** to systematically induce distinct physical phenomena. Scenario numbers are assigned in ascending severity order within each class (lower number = softer, higher number = harder):

* **`BASELINE` Target Class:** Evaluated under `S1` (Light Normal) and `S2` (Higher Normal), verifying that varying traffic volume without capacity exhaustion remains classified as healthy baseline.
* **`RAN` Target Class:** Evaluated under `S3` (Soft Radio Degradation via mild attenuation), `S4` (Hard Radio Channel Degradation via heavy attenuation), and `S5` (Hard Radio Capacity Overload under clean channel).
* **`CORE` Target Class:** Evaluated under `S6` (Soft UPF egress rate limiting) and `S7` (Hard UPF egress rate limiting via binding Token Bucket Filter).
* **`JOINT` Target Class:** Evaluated under `S8` (Simultaneous soft radio + soft core impairment) and `S9` (Simultaneous active radio degradation and binding core transport throttling).
* **Inter-Scenario Reset Policy:** System resets (removing TBF rate limiters, resetting RF attenuation to 0.0 dB, stopping residual traffic) are strictly operational maintenance procedures executed between runs; they do not constitute experimental recording classes.

### 1.1 Treatment Metadata & Ground-Truth Labeling (Full 2-Hour / 7,200s Continuous Campaign Protocol)

The scenario and domain labels recorded in the raw telemetry CSV (`event_scenario`, `event_domain`, `event_component`) represent **experimental treatment metadata** assigned at recorder invocation (e.g., `event_domain = "CORE"` for Scenario S7).

Under the authoritative **Full 2-Hour (7,200-Second) Continuous Campaign Protocol** (`record_experiment.py <SCENARIO> --duration 7200`):
1. **Continuous Traffic Framing:** Traffic generation on VM-5 is framed for **7,260 seconds (121 minutes)** (`trafgen.sh start 7260 <rate>`) and launched $\approx 15\text{–}30\text{ s}$ before starting the recorder. This guarantees seamless traffic flow across all 7,200 seconds without boundary truncation.
2. **Persistent Fault / Operational State:** For fault scenarios (S3–S9), the calibrated impairment condition is established at the onset of the session, enabling hands-free, continuous recording without manual mid-run interruptions. For reference scenarios (S1 & S2), the system operates continuously under unperturbed baseline conditions.
3. **Deterministic Data Partitioning for ML:** The single continuous 7,200-sample (1 Hz) dataset per scenario is systematically partitioned offline into:
   * **Training Partition (50% — 3,600 samples / 1 Hour):** Primary partition used for feature normalization, scaling, and model training.
   * **Testing Partition (25% — 1,800 samples / 30 Minutes):** Held-out partition for unbiased generalization testing.
   * **Validation / Evaluation Partition (25% — 1,800 samples / 30 Minutes):** Held-out partition for hyperparameter tuning and decision threshold evaluation.
4. **Execution Order:** To maximize efficiency and address the most operationally complex conditions first, scenario collection proceeds in descending complexity order:  
   $$\mathbf{S9} \to \mathbf{S8} \to \mathbf{S7} \to \mathbf{S6} \to \mathbf{S5} \to \mathbf{S4} \to \mathbf{S3} \to \mathbf{S2} \to \mathbf{S1}$$

---

## 2. Canonical Scenario Registry (Candidate Parameters for Calibration)

Scenarios are ordered by class and ascending severity (Normal → Soft → Hard). Parameter values represent proposed operating candidates to be calibrated during pilot testing:

| Scenario ID | Treatment Identifier | Target Class | Severity | Physical Target Component | Planned Treatment Mechanism | Candidate Calibration Values *(Proposed, Pending Calibration)* | Hypothesized Response & Evidence to Examine |
|---|---|:---:|:---:|---|---|---|---|
| **`S1`** | `S1_NORMAL_LIGHT` | `BASELINE` | — | None (Reference) | Light baseline traffic on reference channel | Offered load $\approx 5\text{ Mbps}$, reference channel, no Core limiter | Throughput parity, stable RTT, zero UPF backlog. |
| **`S2`** | `S2_NORMAL_HIGH` | `BASELINE` | — | None (Reference) | Higher baseline traffic without bottleneck | Offered load $\approx 10\text{–}12\text{ Mbps}$, reference channel, no Core limiter | Traffic fully served, elevated PRB grant proxy, zero UPF backlog. |
| **`S3`** | `S3_RAN_SOFT` | `RAN` | Soft | DU-1 Uplink (`rfsimu_channel_ue0`) | Soft radio channel degradation via mild attenuation | Fixed load ($\approx 10\text{ Mbps}$), candidate UL attenuation: 25 dB (preliminary; stressed radio, binding status pending receiver evidence — see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) | Moderate SNR drop, MCS shifts down, PRB elevated, mild goodput dip. UPF backlog 0 B. |
| **`S4`** | `S4_RAN_DEGRADATION` | `RAN` | Hard-RF | DU-1 Uplink (`rfsimu_channel_ue0`) | Hard radio channel degradation via heavy attenuation | Fixed load ($\approx 10\text{ Mbps}$), candidate UL attenuation: 30 dB (preliminary; pending stable per-step receiver evidence — see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) | Collapsing SNR, low MCS, elevated BLER/HARQ, unserved traffic demand. UPF backlog 0 B. |
| **`S5`** | `S5_RAN_OVERLOAD` | `RAN` | Hard-Load | gNB DU-1 (Cell-1) | Radio capacity saturation under reference channel | Fixed load via capacity calibration (candidates: $15, 18, 20\text{ Mbps}$) | Receiver throughput capped ($G_{\text{rx}} < R_{\text{tx}}$), $\Delta t > 0$, PRB $\to 51$, UPF backlog 0 B. |
| **`S6`** | `S6_CORE_SOFT` | `CORE` | Soft | UPF-1 Egress (`eth0`) | Soft Core transport rate limiting via mild TBF | Fixed load ($\approx 10\text{ Mbps}$), mild TBF rate ($8\text{–}8.5\text{ Mbps}$, latency $80\text{ ms}$) | UPF backlog stays moderate (6k–14k Bytes), RTT increases mildly, minimal drops. |
| **`S7`** | `S7_CORE_QUEUE_TBF` | `CORE` | Hard | UPF-1 Egress (`eth0`) | Hard UPF-host/container egress rate shaping via binding TBF | Fixed load ($\approx 10\text{ Mbps}$), binding TBF rate ($5\text{–}6\text{ Mbps}$, latency $200\text{ ms}$) | UPF backlog surges, packet drops increase, egress rate matches TBF, radio metrics nominal. |
| **`S8`** | `S8_JOINT_SOFT` | `JOINT` | Soft | DU-1 UL + UPF-1 Egress | Simultaneous soft radio attenuation and soft core rate limiting | Candidate UL attenuation: 25 dB (preliminary; stressed radio, binding status pending receiver evidence per [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) + Soft TBF ($8\text{–}8.5\text{ Mbps}$) | Sub-threshold degradation in both domains: PRB ~58–65%, Backlog ~6k–14k B, RTT ~26–30 ms. |
| **`S9`** | `S9_JOINT_OVERLOAD` | `JOINT` | Hard | DU-1 UL + UPF-1 Egress | Simultaneous active radio impairment and binding Core shaping | Degraded radio forwarding rate $R_{\text{arr}}$ + binding TBF ($R_{\text{TBF}} < R_{\text{arr}}$) | Simultaneous radio degradation (low SNR/MCS, elevated BLER) AND Core congestion (elevated UPF backlog and drops). |

---

## 3. Detailed Specifications per Scenario (Full 2-Hour / 7,200s Continuous Protocol)

### 3.1 Scenario S1 — Normal Light Baseline

1. **Objective:** Establish the healthy reference operating state of the end-to-end network under light traffic demand.
2. **Initial Conditions:** Testbed restored to reference configuration (Profile 1: DU-1 51 PRBs, SCS 30 kHz, `-E`, `chanmod` active with calibrated baseline path loss $0.0\text{ dB}$ and reference noise; DU-2 active comparator; UPF-1/UPF-2 running with standard unshaped `tc qdisc`).
3. **Independent Variables (Changed):** Injected offered traffic on Slice 1 set to candidate $\approx 5\text{ Mbps}$ UDP.
4. **Controlled Variables (Maintained):** Reference radio channel parameters ($0.0\text{ dB}$), unshaped Core egress, Slice 2 canary ping (100 ms interval).
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch light traffic framed for 7,260s (ensuring complete 7,200s coverage)
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 5

   # Terminal 2 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 7200 --notes "S1 Normal Light Reference 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (`telemetry_*.csv`, 7,200 rows), sender/receiver iperf JSON logs, UE-1 and UE-2 ping logs, SFN clock progress ratio.
7. **Responses to Examine:** Verify sender offered rate matches receiver goodput ($G_{\text{rx}} \approx R_{\text{tx}}$); duration difference nominal ($\Delta t \approx 0$); ICMP RTT within healthy bounds ($< 25\text{ ms}$); zero UPF queue backlog (`upf_backlog_bytes_embb = 0`) and zero drops; stable SFN progress.
8. **Interpretation Boundaries:** Entire 7,200s run represents unperturbed `BASELINE`.

---

### 3.2 Scenario S2 — Normal Higher Baseline

1. **Objective:** Distinguish high non-congested traffic load from genuine system bottlenecks, ensuring that elevated resource usage alone is not misclassified as a fault.
2. **Initial Conditions:** System at reference condition; previous scenario treatments cleared.
3. **Independent Variables (Changed):** Injected offered load increased to candidate $\approx 10\text{–}12\text{ Mbps}$ UDP (calibrated below radio saturation ceiling).
4. **Controlled Variables (Maintained):** Reference channel conditions ($0.0\text{ dB}$), unshaped Core egress, Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch higher non-congested traffic framed for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S2 --duration 7200 --notes "S2 Normal Higher Baseline 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), iperf sender and receiver logs, canary ping logs.
7. **Responses to Examine:** Higher PRB grant proxy ($N_{\text{PRB}} / 51 \times 100\%$), while receiver throughput continues to match offered load without backlog accumulation at UPF ($0\text{ B}$) and without excessive duration delta ($\Delta t \approx 0$). Entire 7,200s run represents `BASELINE`.
8. **Interpretation Boundaries:** The label `BASELINE` is strictly conditional on empirical results confirming that traffic demand is fully served without unserved backlog.

---

### 3.3 Scenario S3 — RAN Soft Degradation

1. **Objective:** Observe network behavior under mild sub-threshold radio propagation impairment that causes measurable but non-catastrophic degradation — a marginal RAN case distinguishable from baseline.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at calibrated soft level **15.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-4 RAN): Apply calibrated soft attenuation (15.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 15.0 --channel-id 1 --port 9090

   # Step 2 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 3 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 7200 --notes "S3 RAN Soft Degradation 15dB 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), Telnet command/readback logs, iperf receiver logs.
7. **Responses to Examine:** Moderate SNR drop; MCS shifts downward (23–27, mean ~25); PRB grant proxy elevated to ~73% (peaks at 100%); non-zero BLER (4–10%); healthy connection without RLF. UPF backlog remains $0\text{ B}$.
8. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `RAN` ground-truth labeling.

---

### 3.4 Scenario S4 — RAN Hard Degradation (RF Impairment)

1. **Objective:** Observe network behavior when air-interface performance degrades severely due to physical wireless propagation impairment under fixed moderate traffic load.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at calibrated hard level **18.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-4 RAN): Inject calibrated hard Uplink attenuation (18.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 18.0 --channel-id 1 --port 9090

   # Step 2 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 3 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S4 --duration 7200 --notes "S4 RAN Hard Degradation 18dB 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), Telnet readback logs, iperf receiver logs, softmodem logs.
7. **Responses to Examine:** Decreased Uplink SNR; lower MCS index (16-QAM / MCS ~20–21); elevated BLER (10–25%) and HARQ retransmissions; throughput deficit at receiver (~6–7 Mbps); zero UPF backlog ($0\text{ B}$).
8. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `RAN` ground-truth labeling.

---

### 3.5 Scenario S5 — RAN Overload (Traffic Saturation)

1. **Objective:** Observe radio service limitations and bottleneck signatures caused purely by traffic demand exceeding available air-interface capacity under clean/reference radio conditions.
2. **Initial Conditions:** Reference radio channel (no added attenuation, reference noise); unshaped UPF egress.
3. **Independent Variables (Changed):** Offered load is set to continuous saturated value ($20\text{ Mbps}$) across the 7,260s run (`trafgen.sh start 7260 20`), directly benchmarking Profile 1 scheduling capacity limits ($C \approx 16.6\text{ Mbps}$).
4. **Controlled Variables (Maintained):** Reference RF propagation parameters ($0.0\text{ dB}$), Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-5 UE): Launch continuous saturated traffic (20 Mbps) for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 20

   # Step 2 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S5 --duration 7200 --notes "S5 RAN Overload Capacity Saturation 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), iperf receiver delivery logs (arrival goodput), UE-1 in-band RTT logs, UE-2 cross-slice canary logs, SFN progress audit.
7. **Responses to Examine:** Receiver throughput capped below offered load ($G_{\text{rx}} < R_{\text{tx}}$); positive receiver–sender duration difference ($\Delta t > 0$); instantaneous PRB grant proxy saturating near $100\%$ ($N_{\text{PRB}} \to 51$); Core UPF queue backlog remains zero ($0\text{ B}$).
8. **Interpretation Boundaries:** Capacity exhaustion is a scheduling volume limit, not RF corruption; BLER remains low ($\approx 0\%$) and MCS remains high under clean channels.

---

### 3.6 Scenario S6 — Core Soft Degradation (Mild TBF)

1. **Objective:** Observe system telemetry under mild Core transport shaping where the bottleneck is real but sub-threshold — a marginal CORE case distinct from baseline.
2. **Initial Conditions:** Radio channel at healthy reference condition ($0.0\text{ dB}$); UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on UPF-1 `eth0` at a mild rate ($8.5\text{ Mbps}$, latency $80\text{ ms}$) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-3 Core UPF): Apply mild egress rate shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms

   # Step 2 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 3 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 7200 --notes "S6 Core Soft TBF 8.5M 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF backlog stays moderate (candidate 6k–14k Bytes); RTT increases mildly (~26–30 ms); minimal packet drops; egress rate capped near TBF rate; radio telemetry remains nominal.
8. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `CORE` ground-truth labeling.
---

### 3.7 Scenario S7 — Core Hard Degradation (Binding TBF)

1. **Objective:** Observe system telemetry and end-to-end performance degradation when the bottleneck resides strictly in the Core Network user plane transport queue, with a binding rate limit causing significant backlog and drops.
2. **Initial Conditions:** Radio channel at healthy reference condition ($0.0\text{ dB}$); UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on UPF-1 `eth0` at a binding rate ($5\text{ Mbps}$, latency $200\text{ ms}$) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-3 Core UPF): Apply binding egress rate shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 5mbit burst 10kb latency 200ms

   # Step 2 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 3 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S7 --duration 7200 --notes "S7 Core Hard TBF 5M 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF queue backlog accumulation (`upf_backlog_bytes_embb > 0`); surge in kernel packet drops (`upf_drops_embb`); receiver goodput throttled near TBF rate ($\approx 5\text{ Mbps}$); radio telemetry remains unconstrained (nominal PRB grant proxy, high SNR, high MCS, BLER $\approx 0\%$).
8. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `CORE` ground-truth labeling.

---

### 3.8 Scenario S8 — Joint Soft Degradation

1. **Objective:** Evaluate telemetry signatures when sub-threshold impairments simultaneously affect both radio and core domains — testing whether joint soft degradation is distinguishable from single-domain soft faults.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at calibrated soft level **15.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) persistently across the 2-hour session.
   * Core impairment: Mild TBF shaping on UPF-1 `eth0` ($8.5\text{ Mbps}$, latency $80\text{ ms}$) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), reference noise power, Slice 2 canary probing.
5. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-4 RAN): Apply soft attenuation (15.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 15.0 --channel-id 1 --port 9090

   # Step 2 (VM-3 Core UPF): Apply mild egress rate shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms

   # Step 3 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 4 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S8 --duration 7200 --notes "S8 Joint Soft 15dB + TBF 8.5M 2h Continuous Campaign"
   ```
6. **Evidence to Collect:** Telemetry CSV (7,200 rows), Telnet readback logs, `tc -s qdisc` logs, iperf receiver logs.
7. **Responses to Examine:** Concurrent presence of mild radio strain (PRB ~65–75%, MCS ~24–26, BLER ~3–7%) and mild Core buffering (UPF backlog ~6k–14k Bytes, elevated canary RTT ~26–32 ms).
8. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `JOINT` ground-truth labeling.

---

### 3.9 Scenario S9 — Joint Hard Degradation (Binding)

1. **Objective:** Evaluate telemetry signatures and detection capabilities when distinct hard impairments simultaneously affect both the Radio Access Network and Core Network user plane.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at calibrated hard level **18.0 dB** persistently across the 2-hour session.
   * Core impairment: Binding egress TBF shaping on UPF-1 `eth0` ($4\text{ Mbps}$, latency $200\text{ ms}$) persistently across the 2-hour session.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 7,260s), reference noise power, Slice 2 canary probing.
5. **Architectural Precedence & Binding Condition:**
   > [!IMPORTANT]
   > In Uplink data flow, packets traverse the air interface before arriving at the Core UPF:
   > $$\text{UE} \xrightarrow{\text{Air Interface (RAN)}} \text{gNodeB DU-1/CU} \xrightarrow{\text{N3 / GTP-U}} \text{UPF-1} \xrightarrow{\text{N6 / } \texttt{eth0}} \text{EXT-DN}$$
   > The UPF TBF rate ($R_{\text{TBF}} = 4.0\text{ Mbps}$) is calibrated **strictly below** the degraded radio forwarding rate ($R_{\text{arr}} \approx 6\text{–}7\text{ Mbps}$) to ensure that both bottlenecks bind simultaneously ($R_{\text{TBF}} < R_{\text{arr}} < R_{\text{offered}}$).
6. **Planned Execution Sequence (Full 2-Hour Continuous Protocol):**
   ```bash
   # Step 1 (VM-4 RAN): Apply calibrated hard attenuation (18.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 18.0 --channel-id 1 --port 9090

   # Step 2 (VM-3 Core UPF): Apply binding egress rate shaping (4 Mbps)
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms

   # Step 3 (VM-5 UE): Launch continuous moderate traffic for 7,260s
   sudo /opt/oran/ue/scripts/trafgen.sh start 7260 10

   # Step 4 (VM-6 Monitoring): Start recorder ~15-30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S9 --duration 7200 --notes "S9 Joint Hard Binding RAN 18dB and Core TBF 4M 2h Continuous Campaign"
   ```
7. **Evidence to Collect:** Telemetry CSV (7,200 rows), iperf receiver logs, `tc -s qdisc` readback logs, NWDAF poll archives.
8. **Responses to Examine:** Simultaneous presence of radio domain signatures (degraded SNR ~24 dB, lower MCS ~20–21, elevated BLER ~10–15%, RTT ~600–1000 ms) and Core domain signatures (saturated UPF queue backlog ~109 kB, heavy drops ~590 pkt/s).
9. **Interpretation Boundaries:** Continuous persistent treatment across the full 7,200s run ensuring 100% pure `JOINT` ground-truth labeling.

---

## 4. Operational Reset & Inter-Scenario Cleanup Procedure

1. **Objective:** Deterministically restore all radio, Core, and traffic components to the unperturbed baseline state between experimental runs.
2. **Operational Scope:** This reset sequence is strictly an operational recovery procedure and maintenance action executed between experiment runs; **it is NOT a machine learning training class and is not recorded by the telemetry collector**.
3. **Execution Commands:**
   ```bash
   # 1. VM-3: Remove all qdisc rate limiting on UPF-1
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root 2>/dev/null || true
   # 2. VM-4: Reset all RFSimulator channel parameters to verified Profile 1 baseline
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   # 3. VM-5: Terminate any residual traffic processes
   sudo /opt/oran/ue/scripts/trafgen.sh stop
   ```
4. **Readback Verification:** Verify via `rfsim_channel_control.py show` that path loss is $0.0\text{ dB}$, and via `tc -s qdisc show dev eth0` that UPF-1 is in default unshaped state.

---

## 5. Authoritative Data Collection Sequence (Full 2-Hour Continuous Campaign)

The following sequence governs the official thesis experimental campaign under the **Full 2-Hour (7,200s) Continuous Protocol**. Collection executes in descending complexity order ($\mathbf{S9} \to \mathbf{S1}$):

| Order | Scenario | Target Class | Treatment Setup | Traffic (VM-5) | Recording (VM-6) | Output Dataset |
|:---:|:---:|:---:|---|---|---|---|
| 1 | **S9** | `JOINT` | Hard RF Attenuation ($18.0\text{ dB}$) + UPF TBF ($4.0\text{ Mbps}$, lat $200\text{ ms}$) | `trafgen.sh start 7260 10` | `record_experiment.py S9 --duration 7200` | `telemetry_EXP_S9_*.csv` (7,200 rows) |
| 2 | *Reset* | — | Reset RF to 0.0 dB, remove UPF qdisc, verify pristine baseline | — | — | — |
| 3 | **S8** | `JOINT` | Soft RF Attenuation ($15.0\text{ dB}$) + UPF TBF ($8.5\text{ Mbps}$, lat $80\text{ ms}$) | `trafgen.sh start 7260 10` | `record_experiment.py S8 --duration 7200` | `telemetry_EXP_S8_*.csv` (7,200 rows) |
| 4 | *Reset* | — | Reset RF to 0.0 dB, remove UPF qdisc, verify pristine baseline | — | — | — |
| 5 | **S7** | `CORE` | Binding UPF TBF ($5.0\text{ Mbps}$, lat $200\text{ ms}$) on clean RF | `trafgen.sh start 7260 10` | `record_experiment.py S7 --duration 7200` | `telemetry_EXP_S7_*.csv` (7,200 rows) |
| 6 | *Reset* | — | Remove UPF qdisc, verify pristine baseline | — | — | — |
| 7 | **S6** | `CORE` | Mild UPF TBF ($8.5\text{ Mbps}$, lat $80\text{ ms}$) on clean RF | `trafgen.sh start 7260 10` | `record_experiment.py S6 --duration 7200` | `telemetry_EXP_S6_*.csv` (7,200 rows) |
| 8 | *Reset* | — | Remove UPF qdisc, verify pristine baseline | — | — | — |
| 9 | **S5** | `RAN` | Radio Capacity Saturation ($20.0\text{ Mbps}$ offered load) on clean RF | `trafgen.sh start 7260 20` | `record_experiment.py S5 --duration 7200` | `telemetry_EXP_S5_*.csv` (7,200 rows) |
| 10 | *Reset* | — | Stop overload traffic, verify pristine baseline | — | — | — |
| 11 | **S4** | `RAN` | Hard RF Attenuation ($18.0\text{ dB}$) on unshaped UPF | `trafgen.sh start 7260 10` | `record_experiment.py S4 --duration 7200` | `telemetry_EXP_S4_*.csv` (7,200 rows) |
| 12 | *Reset* | — | Reset RF to 0.0 dB, verify pristine baseline | — | — | — |
| 13 | **S3** | `RAN` | Soft RF Attenuation ($15.0\text{ dB}$) on unshaped UPF | `trafgen.sh start 7260 10` | `record_experiment.py S3 --duration 7200` | `telemetry_EXP_S3_*.csv` (7,200 rows) |
| 14 | *Reset* | — | Reset RF to 0.0 dB, verify pristine baseline | — | — | — |
| 15 | **S2** | `BASELINE` | Unperturbed High Load ($10.0\text{ Mbps}$) on clean RF and unshaped UPF | `trafgen.sh start 7260 10` | `record_experiment.py S2 --duration 7200` | `telemetry_EXP_S2_*.csv` (7,200 rows) |
| 16 | *Reset* | — | Verify pristine baseline | — | — | — |
| 17 | **S1** | `BASELINE` | Unperturbed Light Load ($5.0\text{ Mbps}$) on clean RF and unshaped UPF | `trafgen.sh start 7260 5` | `record_experiment.py S1 --duration 7200` | `telemetry_EXP_S1_*.csv` (7,200 rows) |
| 18 | *Reset* | — | Final campaign cleanup | — | — | — |

> [!NOTE]
> * **Continuous Traffic Framing:** Traffic runs for 7,260s while the recorder captures 7,200 ticks (1 Hz).
> * **Offline Dataset Splitting:** Each 7,200-row dataset is partitioned offline into Training (3,600s / 1 Hour), Testing (1,800s / 30 Minutes), and Evaluation (1,800s / 30 Minutes).

---

## 6. Multi-Slice Context & Canary Isolation Policy

The experimental testbed operates a dual-slice architecture:
* **Slice 1 (eMBB):** Serving cell DU-1 (Cell-1, Port 4043, 51 PRBs, 20 MHz); Core UPF-1 (`oai-upf-slice1`, SST 1, SD 0x000001); generates primary data workload.
* **Slice 2 (URLLC):** Serving cell DU-2 (Cell-2, Port 4044, 106 PRBs, 40 MHz); Core UPF-2 (`oai-upf-slice2`, SST 222, SD 0x00007B); generates periodic 100 ms canary probe (`ping`).

**Canary Integrity & Shared-Infrastructure Demarcation:**  
While Slice 2 operates over a dedicated radio instance (DU-2, Cell-2), separate PRB pools, and an independent UPF container (`oai-upf-slice2`), both network slices share common host-level compute and execution paths (the shared DU/CU host platform VM-4, hypervisor vCPU scheduling, and common network bridges).  
Impact on Slice 2 canary latency is continuously measured and tracked. If degradation occurs on Slice 2 during Slice 1 stress, researchers must evaluate shared resource contention before attributing root causes.

---

## 7. Identified Implementation Gaps (Scripts & Automation)

To support the revised scenario framework, the following implementation status and tooling considerations are formally documented:

1. **Scenario Presets in `record_experiment.py`:**
   * *Status:* Fully aligned. `CANONICAL_PRESETS` in `scripts/record_experiment.py` directly defines `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, and `S9`.

2. **Dynamic Noise Parameter Control in `rfsim_channel_control.py`:**
   * *Gap:* `rfsim_channel_control.py` parses `noise_power_dB` during `show`, but lacks a CLI subcommand (`set-noise-power`) to adjust `noise_power_dB` dynamically via Telnet.
   * *Impact:* Noise calibration sweeps must currently be applied via configuration file edits and DU restarts.

3. **Channel Controller Reset Scope (`scripts/rfsim_channel_control.py` line 349):**
   * *Gap:* The `reset` subcommand only restores `path_loss_dB` (to $0.0\text{ dB}$ Profile 1 baseline). It does **not** restore `noise_power_dB`.
   * *Impact:* If noise was altered during testing, running `reset` will leave the noise parameter at its modified value.

4. **Post-Traffic Canary Observation & Probe Lifecycles in `trafgen.sh`:**
   * *Gap:* In `scripts/trafgen.sh`, parameter `DURATION` simultaneously determines the runtime of `iperf3 -u` (`-t "$DURATION"`), the display loop, and the ping probe packet counts. If the protocol requires observing quiescent recovery after traffic stops, extending `trafgen.sh` duration also extends iperf traffic.
   * *Impact:* Observability after traffic cessation requires launching canary ping probes with an independent lifecycle outside `trafgen.sh`.
