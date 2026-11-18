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

### 1.1 Treatment Metadata vs. Multi-Phase Ground-Truth Labeling (600-Second Nominal Protocol)

The scenario and domain labels recorded in the raw telemetry CSV (`event_scenario`, `event_domain`, `event_component`) represent **experimental treatment metadata** assigned at recorder invocation (e.g., `event_domain = "CORE"` for Scenario S7).

Under the nominal **600-second experimental protocol** (`record_experiment.py <SCENARIO> --duration 600`), traffic generation on VM-5 is framed for **660 seconds** (`trafgen.sh start 660 <rate>`) and launched $\approx 30\text{ s}$ before the recorder starts. This ensures that traffic cleanly covers the entire recording window, eliminates boundary cold-starts, and allows iperf3 to complete gracefully so receiver summaries are generated.

For disturbance scenarios (S3–S9), the 600-second run spans three distinct physical operational regimes under persistent traffic load:
1. *Pre-Disturbance Baseline Phase ($t \in [0, 120\text{ s}]$):* Reference traffic is actively flowing, but no fault or disturbance is applied. Ground truth: `BASELINE`.
2. *Active Disturbance Phase ($t \in [120, 420\text{ s}]$):* The physical impairment is applied for **300 seconds** while reference traffic continues flowing. System displays domain-specific bottleneck signatures (`RAN`, `CORE`, or `JOINT`). Note: 300 seconds is strictly the duration of the disturbance, NOT the traffic generator.
3. *Transient Drainage & Recovery Observation Phase ($t \in [420, 600\text{ s}]$):* The impairment is physically released at $t = 420\text{ s}$, while reference traffic **remains actively flowing**. Residual packets drain from socket buffers, RLC queues, or UPF qdiscs, and radio link adaptation restabilizes.
4. *Reference Scenarios (S1 & S2):* Operate without fault injection across the entire 600 seconds, serving as unperturbed reference observations (`BASELINE`).

* **Methodological Annotation Rule & Notational Demarcation:**  
  Labels must **NOT** be automatically switched to `BASELINE` at the exact instant the fault is physically released ($t = 420\text{ s}$), because physical queue drainage requires non-zero empirical recovery time ($T_{\text{recovery}}$).  
  $T_{\text{recovery}}$ must be determined directly from actual telemetry observations (e.g., when UPF backlog reaches $0\text{ B}$, canary RTT normalizes, and receiver goodput matches offered load), rather than assuming an instantaneous state change. If recovery is not fully captured within the 180-second post-disturbance window, subsequent run durations can be extended (e.g., to 900 seconds) based on pilot evidence. For supervised model training and RCA evaluation, researchers must perform offline temporal segmentation using logged event timestamps combined with empirical telemetry evidence.

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

## 3. Detailed Specifications per Scenario

### 3.1 Scenario S1 — Normal Light Baseline

