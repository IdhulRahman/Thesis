# Experimental Scenarios & Disturbance Registry

**Authoritative Specification:** Single Source of Truth for Scenario Definitions, Treatment Parameters, and Response Hypotheses  
**Target Architecture:** VM-5 (UE Emulation), VM-4 (Split RAN), VM-3 (UPF Core Host), VM-6 (Telemetry Collector & Recorder)  
**Classification Target Classes:** `BASELINE`, `RAN`, `CORE`, `JOINT`  
**Treatment Scenario Identifiers:** `S1`, `S2`, `S3`, `S4`, `S6`, `S9`, `S10`, `CLEAR`

---

> [!IMPORTANT]
> **Status Notice on Parameters & Execution Scope:**
> * All numeric parameter values listed herein (offered loads, attenuation levels, TBF rates, durations) represent **candidates for upcoming calibration**, NOT final static constants, standard mandates, or newly verified runtime measurements.
> * Operational commands are documented strictly as **planned procedures for future execution** following calibration. No experiments, traffic runs, or runtime VM alterations are performed during this documentation revision.
> * Four epistemic categories must be maintained without conflation:
>   1. **Committed Configurations:** Formally recorded in repository files (Profile 1: 51 PRBs, SCS 30 kHz, `-E`, `chanmod`, unity gain 0.0 dB, noise -100.0 dB; Profile 2: 106 PRBs baseline comparator).
>   2. **Historical Empirical Evidence:** Supported by documented test sessions (e.g., Case 55 dilation on 106 PRBs, Case 56 real-time calibration on 51 PRBs).
>   3. **Proposed Parameters:** Candidates awaiting experimental calibration (e.g., noise grid -40 to -20 dB, S3 load 15–20 Mbps, S6 TBF 5–6 Mbps).
>   4. **Runtime Conditions:** Live state of VM processes, softmodems, and network links requiring verification at the time of execution.

---

## 1. Classification Targets vs. Experimental Treatment Identifiers

In this research, machine learning models (NWDAF AnLF and Near-RT RIC xApp) are trained to classify the network state into four discrete operational classes:

$$\mathcal{C} = \{\text{BASELINE}, \text{RAN}, \text{CORE}, \text{JOINT}\}$$

The experimental Scenario IDs (`S1`, `S2`, `S3`, `S4`, `S6`, `S9`, `S10`) serve as **treatment scenario identifiers** to systematically induce distinct physical phenomena. Their count does not correspond 1:1 with the four classification target classes:
* **`BASELINE` Target Class:** Evaluated under `S1` (Light Normal) and `S2` (Higher Normal), verifying that varying traffic volume without capacity exhaustion remains classified as healthy baseline.
* **`RAN` Target Class:** Evaluated under `S3` (Radio Resource Saturation under reference channel) and `S4` (Radio Channel Degradation via added attenuation under fixed traffic).
* **`CORE` Target Class:** Evaluated under `S6` (UPF egress rate limiting via Token Bucket Filter).
* **`JOINT` Target Class:** Evaluated under `S9` (Simultaneous radio degradation and binding core transport throttling).
* **Transitional / Multi-Phase Sequence:** Evaluated under `S10` (Staged recovery across two distinct sequences). **A multi-phase recording covering sequential state transitions must NOT be assigned a single static class label.**
* **Operational Reset Action (`CLEAR`):** `CLEAR` is an **operational reset and baseline recovery procedure**, NOT an additional training class.

---

## 2. Canonical Scenario Registry (Candidate Parameters for Calibration)

The table below outlines the planned treatment matrix. Parameter values represent proposed operating candidates to be calibrated during pilot testing:

| Scenario ID | Treatment Identifier | Target Class | Physical Target Component | Planned Treatment Mechanism | Candidate Calibration Values *(Proposed, Pending Calibration)* | Hypothesized Response & Evidence to Examine |
|---|---|:---:|---|---|---|---|
| **`CLEAR`** | `CLEAR_FAULT` | *Action Only* | All components | Operational baseline restoration | Remove TBF; reset RF attenuation to 0.0 dB baseline; traffic nominal | Sender–receiver match, UPF backlog 0 B, radio link nominal. |
| **`S1`** | `S1_NORMAL_LIGHT` | `BASELINE` | None (Reference) | Light baseline traffic on reference channel | Offered load $\approx 5\text{ Mbps}$, reference channel, no Core limiter | Sender–receiver throughput parity, stable RTT, zero UPF backlog, healthy session. |
| **`S2`** | `S2_NORMAL_HIGH` | `BASELINE` | None (Reference) | Higher baseline traffic without bottleneck | Offered load $\approx 10\text{–}12\text{ Mbps}$, reference channel, no Core limiter | Traffic demand fully served, elevated PRB grant proxy, zero UPF backlog, no queue inflation. |
| **`S3`** | `S3_RAN_OVERLOAD` | `RAN` | gNB DU-1 (Cell-1) | Radio capacity saturation under reference channel | Fixed load selected via capacity calibration (candidates: $15, 18, 20\text{ Mbps}$) | Receiver throughput lags sender; duration delta $\Delta t > 0$; high PRB grant proxy; empty UPF backlog ($0\text{ B}$). BLER may remain low. |
| **`S4`** | `S4_RAN_DEGRADATION`| `RAN` | DU-1 Uplink (`rfsimu_channel_ue0`) | Channel quality degradation under fixed load | Fixed load ($\approx 10\text{ Mbps}$), fixed reference noise, injected UL attenuation ($5\text{–}16\text{ dB}$) | Collapsing SNR, downward link adaptation (lower MCS), elevated BLER / HARQ rounds, unserved traffic demand. UPF backlog remains $0\text{ B}$. |
| **`S6`** | `S6_CORE_QUEUE_TBF` | `CORE` | UPF-1 Egress (`eth0`) | UPF-host/container egress rate shaping | Fixed load ($\approx 10\text{ Mbps}$), binding TBF rate ($5\text{–}6\text{ Mbps}$, latency $200\text{ ms}$) | UPF queue backlog surges, packet drops increase, egress rate matches TBF, radio metrics unconstrained (nominal PRB, high SNR). |
| **`S9`** | `S9_JOINT_OVERLOAD` | `JOINT` | DU-1 UL + UPF-1 Egress | Simultaneous active radio impairment and binding Core shaping | Degraded radio channel forwarding rate $R_{\text{arr}}$ + binding TBF rate ($R_{\text{TBF}} < R_{\text{arr}}$) | Simultaneous evidence of radio degradation (low SNR/MCS, elevated BLER) AND Core congestion (elevated UPF backlog and drops). |
| **`S10`** | `S10_STAGED_RECOVERY`| *Multi-Phase* | DU-1 UL + UPF-1 Egress | Staged impairment release across two distinct sequences | Sequence A: JOINT $\to$ CORE $\to$ BASELINE<br>Sequence B: JOINT $\to$ RAN $\to$ BASELINE | Dynamic phase transitions, telemetry response latencies, and cross-domain recovery decoupling. |

---

## 3. Detailed Specifications per Scenario

### 3.1 Scenario S1 — Normal Light Baseline
1. **Objective:** Establish the healthy reference operating state of the end-to-end network under light traffic demand.
2. **Initial Conditions:** Testbed restored to reference configuration (Profile 1: DU-1 51 PRBs, SCS 30 kHz, `-E`, `chanmod` active with calibrated baseline path loss $0.0\text{ dB}$ and reference noise; DU-2 active comparator; UPF-1/UPF-2 running with standard `pfifo_fast` or unshaped `tc qdisc`).
3. **Independent Variables (Changed):** Injected offered traffic on Slice 1 set to candidate $\approx 5\text{ Mbps}$ UDP.
4. **Controlled Variables (Maintained):** Reference radio channel parameters, unshaped Core egress, Slice 2 canary ping (100 ms interval).
5. **Planned Execution Sequence:**
   ```bash
   # Planned procedure (to be executed during future testing):
   # VM-5: Launch light traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 5
   # VM-6: Record baseline dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 180 --notes "S1 Normal Light Reference"
   ```
6. **Evidence to Collect:** Telemetry CSV (`telemetry_*.csv`), sender/receiver iperf JSON logs, UE-1 and UE-2 ping logs, SFN clock progress ratio.
7. **Responses to Examine:** Sender offered rate matches receiver goodput ($G_{\text{rx}} \approx R_{\text{tx}}$), sender–receiver duration difference $\Delta t \approx 0$, ICMP RTT within healthy bounds ($< 25\text{ ms}$), zero UPF queue backlog and drops, stable SFN progress ($1.05\times - 1.09\times$).
8. **Interpretation Boundaries:** Observation of healthy metrics confirms baseline stability for the session, but does not guarantee immunity from transient hypervisor scheduling jitter.

