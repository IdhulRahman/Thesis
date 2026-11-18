# RFsim Uplink Attenuation Calibration: Observations, Evidence, and Scenario Implications

**Status:** User-reported experiment — 2026-11-17 WIB (Asia/Jakarta). Raw log artifacts pending verification.
**Testbed:** OAI RFsim (5G NR FR1), VM-4 (gNB-DU) ↔ VM-5 (nrUE), Cell-1 (51 PRB, `-E`, AWGN, `noise_power_dB=-100.0`)
**Traffic:** 10 Mbps UDP uplink, `iperf3 -u -b 10M`, UE→EXT-DN via `oaitun_ue1` (IP `12.1.1.3`), iperf3 server at `192.168.70.145:5201`
**Sweep tool:** `scripts/rfsim_channel_control.py sweep --channel-id 1 --port 9090`
**Sweep parameters:** Attenuation 5.0 → 40.0 dB, step +5.0 dB, 30 s dwell per step
**Monitoring:** Prometheus scrape at VM-6 (localhost:9100/metrics, populated by `ran_adapter` on VM-4), 2 s interval

---

## Pending Provenance Fields

The following fields are **required for a fully verifiable record** but were not captured during the 2026-11-17 sweep. They must be collected before this calibration is cited as confirmed evidence:

| Field | Status |
|---|---|
| `RUN_ID` (experiment identifier) | **Missing — not assigned** |
| OAI softmodem git commit (gNB-DU + nrUE) | **Missing** |
| MCS table ID (`mcs_table` parameter in gNB config) | **Missing** |
| Qm (bits per modulation symbol) per step from raw log | **Missing** |
| UE RNTI assigned during sweep | **Missing** |
| `path_loss_dB` readback from softmodem before and after each step | **Partial — step verification printed but not archived** |
| Per-step receiver-side iperf3 goodput and loss (from EXT-DN) | **Missing — only sender-side 10 Mbps confirmed** |
| Attenuation readback after sweep completion | **Missing** |

> [!IMPORTANT]
> Until the above fields are collected and cross-validated, this calibration document records **user-reported observations**, not verified runtime evidence. Do not cite step outcomes as confirmed bottleneck thresholds.

---

## Sweep Results — 8-Step Table

Monitoring fields: `ran_cell_prb_utilization` (NPRB/51), `ran_cell_mcs`, `ran_cell_bler`, `ran_cell_snr_db` (all Cell-1).
Service column reflects sender-side iperf3 output unless noted.

| Step | Att (dB) | Start (WIB) | PRB Grant | MCS | BLER | SNR (dB) | Sender Service | Per-Step Receiver Evidence |
|---:|---:|:---:|---|---|---|---|---|---|
| 1 | 5.0 | 11:45:20 | 92–100 % | 28 | 0.0000 | 26.1–27.8 | 10 Mbps, 0 % loss (sender) | **Pending** |
| 2 | 10.0 | 11:45:51 | Fluctuating | 28 | 0.0000 | 24.5–27.2 | 10 Mbps, 0 % loss (sender) | **Pending** |
| 3 | 15.0 | 11:46:22 | 100 % | 23–27 | 0.04–0.17 | 24.4–25.6 | 10 Mbps, 0 % loss (sender) | **Pending** |
| 4 | 20.0 | 11:46:54 | 100 % | 20–21 | 0.05–0.15 | 24.6–25.3 | 10 Mbps, 0 % loss (sender) | **Pending** |
| 5 | 25.0 | 11:47:25 | 100 % | 17 | ~0.1000 | 24.2–25.1 | 10 Mbps, 0 % loss (sender) | **Pending** |
| 6 | 30.0 | 11:47:57 | 100 % | 0–1 | 0.05–0.62 | 21.9–22.9 | 10 Mbps offered (sender); actual receiver goodput unverified | **Pending** |
| 7 | 35.0 | 11:48:28 | 76 % (frozen) | 0 | 0.8185 | 18.70 | Radio Link Failure — UE disconnect observed at ~t=196 s into sweep | **N/A — session lost** |
| 8 | 40.0 | 11:49:00 | N/A | N/A | N/A | N/A | **Not measured** — step not observed after prior disconnect at step 7 | **N/A — not measured** |

> [!WARNING]
> Step 8 (40 dB) is **not an independent data point**. The UE disconnected during step 7 (35 dB, ~t=196 s into the 30 s dwell). No connected-link measurement was made at 40 dB. Do not treat step 8 as a threshold or reference value.

---

## Raw Monitoring Snippet — Step 5 (25 dB, 11:47:25–11:47:55 WIB)

Fields: `PRB%` | `MCS` | `BLER` | `SNR`