1. **Objective:** Establish the healthy reference operating state of the end-to-end network under light traffic demand.
2. **Initial Conditions:** Testbed restored to reference configuration (Profile 1: DU-1 51 PRBs, SCS 30 kHz, `-E`, `chanmod` active with calibrated baseline path loss $0.0\text{ dB}$ and reference noise; DU-2 active comparator; UPF-1/UPF-2 running with standard `pfifo_fast` or unshaped `tc qdisc`).
3. **Independent Variables (Changed):** Injected offered traffic on Slice 1 set to candidate $\approx 5\text{ Mbps}$ UDP.
4. **Controlled Variables (Maintained):** Reference radio channel parameters, unshaped Core egress, Slice 2 canary ping (100 ms interval).
5. **Planned Execution Sequence (600s Nominal Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch light traffic framed for 660s (ensuring coverage across entire 600s record)
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 5

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 600 --notes "S1 Normal Light Reference 600s"
   ```
6. **Evidence to Collect:** Telemetry CSV (`telemetry_*.csv`), sender/receiver iperf JSON logs, UE-1 and UE-2 ping logs, SFN clock progress ratio.
7. **Responses to Examine:** Verify sender offered rate matches receiver goodput ($G_{\text{rx}} \approx R_{\text{tx}}$); duration difference nominal ($\Delta t \approx 0$); ICMP RTT within healthy bounds (candidate $< 25\text{ ms}$); zero UPF queue backlog (`upf_backlog_bytes_embb = 0`) and zero drops; stable SFN progress.
8. **Interpretation Boundaries:** Healthy metrics confirm baseline stability for the session, but do not guarantee immunity from transient hypervisor scheduling jitter. Entire 600s run is categorized as `BASELINE`.

---

### 3.2 Scenario S2 — Normal Higher Baseline

1. **Objective:** Distinguish high non-congested traffic load from genuine system bottlenecks, ensuring that elevated resource usage alone is not misclassified as a fault.
2. **Initial Conditions:** System at reference condition; previous scenario treatments cleared.
3. **Independent Variables (Changed):** Injected offered load increased to candidate $\approx 10\text{–}12\text{ Mbps}$ UDP (calibrated below radio saturation ceiling).
4. **Controlled Variables (Maintained):** Reference channel conditions, unshaped Core egress, Slice 2 canary probing.
5. **Planned Execution Sequence (600s Nominal Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch higher non-congested traffic framed for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S2 --duration 600 --notes "S2 Normal Higher Baseline 600s"
   ```
6. **Evidence to Collect:** Telemetry CSV, iperf sender and receiver logs, canary ping logs.
7. **Responses to Examine:** Higher PRB grant proxy ($N_{\text{PRB}} / 51 \times 100\%$), while receiver throughput continues to match offered load without backlog accumulation at UPF ($0\text{ B}$) and without excessive duration delta ($\Delta t \approx 0$). Entire 600s run is categorized as `BASELINE`.
8. **Interpretation Boundaries:** The label `BASELINE` is strictly conditional on empirical results confirming that traffic demand is fully served without unserved backlog.

---

### 3.3 Scenario S3 — RAN Soft Degradation

1. **Objective:** Observe network behavior under mild sub-threshold radio propagation impairment that causes measurable but non-catastrophic degradation — a marginal RAN case distinguishable from baseline.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at calibrated soft level **15.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) during $t \in [120, 420\text{ s}]$, released at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 660s), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 600 --notes "S3 RAN Soft Degradation 15dB"

   # Terminal 3 (VM-4 RAN at elapsed t = 120s): Inject calibrated soft attenuation (15.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 15.0 --channel-id 1 --port 9090

   # Terminal 3 (VM-4 RAN at elapsed t = 420s): Release attenuation; observe recovery until t = 600s
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
6. **Evidence to Collect:** Telemetry CSV (NPRB, SNR, MCS, BLER), Telnet command/readback logs, iperf receiver logs.
7. **Responses to Examine:** Moderate SNR drop; MCS shifts downward (23–27, mean ~25); PRB grant proxy elevated to ~73% (peaks at 100%); non-zero BLER (4–10%); healthy connection without RLF. UPF backlog remains $0\text{ B}$.
8. **Interpretation Boundaries:** Temporal segmentation rules apply: $[0, 120\text{ s}]$ is Baseline, $[120, 420\text{ s}]$ is Active Soft RAN, and $[420, 600\text{ s}]$ captures drainage/recovery under persistent load. Calibrated at 15.0 dB where link adaptation stabilizes at ~8–9 Mbps without causing connection loss.

---

### 3.4 Scenario S4 — RAN Hard Degradation (RF Impairment)

1. **Objective:** Observe network behavior when air-interface performance degrades severely due to physical wireless propagation impairment under fixed moderate traffic load.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at calibrated hard level **20.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) during $t \in [120, 420\text{ s}]$, released at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 660s), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S4 --duration 600 --notes "S4 RAN Hard Degradation 20dB"

   # Terminal 3 (VM-4 RAN at elapsed t = 120s): Inject calibrated hard Uplink attenuation (20.0 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 20.0 --channel-id 1 --port 9090

   # Terminal 3 (VM-4 RAN at elapsed t = 420s): Release attenuation; observe recovery until t = 600s
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
6. **Evidence to Collect:** Telemetry CSV (NPRB, SNR, MCS, BLER), Telnet command/readback logs, iperf receiver logs, softmodem logs.
7. **Responses to Examine:** Decreased Uplink SNR; lower MCS index; increased BLER and HARQ retransmissions; throughput deficit at receiver; zero UPF backlog ($0\text{ B}$). Post $t = 420\text{ s}$, link adaptation recovers to baseline bounds.
8. **Interpretation Boundaries:** If severe attenuation induces softmodem assertion crashes or process termination, this must be logged as an operational boundary failure. Recovery requires non-zero time ($T_{\text{recovery}}$) to re-converge.

---

### 3.5 Scenario S5 — RAN Overload (Traffic Saturation)

