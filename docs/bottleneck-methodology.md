# Bottleneck Diagnosis & Comparative Baseline Methodology

This document defines the formal experimental methodology, comparative baseline specifications, and evaluation procedures for the thesis:

> **Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks**  
> *(Pengarahan Trafik Berbasis Identifikasi Bottleneck melalui Koordinasi O-RAN RIC–NWDAF dengan Kendali Closed-Loop pada Jaringan 5G Multi-Slice)*

---

## 1. Scientific Framework & Purpose of Baselines

In academic network systems research, proposing a novel coordination mechanism is insufficient without proving its superiority against standard and alternative operational paradigms. 

The core hypothesis is that **diagnosing the exact location of a network bottleneck (RAN vs. Core User Plane vs. Joint) prior to actuation significantly reduces SLA violations and recovery time** compared to uncoordinated or naive control loops.

To validate this hypothesis, the experimental testbed is configured to execute **five comparative baselines (B0 to B4)** alongside the **Proposed System**:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          SPEKTRUM PARADIGMA KENDALI JARINGAN                           │
├─────────────────┬──────────────────┬─────────────────┬────────────────┬────────────────┤
│       B0        │      B1 & B2     │       B3        │       B4       │    PROPOSED    │
│  Static Default │  Single-Domain   │   Decoupled /   │  Coordinated   │  Bottleneck-   │
│  (Tanpa RIC)    │  (RAN/Core Only) │  Uncoordinated  │ Naive / Fixed  │  Aware Closed  │
│                 │                  │                 │   Heuristic    │      Loop      │
└─────────────────┴──────────────────┴─────────────────┴────────────────┴────────────────┘
```

---

## 2. Detailed Baseline Matrix & Execution Guide

The following table details the operational definition, behavioral policy, and exact configuration required across the 6 VMs to execute each baseline:

### Summary Matrix

| Baseline ID | Paradigm | Decision Input | Actuation Scope | Weakness / Expected Failure Mode |
|---|---|---|---|---|
| **B0** | **Static 3GPP Default** | RSRP only (Standard A3 Event) | Standard 3GPP Handover | Completely blind to slice SLAs and Core congestion; no dynamic steering. |
| **B1** | **RAN-Only Control** | Radio metrics (PRB, CQI, RLC delay) | Inter-cell steering via E2SM-RC | **Core-Blind:** When Core UPF is congested, triggers futile handovers and ping-pong instability. |
| **B2** | **Core-Only Control** | Core metrics (UPF queue, packet loss) | Core user-plane rate shaping | **Radio-Blind:** Cannot mitigate radio channel degradation; cannot leverage alternative cells. |
| **B3** | **Decoupled Controllers** | Both domains monitored independently | Independent xApp & Core actions | **Conflicting Actions:** Both controllers act simultaneously without coordination, destabilizing QoS. |
| **B4** | **Coordinated (Fixed Heuristic)** | Aggregated cross-domain telemetry | Fixed action order (e.g., Handover $\rightarrow$ Shape) | **Ineffective Actions:** Tries wrong action first when bottleneck origin does not match fixed priority. |
| **PROPOSED** | **Bottleneck-Aware Closed-Loop** | Correlated RAN + Core Telemetry | Matched Action (RAN / Core / Joint) + SLA Verify | **Optimal Recovery:** Acts directly on root-cause domain; suppresses action churn via closed-loop feedback. |

---

### Baseline B0 — Static 3GPP Baseline (Standard Default)

* **Definition:** Standard 3GPP Rel-16/17 network slicing without dynamic RIC intervention. Each slice has fixed radio resource partitions, and handovers follow standard RRC A3 event thresholds ($RSRP_{target} - RSRP_{source} > \text{offset}$).
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** Stop/suspend the custom rApp service or do not create active A1 policy instances.
  2. **VM-2 (`near-rt-ric`):** Run the xApp in *monitor-only* mode (subscribes to E2SM-KPM for telemetry logging, but does NOT send E2SM-RC control requests).
  3. **VM-3 (`oai-5gc`):** UPF queues and bandwidth allocations remain static; no rate shaping.
  4. **VM-4 (`oai-ran`):** CU executes autonomous standard handover only if RSRP delta exceeds `handover_margin` configured in `cu_gnb.conf`.

---

### Baseline B1 — RAN-Only Control (Standalone xApp)

* **Definition:** An active Near-RT RIC xApp executes dynamic inter-cell traffic steering (Cell-1 $\leftrightarrow$ Cell-2) based solely on radio channel quality and PRB utilization per slice. The xApp operates without any policy guidance or visibility into the 5G Core.
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** Inactive or dispatches a static dummy A1 policy with unbounded thresholds.
  2. **VM-2 (`near-rt-ric`):** Enable xApp steering logic. If $PRB_{cell1}^{slice1} > 80\%$, the xApp issues E2SM-RC control requests to handover UE to Cell-2.
  3. **VM-3 (`oai-5gc`):** NWDAF / Core adapter is disabled or disconnected from RIC.
  4. **Test Observation:** When UPF-1 experiences congestion while radio is clear, B1 fails to detect the problem and does not trigger recovery, or triggers irrelevant handovers.

---

### Baseline B2 — Core-Only Control (NWDAF / User-Plane Adaptation)

* **Definition:** Network adaptation occurs strictly within the 5G Core domain. The Core adapter monitors UPF queue delay and packet loss via NWDAF, and applies dynamic traffic conditioning/shaping on user-plane flows without knowing radio conditions.
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** Disabled; no A1 policy generation.
  2. **VM-2 (`near-rt-ric`):** xApp set to monitor-only; inter-cell steering disabled.
  3. **VM-3 (`oai-5gc`):** Enable Core Adapter. If $Delay_{UPF} > \text{Threshold}$, the adapter applies traffic rate limiting on the offending slice container via Linux `tc`.
  4. **Test Observation:** When radio channel fades or Cell-1 PRBs are exhausted, B2 throttles user-plane traffic unnecessarily instead of offloading UEs to the available Cell-2.

---

### Baseline B3 — Decoupled / Independent Controllers (Uncoordinated)

* **Definition:** Both the RAN xApp (VM-2) and the Core Adapter (VM-3) are active simultaneously, but operate independently without sharing telemetry, policies, or coordination mechanisms.
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** Disabled; no cross-domain coordination.
  2. **VM-2 (`near-rt-ric`):** xApp actively executes radio steering based on local E2SM-KPM.
  3. **VM-3 (`oai-5gc`):** Core adapter actively executes traffic shaping based on local UPF metrics.
  4. **Test Observation:** In joint congestion scenarios, both controllers act concurrently, causing severe oscillations, high action churn, and uncoordinated SLA degradation.

---

### Baseline B4 — Coordinated Steering without Bottleneck Diagnosis (Fixed Heuristic)

* **Definition:** The rApp aggregates telemetry from both RAN and Core domains and coordinates both xApp and Core adapter. However, the decision logic uses a **rigid, hardcoded action priority** (e.g., Step 1: Always attempt inter-cell handover; Step 2: If SLA is still violated after $T$ seconds, apply Core shaping) **without diagnosing which domain actually caused the bottleneck**.
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** rApp receives both E2 and NWDAF telemetry.
  2. **VM-1 Decision Logic:** Disable the bottleneck classifier. Replace it with a fixed sequential heuristic:
     ```python
     # Fixed Heuristic Logic in B4:
     if sla_violated(slice):
       try_action_ran_handover()
       wait(evaluation_window)
       if sla_violated(slice):
         try_action_core_shaping()
