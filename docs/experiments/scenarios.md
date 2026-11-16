# Experimental Scenarios & Disturbance Registry

**Authoritative Specification:** Single Source of Truth for Scenario Definitions, Treatment Parameters, and Response Hypotheses  
**Target Architecture:** VM-5 (UE Emulation), VM-4 (Split RAN), VM-3 (UPF Core Host), VM-6 (Telemetry Collector & Recorder)  
**Classification Target Classes:** `BASELINE`, `RAN`, `CORE`, `JOINT`  
**Treatment Scenario Identifiers:** `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, `S9`, `CLEAR`

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
* **Operational Reset Action (`CLEAR`):** `CLEAR` is an **operational reset and baseline recovery procedure**, NOT an additional training class.

### 1.1 Treatment Metadata vs. Multi-Phase Ground-Truth Labeling

The scenario and domain labels recorded in the raw telemetry CSV (`event_scenario`, `event_domain`, `event_component`) represent **experimental treatment metadata** assigned at recorder invocation (e.g., `event_domain = "CORE"` for Scenario S7).

When single-fault scenarios (S4, S5, S7, S9) are recorded with an extended duration to capture post-fault recovery (e.g., `--duration 240` where the fault is released at $t = 180\text{ s}$):
* **Raw Recorder Behavior:** The recorder assigns the initial preset label statically across all 240 seconds.
* **Physical Temporal Regimes:** The recording actually spans three distinct physical phases:
  1. *Active Disturbance Phase ($t \in [0, 180\text{ s}]$):* Impairment is actively applied; system displays domain-specific bottleneck signatures.
  2. *Transient Drainage / Recovery Phase ($t \in [180\text{ s}, 180 + T_{\text{recovery}}]$):* Impairment is physically released, but residual packets queued in socket buffers, RLC entities, or UPF qdiscs drain gradually, and radio link adaptation stabilizes.
  3. *Steady-State Post-Recovery Baseline Phase ($t > 180 + T_{\text{recovery}}$):* Queues are empty, receiver throughput matches offered load, and latency returns to nominal SLA bounds.
* **Methodological Annotation Rule & Notational Demarcation:**  
  Labels must **NOT** be automatically switched to `BASELINE` at the exact instant the fault is physically released ($t = 180\text{ s}$), because physical queue drainage requires non-zero empirical recovery time ($T_{\text{recovery}}$).  
  $T_{\text{recovery}}$ must be determined directly from actual telemetry observations (e.g., when UPF backlog reaches 0 B, canary RTT normalizes, and receiver goodput matches offered load), rather than assuming the iperf session duration delta ($\Delta t$) as the boundary. For supervised model training and RCA evaluation, researchers must perform offline temporal segmentation using logged event timestamps combined with empirical telemetry evidence.

---

## 2. Canonical Scenario Registry (Candidate Parameters for Calibration)

Scenarios are ordered by class and ascending severity (Normal → Soft → Hard). Parameter values represent proposed operating candidates to be calibrated during pilot testing:

| Scenario ID | Treatment Identifier | Target Class | Severity | Physical Target Component | Planned Treatment Mechanism | Candidate Calibration Values *(Proposed, Pending Calibration)* | Hypothesized Response & Evidence to Examine |
|---|---|:---:|:---:|---|---|---|---|
| **`CLEAR`** | `CLEAR_FAULT` | *Action Only* | — | All components | Operational baseline restoration | Remove TBF; reset RF attenuation to 0.0 dB; traffic nominal | Sender–receiver match, UPF backlog 0 B, radio link nominal. |
| **`S1`** | `S1_NORMAL_LIGHT` | `BASELINE` | — | None (Reference) | Light baseline traffic on reference channel | Offered load $\approx 5\text{ Mbps}$, reference channel, no Core limiter | Throughput parity, stable RTT, zero UPF backlog. |
| **`S2`** | `S2_NORMAL_HIGH` | `BASELINE` | — | None (Reference) | Higher baseline traffic without bottleneck | Offered load $\approx 10\text{–}12\text{ Mbps}$, reference channel, no Core limiter | Traffic fully served, elevated PRB grant proxy, zero UPF backlog. |
| **`S3`** | `S3_RAN_SOFT` | `RAN` | Soft | DU-1 Uplink (`rfsimu_channel_ue0`) | Soft radio channel degradation via mild attenuation | Fixed load ($\approx 10\text{ Mbps}$), injected UL attenuation ($4\text{–}6\text{ dB}$) | Moderate SNR drop, MCS 22–24, PRB elevated to 57–65%, mild goodput dip. UPF backlog 0 B. |
| **`S4`** | `S4_RAN_DEGRADATION` | `RAN` | Hard-RF | DU-1 Uplink (`rfsimu_channel_ue0`) | Hard radio channel degradation via heavy attenuation | Fixed load ($\approx 10\text{ Mbps}$), injected UL attenuation ($10\text{–}12\text{ dB}$) | Collapsing SNR, low MCS, elevated BLER/HARQ, unserved traffic demand. UPF backlog 0 B. |
| **`S5`** | `S5_RAN_OVERLOAD` | `RAN` | Hard-Load | gNB DU-1 (Cell-1) | Radio capacity saturation under reference channel | Fixed load via capacity calibration (candidates: $15, 18, 20\text{ Mbps}$) | Receiver throughput capped ($G_{\text{rx}} < R_{\text{tx}}$), $\Delta t > 0$, PRB $\to 51$, UPF backlog 0 B. |
| **`S6`** | `S6_CORE_SOFT` | `CORE` | Soft | UPF-1 Egress (`eth0`) | Soft Core transport rate limiting via mild TBF | Fixed load ($\approx 10\text{ Mbps}$), mild TBF rate ($8\text{–}8.5\text{ Mbps}$, latency $80\text{ ms}$) | UPF backlog stays moderate (6k–14k Bytes), RTT increases mildly, minimal drops. |
| **`S7`** | `S7_CORE_QUEUE_TBF` | `CORE` | Hard | UPF-1 Egress (`eth0`) | Hard UPF-host/container egress rate shaping via binding TBF | Fixed load ($\approx 10\text{ Mbps}$), binding TBF rate ($5\text{–}6\text{ Mbps}$, latency $200\text{ ms}$) | UPF backlog surges, packet drops increase, egress rate matches TBF, radio metrics nominal. |
| **`S8`** | `S8_JOINT_SOFT` | `JOINT` | Soft | DU-1 UL + UPF-1 Egress | Simultaneous soft radio attenuation and soft core rate limiting | Soft UL attenuation ($4\text{–}6\text{ dB}$) + Soft TBF ($8\text{–}8.5\text{ Mbps}$) | Sub-threshold degradation in both domains: PRB ~58–65%, Backlog ~6k–14k B, RTT ~26–30 ms. |
| **`S9`** | `S9_JOINT_OVERLOAD` | `JOINT` | Hard | DU-1 UL + UPF-1 Egress | Simultaneous active radio impairment and binding Core shaping | Degraded radio forwarding rate $R_{\text{arr}}$ + binding TBF ($R_{\text{TBF}} < R_{\text{arr}}$) | Simultaneous radio degradation (low SNR/MCS, elevated BLER) AND Core congestion (elevated UPF backlog and drops). |

---

## 3. Detailed Specifications per Scenario

### 3.1 Scenario S1 — Normal Light Baseline

1. **Objective:** Establish the healthy reference operating state of the end-to-end network under light traffic demand.
2. **Initial Conditions:** Testbed restored to reference configuration (Profile 1: DU-1 51 PRBs, SCS 30 kHz, `-E`, `chanmod` active with calibrated baseline path loss $0.0\text{ dB}$ and reference noise; DU-2 active comparator; UPF-1/UPF-2 running with standard `pfifo_fast` or unshaped `tc qdisc`).
3. **Independent Variables (Changed):** Injected offered traffic on Slice 1 set to candidate $\approx 5\text{ Mbps}$ UDP.
4. **Controlled Variables (Maintained):** Reference radio channel parameters, unshaped Core egress, Slice 2 canary ping (100 ms interval).
5. **Planned Execution Sequence:**
   ```bash
   # VM-5: Launch light traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 5
   # VM-6: Record baseline dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 180 --notes "S1 Normal Light Reference"
   ```
6. **Evidence to Collect:** Telemetry CSV (`telemetry_*.csv`), sender/receiver iperf JSON logs, UE-1 and UE-2 ping logs, SFN clock progress ratio.
7. **Responses to Examine:** Verify sender offered rate matches receiver goodput ($G_{\text{rx}} \approx R_{\text{tx}}$); duration difference nominal ($\Delta t \approx 0$); ICMP RTT within healthy bounds (candidate $< 25\text{ ms}$); zero UPF queue backlog (`upf_backlog_bytes_embb = 0`) and zero drops; stable SFN progress.
8. **Interpretation Boundaries:** Healthy metrics confirm baseline stability for the session, but do not guarantee immunity from transient hypervisor scheduling jitter.

---

### 3.2 Scenario S2 — Normal Higher Baseline

1. **Objective:** Distinguish high non-congested traffic load from genuine system bottlenecks, ensuring that elevated resource usage alone is not misclassified as a fault.
2. **Initial Conditions:** System at reference condition; previous scenario treatments cleared.
3. **Independent Variables (Changed):** Injected offered load increased to candidate $\approx 10\text{–}12\text{ Mbps}$ UDP (calibrated below radio saturation ceiling).
4. **Controlled Variables (Maintained):** Reference channel conditions, unshaped Core egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # VM-5: Launch higher non-congested traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # VM-6: Record higher baseline dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S2 --duration 180 --notes "S2 Normal Higher Baseline"
   ```
