# Software & Artifact Manifest

This document serves as the authoritative, peer-reviewed inventory detailing all software versions, source code repository commits, container image tags, custom patches, and configuration identities deployed across the 6-VM testbed.

---

## 1. Virtual Machine Inventory & Network Identifiers

All virtual machines operate within the dedicated inter-VM subnet `10.102.0.0/24` on Ubuntu 22.04 LTS:

| VM ID | Hostname | Management IP | Primary Subsystem | Host Hardware Allocation |
|---|---|---:|---|---|
| **VM-1** | `nonrt-ric` | `10.102.0.168` | O-RAN Non-RT RIC, A1 PMS v2.6.0, rApp Execution Environment | 4 vCPU, 8 GB RAM |
| **VM-2** | `near-rt-ric` | `10.102.0.66` | O-RAN Near-RT RIC (O-RAN SC Dawn), A1 Mediator, E2Term, xApp | 4 vCPU, 8 GB RAM |
| **VM-3** | `oai-core` | `10.102.0.164` | OAI 5G Core Multi-Slice, 3GPP NWDAF Stack, Core Adapter v9 | 8 vCPU, 16 GB RAM |
| **VM-4** | `oai-ran` | `10.102.0.167` | OAI Split RAN (CU + DU-1 + DU-2 + FlexRIC E2 Agent), RAN Adapter | 8 vCPU, 16 GB RAM |
| **VM-5** | `ue-emulator` | `10.102.0.165` | OAI nrUE Multi-Instance Emulator (`ue1`, `ue2` netns), TrafGen | 4 vCPU, 8 GB RAM |
| **VM-6** | `monitoring-data` | `10.102.0.67` | Prometheus TSDB, Grafana, Telemetry Collector, Monotonic Logger | 4 vCPU, 8 GB RAM |

---

## 2. Software Versions, Repositories & Commit Baselines

### 2.1 5G Core Network & Analytics (VM-3)

