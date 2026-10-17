# Normative Standards Claim Mapping & Technical Citations

**Authoritative Specification:** Single Source of Truth for Technical Standards Alignment  
**Standardization Bodies:** 3GPP (3rd Generation Partnership Project), ETSI, O-RAN Alliance, ITU-T  
**Evaluation Scope:** Strict boundary demarcation between normative specifications, open-source behaviors, and empirical research adaptations.

---

## 1. Normative Standards Claim Mapping Table

| Claim ID | Formal Technical Statement | Standard Document & Version | Clause / Section / Table | Official Specification URL | Relationship with Testbed Implementation | Concrete Claim Boundaries & Disclaimers |
|:---:|---|---|---|---|---|---|
| **`CLM-01`** | High resource utilization (e.g., PRB or CPU) does not inherently constitute network congestion. | **3GPP TS 23.288**<br>(Release 17 / Rel-19) | Clause 6.8.2 | [ETSI TS 123 288](https://www.etsi.org/deliver/etsi_ts/123200_123299/123288/) | Justifies multi-domain cross-correlation in the rApp (combining PRB utilization with queuing and packet loss). | Telemetry showing 100% PRB is classified as congestion only when accompanied by BLER degradation or scheduling stalls. |
| **`CLM-02`** | PRB utilization represents the ratio of resource blocks used for traffic transmission over total available PRBs per cell. | **3GPP TS 38.314**<br>(Release 16/17) | Clause 4.2.1.6 | [ETSI TS 128 552](https://www.etsi.org/deliver/etsi_ts/128500_128599/128552/) | `ran_adapter.py` extracts instantaneous MAC slot allocation ($NPRB / 106$) from DU logs. | Our metric is an instantaneous slot allocation sample of the active UE, not a time-integrated cell-wide average over an OAM interval. |
| **`CLM-03`** | UPF packet delay measurement assesses internal GTP-U packet processing transit time. | **3GPP TS 28.552**<br>(Release 17) | Clause 5.4.5 | [ETSI TS 128 552](https://www.etsi.org/deliver/etsi_ts/128500_128599/128552/) | `core_adapter.py` reads Linux host interface queue backlog (`tc qdisc`) on UPF `eth0`. | `upf_queue_backlog_bytes` measures Linux kernel socket buffer depth, not internal C-based UPF GTP-U parsing latency. |
| **`CLM-04`** | Standard 3GPP NWDAF service-based interfaces expose analytical events over HTTP/2 REST APIs (`EventId`). | **3GPP TS 29.520**<br>(Release 17 / Rel-19) | Clauses 4, 5.1, 5.2 | [ETSI TS 129 520](https://www.etsi.org/deliver/etsi_ts/129500_129599/129520/) | Kong API Gateway (`:8080`) routes queries to `oai-nwdaf-nbi-analytics` for `UE_COMMUNICATION`. | In TS 29.520 Rel-17, slice load is identified by `LOAD_LEVEL_INFORMATION` / `NSI_LOAD_LEVEL`; in OAI NWDAF, slice load is unsupported (emits `NaN`). |
| **`CLM-05`** | NWDAF architecture comprises AnLF (analytics generation) and MTLF (model training) logical functions. | **3GPP TS 23.288**<br>(Release 17 / Rel-19) | Clauses 4 & 5 | [ETSI TS 123 288](https://www.etsi.org/deliver/etsi_ts/123200_123299/123288/) | OAI NWDAF container cluster implements AnLF; model training is decoupled to Non-RT RIC rApp (VM-1). | External rApp model training on VM-1 is an O-RAN research architecture choice, not an internal 3GPP NWDAF MTLF. |
| **`CLM-06`** | O-RAN Non-RT RIC coordinates with 5G Core analytics to execute cross-domain policy optimization. | **ETSI TR 104 037**<br>/ O-RAN WG2 | Use Cases Report | [ETSI TR 104 037](https://www.etsi.org/deliver/etsi_tr/104000_104099/104037/) | Informs the Non-RT RIC rApp architecture consuming both NWDAF and O-RAN radio telemetry. | Implementation uses REST NBI and Prometheus adapters; not all O-RAN standardized R1 services are active. |
| **`CLM-07`** | Session-AMBR and QoS flow bitrates are enforced in the user plane via QoS Enforcement Rules (QER). | **3GPP TS 23.501**<br>§5.7.1.8 & TS 29.244 | Clause 5.2.5 | [ETSI TS 129 244](https://www.etsi.org/deliver/etsi_ts/129200_129299/129244/) | Core traffic shaping is emulated using Linux `tc tbf` on the UPF container egress interface (`eth0`). | TBF rate shaping on `eth0` is an empirical host emulation mechanism, not an internal UPF datapath QER enforcement. |
| **`CLM-08`** | End-to-end packet delay budget specifies latency targets across radio and core segments. | **3GPP TS 23.501**<br>(Release 17) | Table 5.7.4-1 | [ETSI TS 123 501](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/) | Canary ping RTT ($20 - 30\text{ ms}$) on Slice 2 evaluates compliance against low-latency targets. | Measured canary RTT includes full host hypervisor stack latency, operating system scheduling, and virtual RFsim propagation. |
| **`CLM-09`** | UPF usage reporting rules (URR) generate periodic session report requests over N4 PFCP. | **3GPP TS 29.244**<br>(Release 16/17) | Clause 5.2.2 & §8.2.40 | [ETSI TS 129 244](https://www.etsi.org/deliver/etsi_ts/129200_129299/129244/) | UPF `simpleswitch` emits periodic reports (msg type 56) containing IE 62 to SMF-1. | The 30-second reporting cadence is an implementation-defined parameter (`PERIODIC_REPORT_TIME`), not a standard-mandated minimum. |

---

## 2. Parameter Origin & Calibration Classifications

To prevent false claims of standardization, every experimental threshold, buffer size, capacity bound, and polling cadence is classified into four formal origin tiers:

| Tier | Definition & Research Context |
|---|---|
| **Standard-Defined** | Explicitly mandated or standardized in 3GPP/ETSI/O-RAN specifications. |
| **Implementation-Defined** | Behavior or setting dictated by upstream open-source software (OAI / O-RAN SC). |
| **Calibrated** | Empirically measured and verified under testbed stress conditions. |
| **Research-Selected** | Selected specifically for this thesis's evaluation methodology and hypothesis testing. |

| Parameter Name | Value | Origin Tier | Origin Justification & Technical Basis |
|---|---|:---:|---|
| **Total Radio PRBs** | `106 PRBs` | **Standard-Defined** | 3GPP TS 38.101-1 for 5G NR Band n78 with 40 MHz channel bandwidth ($\mu=1$, 30 kHz SCS). |
| **eMBB S-NSSAI** | `SST: 1, SD: 000001` | **Standard-Defined** | 3GPP TS 23.501 §5.15.2 (SST 1 standardized internationally for eMBB). |
| **URLLC S-NSSAI** | `SST: 222, SD: 00007B` | **Standard-Defined** | 3GPP TS 23.501 §5.15.2 (SST 222 in operator-specific range for low latency). |
| **NWDAF URR Reporting Cadence**| `30 seconds` | **Implementation** | Configured in OAI SMF/UPF `conf/slicing_slice1_config.yaml` (`PERIODIC_REPORT_TIME: 30`). |
| **NWDAF Engine Stubbing** | `relativeRatio = 0` | **Implementation** | Uncompleted `//TODO` in `components/oai-nwdaf-engine/internal/engine/network_performance.go`. |
| **Radio UL Saturation Limit**| $\approx 28.4\text{ Mbps}$ | **Calibrated** | Maximum attainable uplink throughput in OAI RFsimulator with 106 PRBs and 64-QAM. |
| **Estimated Load Capacity** | $25\text{ Mbps}$ (eMBB) / $5\text{ Mbps}$ (URLLC) | **Calibrated** | Empirical maximum goodput baseline before queue accumulation begins. |
| **Logging & Polling Cadence**| `1.000 Hz (1.0 s)` | **Research-Choice** | Configured in `record_experiment.py` to capture second-by-second dynamic transients for analysis. |
| **Staleness Auto-Reset Window**| `3.5 seconds` | **Research-Choice** | Configured in `telemetry_collector.py` to prevent stale telemetry from misrepresenting inactive sources. |
| **TBF Emulation Shaper** | `12 Mbps, latency 200ms` | **Research-Choice** | Configured on UPF-1 container `eth0` in Scenario S6 to emulate core transport link throttling. |