```
  3. **Test Observation:** When a pure Core bottleneck occurs, B4 wastes one full evaluation window executing an ineffective radio handover before attempting Core mitigation, doubling the recovery time ($T_{rec}$).

---

### Proposed System — Bottleneck-Aware Closed-Loop Coordination

* **Definition:** The rApp continuously aggregates synchronized telemetry, executes an explainable classification engine to identify the root cause domain (`NORMAL`, `RAN`, `CORE`, `JOINT`), selects domain-matched actions, and verifies SLA recovery in a closed loop.
* **What to configure:**
  1. **VM-1 (`nonrt-ric`):** Full rApp enabled with Telemetry Aggregator, Bottleneck Classifier, Action Selector, and Closed-Loop SLA Verifier.
  2. **VM-2 (`near-rt-ric`):** xApp receives dynamic A1 policy constraints (`bottleneck_location`, target cell preference, and allowed action bounds).
  3. **VM-3 (`oai-5gc`):** Core adapter receives targeted shaping commands only when a Core or Joint bottleneck is diagnosed.
  4. **Closed-Loop Feedback:** If SLA is restored within the verification window, actions are stabilized; if ineffective, escalation or churn suppression is triggered.

---

## 3. Bottleneck Diagnosis Logic (The rApp Decision Engine)

The rApp diagnosis engine evaluates four operational states based on normalized telemetry features:

```text
                                  ┌────────────────────────┐
                                  │ Cross-Domain Telemetry │
                                  │ (RAN PRB + Core Delay) │
                                  └───────────┬────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         [RAN Congestion Detected?]                      [Core Congestion Detected?]
            (PRB > Th_ran OR CQI < 5)                      (Delay_upf > Th_core)
                      │                                               │
             YES ─────┴───── NO                              YES ─────┴───── NO
              │               │                               │               │
              ▼               ▼                               ▼               ▼
       ┌─────────────┐ ┌─────────────┐                 ┌─────────────┐ ┌─────────────┐
       │ Core Check  │ │ Core Check  │                 │  RAN Check  │ │  RAN Check  │
       └──────┬──────┘ └──────┬──────┘                 └──────┬──────┘ └──────┬──────┘
              │               │                               │               │
        YES ──┴── NO    YES ──┴── NO                    YES ──┴── NO    YES ──┴── NO
         │         │     │         │                     │         │     │         │
         ▼         ▼     ▼         ▼                     ▼         ▼     ▼         ▼
       JOINT      RAN   CORE    NORMAL                 JOINT     CORE   RAN    NORMAL