6. **Evidence to Collect:** Telemetry CSV, iperf sender and receiver logs, canary ping logs.
7. **Responses to Examine:** Higher PRB grant proxy ($N_{\text{PRB}} / 51 \times 100\%$), while receiver throughput continues to match offered load without backlog accumulation at UPF ($0\text{ B}$) and without excessive duration delta ($\Delta t \approx 0$).
8. **Interpretation Boundaries:** The label `BASELINE` is strictly conditional on future empirical results confirming that traffic demand is fully served without unserved backlog. If capacity calibration reveals queue onset at $12\text{ Mbps}$, the load must be adjusted downward.

---

### 3.3 Scenario S3 — RAN Soft Degradation

1. **Objective:** Observe network behavior under mild sub-threshold radio propagation impairment that causes measurable but non-catastrophic degradation — a marginal RAN case distinguishable from baseline.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at a mild level (candidate: $4\text{–}6\text{ dB}$) while maintaining reference noise power constant.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Terminal 1 (VM-5 UE): Launch fixed moderate traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10

   # Terminal 2 (VM-4 RAN): Inject mild attenuation (candidate: 5 dB) and verify readback
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 5.0 --channel-id 1 --port 9090
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py show --port 9090

   # Terminal 3 (VM-6 Monitoring): Record soft RAN degradation
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 180 --notes "S3 RAN Soft Degradation 5dB"

   # Terminal 2 (VM-4 at completion): Restore baseline
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
6. **Evidence to Collect:** Telemetry CSV (NPRB, SNR, MCS, BLER), Telnet command/readback logs, iperf receiver logs.
7. **Responses to Examine:** Moderate SNR drop (candidate ~20 dB range); MCS shifts downward but remains in mid-range (22–24); PRB grant proxy elevated to 57–65% (approaching but not exceeding saturation); mild goodput reduction (~9–9.5 Mbps). UPF backlog remains $0\text{ B}$.
8. **Interpretation Boundaries:** The soft boundary between S3 and S4 must be empirically verified. If $5\text{ dB}$ produces the same telemetry signature as the reference (S1/S2), attenuation must be increased. The classification boundary PRB ~65% and UPF backlog $0\text{ B}$ are directional hypotheses, not rigid thresholds.