1. **Objective:** Observe radio service limitations and bottleneck signatures caused purely by traffic demand exceeding available air-interface capacity under clean/reference radio conditions.
2. **Initial Conditions:** Reference radio channel (no added attenuation, reference noise); unshaped UPF egress.
3. **Independent Variables (Changed):** Under the current unified tooling lifecycle, offered load is set to a single continuous saturated value (candidate: $20\text{ Mbps}$) across the 660s run (`trafgen.sh start 660 20`), directly benchmarking Profile 1 scheduling capacity limits ($C \approx 16.6\text{ Mbps}$). The three-phase dynamic offered load transition ($10 \to 20 \to 10\text{ Mbps}$) is documented as not yet implemented in testbed tooling pending decoupled probe lifecycle support.
4. **Controlled Variables (Maintained):** Reference RF propagation parameters, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous saturated traffic (20 Mbps) for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 20

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S5 --duration 600 --notes "S5 RAN Overload Capacity Saturation 600s"
   ```
   > **Tooling boundary:** S5 is executed as a single continuous 20 Mbps saturated load across the 660-second window. A dynamic mid-run rate transition ($10 \to 20 \to 10\text{ Mbps}$) is not yet implemented in `trafgen.sh` because restarting `trafgen.sh` mid-run triggers `cleanup()`, which terminates active ping canary processes.
6. **Evidence to Collect:** Telemetry CSV, iperf receiver delivery logs (arrival goodput), UE-1 in-band RTT logs, UE-2 cross-slice canary logs, SFN progress audit.
7. **Responses to Examine:** Receiver throughput capped below offered load ($G_{\text{rx}} < R_{\text{tx}}$); positive receiver–sender duration difference ($\Delta t > 0$); instantaneous PRB grant proxy saturating near $100\%$ ($N_{\text{PRB}} \to 51$); Core UPF queue backlog remains zero ($0\text{ B}$).
8. **Interpretation Boundaries:** Capacity exhaustion is a scheduling volume limit, not RF corruption; BLER remains low ($\approx 0\%$) and MCS remains high under clean channels.

---

### 3.6 Scenario S6 — Core Soft Degradation (Mild TBF)

1. **Objective:** Observe system telemetry under mild Core transport shaping where the bottleneck is real but sub-threshold — a marginal CORE case distinct from baseline.
2. **Initial Conditions:** Radio channel at healthy reference condition; UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on UPF-1 `eth0` at a mild rate (candidate: $8.5\text{ Mbps}$) during $t \in [120, 420\text{ s}]$, removed at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$ continuous across 660s), Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 600 --notes "S6 Core Soft TBF 8.5M"

   # Terminal 3 (VM-3 Core UPF at elapsed t = 120s): Apply mild egress rate shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms

   # Terminal 3 (VM-3 Core UPF at elapsed t = 420s): Remove shaping; observe recovery until t = 600s
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV (`upf_backlog_bytes_embb`, `upf_drops_embb`), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF backlog stays moderate (candidate 6k–14k Bytes); RTT increases mildly (~26–30 ms); minimal packet drops; egress rate capped near TBF rate; radio telemetry remains nominal.
8. **Interpretation Boundaries:** UPF queue backlog and drops return to zero post $t = 420\text{ s}$ as buffers drain.

---

### 3.7 Scenario S7 — Core Hard Degradation (Binding TBF)

1. **Objective:** Observe system telemetry and end-to-end performance degradation when the bottleneck resides strictly in the Core Network user plane transport queue, with a binding rate limit causing significant backlog and drops.
2. **Initial Conditions:** Radio channel at healthy reference condition; UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on UPF-1 `eth0` at a binding rate (candidate: $5\text{ Mbps}$, latency $200\text{ ms}$) during $t \in [120, 420\text{ s}]$, removed at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$ continuous across 660s), Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S7 --duration 600 --notes "S7 Core Hard TBF 5M"

   # Terminal 3 (VM-3 Core UPF at elapsed t = 120s): Apply binding egress rate shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 5mbit burst 10kb latency 200ms

   # Terminal 3 (VM-3 Core UPF at elapsed t = 420s): Remove shaping; observe queue drainage until t = 600s
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV (`upf_backlog_bytes_embb`, `upf_drops_embb`), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF queue backlog accumulation (`upf_backlog_bytes_embb > 0`); surge in kernel packet drops (`upf_drops_embb`); receiver goodput throttled near TBF rate ($\approx 5\text{ Mbps}$); radio telemetry remains unconstrained (nominal PRB grant proxy, high SNR, high MCS, BLER $\approx 0\%$).
8. **Interpretation Boundaries:** Recovery segmentation rule: transient UPF queue drainage ($[420, 420 + T_{\text{recovery}}]$) must be determined empirically from `upf_backlog_bytes_embb` reaching $0\text{ B}$.

---

### 3.8 Scenario S8 — Joint Soft Degradation

1. **Objective:** Evaluate telemetry signatures when sub-threshold impairments simultaneously affect both radio and core domains — testing whether joint soft degradation is distinguishable from single-domain soft faults.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at calibrated soft level **15.0 dB** (see [rf-attenuation-calibration.md](rf-attenuation-calibration.md)) during $t \in [120, 420\text{ s}]$, reset at $t = 420\text{ s}$.
   * Core impairment: Mild TBF shaping on UPF-1 `eth0` ($8.5\text{ Mbps}$, latency $80\text{ ms}$) during $t \in [120, 420\text{ s}]$, removed at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 660s), reference noise power, Slice 2 canary probing.
5. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S8 --duration 600 --notes "S8 Joint Soft 15dB + TBF 8.5M"

   # At elapsed t = 120s (VM-4 RAN & VM-3 Core): Apply simultaneous soft impairments
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 15.0 --channel-id 1 --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms

   # At elapsed t = 420s (VM-4 RAN & VM-3 Core): Release both impairments; observe recovery until t = 600s
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV showing concurrent radio and Core degradation features; iperf receiver logs; qdisc readback.
7. **Responses to Examine:** Simultaneous presence of sub-threshold signatures in both domains: PRB ~70–75%, moderate MCS drop (~25), non-zero BLER (~5–10%), UPF backlog ~6k–15k B, RTT ~25–40 ms, minimal drops.
8. **Interpretation Boundaries:** Two simultaneously active treatments (e.g., attenuation + TBF) do not automatically constitute two active bottlenecks. JOINT classification requires that both the RAN and Core limits are verified as simultaneously binding on the same measurement interval per [rf-attenuation-calibration.md](rf-attenuation-calibration.md).

---

### 3.9 Scenario S9 — Joint Hard Degradation (Binding)

1. **Objective:** Evaluate telemetry signatures and detection capabilities when distinct hard impairments simultaneously affect both the Radio Access Network and Core Network user plane.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at calibrated hard level **20.0 dB** during $t \in [120, 420\text{ s}]$, reset at $t = 420\text{ s}$.
   * Core impairment: Binding egress TBF shaping on UPF-1 `eth0` ($4\text{ Mbps}$, latency $200\text{ ms}$) during $t \in [120, 420\text{ s}]$, removed at $t = 420\text{ s}$.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$ continuous across 660s), reference noise power, Slice 2 canary probing.
5. **Architectural Precedence & Binding Condition:**
   > [!IMPORTANT]
   > In Uplink data flow, packets traverse the air interface before arriving at the Core UPF:
   > $$\text{UE} \xrightarrow{\text{Air Interface (RAN)}} \text{gNodeB DU-1/CU} \xrightarrow{\text{N3 / GTP-U}} \text{UPF-1} \xrightarrow{\text{N6 / } \texttt{eth0}} \text{EXT-DN}$$
   > If radio degradation throttles delivered throughput entering the UPF to $R_{\text{arr}}$ (e.g., $6\text{–}7\text{ Mbps}$ under $20\text{ dB}$ attenuation), an egress TBF configured at $12\text{ Mbps}$ will **never be reached**, leaving Core queue buffers empty ($0\text{ B}$) and causing the joint fault to degenerate into a single-domain RAN fault.
   > **Binding Requirement:** The UPF TBF rate ($R_{\text{TBF}}$) must be calibrated **strictly below** the degraded radio forwarding rate ($R_{\text{arr}}$) for both bottlenecks to bind simultaneously ($R_{\text{TBF}} < R_{\text{arr}} < R_{\text{offered}}$).
6. **Planned Execution Sequence (600s Continuous Protocol):**
   ```bash
   # Terminal 1 (VM-5 UE): Launch continuous moderate traffic for 660s
   sudo /opt/oran/ue/scripts/trafgen.sh start 660 10

   # Terminal 2 (VM-6 Monitoring): Start recorder ~30s after traffic starts
   python3 /opt/oran/monitoring/scripts/record_experiment.py S9 --duration 600 --notes "S9 Joint Hard Binding RAN and Core"

   # At elapsed t = 120s (VM-4 RAN & VM-3 Core): Apply simultaneous hard impairments
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 20.0 --channel-id 1 --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms

   # At elapsed t = 420s (VM-4 RAN & VM-3 Core): Release both impairments; observe recovery until t = 600s
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
7. **Evidence to Collect:** Telemetry CSV showing simultaneous radio degradation features and Core queue features; iperf receiver logs; qdisc readback.
8. **Responses to Examine:** Simultaneous presence of radio domain signatures (degraded SNR ~24 dB, lower MCS ~20–21, elevated BLER ~10–15%) and Core domain signatures (saturated UPF queue backlog ~109 kB, heavy drops ~590 pkt/s, and high RTT).
9. **Interpretation Boundaries:** True Joint classification requires verified empirical evidence of binding congestion in both domains. If UPF queue remains empty, the condition is not empirically Joint. Two simultaneously active treatments do not automatically constitute two active bottlenecks; both limits must be verified as simultaneously binding on the same measurement interval per [rf-attenuation-calibration.md](rf-attenuation-calibration.md).

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

