# 3GPP & ETSI Regulatory Bottleneck Taxonomy

This document provides the formal regulatory and standardization reference for network bottleneck categorization in 5G Standalone (SA) and O-RAN systems, compiled in accordance with **3GPP Release 17** specifications published by **ETSI**.

---

## 1. Guiding Principle: Congestion vs. Utilization

In telecommunication standards, high resource utilization does not inherently constitute a bottleneck. In **3GPP TS 23.288 §6.8.2**, it is formally stated:

> *"Measurements of resource utilization (e.g., PRB or CPU usage) do not, by themselves, indicate the event of congestion or congestion levels."*

Therefore, a genuine operational bottleneck requires **high utilization coupled with observable service degradation**—such as accumulating queue depth, soaring latency, retransmissions, or packet drops.

---

## 2. Core Network Bottleneck Taxonomy (5GC & UPF)

The following taxonomy outlines specific bottleneck locations, behavioral signatures, relevant metrics, and official 3GPP standard references within the 5G Core domain:

| Domain Location | Specific Location / Bottleneck Type | Behavioral Characteristics & Symptoms | Relevant Metrics & Root Causes | 3GPP / ETSI Regulatory Specification |
|---|---|---|---|---|
| **Core User Plane** | **UPF — User-Plane Processing Capacity** | Internal processing delay in UPF increases; packet forwarding rate fails to keep up with incoming traffic even though transport links have remaining capacity. | **Metrics:** Internal UPF delay, NF CPU/Memory utilization, ingress/egress throughput.<br>**Causes:** Limited packet processing pipeline, CPU thread starvation, or compute container limits. | **3GPP TS 28.552 §5.4.5:** *"GTP packets delay in UPF"*.<br>**3GPP TS 23.288 §6.5.3:** NF resource usage analytics covering CPU, memory, and disk. |
| **Core User Plane** | **UPF — QoS Rate Limiting & Egress Capacity** | Throughput plateaus at configured maximum rate; queue backlog accumulates and packet drops surge when offered load exceeds service rate. | **Metrics:** Session-AMBR, MBR/MFBR, ingress vs. egress throughput, interface queue backlog bytes, drop rate.<br>**Causes:** QoS policy enforcement, Token Bucket Filter (TBF) rate shaper/policer, or egress port capacity. | **3GPP TS 23.501 §5.7.1.8:** Session-AMBR *"shall be enforced by the UPF"*.<br>**3GPP TS 29.244 §5.2.5:** QoS Enforcement Rule (QER) management in PFCP. |
| **Core Transport** | **N3 Interface (gNB–UPF) or N9 (Inter-UPF)** | Delay and packet drops increase on the transport segment, while internal NF processing delay remains nominal. | **Metrics:** Segment N3/N9 delay, link utilization, GTP-U transport volume, transport port queue/drops.<br>**Causes:** Constrained transport bandwidth or link contention. | **3GPP TS 28.552 §5.4.4.1:** *"Average round-trip N9 delay"*.<br>**3GPP TS 28.552 §5.4.7–§5.4.8:** Delay measurement procedures between NG-RAN and PSA UPF. |
| **Core Control Plane** | **AMF — Access & Mobility Signalling Overload** | Registration or NAS signalling requests delayed or rejected; NAS congestion control and access throttling activated. | **Metrics:** NAS/Registration request rate, procedure failure rate, AMF CPU load, OVERLOAD START/STOP messages.<br>**Causes:** Signalling volume exceeding AMF capacity. | **3GPP TS 23.501 §5.19.5.2:** *"AMF has reached overload situation"* (triggers NAS congestion control and N2 access restriction). |
| **Core Control Plane** | **SMF — Session Management Overload** | PDU session establishment or modification requests delayed or rejected; active sessions may remain unaffected. | **Metrics:** PDU session request rate, procedure latency, failure rate, SMF compute load.<br>**Causes:** SMF transaction processing capacity exhausted. | **3GPP TS 23.501 §5.19.6:** SMF overload resulting in *"rejections of NAS requests"*. |
| **Core Control Plane** | **UPF — PFCP / N4 Signalling Overload** | Processing of N4 session management transactions degraded; UPF requests control-plane to throttle incoming transactions. | **Metrics:** PFCP request rate, transaction response latency/timeout, Overload Control Information (OCI), Overload Reduction Metric.<br>**Causes:** Control-plane transaction load exceeding UPF PFCP processor. | **3GPP TS 29.244 §6.2.4.1–§6.2.4.3:** Overload control to reduce *"incoming signalling load"*. |
| **Core Control Plane** | **Service-Based Interface (SBI) Overload (PCF / UDM / NRF)** | API response latency spikes; HTTP requests rejected or timeout; dependent network procedures delayed. | **Metrics:** HTTP requests/sec, REST response latency, rejected requests, HTTP status codes 503/429.<br>**Causes:** Server capacity exhaustion on target NF. | **3GPP TS 29.500 §6.4.2–§6.4.3:** SBI overload control utilizing *"503 Service Unavailable"*, *"429 Too Many Requests"*, and OCI. |

