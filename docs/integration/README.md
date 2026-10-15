# Cross-Domain Interface Integration Guides

This directory contains the authoritative integration specifications and validation guides for the cross-domain interfaces linking the 6 virtual machines in the O-RAN 5G Core testbed.

**Thesis Research Title:**  
*Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Integration Matrix & Specification Mapping

| Document | Primary Interface | Cross-VM Boundary | Protocol & Transport | Standard Specification | Operational Status |
|---|---|---|---|---|:---:|
| [`a1-integration.md`](a1-integration.md) | **O-RAN A1** | VM-1 (Non-RT) $\to$ VM-2 (Near-RT) | REST HTTP/1.1 (`:10001`) & RMR (`:4560`) | O-RAN.WG2.A1AP v03.01 | **`Validated`** |
| [`e2-integration.md`](e2-integration.md) | **O-RAN E2** | VM-4 (Split RAN) $\leftrightarrow$ VM-2 (Near-RT) | E2AP over SCTP (`:36421`) | O-RAN.WG3.E2AP v02.03 | **`Validated` (E2Setup)** |
| [`nwdaf-integration.md`](nwdaf-integration.md) | **3GPP NWDAF** | VM-3 (5GC) $\to$ VM-6 (Collector) | N4 PFCP, SBA HTTP/2, REST NBI (`:8080`) | 3GPP TS 23.288 / TS 29.520 | **`Validated` (Channel E)** |

---

## 2. Interface Overview & Dataflows

### 2.1 A1 Interface Path (VM-1 $\to$ VM-2)
The A1 path allows the Non-RT RIC coordinator on VM-1 to deliver policy guidelines and SLA constraints (Policy Type `20008`) to the Near-RT RIC xApp on VM-2:
```text
 Non-RT RIC (VM-1)                   Near-RT RIC (VM-2)
 ┌─────────────────┐                 ┌──────────────────────┐
 │ A1 PMS (:8081)  │ ──► OscA1Client ──► NGINX Shim (:10001) │
 └─────────────────┘                 └──────────┬───────────┘
                                                ▼
                                     ┌──────────────────────┐
                                     │ A1 Mediator (:10000) │
                                     └──────────┬───────────┘
                                                ▼ RMR 20010
                                     ┌──────────────────────┐
                                     │ xApp Runner (:4560)  │
                                     └──────────┬───────────┘
                                                ▼ RMR RTS 20011 (ENFORCED)
                                     ┌──────────────────────┐
                                     │ A1 Mediator Status   │
                                     └──────────────────────┘
```
> [!NOTE]
> A status of `ENFORCED` confirms that the xApp received and accepted the policy. Physical radio steering actuation over E2 is evaluated separately.

### 2.2 E2 Interface Path (VM-4 $\leftrightarrow$ VM-2)
The E2 path connects the OAI gNB Centralized Unit (CU) to the Near-RT RIC, providing node discovery, telemetry indications, and radio control actuation:
```text
 OAI Split RAN (VM-4)                Near-RT RIC (VM-2)
 ┌──────────────────────┐            ┌──────────────────────┐
 │ CU-CP / CU-UP Softm. │            │ ric_e2term (:36421)  │
 │  ├── FlexRIC Agent   │ ──► SCTP ──►  ├── Decodes ASN.1   │
 │  ├── E2SM-KPM (ID: 2)│            │  └── RMR msg 12001   │
 │  └── E2SM-RC  (ID: 3)│            └──────────┬───────────┘
 └──────────────────────┘                       ▼
                                     ┌──────────────────────┐
                                     │ ric_e2mgr / DBaaS    │
                                     │ (NodeB Registered)   │
                                     └──────────────────────┘
```

### 2.3 NWDAF & Core Telemetry Path (VM-3 $\to$ VM-6)
Exposes standardized 3GPP user-plane communication analytics (`UE_COMMUNICATION`) from the 5G Core datapath alongside high-frequency host telemetry:
```text
 5G Core Datapath (VM-3)             Monitoring Host (VM-6)
 ┌──────────────────────┐            ┌──────────────────────┐
 │ UPF simpleswitch     │            │ telemetry_collector  │
 │  └── URR 1 via N4    │            │  ├── GET :8080 (3GPP)│
 └──────────┬───────────┘            │  └── POST :9100/rep. │
            ▼ PFCP msg 56            └──────────┬───────────┘
 ┌──────────────────────┐                       ▼
 │ SMF-1 (QOS_MON)      │            ┌──────────────────────┐
 └──────────┬───────────┘            │ Prometheus &         │
            ▼ HTTP/2 SBI             │ record_dual_stream   │
 ┌──────────────────────┐            │ (37-Column Dataset)  │
 │ oai-nwdaf-sbi/engine │            └──────────────────────┘
 │  └── Kong (:8080)    │
 └──────────────────────┘
```

---

## 3. Related Documentation

* **Deployment Guides:** [docs/deployment/README.md](../deployment/README.md)
* **Telemetry Metric Catalog:** [docs/telemetry/metric-catalog.md](../telemetry/metric-catalog.md)
* **Troubleshooting Cases:** [docs/troubleshooting/README.md](../troubleshooting/README.md)
