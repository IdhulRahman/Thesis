# Cross-Domain Bottleneck Research Taxonomy Mapped to 3GPP & ETSI Specifications

**Authoritative Specification:** Theoretical & Standardized Taxonomy of Bottleneck Locations  
**Standard References:** 3GPP TS 23.288, TS 28.552, TS 23.501, TS 38.314, TS 38.401, ETSI TS 103 859  
**Academic Role:** Conceptual Grounding for Closed-Loop Bottleneck Diagnosis in 5G & O-RAN Networks

---

## 1. Guiding Principle: Resource Utilization vs. Operational Congestion

In telecommunication networks, elevated resource utilization does not inherently constitute an operational bottleneck. As formally articulated in **3GPP TS 23.288 Clause 6.8.2**:

> *"Measurements of resource utilization (e.g., PRB or CPU usage) do not, by themselves, indicate the event of congestion or congestion levels."*

A genuine operational bottleneck requires **high utilization coupled with observable, adverse quality-of-service degradation**—such as escalating buffer queue depths, latency spikes, packet drops, or application-layer throughput throttling. The taxonomy below outlines the architectural locations where bottlenecks manifest across 5G Core and O-RAN domains.

---

## 2. 5G Core Domain Bottleneck Taxonomy

| Domain Location | Specific Location / Bottleneck Type | Behavioral Characteristics & Symptoms | Relevant Metrics & Root Causes | 3GPP / ETSI Regulatory Specification |
|---|---|---|---|---|
| **Core User Plane** | **UPF Processing Pipeline Saturation** | Internal packet processing delay within UPF escalates; packet forwarding rate plateaus while transport links have spare capacity. | **Metrics:** Internal UPF delay, vCPU utilization, ingress/egress rate.<br>**Causes:** Thread starvation, packet header parsing overhead, container CPU limits. | **3GPP TS 28.552 §5.4.5:** *"GTP packets delay in UPF"*.<br>**3GPP TS 23.288 §6.5.3:** NF resource usage analytics. |
| **Core User Plane** | **UPF QoS Rate Limiting & Egress Backpressure** | Egress throughput is clamped at maximum bitrate; queue backlog accumulates and packet drops surge as offered load exceeds service rate. | **Metrics:** Session-AMBR, MFBR, interface queue backlog bytes (`tc qdisc`), packet drop rate.<br>**Causes:** QoS policy enforcement, Token Bucket Filter (TBF) policing, egress port saturation. | **3GPP TS 23.501 §5.7.1.8:** Session-AMBR enforcement in UPF.<br>**3GPP TS 29.244 §5.2.5:** QoS Enforcement Rules (QER). |
| **Core Transport** | **N3 Interface (gNB $\to$ UPF) or N9 (Inter-UPF)** | Segment latency and packet drops increase on the physical or virtual bridge link, while internal UPF compute latency remains nominal. | **Metrics:** N3/N9 RTT, transport bridge drop counters, link bandwidth saturation.<br>**Causes:** Intermediate network switch buffer overflow or link contention. | **3GPP TS 28.552 §5.4.4.1:** *"Average round-trip N9 delay"*.<br>**3GPP TS 28.552 §5.4.7–§5.4.8:** Transport delay measurements. |
| **Core Control Plane**| **AMF Signaling Overload** | NAS signaling and registration requests delayed or rejected; access throttling and back-off timers activated. | **Metrics:** Registration attempt rate, procedure failure rate, AMF CPU load, OVERLOAD START/STOP.<br>**Causes:** Signaling storms exceeding AMF transaction capacity. | **3GPP TS 23.501 §5.19.5.2:** AMF overload control and N2 access restriction. |
| **Core Control Plane**| **SMF Session Management Overload** | PDU session establishment or modification requests delayed or rejected; established sessions continue forwarding normally. | **Metrics:** PDU session request rate, establishment latency, failure rate.<br>**Causes:** Transaction state machine processing exhaustion. | **3GPP TS 23.501 §5.19.6:** SMF overload management. |
| **Core Control Plane**| **UPF PFCP / N4 Signaling Overload** | Processing of N4 session management transactions degraded; UPF triggers control-plane throttling via Overload Control Information (OCI). | **Metrics:** PFCP transaction response latency, timeouts, Overload Reduction Metric.<br>**Causes:** Control-plane transaction load exceeding UPF PFCP parser. | **3GPP TS 29.244 §6.2.4.1–§6.2.4.3:** Overload control on PFCP. |

---

## 3. Radio Access Network (NG-RAN & O-RAN) Bottleneck Taxonomy

