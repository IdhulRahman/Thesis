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

## Scenario Implications

The table below maps sweep observations to scenario candidates. All candidate values are **preliminary** pending receiver evidence.

| Scenario | Role | Attenuation Candidate | Rationale | Confidence |
|---|---|---|---|---|
| S1 / S2 (Baseline) | Healthy radio | 0 dB (no attenuation) | Low PRB grant, high MCS, BLER ≈ 0, service met | Confirmed (existing data) |
| S3 (RAN-stressed) | Stressed radio, binding status pending receiver evidence | **25 dB** (preliminary) | BLER ≈ 10 %, MCS 17, 100 % PRB; sender service met; receiver pending | **Preliminary — pending receiver evidence** |
| S4 (RAN-binding) | Active RAN bottleneck | **30 dB** (preliminary) | BLER 0.05–0.62, MCS 0–1; receiver goodput unverified | **Preliminary — pending per-step receiver evidence** |
| S8 (RAN + Core, Joint) | Two simultaneous treatments | 25 dB + TBF | Note: two active treatments ≠ two active bottlenecks. JOINT class requires binding evidence from both domains on the same measurement interval. | Procedure pending binding evidence |
| S9 (Joint bottleneck) | Both domains confirmed binding | TBD | Must verify receiver goodput degradation independently for both RAN and Core paths | Not yet established |

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