---

### 3.4 Scenario S4 — RAN Hard Degradation (RF Impairment)

1. **Objective:** Observe network behavior when air-interface performance degrades severely due to physical wireless propagation impairment under fixed moderate traffic load.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) that is fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) at a hard level (candidate: $10\text{–}12\text{ dB}$) while maintaining reference noise power constant.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence & Terminal Separation:**
   *Note on Execution Timing & Recovery:* To record both active disturbance (~180s) and recovery (~60s+), the recorder must span the combined duration (`--duration 240`) or operate in manual stop mode (`--duration 0`).
   ```bash
   # Terminal 1 (VM-5 UE): Launch fixed moderate traffic in foreground
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10

   # Terminal 2 (VM-4 RAN): Inject hard Uplink path attenuation (candidate: 12 dB) and verify readback
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 12.0 --channel-id 1 --port 9090
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py show --port 9090

   # Terminal 3 (VM-6 Monitoring): Record active disturbance and recovery window (~240s total)
   python3 /opt/oran/monitoring/scripts/record_experiment.py S4 --duration 240 --notes "S4 RAN Hard Degradation 12dB + Recovery"

   # Terminal 2 (VM-4 RAN at t = 180s): Restore path attenuation back to 0.0 dB
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
6. **Evidence to Collect:** Telemetry CSV (NPRB, SNR, MCS, BLER), Telnet command/readback logs, iperf receiver logs, softmodem logs.
7. **Responses to Examine:** Decreased Uplink SNR; downward link adaptation (lower MCS index); increased BLER and HARQ retransmissions (`ulsch_rounds`); throughput deficit at receiver; zero UPF backlog ($0\text{ B}$).
8. **Interpretation Boundaries:**
   * Target channel model identity (`rfsimu_channel_ue0` for Channel 1 UL) must be verified via explicit readback.
   * If severe attenuation induces softmodem assertion crashes or process termination, this must be logged as a **testbed operational boundary failure**, NOT as an acceptable training sample.
   * **Recovery Segmentation Rule:** When recorded with an extended duration spanning treatment release at $t = 180\text{ s}$, the active degradation window ($[0, 180\text{ s}]$), transient link recovery ($[180, 180 + T_{\text{recovery}}]$), and post-recovery baseline ($> 180 + T_{\text{recovery}}$) must be partitioned offline based on logged timestamps and telemetry evidence, not assumed to switch instantaneously at $t = 180\text{ s}$.

---

### 3.5 Scenario S5 — RAN Overload (Traffic Saturation)

1. **Objective:** Observe radio service limitations and bottleneck signatures caused purely by traffic demand exceeding available air-interface capacity under clean/reference radio conditions.
2. **Initial Conditions:** Reference radio channel (no added attenuation, reference noise); unshaped UPF egress.
3. **Independent Variables (Changed):** Offered load set to a fixed saturation value selected via prior pilot calibration (candidate evaluation grid: $15, 18, 20\text{ Mbps}$).
4. **Controlled Variables (Maintained):** Reference RF propagation parameters, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # VM-5: Launch saturation traffic (using fixed load from capacity pilot, e.g., 20 Mbps)
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 20
   # VM-6: Record RAN overload dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S5 --duration 180 --notes "S5 RAN Overload Capacity Saturation"
   ```