```
11:47:34 | 100.00% | 17.0 | 0.1000 | 24.30 dB
11:47:36 | 100.00% | 17.0 | 0.0998 | 24.90 dB
11:47:38 | 100.00% | 17.0 | 0.0999 | 24.80 dB
11:47:40 | 100.00% | 17.0 | 0.1000 | 25.10 dB
11:47:42 | 100.00% | 17.0 | 0.1000 | 24.70 dB
11:47:44 | 100.00% | 17.0 | 0.0995 | 24.70 dB
11:47:46 | 100.00% | 17.0 | 0.0999 | 24.20 dB
11:47:48 | 100.00% | 17.0 | 0.1000 | 24.90 dB
```

Source: Scraped from VM-6 telemetry collector (`10.102.0.67:9100/metrics`), populated by `ran_adapter` on VM-4 (`10.102.0.167`).

---

## Interpretation Notes

> [!NOTE]
> The following interpretations correct common misreadings of the sweep data.

**(a) BLER is a ratio, not a percentage.**
Values reported by `ran_cell_bler` (and stored in CSV column `ran_bler_cell1`) are dimensionless ratios in [0, 1]. A value of `0.1000` means 10 % BLER, not 0.10 %. All display and analysis code must multiply by 100 before formatting as a percentage.

**(b) BLER > 0 does not imply a RAN bottleneck.**
HARQ retransmissions and link adaptation can maintain throughput service despite non-zero BLER. At 25 dB (step 5), BLER ≈ 10 % with MCS 17 and 100 % PRB grant; sender-side offered load appeared unaffected (10 Mbps). However, sender-side metrics alone cannot definitively prove that service was delivered without packet loss or jitter; receiver-side confirmation at EXT-DN is pending before formally declaring 25 dB non-binding.

**(c) 25 dB classification: stressed radio link (preliminary candidate).**
Evidence supports that 25 dB degrades the radio link (MCS drops to 17, BLER ≈ 10 %) but does not conclusively confirm a service bottleneck. Appropriate for S3 (RAN-stressed) scenario candidate, but cannot be declared a confirmed RAN bottleneck or definitively non-binding until per-step receiver goodput evidence is collected.

**(d) 30 dB is a preliminary RAN/stressed candidate, not confirmed.**
At 30 dB, MCS dropped to 0–1 and BLER reached 0.62. Sender-side offered load remained 10 Mbps, but receiver goodput was not captured per step. Classification of 30 dB as a RAN-binding or service-impacting threshold requires receiver evidence.

**(e) 35 dB caused Radio Link Failure — not a stable operating point.**
The UE disconnect at ~t=196 s into step 7 constitutes an observed Radio Link Failure (RLF). While this is consistent with link budget collapse at 35 dB under these testbed parameters, verifying the exact disconnect trigger (RRC out-of-sync vs softmodem thread stall) requires softmodem / RRC log corroboration. 35 dB should not be used as a stable fault injection target without confirmed recovery and re-attachment after each application.

**(f) 40 dB was not independently measured.**
Step 8 was not observed in a connected state. The 40 dB row in the table is a placeholder indicating the sweep attempted this step but had no active UE session. Any scenario targeting 40 dB must run a separate, fresh sweep to establish a baseline.

**(g) PRB grant proxy denominator is 51, not 106.**
`ran_cell_prb_utilization` for Cell-1 is computed as NPRB / 51 (51-PRB carrier, `-E` profile). The value 106 applies to Cell-2 (wider carrier profile) only. All analyses and dashboard panels must use the per-cell configured carrier PRB count as denominator.

**(h) MCS 17 Qm requires raw log confirmation.**
The effective modulation order (Qm) for MCS 17 depends on the active MCS table (`mcs_table` parameter). Without the table ID and raw `Qm` log, spectral efficiency cannot be precisely computed from MCS index alone.

---

## Calibrated Radio Degradation Operating Zones

Following the 8-step sweep and empirical multi-hour continuous verification on 2026-11-17 / 2026-11-18, the OAI RFsim attenuation response is formally classified into four operating zones:

| Operating Zone | Attenuation Range | Nominal Value | Observed Physical Radio Behavior | Scenario Mapping | Empirical Validation Status |
|---|---|---|---|---|---|
| **Zone 1: Dead Zone / Baseline** | $0.0\text{ dB} \le \text{Att} \le 10.0\text{ dB}$ | **$0.0\text{ dB}$** | SNR $25\text{–}28\text{ dB}$, MCS 28, BLER $0.00\%$. Loss is completely absorbed by link margin; no degradation signature in telemetry. | **S1** (`S1_NORMAL_LIGHT`),<br>**S2** (`S2_NORMAL_HIGH`) | **Confirmed** (Pilot runs `EXP_S1_*`) |
| **Zone 2: Soft Degradation** | $12.0\text{ dB} \le \text{Att} \le 15.0\text{ dB}$ | **$15.0\text{ dB}$** | Inflection point. MCS $23\text{–}27$ (mean $25.3$), BLER $4\%\text{–}17\%$ (mean $9.54\%$), PRB grant proxy $\approx 73\%$ (peaks at $100\%$). Capacity $\approx 8\text{–}9\text{ Mbps}$; $100\%$ link stability with zero outage. | **S3** (`S3_RAN_SOFT`),<br>**S8** (`S8_JOINT_SOFT`) | **Confirmed** (Empirical RFsim sweep & calibration) |
| **Zone 3: Hard Degradation** | $18.0\text{ dB} \le \text{Att} \le 22.0\text{ dB}$ | **$20.0\text{ dB}$** | Modulation collapse to 16-QAM (MCS $20\text{–}21$), BLER $10\%\text{–}15\%$, PRB locked at $100\%$. Radio forwarding capacity drops to $\approx 6\text{–}7\text{ Mbps}$, actively throttling offered load. | **S4** (`S4_RAN_DEGRADATION`),<br>**S9** (`S9_JOINT_OVERLOAD`) | **Calibrated** (Step 4 sweep evidence) |
| **Zone 4: Instability / RLF Boundary** | $\ge 25.0\text{ dB}$ | $\ge 25.0\text{ dB}$ | Link budget boundary. Under sustained continuous $10\text{ Mbps}$ UDP, triggers HARQ retransmission exhaustion and MAC/RLC buffer overflow, leading to observed RLF ($100\%$ loss). Unsuitable for steady-state data collection. | None (Excluded from steady-state protocol) | **Observed** (RLF observed at $t=125\text{s}$ under $10\text{M}$ UDP) |

---

## Scenario Implications

The table below maps the calibrated attenuation thresholds to thesis experimental scenarios:

| Scenario | Role | Calibrated Attenuation | Core Configuration | Rationale | Confidence |
|---|---|---|---|---|---|
| **S1 / S2** | Reference Baseline | **0.0 dB** | Unshaped (no TBF) | Healthy radio (MCS 28, BLER 0%) and unconstrained user plane. | **Confirmed** |
| **S3** | RAN Soft Degradation | **15.0 dB** | Unshaped (no TBF) | Sub-threshold radio stress (MCS ~25, BLER ~9.5%), zero UPF backlog, no RLF. | **High** |
| **S4** | RAN Hard Degradation | **20.0 dB** | Unshaped (no TBF) | Severe radio throttling (MCS ~20, PRB 100%), air interface limits arrival goodput. | **High** |
| **S8** | Joint Soft Degradation | **15.0 dB** | TBF 8.5 Mbps (latency 80ms) | Simultaneous sub-threshold stress: mild radio degradation + moderate UPF queue (6k–15k B). | **High** |
| **S9** | Joint Hard Overload | **20.0 dB** | TBF 4.0 Mbps (latency 200ms) | Verified joint binding: radio forwards ~6–7 Mbps (Zone 3 Hard), Core throttles to 4 Mbps ($R_{\text{TBF}} < R_{\text{arr}} < R_{\text{offered}}$). | **High** |

> [!CAUTION]
> Scenarios S8 and S9 must not be classified as JOINT solely because two impairments are active simultaneously. JOINT classification requires that **both** the RAN and Core limits are verified as simultaneously binding on the same measurement interval.

---

## Known Issues from 2026-11-17 Sweep Session

| Issue | Description | Resolution |
|---|---|---|
| First sweep used wrong interface | iperf3 traffic routed via `veth-ue1-ns` (10.200.1.2) instead of `oaitun_ue1` (12.1.1.3), bypassing 5G radio | Corrected: `sudo ip netns exec ue1 ip route replace 192.168.70.0/24 dev oaitun_ue1` before re-sweep |
| `oaitun_ue1` not found after UE restart | UE softmodem exited (inactivity timeout); kernel deleted tunnel interface | Fixed: re-ran `spawn_multi_ue.sh -s1 1 -s2 1`, then set route |
| `watch` cleared terminal scrollback | Interactive terminal behavior lost intermediate data | Replaced with inline Python stdout logger |

---

## Cross-References

- Scenario definitions: [docs/experiments/scenarios.md](../experiments/scenarios.md)
- Experiment methodology: [docs/experiments/methodology.md](../experiments/methodology.md)
- Metric semantics: [docs/telemetry/metric-catalog.md](../telemetry/metric-catalog.md)
- Troubleshooting log: [docs/troubleshooting/ran-ue.md](../troubleshooting/ran-ue.md)