## 5. Recommended Data Collection Sequence (600-Second Continuous Protocol)

The following sequence is recommended for each full dataset collection run under the **600-second continuous protocol**. Always execute the operational reset procedure before each scenario to guarantee a clean baseline state. In each run, traffic on VM-5 is framed for **660 seconds** (`trafgen.sh start 660 <rate>`) and launched $\approx 30\text{ s}$ before starting the 600-second recorder (`record_experiment.py <SCENARIO> --duration 600`), ensuring full traffic coverage across the entire run.

| Order | Step Type | Action / Command | Purpose |
|:---:|---|---|---|
| 1 | *Reset* | Run operational reset commands | Ensure unperturbed initial condition |
| 2 | **Record S1** | `record_experiment.py S1 --duration 600` | `BASELINE` light load (5 Mbps across 600s) |
| 3 | *Reset* | Run operational reset commands | Clear residual buffers |
| 4 | **Record S2** | `record_experiment.py S2 --duration 600` | `BASELINE` high load (10–12 Mbps across 600s) |
| 5 | *Reset* | Run operational reset commands | Clear residual buffers |
| 6 | **Record S3** | `record_experiment.py S3 --duration 600` | `RAN` soft attenuation (calibrated: 15.0 dB sub-threshold radio stress; active at 120–420s) |
| 7 | *Reset* | Run operational reset commands | Reset RF attenuation to 0.0 dB |
| 8 | **Record S4** | `record_experiment.py S4 --duration 600` | `RAN` hard RF attenuation (calibrated: 20.0 dB heavy attenuation/16-QAM transition; active at 120–420s) |
| 9 | *Reset* | Run operational reset commands | Reset RF attenuation to 0.0 dB |
| 10 | **Record S5** | `record_experiment.py S5 --duration 600` | `RAN` capacity overload (continuous saturated load 20 Mbps across 660s; Profile 1 capacity limit) |
| 11 | *Reset* | Run operational reset commands | Stop overload traffic |
| 12 | **Record S6** | `record_experiment.py S6 --duration 600` | `CORE` soft rate shaping (TBF 8.5 Mbps active at 120–420s) |
| 13 | *Reset* | Run operational reset commands | Remove UPF TBF |
| 14 | **Record S7** | `record_experiment.py S7 --duration 600` | `CORE` hard rate shaping (TBF 5 Mbps active at 120–420s) |
| 15 | *Reset* | Run operational reset commands | Remove UPF TBF |
| 16 | **Record S8** | `record_experiment.py S8 --duration 600` | `JOINT` soft (calibrated: 15.0 dB + TBF 8.5M active at 120–420s; sub-threshold joint stress) |
| 17 | *Reset* | Run operational reset commands | Reset RF and remove UPF TBF |
| 18 | **Record S9** | `record_experiment.py S9 --duration 600` | `JOINT` hard (calibrated: 20.0 dB + TBF 4.0M active at 120–420s; binding air-interface and core user plane) |
| 19 | *Reset* | Run operational reset commands | Final cleanup |

> [!NOTE]
> * **Continuous Traffic Framing:** Traffic runs for 660s while the recorder captures 600 ticks (1 Hz). The 300-second window ($t \in [120, 420\text{ s}]$) is strictly the active duration of the disturbance.
> * **Recovery Duration Extension:** If the 180-second post-disturbance observation ($t \in [420, 600\text{ s}]$) is insufficient to capture complete queue drainage and link restabilization, run duration can be extended (e.g., to 900 seconds with 840s disturbance / recovery) based on pilot evidence.
> * **Independent Run Partitioning:** Evaluation datasets must be divided by complete, independent runs (e.g., 6 train, 2 validation, 2 test per scenario), ensuring no temporal overlap or leakage across splits.

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