6. **Evidence to Collect:** Telemetry CSV, iperf receiver delivery logs (arrival goodput), UE-1 in-band RTT logs, UE-2 cross-slice canary logs, SFN progress audit.
7. **Responses to Examine:** Receiver throughput capped below offered load ($G_{\text{rx}} < R_{\text{tx}}$); positive receiver–sender duration difference ($\Delta t > 0$); instantaneous PRB grant proxy saturating near $100\%$ ($N_{\text{PRB}} \to 51$); Core UPF queue backlog remains zero ($0\text{ B}$).
8. **Interpretation Boundaries:**
   * High PRB grant proxy indicates full scheduling grant allocation per TTI, but does not alone prove a bottleneck without evidence of unserved traffic demand, latency inflation, or goodput shortfall.
   * Under clean channel conditions, **BLER can legitimately remain low ($\approx 0\%$) and MCS remain high**, because capacity exhaustion is a scheduling volume limit, not RF corruption. Overload must not be rejected merely because BLER is low.

---

### 3.6 Scenario S6 — Core Soft Degradation (Mild TBF)

1. **Objective:** Observe system telemetry under mild Core transport shaping where the bottleneck is real but sub-threshold — a marginal CORE case distinct from baseline.
2. **Initial Conditions:** Radio channel at healthy reference condition; UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on the egress interface of UPF-1 (`oai-upf-slice1` container `eth0`) at a mild rate.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$), Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Terminal 1 (VM-3 Core UPF): Apply mild egress rate shaping on UPF-1 (candidate: 8.5 Mbps)
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms
   sudo docker exec oai-upf-slice1 tc -s qdisc show dev eth0

   # Terminal 2 (VM-5 UE): Launch traffic at offered load
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10

   # Terminal 3 (VM-6 Monitoring): Record soft Core degradation
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 180 --notes "S6 Core Soft TBF 8.5M"

   # Terminal 1 (VM-3 Core UPF at completion): Remove shaping
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV (`upf_backlog_bytes_embb`, `upf_drops_embb`), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF backlog stays moderate (candidate 6k–14k Bytes, below 20k threshold); RTT increases to candidate ~26–30 ms; minimal packet drops; egress rate capped near TBF rate; radio telemetry remains nominal (high SNR, high MCS, BLER $\approx 0\%$).
8. **Interpretation Boundaries:** The soft/hard boundary (S6 vs. S7) is defined empirically by backlog magnitude and drop rate. If $8.5\text{ Mbps}$ TBF produces negligible backlog indistinguishable from baseline, the rate must be reduced.