---

### 3.2 Scenario S2 — Normal Higher Baseline
1. **Objective:** Distinguish high non-congested traffic load from genuine system bottlenecks, ensuring that elevated resource usage alone is not misclassified as a fault.
2. **Initial Conditions:** System at reference condition; previous scenario treatments cleared.
3. **Independent Variables (Changed):** Injected offered load increased to candidate $\approx 10\text{–}12\text{ Mbps}$ UDP (calibrated below radio saturation ceiling).
4. **Controlled Variables (Maintained):** Reference channel conditions, unshaped Core egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Planned procedure:
   # VM-5: Launch higher non-congested traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # VM-6: Record higher baseline dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S2 --duration 180 --notes "S2 Normal Higher Baseline"
   ```
6. **Evidence to Collect:** Telemetry CSV, iperf sender and receiver logs, canary ping logs.
7. **Responses to Examine:** Higher PRB grant proxy ($N_{\text{PRB}} / 51 \times 100\%$), while receiver throughput continues to match offered load without backlog accumulation at UPF ($0\text{ B}$) and without excessive duration delta ($\Delta t \approx 0$).
8. **Interpretation Boundaries:** The label `BASELINE` is strictly conditional on future empirical results confirming that traffic demand is fully served without unserved backlog. Candidate $12\text{ Mbps}$ is an operating proposal; if capacity calibration reveals queue onset at $12\text{ Mbps}$, the load must be adjusted downward.

---

### 3.3 Scenario S3 — RAN Overload (Traffic Saturation)
1. **Objective:** Observe radio service limitations and bottleneck signatures caused purely by traffic demand exceeding available air-interface capacity under clean/reference radio conditions.
2. **Initial Conditions:** Reference radio channel (no added attenuation, reference noise); unshaped UPF egress.
3. **Independent Variables (Changed):** Offered load set to a fixed saturation value selected via prior pilot calibration (candidate evaluation grid: $15, 18, 20\text{ Mbps}$).
4. **Controlled Variables (Maintained):** Reference RF propagation parameters, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Planned procedure (using fixed load determined from capacity pilot, e.g., 20 Mbps):
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 20
   python3 /opt/oran/monitoring/scripts/record_experiment.py S3 --duration 180 --notes "S3 RAN Overload Capacity Saturation"
   ```
6. **Evidence to Collect:** Telemetry CSV, iperf receiver delivery logs (arrival goodput), UE-1 in-band RTT logs, UE-2 cross-slice canary logs, SFN progress audit.
7. **Responses to Examine:** Receiver throughput capped below offered load ($G_{\text{rx}} < R_{\text{tx}}$); positive receiver–sender duration difference ($\Delta t > 0$); instantaneous PRB grant proxy saturating near $100\%$ ($N_{\text{PRB}} \to 51$); Core UPF queue backlog remains zero ($0\text{ B}$).
8. **Interpretation Boundaries:**
   * High PRB grant proxy indicates full scheduling grant allocation per TTI, but does not alone prove a bottleneck without evidence of unserved traffic demand, latency inflation, or goodput shortfall.
   * Under clean channel conditions, **BLER can legitimately remain low ($\approx 0\%$) and MCS remain high**, because capacity exhaustion is a scheduling volume limit, not RF corruption. Overload must not be rejected merely because BLER is low.

---

### 3.4 Scenario S4 — RAN Channel Degradation (RF Impairment)
1. **Objective:** Observe network behavior when air-interface performance degrades due to physical wireless propagation impairment under fixed moderate traffic load.
2. **Initial Conditions:** Reference channel baseline ($0.0\text{ dB}$); fixed moderate traffic demand ($\approx 10\text{ Mbps}$) that is fully served under reference conditions.
3. **Independent Variables (Changed):** Injected Uplink path attenuation on DU-1 Channel 1 (`rfsimu_channel_ue0`) via Telnet controller while maintaining reference noise power constant.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Core UPF unshaped egress, Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Planned procedure:
   # 1. VM-5: Launch fixed moderate traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # 2. VM-4: Inject Uplink path attenuation (candidate: 12 dB) and verify readback
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 12.0 --channel-id 1 --port 9090
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py show --port 9090
   # 3. VM-6: Record RAN impairment dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S4 --duration 180 --notes "S4 RAN Channel Degradation 12dB Attenuation"
   # 4. VM-4: Restore reference channel baseline
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
6. **Evidence to Collect:** Telemetry CSV (NPRB, SNR, MCS, BLER), Telnet command/readback logs, iperf receiver logs, softmodem logs.
7. **Responses to Examine:** Decreased Uplink SNR; downward link adaptation (lower MCS index); increased BLER and HARQ retransmissions (`ulsch_rounds`); throughput deficit at receiver; zero UPF backlog ($0\text{ B}$).
8. **Interpretation Boundaries:**
   * Target channel model identity (`rfsimu_channel_ue0` for Channel 1 UL) must be verified via explicit readback.
   * If attenuation induces softmodem assertion crashes or process termination, this must be logged as a **testbed operational boundary failure**, NOT as an acceptable training sample of radio congestion.
   * Specific BLER, MCS, or SNR numerical thresholds are behavioral hypotheses, not strict prerequisites.