*\* Note: The N3 interface crosses the RAN–Core boundary. In diagnostic classification, boundary demarcation must be established based on the specific port, link, or appliance experiencing the queue accumulation.*

---

## 3. Radio Access Network Bottleneck Taxonomy (NG-RAN & O-RAN)

In accordance with **3GPP TS 38.401 §3.1**, the split gNB architecture separates functions between the **gNB-DU** (housing RLC, MAC, and High-PHY) and the **gNB-CU-UP** (housing PDCP and SDAP):

| Domain Location | Specific Location / Bottleneck Type | Behavioral Characteristics & Symptoms | Relevant Metrics & Root Causes | 3GPP / ETSI Regulatory Specification |
|---|---|---|---|---|
| **RAN Radio Layer** | **gNB-DU MAC Scheduler — Radio Resource Exhaustion** | Service demands exceed available physical resource blocks; transmission queues/delays increase; throughput plateaus despite offered traffic. | **Metrics:** PRBs used vs. available (UL & DL), cell delivered throughput, active UE count, scheduling queue delay.<br>**Causes:** Excessive offered traffic or restricted radio bandwidth. | **3GPP TS 38.314 §4.2.1.6:** Distinct measurement of available PRBs and *"PRBs used for traffic transmission"* per cell. |
| **RAN Radio Layer** | **Air Interface (Uu) — Channel Condition Degradation** | Effective channel capacity collapses; retransmissions and required resource allocation per bit escalate; service fails to meet QoS demand. | **Metrics:** CQI, SINR, Modulation and Coding Scheme (MCS), BLER, HARQ retransmission count, throughput.<br>**Causes:** Radio interference, shadowing, multi-path fading, or pathloss. | **3GPP TS 38.300 §5.2.5.1 & §5.3.5.1:** Link adaptation mechanisms, including *"adaptive modulation and coding"*. |
| **RAN Layer 2** | **gNB-DU — RLC Queuing & MAC Service Bottleneck** | Packets queue extensively in the DU before transmission over the air; local DU packet drops escalate prior to RF transmission. | **Metrics:** RLC buffer occupancy, DU queuing delay, RLC SDU drop rate, MAC scheduling latency.<br>**Causes:** Ingress traffic exceeding DU transmission rate (due to radio constraints or scheduler stalls). | **3GPP TS 28.552 §5.1.3.2.2:** DU packet drops occurring *"due to high traffic load"*.<br>**3GPP TS 28.552 §5.1.3.3.3:** Downlink delay measurements in the DU. |
| **RAN Layer 2/3** | **gNB-CU-UP — PDCP Processing & Queuing** | Delays or packet drops occur within the CU-UP prior to forwarding over F1-U to the DU; radio PRB usage may remain low. | **Metrics:** CU-UP internal processing latency, PDCP SDU drop rate, CU-UP buffer depth.<br>**Causes:** High traffic volume, packet header processing bottleneck, or compute constraints. | **3GPP TS 28.552 §5.1.3.2.1:** *"DL PDCP SDU Drop rate"*.<br>**3GPP TS 28.552 §5.1.3.3.1:** Downlink delay definitions in the CU-UP. |
| **RAN Transport** | **F1-U Transport Interface (CU-UP ↔ DU)** | Packet loss and delay spikes concentrated strictly across the F1-U network segment, isolated from radio or internal node delay. | **Metrics:** F1-U packet loss rate, F1-U round-trip delay, link utilization, interface buffer depth.<br>**Causes:** Transport capacity constraints or network bridge contention. | **3GPP TS 28.552 §5.1.3.1.2–§5.1.3.1.3:** F1-U packet loss measurements.<br>**3GPP TS 28.552 §5.1.3.3.2:** Downlink delay measurements on F1-U. |
| **RAN Compute** | **Host / VM / Container Compute Exhaustion** | Packet processing stalls despite ample radio and transport bandwidth. Critical in virtualized/software-defined RAN (vRAN / O-RAN). | **Metrics:** CPU utilization, memory pressure, context switch latency, process cycle time, throughput.<br>**Causes:** Compute resource starvation or thread contention on the host CPU. | **3GPP TS 23.288 §6.6.3, Table 6.6.3-1:** gNB NF resource usage analytics covering *"CPU, memory, disk"*. |
| **O-RAN Fronthaul** | **Open Fronthaul (O-DU ↔ O-RU) — Timing & Transport Constraints** | IQ sample packets arrive outside the reception window; jitter and transport delays exceed strict timing budgets. | **Metrics:** Fronthaul delay and variation, early/late packet count, fronthaul bandwidth saturation.<br>**Causes:** Transport queue delays or clock synchronization drift. | **ETSI TS 103 859 V12.0.1 §4.4–§4.5:** *"Reception window monitoring"*. |