In accordance with **3GPP TS 38.401 Clause 3.1**, the split gNB architecture disaggregates functions between the **gNB-DU** (housing RLC, MAC, and High-PHY) and the **gNB-CU** (housing PDCP, SDAP, and RRC):

| Domain Location | Specific Location / Bottleneck Type | Behavioral Characteristics & Symptoms | Relevant Metrics & Root Causes | 3GPP / ETSI Regulatory Specification |
|---|---|---|---|---|
| **RAN Radio Layer** | **gNB-DU MAC Scheduler — PRB Exhaustion** | Service demands exceed available physical resource blocks; transmission queues grow; throughput plateaus despite increased offered load. | **Metrics:** Available vs. used PRBs (UL & DL), cell delivered throughput, scheduling queue latency.<br>**Causes:** High aggregate slice traffic exceeding allocated PRB quota. | **3GPP TS 38.314 §4.2.1.6:** Measurement of available PRBs and *"PRBs used for traffic transmission"*. |
| **RAN Radio Layer** | **Air Interface (Uu) — Channel Condition Collapse**| Effective channel capacity collapses; retransmissions and required resource allocation per bit escalate; throughput plummets. | **Metrics:** CQI, SNR, Modulation & Coding Scheme (MCS), BLER, HARQ retransmissions.<br>**Causes:** Radio interference, shadowing, multi-path fading, or pathloss. | **3GPP TS 38.300 §5.2.5.1 & §5.3.5.1:** Link adaptation and adaptive modulation and coding. |
| **RAN Layer 2** | **gNB-DU — RLC Queuing & Service Bottleneck** | Packets queue extensively in the DU before transmission over the air; local DU packet drops escalate prior to RF transmission. | **Metrics:** RLC buffer occupancy, DU queuing delay, RLC SDU drop rate.<br>**Causes:** Ingress traffic exceeding DU transmission rate due to radio stalls. | **3GPP TS 28.552 §5.1.3.2.2:** DU packet drops due to high traffic load.<br>**3GPP TS 28.552 §5.1.3.3.3:** Downlink delay in DU. |
| **RAN Layer 2/3** | **gNB-CU-UP — PDCP Processing & Queuing** | Delays or packet drops occur within the CU-UP prior to forwarding over F1-U to the DU; radio PRB usage may remain low. | **Metrics:** CU-UP internal processing latency, PDCP SDU drop rate, CU-UP buffer depth.<br>**Causes:** High packet rate, header compression overhead, compute constraints. | **3GPP TS 28.552 §5.1.3.2.1:** *"DL PDCP SDU Drop rate"*.<br>**3GPP TS 28.552 §5.1.3.3.1:** Downlink delay in CU-UP. |
| **RAN Transport** | **F1-U Transport Interface (CU-UP $\leftrightarrow$ DU)** | Packet loss and delay spikes concentrated across the F1-U network segment, isolated from radio or internal node delay. | **Metrics:** F1-U packet loss rate, round-trip delay, interface queue depth.<br>**Causes:** F1 transport capacity constraints or network bridge contention. | **3GPP TS 28.552 §5.1.3.1.2–§5.1.3.1.3:** F1-U packet loss.<br>**3GPP TS 28.552 §5.1.3.3.2:** Downlink delay on F1-U. |
| **RAN Compute** | **Host CPU Starvation (vRAN / O-RAN)** | Softmodem thread processing cycles exceed timing deadlines; slot processing slips and packet drops surge despite ample radio bandwidth. | **Metrics:** CPU utilization, context switch latency, process cycle execution time.<br>**Causes:** Virtualization overhead, compute resource contention on host CPU. | **3GPP TS 23.288 §6.6.3 Table 6.6.3-1:** gNB NF resource usage analytics (CPU, memory, disk). |

---

## 4. Priority Scenarios Evaluated in Testbed

The experimental scenarios evaluated in this thesis map directly to this taxonomy:
* **Scenario S1 & S2:** Baseline healthy operation across all domains.
* **Scenario S3:** RAN MAC Scheduler PRB Exhaustion (Domain 1 above).
* **Scenario S6:** Core UPF QoS Rate Limiting & Queue Backpressure (Domain 2 above).
* **Scenario S9:** Joint Overload (simultaneous RAN PRB Exhaustion and Core Queue Backpressure).
* **Scenario S10_A & S10_B:** Staged Recovery evaluating domain decoupling during sequential remediation.

For the exact fault injection mechanisms and parameter values, refer to [docs/experiments/scenarios.md](../experiments/scenarios.md).