---

### 3.5 Scenario S6 — Core Transport Bottleneck (UPF Egress Shaping)
1. **Objective:** Observe system telemetry and end-to-end performance degradation when the bottleneck resides strictly in the Core Network user plane transport queue.
2. **Initial Conditions:** Radio channel at healthy reference condition (capable of fully forwarding the offered load); UPF-1 container running with default qdisc.
3. **Independent Variables (Changed):** Linux Token Bucket Filter (`tbf`) configured on the egress interface of UPF-1 (`oai-upf-slice1` container `eth0`, facing EXT-DN).
4. **Controlled Variables (Maintained):** Clean radio channel (51 PRBs, unity gain, reference noise), offered load ($\approx 10\text{ Mbps}$), Slice 2 canary probing.
5. **Planned Execution Sequence:**
   ```bash
   # Planned procedure:
   # 1. VM-3: Apply binding egress rate shaping on UPF-1 container
   # Terminology: UPF-host/container egress shaping
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 5mbit burst 10kb latency 200ms
   # Verify qdisc readback:
   sudo docker exec oai-upf-slice1 tc -s qdisc show dev eth0
   # 2. VM-5: Launch traffic exceeding TBF rate
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # 3. VM-6: Record Core bottleneck dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S6 --duration 180 --notes "S6 Core Bottleneck UPF-1 TBF 5Mbps"
   # 4. VM-3: Remove shaping after session
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
6. **Evidence to Collect:** Telemetry CSV (`upf_backlog_bytes_slice1`, `upf_drops_slice1`), `tc -s qdisc` readback logs, iperf receiver throughput and packet loss logs, in-band RTT.
7. **Responses to Examine:** UPF queue backlog accumulation (`upf_backlog_bytes_slice1 > 0`); surge in kernel packet drops (`upf_drops_slice1`); receiver goodput throttled near TBF rate ($\approx 5\text{ Mbps}$); radio telemetry remains unconstrained (nominal PRB grant proxy, high SNR, high MCS, BLER $\approx 0\%$).
8. **Interpretation Boundaries:**
   * Terminology must consistently specify **UPF-host/container egress shaping**.
   * Shaping binds on traffic exiting UPF-1 towards EXT-DN across interface `eth0`.
   * Radio path must be independently verified as capable of serving the offered load, ensuring the bottleneck is isolated to the Core.

---

### 3.6 Scenario S9 — Joint RAN & Core Bottleneck
1. **Objective:** Evaluate telemetry signatures and detection capabilities when distinct impairments simultaneously affect both the Radio Access Network and Core Network user plane.
2. **Initial Conditions:** Reference configuration; previous scenario treatments cleared.
3. **Independent Variables (Changed):**
   * RAN impairment: Injected Uplink path attenuation on Channel 1 (S4 condition).
   * Core impairment: Egress TBF shaping applied on UPF-1 `eth0`.
4. **Controlled Variables (Maintained):** Offered load ($\approx 10\text{ Mbps}$), reference noise power, Slice 2 canary probing.
5. **Architectural Precedence & Binding Condition:**
   > [!IMPORTANT]
   > In Uplink data flow, packets traverse the air interface before arriving at the Core UPF:
   > $$\text{UE} \xrightarrow{\text{Air Interface (RAN)}} \text{gNodeB DU-1/CU} \xrightarrow{\text{N3 / GTP-U}} \text{UPF-1} \xrightarrow{\text{N6 / } \texttt{eth0}} \text{EXT-DN}$$
   > If radio degradation throttles delivered throughput entering the UPF to $R_{\text{arr}}$ (e.g., $7\text{ Mbps}$), an egress TBF configured at $12\text{ Mbps}$ will **never be reached**, leaving Core queue buffers empty ($0\text{ B}$) and causing the joint fault to degenerate into a single-domain RAN fault.
   > **Binding Requirement:** The UPF TBF rate ($R_{\text{TBF}}$) must be calibrated **strictly below** the degraded radio forwarding rate ($R_{\text{arr}}$) for both bottlenecks to bind simultaneously (e.g., $R_{\text{offered}} = 10\text{ Mbps}$, radio throttles to $R_{\text{arr}} \approx 7\text{ Mbps}$, and TBF limits egress to $R_{\text{TBF}} \approx 4\text{ Mbps}$).
6. **Planned Execution Sequence:**
   ```bash
   # Planned procedure:
   # 1. VM-4: Apply radio attenuation (e.g., 10 dB on UL Channel 1)
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 10.0 --channel-id 1 --port 9090
   # 2. VM-3: Apply binding egress TBF on UPF-1 (e.g., 4 Mbps)
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms
   # 3. VM-5: Launch traffic
   sudo /opt/oran/ue/scripts/trafgen.sh start 300 10
   # 4. VM-6: Record Joint bottleneck dataset
   python3 /opt/oran/monitoring/scripts/record_experiment.py S9 --duration 180 --notes "S9 Joint Overload Binding RAN and Core"
   # 5. Cleanup both domains
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
7. **Evidence to Collect:** Telemetry CSV showing simultaneous radio degradation features and Core queue features; iperf receiver logs; qdisc readback.
8. **Responses to Examine:** Simultaneous presence of:
   * Radio domain signatures: degraded SNR, lower MCS, elevated BLER / retransmissions.
   * Core domain signatures: non-zero UPF queue backlog (`upf_backlog_bytes_slice1 > 0`) and elevated packet drops.
