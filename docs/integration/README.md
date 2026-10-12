# Interface Integration Guides

This folder contains the validated end-to-end integration guides for the inter-VM protocol interfaces in the O-RAN 5G thesis testbed.

> **Thesis:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## Integration Index

| File | Interface | Endpoints | Status |
|---|---|---|:---:|
| [a1-integration.md](a1-integration.md) | **A1 Interface** | VM-1 (A1 PMS) → VM-2 (A1 Mediator → xApp via RMR 20010/20011) | ✅ Verified |
| [e2-integration.md](e2-integration.md) | **E2 Interface** | VM-4 (OAI FlexRIC E2 Agent) → VM-2 (E2Term SCTP :36421) | ✅ Verified |

---

## Overview

### A1 Interface (VM-1 ↔ VM-2)

The A1 path enables the Non-RT RIC rApp to dispatch policy constraints to the Near-RT RIC xApp:

```
A1 PMS (VM-1 :8081)
   │  OscA1Client (HTTP)
   ▼
A1 Compatibility Shim (VM-2 :10001, Nginx)
   │
   ▼
A1 Mediator (VM-2 :10000)
   │  RMR mtype 20010
   ▼
Traffic Steering xApp (VM-2 :4560)
   │  RMR RTS mtype 20011
   ▼
A1 Mediator (status ENFORCED)
```

### E2 Interface (VM-4 ↔ VM-2)

The E2 path enables near-real-time RAN telemetry ingestion and radio actuation:

```
OAI FlexRIC E2 Agent (VM-4)
   │  E2AP over SCTP (port 36421)
   ▼
E2Term (VM-2)
   │  RMR (msg 12001 E2_SETUP_REQ)
   ▼
E2Mgr → RNIB/DBaaS (Redis)
```

Verified Service Models: **E2SM-KPM (ID: 2)**, **E2SM-RC (ID: 3)**, and 6× FlexRIC layer-2 SMs.

---

See also:
- [../vm/vm1-nonrt-ric.md](../vm/vm1-nonrt-ric.md) — VM-1 deployment guide
- [../vm/vm2-nearrt-ric.md](../vm/vm2-nearrt-ric.md) — VM-2 deployment guide
- [../vm/vm4-oai-ran.md](../vm/vm4-oai-ran.md) — VM-4 (RAN) deployment guide
- [../troubleshooting.md](../troubleshooting.md) — Validated fixes for known integration issues