```

### Decision Table

| Diagnosed State | RAN Condition ($PRB, Delay_{rad}$) | Core Condition ($Delay_{upf}, Loss_{core}$) | Selected Matched Action |
|---|---|---|---|
| **`NORMAL`** | Below thresholds ($< 70\%$) | Below thresholds ($< 5\text{ ms}$) | Maintain current policy; log telemetry. |
| **`RAN_BOTTLENECK`** | High ($> 80\%$) or CQI degradation | Normal ($< 5\text{ ms}$, zero drop) | **Action A (RAN):** Authorize xApp inter-cell steering via A1; steer UE from Cell-1 to Cell-2. |
| **`CORE_BOTTLENECK`** | Normal / Moderate ($< 70\%$) | High queuing delay or packet drop | **Action B (Core):** Prohibit inter-cell handover (suppress churn); apply Core rate-limiting/shaping on non-priority slice. |
| **`JOINT_BOTTLENECK`** | High ($> 80\%$) | High queuing delay or packet drop | **Action C (Joint):** Coordinated radio admission throttling + Core user-plane backpressure mitigation. |
| **`UNCERTAIN`** | Telemetry timestamp delta $> \Delta T_{max}$ | Missing or stale reports | Hold previous action; suppress premature decisions until synchronized. |

---

## 4. Controlled Failure Injection Procedures

To conduct rigorous, repeatable experiments, the following fault injection methods are implemented:

### Scenario 1: Pure RAN Bottleneck Injection
* **Mechanism:** In VM-4 / VM-5, inject heavy background UDP traffic on Cell-1 (DU-1 port `:4043`) using `iperf3 -u -b 80M` targeting a dummy UE.
* **Effect:** Cell-1 PRB utilization spikes to $>90\%$, while UPF-1 processing delay remains $<3\text{ ms}$.

### Scenario 2: Pure Core User-Plane Bottleneck Injection
* **Mechanism:** In VM-3, apply traffic conditioning inside the `oai-upf-slice1` container using Linux `tc`:
  ```bash
  # Inject 50ms queuing delay and 10% packet drop on N6 interface
  docker exec -it oai-upf-slice1 tc qdisc add dev eth0 root netem delay 50ms loss 10%
  ```
* **Effect:** Radio link is pristine ($PRB < 30\%$, CQI 15), but end-to-end latency explodes to $>60\text{ ms}$ with severe packet loss.

### Scenario 3: Joint Bottleneck Injection
* **Mechanism:** Activate both Scenario 1 (RAN radio saturation on Cell-1) and Scenario 2 (`tc` delay on UPF-1) simultaneously.
* **Effect:** Both radio scheduler and Core user-plane queues are saturated.

### Scenario 4: Shifting Bottleneck (Dynamic Transition)
* **Mechanism:** 
  - $t = 0\text{s} - 60\text{s}$: Inject RAN bottleneck on Cell-1.
  - $t = 60\text{s}$: Clear RAN bottleneck, inject Core bottleneck on UPF-1.
  - $t = 120\text{s}$: Clear Core bottleneck, restore normal load.
* **Effect:** Tests the controller's ability to adapt when the failure location moves across domains.

---

## 5. Formal Evaluation Metrics

For each experimental run of duration $T$, metrics are computed per slice $s$:

### 1. SLA Violation Rate ($V_s$)
The proportion of evaluation observation windows where one or more SLA thresholds (latency, throughput) are violated:
$$V_s = \frac{\sum_{k=1}^{K} \mathbb{I}(\text{SLA violated in window } k)}{K} \times 100\%$$
where $K$ is the total number of evaluation windows and $\mathbb{I}(\cdot)$ is the indicator function.

### 2. Recovery Time ($T_{rec}$)
The duration between the injection of a bottleneck event $t_{inject}$ and the timestamp $t_{recover}$ where the slice SLA is continuously satisfied for at least $W$ consecutive windows:
$$T_{rec} = t_{recover} - t_{inject}$$

### 3. Macro-F1 Diagnosis Score
To validate the classification accuracy of the rApp diagnosis engine across all states:
$$\text{Macro-F1} = \frac{1}{|C|} \sum_{c \in C} \frac{2 \cdot P_c \cdot R_c}{P_c + R_c}$$
where $C = \{\text{NORMAL}, \text{RAN}, \text{CORE}, \text{JOINT}\}$, and $P_c, R_c$ are the precision and recall for class $c$.

### 4. Action Churn Rate ($C_{act}$)
The total number of policy alterations or handover actuations executed per minute:
$$C_{act} = \frac{N_{act}}{T_{\text{minutes}}}$$
A lower churn rate indicates a stable, non-oscillating control loop.