---

### 3.7 Scenario S7 — Core Hard Degradation (Binding TBF)

1. **Objective:** Observe system telemetry and end-to-end performance degradation when the bottleneck resides strictly in the Core Network user plane transport queue, with a binding rate limit that causes significant backlog and drops.
2. **Initial Conditions:** Radio channel at healthy reference condition; UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on the egress interface of UPF-1 (`oai-upf-slice1` container `eth0`, facing EXT-DN) at a binding (hard) rate.
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$), Slice 2 canary probing.
5. **Planned Execution Sequence & Terminal Separation:**
   *Note on Execution Timing & Recovery:* To record both active disturbance (~180s) and recovery (~60s+), the recorder may span the combined duration (`--duration 240`).
   ```bash
   # Terminal 1 (VM-3 Core UPF): Apply binding egress rate shaping on UPF-1
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 5mbit burst 10kb latency 200ms
   sudo docker exec oai-upf-slice1 tc -s qdisc show dev eth0

   # Terminal 2 (VM-5 UE): Launch traffic exceeding TBF rate
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10

   # Terminal 3 (VM-6 Monitoring): Record active disturbance and recovery window
   python3 /opt/oran/monitoring/scripts/record_experiment.py S7 --duration 240 --notes "S7 Core Hard TBF 5M + Recovery"

   # Terminal 1 (VM-3 Core UPF at t = 180s): Remove shaping to assess recovery
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV (`upf_backlog_bytes_embb`, `upf_drops_embb`), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF queue backlog accumulation (`upf_backlog_bytes_embb > 0`); surge in kernel packet drops (`upf_drops_embb`); receiver goodput throttled near TBF rate ($\approx 5\text{ Mbps}$); radio telemetry remains unconstrained (nominal PRB grant proxy, high SNR, high MCS, BLER $\approx 0\%$).
8. **Interpretation Boundaries:**
   * Terminology must consistently specify **UPF-host/container egress shaping**.
   * Radio path must be independently verified as capable of serving the offered load, ensuring the bottleneck is isolated to the Core.
   * **Recovery Segmentation Rule:** In an extended recording (e.g. 240s) where TBF is removed at $t = 180\text{ s}$, the active Core queuing phase ($[0, 180\text{ s}]$), transient UPF queue drainage ($[180, 180 + T_{\text{recovery}}]$), and post-recovery baseline ($> 180 + T_{\text{recovery}}$) must be segmented offline using logged timestamps and `upf_backlog_bytes_embb` drainage evidence, rather than assuming an immediate switch to `BASELINE` at $t = 180\text{ s}$.

---

### 3.8 Scenario S8 — Joint Soft Degradation

1. **Objective:** Evaluate telemetry signatures when sub-threshold impairments simultaneously affect both radio and core domains — testing whether joint soft degradation is distinguishable from single-domain soft faults.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at soft level (candidate: $4\text{–}6\text{ dB}$).
   * Core impairment: Mild TBF shaping on UPF-1 `eth0` (candidate: $8\text{–}8.5\text{ Mbps}$).
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # 1. VM-4: Apply soft radio attenuation (candidate: 5 dB)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 5.0 --channel-id 1 --port 9090
   # 2. VM-3: Apply soft egress TBF (candidate: 8.5 Mbps)
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 8500kbit burst 10kb latency 80ms
   # 3. VM-5: Launch traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # 4. VM-6: Record joint soft degradation
   python3 /opt/oran/monitoring/scripts/record_experiment.py S8 --duration 180 --notes "S8 Joint Soft 5dB + TBF 8.5M"
   # 5. Cleanup both domains
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV showing concurrent radio and Core degradation features; iperf receiver logs; qdisc readback.
7. **Responses to Examine:** Simultaneous presence of sub-threshold signatures in both domains: PRB ~58–65%, moderate SNR reduction, mild goodput dip (~8–9 Mbps), UPF backlog ~6k–14k B, RTT ~26–30 ms, minimal drops.
8. **Interpretation Boundaries:** S8 is classified as `JOINT` only when both RAN and Core simultaneously exhibit non-baseline telemetry. If only one domain is measurably affected, the sample may be misclassified.

---

### 3.9 Scenario S9 — Joint Hard Degradation (Binding)

1. **Objective:** Evaluate telemetry signatures and detection capabilities when distinct hard impairments simultaneously affect both the Radio Access Network and Core Network user plane.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 at hard level (candidate: $8\text{–}10\text{ dB}$).
   * Core impairment: Binding egress TBF shaping on UPF-1 `eth0` (candidate: $4\text{ Mbps}$).
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Slice 2 canary probing.
5. **Architectural Precedence & Binding Condition:**
   > [!IMPORTANT]
   > In Uplink data flow, packets traverse the air interface before arriving at the Core UPF:
   > $$\text{UE} \xrightarrow{\text{Air Interface (RAN)}} \text{gNodeB DU-1/CU} \xrightarrow{\text{N3 / GTP-U}} \text{UPF-1} \xrightarrow{\text{N6 / } \texttt{eth0}} \text{EXT-DN}$$
   > If radio degradation throttles delivered throughput entering the UPF to $R_{\text{arr}}$ (e.g., $7\text{ Mbps}$), an egress TBF configured at $12\text{ Mbps}$ will **never be reached**, leaving Core queue buffers empty ($0\text{ B}$) and causing the joint fault to degenerate into a single-domain RAN fault.
   > **Binding Requirement:** The UPF TBF rate ($R_{\text{TBF}}$) must be calibrated **strictly below** the degraded radio forwarding rate ($R_{\text{arr}}$) for both bottlenecks to bind simultaneously (e.g., $R_{\text{offered}} = 10\text{ Mbps}$, radio throttles to $R_{\text{arr}} \approx 7\text{ Mbps}$, and TBF limits egress to $R_{\text{TBF}} \approx 4\text{ Mbps}$).
6. **Planned Execution Sequence:**
   ```bash
   # 1. VM-4: Apply hard radio attenuation (candidate: 10 dB on UL Channel 1)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 10.0 --channel-id 1 --port 9090
   # 2. VM-3: Apply binding egress TBF on UPF-1 (candidate: 4 Mbps)
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms
   # 3. VM-5: Launch traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # 4. VM-6: Record joint hard degradation
   python3 /opt/oran/monitoring/scripts/record_experiment.py S9 --duration 180 --notes "S9 Joint Hard Binding RAN and Core"
   # 5. Cleanup both domains
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
7. **Evidence to Collect:** Telemetry CSV showing simultaneous radio degradation features and Core queue features; iperf receiver logs; qdisc readback.
8. **Responses to Examine:** Simultaneous presence of:
   * Radio domain signatures: degraded SNR, lower MCS, elevated BLER / retransmissions.
   * Core domain signatures: non-zero UPF queue backlog (`upf_backlog_bytes_embb > 0`) and elevated packet drops.