9. **Interpretation Boundaries:** True Joint classification requires verified empirical evidence of binding congestion in both domains. If UPF queue remains empty, the condition is not empirically Joint.

---

### 3.7 Scenario S10 — Staged Multi-Phase Recovery Sequences
1. **Objective:** Evaluate dynamic transition behavior, telemetry reporting latencies, and cross-domain diagnostic decoupling as impairments are removed sequentially.
2. **Initial Conditions:** Simultaneous active impairments (Joint condition as established in S9).
3. **Execution Sequences:** To avoid order bias, S10 evaluates two counterbalanced sequences:
   * **Sequence A (Radio First):**
     $$\text{JOINT} \xrightarrow{\text{Restore Radio}} \text{CORE} \xrightarrow{\text{Release TBF}} \text{BASELINE}$$
     1. Phase 1 (Joint): Radio attenuation active + UPF TBF active (~120s proposed).
     2. Phase 2 (Core Only): Radio attenuation reset to baseline ($0.0\text{ dB}$); UPF TBF remains active (~120s proposed).
     3. Phase 3 (Baseline): UPF TBF deleted; system operating clean (~120s proposed).
   * **Sequence B (Core First):**
     $$\text{JOINT} \xrightarrow{\text{Release TBF}} \text{RAN} \xrightarrow{\text{Restore Radio}} \text{BASELINE}$$
     1. Phase 1 (Joint): Radio attenuation active + UPF TBF active (~120s proposed).
     2. Phase 2 (RAN Only): UPF TBF deleted; radio attenuation remains active (~120s proposed).
     3. Phase 3 (Baseline): Radio attenuation reset to baseline ($0.0\text{ dB}$); system operating clean (~120s proposed).
4. **Planned Execution Sequence (Illustration for Sequence A):**
   ```bash
   # Planned procedure:
   # Step 1: Establish Joint Stress
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 10.0 --channel-id 1 --port 9090
   sudo docker exec oai-upf-slice1 tc qdisc replace dev eth0 root tbf rate 4mbit burst 10kb latency 200ms
   sudo /opt/oran/ue/scripts/trafgen.sh start 450 10
   # Step 2: Record continuous run with manual phase logging
   python3 /opt/oran/monitoring/scripts/record_experiment.py S10 --duration 360 --notes "S10 Staged Recovery Sequence A"
   # At t = 120s: Reset radio
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   # At t = 240s: Clear Core TBF
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root
   ```
