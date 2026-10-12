# VM Deployment Guides

This folder contains the complete, step-by-step installation, configuration, and operations guide for each virtual machine in the O-RAN 5G thesis testbed.

> **Thesis:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## VM Index

| File | VM | IP Address | Role | Status |
|---|---|---|---|:---:|
| [vm1-nonrt-ric.md](vm1-nonrt-ric.md) | VM-1 | `10.102.0.168` | Non-RT RIC, A1 PMS v2.6.0, Bottleneck-Aware Coordinator rApp | ✅ |
| [vm2-nearrt-ric.md](vm2-nearrt-ric.md) | VM-2 | `10.102.0.66` | Near-RT RIC, A1 Mediator, xApp, E2Term, E2Mgr, DBaaS Redis 5.0.9 | ✅ |
| [vm3-oai-5gc.md](vm3-oai-5gc.md) | VM-3 | `10.102.0.164` | OAI 5GC Multi-Slice (AMF, SMF-1/2, UPF-1/2, NRF, UDM, MySQL) + Core Adapter v9 | ✅ |
| [vm4-oai-ran.md](vm4-oai-ran.md) | VM-4 | `10.102.0.167` | OAI 5G RAN (CU + DU-1 + DU-2 + FlexRIC E2 Agent + RFsim :4043/:4044) | ✅ |
| [vm5-nrue.md](vm5-nrue.md) | VM-5 | `10.102.0.165` | OAI nrUE Multi-Instance Emulator (rfsim client) | ✅ |
| [vm6-monitoring.md](vm6-monitoring.md) | VM-6 | `10.102.0.67` | Prometheus TSDB, Grafana Dashboards, Telemetry Collector & Monotonic Logger | ✅ |

---

## Network Subnet

All VMs are on the static inter-VM subnet: `10.102.0.0/24`

---

## Deployment Order

Deploy and verify VMs in this order for correct system bring-up:

```
VM-3 (5GC)  →  VM-4 (RAN)  →  VM-1 (Non-RT RIC)  →  VM-2 (Near-RT RIC)  →  VM-5 (UE)  →  VM-6 (Monitoring)
```

See also:
- [../integration/a1-integration.md](../integration/a1-integration.md) — A1 policy path from VM-1 to VM-2
- [../integration/e2-integration.md](../integration/e2-integration.md) — E2 setup from VM-4 to VM-2
- [../troubleshooting.md](../troubleshooting.md) — Validated fixes for known deployment issues
