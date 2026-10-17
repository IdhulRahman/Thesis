# 6-VM Testbed Deployment & Operations Guide

This directory provides the authoritative, step-by-step deployment, configuration, startup, and operational procedures for each virtual machine in the 6-VM experimental testbed.

**Thesis Research Title:**  
*Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Virtual Machine Deployment Index

| Guide | Target Node | Subnet IP | Architectural Role | Core Software Framework |
|---|---|---|---|---|
| [`vm-01-non-rt-ric.md`](vm-01-non-rt-ric.md) | **VM-1** | `10.102.0.168` | Non-RT RIC & SMO Host | O-RAN SC A1 PMS v2.6.0, rApp Execution Environment |
| [`vm-02-near-rt-ric.md`](vm-02-near-rt-ric.md) | **VM-2** | `10.102.0.66` | Near-RT RIC Platform | O-RAN SC Dawn (A1 Mediator, E2Term, E2Mgr, DBaaS, xApp) |
| [`vm-03-5g-core.md`](vm-03-5g-core.md) | **VM-3** | `10.102.0.164` | Multi-Slice 5GC & NWDAF | OAI 5GC v2.1.0, OAI NWDAF (AnLF), Core Telemetry Adapter v9 |
| [`vm-04-ran.md`](vm-04-ran.md) | **VM-4** | `10.102.0.167` | Split 5G RAN | OAI gNB CU-CP/UP, DU-1 (Cell-1), DU-2 (Cell-2), RAN Adapter |
| [`vm-05-ue.md`](vm-05-ue.md) | **VM-5** | `10.102.0.165` | Multi-UE Emulator | OAI nrUE Emulator (netns: `ue1`, `ue2`), Multi-Slice TrafGen |
| [`vm-06-monitoring.md`](vm-06-monitoring.md) | **VM-6** | `10.102.0.67` | Telemetry & Observability | Telemetry Collector (:9100), Prometheus, Grafana, Recorder |

---

## 2. Deterministic Startup & Verification Sequence

To ensure proper cross-VM signaling binding (N2 SCTP, N4 PFCP, E2 SCTP, and A1 HTTP), start the nodes strictly in the following sequence:

```text
Step 1: VM-3 (5G Core) ──► Step 2: VM-4 (Split RAN) ──► Step 3: VM-1 (Non-RT RIC)
                                                                 │
Step 6: VM-6 (Monitor) ◄── Step 5: VM-5 (nrUE)      ◄── Step 4: VM-2 (Near-RT RIC)
```

1. **Step 1 — VM-3 (5G Core Bring-Up):**  
   Start MySQL, NRF, NSSF, AMF, SMF-1, SMF-2, UPF-1, UPF-2, Ext-DN, and the 8 NWDAF microservices. Verify AMF port `38412` and Kong port `8080` are listening. Launch `core_adapter.py`.
2. **Step 2 — VM-4 (Split RAN Bring-Up):**  
   Start CU softmodem (`cu_gnb.conf`). Confirm N2 association with AMF (`associated AMF 1`). Start DU-1 (`du_gnb1.conf`, port `4043`) and DU-2 (`du_gnb2.conf`, port `4044`). Launch `ran_adapter.py`.
3. **Step 3 — VM-1 (Non-RT RIC Bring-Up):**  
   Start A1 Policy Management Service (A1 PMS v2.6.0). Confirm REST API is healthy at `http://10.102.0.168:8081/actuator/health`.
4. **Step 4 — VM-2 (Near-RT RIC Bring-Up):**  
   Start DBaaS (Redis 5.0.9), E2Mgr, E2Term, Subscription Manager, A1 Mediator, and Traffic Steering xApp. Confirm E2 SCTP port `36421` is listening and A1 Mediator passes `/a1-p/healthcheck`.
5. **Step 5 — VM-5 (nrUE Bring-Up & Canary Validation):**  
   Execute `spawn_multi_ue.sh -s1 1 -s2 1`. Verify `oaitun_ue1` inside `ue1` (`12.1.1.2`) and `ue2` (`12.1.2.2`). Run ping canary to `192.168.70.145` confirming 0% packet loss. Start `trafgen.sh`.
6. **Step 6 — VM-6 (Monitoring & Telemetry Pipeline):**  
   Start `telemetry_collector.py` on port `9100`. Verify Prometheus scrapes `:9100/metrics`. Execute `record_experiment.py` to record single-scenario experimental runs.

---

## 3. Related Documentation

* **Software Manifest:** [docs/software-manifest.md](../software-manifest.md)
* **Integration Guides:** [docs/integration/README.md](../integration/README.md)
* **Metric Catalog:** [docs/telemetry/metric-catalog.md](../telemetry/metric-catalog.md)
* **Troubleshooting Index:** [docs/troubleshooting/README.md](../troubleshooting/README.md)