| Component | Upstream Repository | Target Branch / Tag | Pinned Commit Hash | Deployed Artifact / Container Image |
|---|---|---|---|---|
| **5GC Federation** | `openairinterface/oai-cn5g-fed` | `v2.1.0` | `2631021` | Orchestrates slicing compose deployment |
| **AMF** | `openairinterface/oai-cn5g-amf` | `v2.1.0` baseline | `58f77cfb` | Custom built image: `oai-amf:thesis-nrf-uri-v1` (Rel-16/17 compliant dynamic NRF URI) |
| **SMF (Slice 1 & 2)** | `openairinterface/oai-cn5g-smf` | `v2.1.0` | `531b6d87` | Official image: `oaisoftwarealliance/oai-smf:v2.1.0` |
| **UPF-1 (eMBB Slice 1)** | `openairinterface/oai-cn5g-upf` | `develop` (URR PoC) | `c51cae23` | Custom built image: `oai-upf:poc-develop-ie43-compat-v1` (Rel-16 IE 43 clamped) |
| **UPF-2 (URLLC Slice 2)** | `openairinterface/oai-cn5g-upf` | `v2.1.0` | `89ee4c9` | Official image: `oaisoftwarealliance/oai-upf:v2.1.0` |
| **NRF (Slice 1-2 & 3)** | `openairinterface/oai-cn5g-nrf` | `v2.1.0` | `4b0faee` | Official image: `oaisoftwarealliance/oai-nrf:v2.1.0` |
| **UDM / UDR / AUSF / NSSF** | `openairinterface/oai-cn5g-*` | `v2.1.0` | Various | Official images: `oaisoftwarealliance/oai-*:v2.1.0` |
| **Database** | MySQL | `8.0` | `mysql:8.0` | Official container with custom provisioning script |
| **External DN** | Ubuntu 22.04 base | LTS | `trf-gen-cn5g:latest` | Container IP `192.168.70.145` (iperf3 server `:5201` & ICMP target) |
| **NWDAF Engine** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-engine:develop` |
| **NWDAF NBI Analytics** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-nbi-analytics:develop` |
| **NWDAF NBI Events** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-nbi-events:develop` |
| **NWDAF NBI ML** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-nbi-ml:develop` |
| **NWDAF Engine ADS** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-engine-ads:develop` |
| **NWDAF SBI** | `openairinterface/oai-cn5g-nwdaf` | `develop` | `9d82b75` | Official image: `oaisoftwarealliance/oai-nwdaf-sbi:develop` |
| **NWDAF Gateway** | Kong API Gateway | `3.3.0` | `kong:3.3.0` | Reverse proxy exposing port `8080` (HTTP) and `8001` (Admin) |
| **NWDAF Datastore** | MongoDB | `4.4` | `mongo:4.4` | Port `27017`, stores database `testing` and collection `smf` |
| **Core Adapter Daemon** | In-house Python daemon | v9.0.0 | Repository HEAD | Host process (`scripts/core_adapter.py`) |

### 2.2 O-RAN Radio Access Network (VM-4)

| Component | Upstream Repository | Target Branch / Tag | Pinned Commit Hash | Deployed Artifact / Binary |
|---|---|---|---|---|
| **OAI gNB CU-CP & CU-UP** | `openairinterface/openairinterface5g` | `develop` (`2026.w39`) | `29d5fa7d` | Native binary: `cmake_targets/ran_build/build/nr-softmodem` |
| **OAI gNB DU-1 (Cell-1)** | `openairinterface/openairinterface5g` | `develop` (`2026.w39`) | `29d5fa7d` | Native binary: `nr-softmodem --rfsim` (PCI 1, TCP server `:4043`) |
| **OAI gNB DU-2 (Cell-2)** | `openairinterface/openairinterface5g` | `develop` (`2026.w39`) | `29d5fa7d` | Native binary: `nr-softmodem --rfsim` (PCI 2, TCP server `:4044`) |
| **FlexRIC E2 Agent** | FlexRIC submodule (`openairinterface5g`) | `develop` | Pinned to OAI | Embedded shared library linked into CU softmodem |
| **RAN Adapter Daemon** | In-house Python daemon | v1.0.0 | Repository HEAD | Host process (`scripts/ran_adapter.py`) reading `du1.log` & `du2.log` |

### 2.3 O-RAN Near-RT RIC (VM-2) & Non-RT RIC (VM-1)

| Subsystem | Component | Upstream Project / Repository | Pinned Version / Release | Exposure / Ports |
|---|---|---|---|---|
| **VM-1 (Non-RT)** | **A1 Policy Management Service** | O-RAN SC `nonrtric-plt-a1policymanagementservice` | `2.6.0` (H-Release) | Spring Boot REST API (`:8081`) |
| **VM-1 (Non-RT)** | **Bottleneck-Aware Coordinator rApp** | In-house Python rApp | Research Prototype | Non-RT RIC Host execution environment |
| **VM-2 (Near-RT)** | **A1 Mediator** | O-RAN SC `ric-plt-a1` | `3.2.2` (Dawn Release) | HTTP REST API (`:10001` via NGINX shim) |
| **VM-2 (Near-RT)** | **E2 Termination (E2Term)** | O-RAN SC `ric-plt-e2` | `6.0.4` | SCTP Server (`:36421`), RMR (`:38000`) |
| **VM-2 (Near-RT)** | **E2 Manager (E2Mgr)** | O-RAN SC `ric-plt-e2mgr` | `6.0.4` | HTTP REST API (`:3801`) |
| **VM-2 (Near-RT)** | **Subscription Manager (SubMgr)** | O-RAN SC `ric-plt-submgr` | `0.7.3` | RMR (`:4560`) |
| **VM-2 (Near-RT)** | **Shared Data Layer (DBaaS)** | O-RAN SC `ric-plt-dbaas` / Redis | `0.5.7` / Redis `5.0.9` | RESP2 Protocol (`:6379`) |
| **VM-2 (Near-RT)** | **Traffic Steering xApp** | In-house Python xApp | Python `ricxappframe` | RMR (`:4560`), Container IP `10.0.2.20` |

### 2.4 User Equipment & Traffic Generation (VM-5)

| Component | Upstream Repository | Target Branch / Tag | Deployed Artifact / Script | Execution Context |
|---|---|---|---|---|
| **OAI nrUE Emulator** | `openairinterface/openairinterface5g` | `develop` (`2026.w39`) | Native binary: `nr-uesoftmodem` | Staggered multi-instance spawner in Linux netns |
| **Multi-UE Spawner** | In-house Bash script | v2.0.0 | `scripts/spawn_multi_ue.sh` | Orchestrates namespaces `ue1`, `ue2`, veth, and NAT |
| **Multi-Slice TrafGen** | In-house Bash script | v2.0.0 | `scripts/trafgen.sh` | Injects iperf3 UDP & ICMP canary probes |

### 2.5 Telemetry Collection & Monitoring (VM-6)

| Component | Software Framework | Version | Deployment Mode | Primary Port / Resource |
|---|---|---|---|---|
| **Telemetry Collector** | In-house Python HTTP server | v2.1.0 | Host process (`scripts/telemetry_collector.py`) | Ingestion endpoint `POST :9100/report`, Prometheus `GET :9100/metrics` |
| **Prometheus TSDB** | Prometheus | `v2.45.0` (LTS) | Systemd / Host binary | TSDB scraper polling `:9100/metrics` at 1.0 Hz |
| **Grafana** | Grafana Community | `v10.0.3` | Host service | Visualization dashboards on port `3000` |
| **Telemetry Recorder** | In-house Python script | v2.2.0 | Script (`scripts/record_experiment.py`) | Single-scenario 1.000 Hz 40-column monotonic recorder with manifest metadata |

---

## 3. Custom Source Code Patches Applied

The repository maintains formal Git patch files under `patches/` to document and resolve upstream open-source defects:

### 3.1 Patch: AMF Dynamic NRF Instance Resource URI
* **File Path:** [`patches/amf/0001-fix-amf-nrf-resource-uri.patch`](../patches/amf/0001-fix-amf-nrf-resource-uri.patch)
* **Target File:** `component/oai-amf/src/amf-app/amf_app.cpp` (around line 1614)
* **Root Cause:** In OAI AMF v2.1.0, `amf_app.cpp` omitted the runtime `/{nfInstanceId}` UUID when constructing the HTTP `PUT` registration URI against NSSF-discovered NRF endpoints.
* **Standard Reference:** 3GPP TS 29.510 §6.1.3.3.2 and §6.1.3.3.3.2 (`NFRegister`).
* **Deployment Override:** Committed Docker Compose override [`deploy/compose.amf-nrf-uri.yaml`](../deploy/compose.amf-nrf-uri.yaml).

### 3.2 Patch: UPF PFCP IE Type 43 Release 16 Clamping
* **File Path:** [`patches/upf/0001-fix-upf-pfcp-ie43-rel16-compat.patch`](../patches/upf/0001-fix-upf-pfcp-ie43-rel16-compat.patch)
* **Target File:** `src/common-src/pfcp/3gpp_29.244.hpp` (in UPF `develop` commit `c51cae23`)
* **Root Cause:** Upstream UPF `develop` serializes IE Type 43 (`UP Function Features`) as 8 octets (Rel-17 format), while deployed OAI SMF `v2.1.0` strictly bounds IE 43 length to 6 octets (Rel-16 format), causing SMF to throw a length exception and abort PFCP Association.
* **Resolution:** Clamps serialization of IE 43 to 6 octets while retaining native datapath URR support (`create_urrs`, `pfcp_urr.cpp`, and periodic N4 Session Reports).
* **Deployment Override:** Committed Docker Compose override [`deploy/compose.upf-poc.yaml`](../deploy/compose.upf-poc.yaml).

---

## 4. Slice Identifiers & IP Allocation Table

| Slice Name | SST | SD (Hex) | SD (Dec) | Target DNN | Subnet (UPF Anchor) | Default Serving Cell |
|---|---|---|---|---|---|---|
| **Slice 1 (eMBB)** | `1` | `000001` | `1` | `default` | `12.1.1.0/24` (UPF-1 `192.168.70.142`) | Cell-1 (`du_gnb1.conf`, TCP `:4043`) |
| **Slice 2 (URLLC)** | `222` | `00007B` | `123` | `lowlatency` | `12.1.2.0/24` (UPF-2 `192.168.70.143`) | Cell-2 (`du_gnb2.conf`, TCP `:4044`) |