5. **Evidence to Collect:** Continuous high-resolution CSV, phase transition timestamp logs, receiver goodput traces, canary ping traces across transitions.
6. **Responses to Examine:** Telemetry recovery latency per domain ($T_{\text{rec,RAN}}$ vs $T_{\text{rec,Core}}$); time lag between physical impairment removal and telemetry indicator settling; verification that clearing one domain does not cause false degradation in the other.
7. **Interpretation Boundaries:**
   * **Labeling Rule:** The recording must NOT be stamped with a single uniform class label. Each phase must be annotated with its corresponding ground-truth regime (`JOINT` for Phase 1, `CORE` or `RAN` for Phase 2, `BASELINE` for Phase 3).
   * Transition boundaries must account for physical drainage delays (e.g. queue drainage time $\Delta t$) before scoring state classification.

---

### 3.8 Operational Reset Procedure (`CLEAR`)
1. **Objective:** Deterministically restore all radio, Core, and traffic components to the unperturbed baseline state between experimental runs.
2. **Operational Scope:** `CLEAR` is strictly an operational recovery procedure and maintenance action; **it is NOT a machine learning training class**.
3. **Execution Commands:**
   ```bash
   # Planned reset procedure:
   # 1. VM-3: Remove all qdisc rate limiting on UPF-1
   sudo docker exec oai-upf-slice1 tc qdisc del dev eth0 root 2>/dev/null || true
   # 2. VM-4: Reset all RFSimulator channel parameters to verified Profile 1 baseline
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   # 3. VM-5: Terminate any residual traffic processes
   sudo /opt/oran/ue/scripts/trafgen.sh stop
   ```
4. **Readback Verification:** Verify via `rfsim_channel_control.py show` that path loss is $0.0\text{ dB}$, and via `tc -s qdisc show dev eth0` that UPF-1 is in default unshaped state.

---

## 4. Multi-Slice Context & Canary Isolation Policy

The experimental testbed operates a dual-slice architecture:
* **Slice 1 (eMBB):** Serving cell DU-1 (Cell-1, Port 4043, 51 PRBs, 20 MHz); Core UPF-1 (`oai-upf-slice1`, SST 1, SD 0x000001); generates primary data workload.
* **Slice 2 (URLLC):** Serving cell DU-2 (Cell-2, Port 4044, 106 PRBs, 40 MHz); Core UPF-2 (`oai-upf-slice2`, SST 222, SD 0x00007B); generates periodic 100 ms canary probe (`ping`).

**Canary Integrity Principle:**  
Because Slice 2 operates over independent radio instances, separate PRB pools, and a dedicated UPF container, treatments applied to Slice 1 (radio attenuation on DU-1 or egress TBF on UPF-1) must **NOT degrade Slice 2 canary latency** under proper slice isolation. Degradation on Slice 2 during Slice 1 stress indicates hypervisor CPU starvation or testbed infrastructure contention, which must be logged as testbed interference rather than normal intra-slice queuing.

---

## 5. Identified Implementation Gaps (Scripts & Automation)

To support the revised scenario framework without modifying code during this documentation phase, the following implementation gaps are formally documented:

1. **Scenario Preset Gap in `record_experiment.py` (`scripts/record_experiment.py` lines 49–59):**
   * *Gap:* `CANONICAL_PRESETS` contains `S1`, `S2`, `S3`, `S6`, `S9`, `S10_A`, `S10_B`, `RECOVERY`, and `CLEAR`. Scenario `S4` (`S4_RAN_DEGRADATION`) is not defined in the presets dictionary.
   * *Impact:* Running `record_experiment.py S4` will raise a dictionary lookup error or fall back to unknown event labels unless invoked with custom flag overrides or until `CANONICAL_PRESETS` is updated.
2. **Multi-Phase Dynamic Annotation Gap in `record_experiment.py`:**
   * *Gap:* `record_experiment.py` applies static scenario and domain labels (`event_scenario`, `event_domain`) across the entire recording duration.
   * *Impact:* For `S10` multi-phase staged recovery, the recorder cannot dynamically switch phase labels mid-run without external orchestration or manual segment concatenation.
3. **Dynamic Noise Parameter Control in `rfsim_channel_control.py` (`scripts/rfsim_channel_control.py`):**
   * *Gap:* `rfsim_channel_control.py` parses `noise_power_dB` during `show`, but lacks a CLI subcommand to adjust `noise_power_dB` dynamically via Telnet.
   * *Impact:* Noise calibration sweeps must either be applied via configuration file edits and DU restarts, or an enhanced Telnet command must be verified in future script updates.