---

## 4. Priority Scenarios for Multi-Slice Thesis Evaluation

For the scope of **Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination**, four primary bottleneck locations are prioritized for experimental fault injection:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PRIORITIZED BOTTLENECK EXPERIMENT MATRIX                             │
├────────────────────┬────────────────────────────────────┬──────────────────────────────────────────────┤
│ Prioritized Domain │ 3GPP Regulatory Location           │ Testbed Emulation Mechanism & Instrumentation│
├────────────────────┼────────────────────────────────────┼──────────────────────────────────────────────┤
│ 1. RAN (Radio)     │ gNB-DU MAC Scheduler (TS 38.314)   │ Offered load saturation (40M > 25M capacity) │
│                    │                                    │ $\rightarrow$ NPRB reaches 106 (100% PRB)     │
├────────────────────┼────────────────────────────────────┼──────────────────────────────────────────────┤
│ 2. RAN (Channel)   │ Air Interface Uu Fading (TS 38.300)│ RFsimulator attenuation / pathloss drop       │
│                    │                                    │ $\rightarrow$ MCS drops, BLER escalates      │
├────────────────────┼────────────────────────────────────┼──────────────────────────────────────────────┤
│ 3. Core (Egress)   │ UPF QoS Enforcement (TS 23.501)    │ Linux `tc tbf` on UPF-1 container `eth0`     │
│                    │                                    │ $\rightarrow$ Backlog ~300 KB, Drops >1000/s │
├────────────────────┼────────────────────────────────────┼──────────────────────────────────────────────┤
│ 4. Core (Process)  │ UPF GTP Packet Delay (TS 28.552)   │ UPF CPU throttling or N3 `tc netem delay`    │
│                    │                                    │ $\rightarrow$ GTP forwarding delay spikes    │
└────────────────────┴────────────────────────────────────┴──────────────────────────────────────────────┘
```

### Strategic Alignment with Research Hypothesis
* **When Bottleneck is in Domain 1 or 2 (RAN):**
  Actuating an **E2SM-RC handover from Cell-1 to Cell-2** effectively mitigates the congestion, restoring user QoS.
* **When Bottleneck is in Domain 3 or 4 (Core):**
  Triggering an inter-cell handover is **completely futile** because both cells terminate in the congested UPF. The proper actuation is **Core QoS rate-shaping or slice admission adaptation**.
* **When Bottleneck is Joint:**
  Both controllers must coordinate to execute radio offloading alongside Core user-plane backpressure mitigation.