9. **Interpretation Boundaries:** True Joint classification requires verified empirical evidence of binding congestion in both domains. If UPF queue remains empty, the condition is not empirically Joint.

---

### 3.10 Operational Reset Procedure (`CLEAR`)

1. **Objective:** Deterministically restore all radio, Core, and traffic components to the unperturbed baseline state between experimental runs.
2. **Operational Scope:** `CLEAR` is strictly an operational recovery procedure and maintenance action; **it is NOT a machine learning training class**.
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

## 4. Recommended Data Collection Sequence

The following sequence is recommended for each full dataset collection run. Always execute `CLEAR` before each scenario to guarantee a known baseline state.

| Order | Scenario | Command | Notes |
|:---:|---|---|---|
| 1 | `CLEAR` | Reset all | Restore baseline before recording |
| 2 | `S1` | `record_experiment.py S1 --duration 180` | BASELINE light |
| 3 | `CLEAR` | Reset all | Between each scenario |
| 4 | `S2` | `record_experiment.py S2 --duration 180` | BASELINE high |
| 5 | `CLEAR` | Reset all | |
| 6 | `S3` | `record_experiment.py S3 --duration 180` | RAN soft |
| 7 | `CLEAR` | Reset all | |
| 8 | `S4` | `record_experiment.py S4 --duration 180` | RAN hard-RF |
| 9 | `CLEAR` | Reset all | |
| 10 | `S5` | `record_experiment.py S5 --duration 180` | RAN hard-load |
| 11 | `CLEAR` | Reset all | |
| 12 | `S6` | `record_experiment.py S6 --duration 180` | CORE soft |
| 13 | `CLEAR` | Reset all | |
| 14 | `S7` | `record_experiment.py S7 --duration 180` | CORE hard |
| 15 | `CLEAR` | Reset all | |
| 16 | `S8` | `record_experiment.py S8 --duration 180` | JOINT soft |
| 17 | `CLEAR` | Reset all | |
| 18 | `S9` | `record_experiment.py S9 --duration 180` | JOINT hard |
| 19 | `CLEAR` | Reset all | Final cleanup |

