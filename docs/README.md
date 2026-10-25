# Technical Documentation Map & Reading Guide

This document provides the authoritative sitemap, documentation hierarchy, and reading order for the technical artifacts supporting the thesis:

> **Thesis Research Title:**  
> *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Documentation Map by Functional Domain

```text
d:\Idhul\Program\Thesis\docs
├── README.md                           ◄── [You are here] Sitemap & Reading Guide
├── architecture.md                     ◄── Component Roles, Topography & Control Flows
├── implementation-status.md            ◄── Status Matrix & Empirical Validation Evidence
├── software-manifest.md                ◄── Versions, Git Commits, Container Images & Patches
│
├── deployment/                         ◄── 6-VM Step-by-Step Bring-up & Operational Guides
│   ├── README.md                       ◄── Startup Sequence & Index
│   ├── vm-01-non-rt-ric.md             ◄── Non-RT RIC, A1 PMS v2.6.0, rApp Environment
│   ├── vm-02-near-rt-ric.md            ◄── Near-RT RIC (Dawn), A1 Mediator, E2Term, xApp
│   ├── vm-03-5g-core.md                ◄── Multi-Slice 5GC, NWDAF Stack, UPF Overrides
│   ├── vm-04-ran.md                    ◄── Split RAN (CU, DU-1 :4043, DU-2 :4044), E2 Agent
│   ├── vm-05-ue.md                     ◄── Multi-Instance nrUE, Network Namespaces, TrafGen
│   └── vm-06-monitoring.md             ◄── Prometheus, Grafana, Collector, Monotonic Logger
│
├── integration/                        ◄── Cross-VM Protocols & Service-Based Interfaces
│   ├── README.md                       ◄── Integration Interface Matrix
│   ├── a1-integration.md               ◄── A1 Interface (A1 PMS → A1 Mediator → xApp)
│   ├── e2-integration.md               ◄── E2 Interface (CU E2 Agent → E2Term SCTP :36421)
│   └── nwdaf-integration.md            ◄── Native 3GPP NWDAF Pipeline & Scope Delimitation
│
├── telemetry/                          ◄── Telemetry Dataflows & Dictionaries
│   └── metric-catalog.md               ◄── Single Authoritative 40-Column Dataset Dictionary
│
├── experiments/                        ◄── Evaluation Framework & Scenario Registries
│   ├── methodology.md                  ◄── Baselines (B0 to B4 vs Proposed), Metrics, Rules
│   └── scenarios.md                    ◄── Scenarios (S1, S2, S3, S6, S9, S10_A, S10_B)
│
├── references/                         ◄── Standards Alignment & Conceptual Foundations
│   ├── standards.md                    ◄── Normative Claim Mapping Table (3GPP / ETSI / O-RAN)
│   └── bottleneck-taxonomy.md          ◄── Bottleneck Taxonomy Mapped to 3GPP Specs
│
├── troubleshooting/                    ◄── Modular Domain-Separated Troubleshooting Guides
│   ├── README.md                       ◄── Diagnostic Flow & Historical Case Cross-Reference
│   ├── ric-a1.md                       ◄── Non-RT & Near-RT RIC (A1 / RMR / xApp)
│   ├── e2-networking.md                ◄── O-RAN E2 Termination & RIC Inter-VM Networking
│   ├── ran-ue.md                       ◄── OAI Split RAN & User Equipment (CU/DU/nrUE)
│   ├── 5g-core.md                      ◄── 5G Core Network Functions & User Plane
│   └── nwdaf.md                        ◄── 3GPP NWDAF SBI/NBI & Telemetry Pipeline
│
├── diagrams/                           ◄── Source Mermaid & Rendered Architectural Diagrams
│   ├── current-system-architecture.mmd ◄── Source Mermaid of Current 6-VM Architecture
│   ├── current-system-architecture.png ◄── Rendered Diagram
│   ├── proposed-control-loop.mmd       ◄── Source Mermaid of Proposed MAPE-K Loop
│   └── proposed-control-loop.png       ◄── Rendered Diagram
│
└── archive/                            ◄── Historical Investigation Reports & Snapshot Audits
    ├── README.md                       ◄── Archive Inventory & Context
    ├── thesis-system-technical-snapshot-20261015.md
    ├── nwdaf-investigation-report-20261015.md
    └── nwdaf-instructions-20261015.md
```

---

## 2. Recommended Reading Order by Audience

### 2.1 For Thesis Advisors & Technical Reviewers
1. **[System Architecture](architecture.md):** Understand the multi-timescale cross-domain paradigm and the boundary between validated telemetry vs. planned closed-loop actuation.
2. **[Implementation Status](implementation-status.md):** Verify the empirical evidence supporting each system capability.
3. **[Normative Standards Claims](references/standards.md):** Review the mapping of research claims to official 3GPP and ETSI specifications.
4. **[Experimental Methodology](experiments/methodology.md):** Examine the baseline control paradigms (B0 to B4 vs. Proposed) and evaluation criteria.
5. **[Telemetry Metric Catalog](telemetry/metric-catalog.md):** Review the 40-column dataset schema and measurement semantics.

### 2.2 For Testbed Operators & Reproducibility Engineers
1. **[Software Manifest](software-manifest.md):** Verify host allocations, pinned Git commits, container images, and custom patches.
2. **[Deployment Guides Index](deployment/README.md):** Follow the deterministic 6-step startup sequence (`VM-3 → VM-4 → VM-1 → VM-2 → VM-5 → VM-6`).
3. **[NWDAF Integration](integration/nwdaf-integration.md):** Verify the 5-layer native 3GPP user-plane telemetry chain and REST API health.
4. **[Troubleshooting Index](troubleshooting/README.md):** Consult verified fixes for known operational issues across all domains.

### 2.3 For Data Scientists & Experimenters
1. **[Experimental Scenarios](experiments/scenarios.md):** Learn how to trigger fault injections (S1 to S10) and annotate ground truth.
2. **[Telemetry Metric Catalog](telemetry/metric-catalog.md):** Understand feature formulas, missing value handling (`NaN`), and semantic caveats.
3. **[Model Comparison Outline](../research/papers/model-comparison-outline.md):** Review the predictive model architectures and comparative evaluation hypotheses.