> [!NOTE]
> Each scenario should produce ~180 samples at 1 Hz. For `S4` and `S7`, an optional extended recording (`--duration 240`) may be used to capture post-fault recovery, with offline temporal segmentation applied during preprocessing.

---

## 5. Multi-Slice Context & Canary Isolation Policy

The experimental testbed operates a dual-slice architecture:
* **Slice 1 (eMBB):** Serving cell DU-1 (Cell-1, Port 4043, 51 PRBs, 20 MHz); Core UPF-1 (`oai-upf-slice1`, SST 1, SD 0x000001); generates primary data workload.
* **Slice 2 (URLLC):** Serving cell DU-2 (Cell-2, Port 4044, 106 PRBs, 40 MHz); Core UPF-2 (`oai-upf-slice2`, SST 222, SD 0x00007B); generates periodic 100 ms canary probe (`ping`).

**Canary Integrity & Shared-Infrastructure Demarcation:**  
While Slice 2 operates over a dedicated radio instance (DU-2, Cell-2), separate PRB pools, and an independent UPF container (`oai-upf-slice2`), both network slices share common host-level compute and execution paths (the shared DU/CU host platform VM-4, hypervisor vCPU scheduling, and common network bridges).  
Impact on Slice 2 canary latency is continuously measured and tracked. If degradation occurs on Slice 2 during Slice 1 stress, researchers must evaluate shared resource contention before attributing root causes.

---

## 6. Identified Implementation Gaps (Scripts & Automation)

To support the revised scenario framework without modifying code during this documentation phase, the following implementation gaps are formally documented:

1. **Scenario Preset Gap in `record_experiment.py` (`scripts/record_experiment.py` lines 49–59):**
   * *Gap:* `CANONICAL_PRESETS` currently contains entries for `S1`, `S2`, `S3`, `S6`, `S9`, `RECOVERY`, and `CLEAR` (with the old ID mapping). Scenarios `S3` through `S8` under the revised numbering, plus `S10_A` and `S10_B` presets that are no longer used, are misaligned with the current scenario IDs.
   * *Impact:* Running `record_experiment.py` with any unregistered scenario ID falls back to `event_domain = "CUSTOM"` and `event_component = "NONE"`. The presets must be updated on VM-6 to match the new scenario IDs: `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, `S9`, `CLEAR`.

2. **Dynamic Noise Parameter Control in `rfsim_channel_control.py`:**
   * *Gap:* `rfsim_channel_control.py` parses `noise_power_dB` during `show`, but lacks a CLI subcommand (`set-noise-power`) to adjust `noise_power_dB` dynamically via Telnet.
   * *Impact:* Noise calibration sweeps must currently be applied via configuration file edits and DU restarts.

3. **Channel Controller Reset Scope (`scripts/rfsim_channel_control.py` line 349):**
   * *Gap:* The `reset` subcommand only restores `path_loss_dB` (to $0.0\text{ dB}$ Profile 1 baseline). It does **not** restore `noise_power_dB`.
   * *Impact:* If noise was altered during testing, running `reset` will leave the noise parameter at its modified value.

4. **Post-Traffic Canary Observation & Probe Lifecycles in `trafgen.sh`:**
   * *Gap:* In `scripts/trafgen.sh`, parameter `DURATION` simultaneously determines the runtime of `iperf3 -u` (`-t "$DURATION"`), the display loop, and the ping probe packet counts. If the protocol requires observing quiescent recovery after traffic stops, extending `trafgen.sh` duration also extends iperf traffic.
   * *Impact:* Observability after traffic cessation requires launching canary ping probes with an independent lifecycle outside `trafgen.sh`.
