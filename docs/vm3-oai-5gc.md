# VM-3 — OAI 5G Core (Multi-Slice)

This document describes the deployment of **VM-3 (`oai-5gc`)**, which hosts the OpenAirInterface 5G Core Network (OAI 5GC) configured with **Network Slicing** support.

VM-3 provides the core network control plane and multi-slice user plane functions required by the experimental platform:

```text
VM-4 OAI RAN (gNB CU/DU)
      │
      ├── N2 (NG-AP / 38412 SCTP) ──► oai-amf
      │
      └── N3 (GTP-U / 2152 UDP)   ──► oai-upf (Slice 1 & Slice 2)
                                          │
                                     [VM-3 5GC]
```

The deployment follows official OpenAirInterface guidelines from `oai-cn5g-fed` (pinned release `v2.1.0`) with two logical slices defined for throughput-oriented and low-latency services.

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| VM | VM-3 | Virtual Machine index |
| Hostname | `oai-5gc` | Host identifier |
| IP address | `10.10.10.13` | Static IP on thesis research subnet |
| Subnet | `10.10.10.0/24` | Main inter-VM communication network |
| Main role | 5G Core Network (Multi-Slice) | Multi-slice 3GPP 5GC Control & User Plane |
| Container runtime | Docker & Docker Compose | Containerized Network Functions (NF) |
| Recommended resources | 4 vCPU, 8 GB RAM, 30 GB Disk | Host compute allocation |
| N2 external endpoint | `10.10.10.13:38412/SCTP` | AMF NG-AP interface published to VM-3 host |
| N3 external endpoint | `192.168.70.0/24` via `10.10.10.13` | Multi-UPF routed Docker bridge network |

---

## 2. Software Components & Versions

The deployment uses official container images from the OpenAirInterface Software Alliance:

| Component | Tag / Version | Image |
|---|---|---|
| OAI 5G Core Federation | `v2.1.0` (pinned) | `https://github.com/OPENAIRINTERFACE/oai-cn5g-fed` |
| AMF | `v2.1.0` | `oaisoftwarealliance/oai-amf:v2.1.0` |
| SMF | `v2.1.0` | `oaisoftwarealliance/oai-smf:v2.1.0` |
| UPF | `v2.1.0` | `oaisoftwarealliance/oai-upf:v2.1.0` |
| NRF | `v2.1.0` | `oaisoftwarealliance/oai-nrf:v2.1.0` |
| UDM | `v2.1.0` | `oaisoftwarealliance/oai-udm:v2.1.0` |
| UDR | `v2.1.0` | `oaisoftwarealliance/oai-udr:v2.1.0` |
| AUSF | `v2.1.0` | `oaisoftwarealliance/oai-ausf:v2.1.0` |
| NSSF | `v2.1.0` | `oaisoftwarealliance/oai-nssf:v2.1.0` |
| Database | `8.0` | `mysql:8.0` |

---

## 3. Theoretical & Standardization Rationale for 5GC Parameters

### 3.1 3GPP Network Slicing Model (S-NSSAI)
- **Standard:** **3GPP TS 23.501 Clause 5.15.2** and **3GPP TS 29.531 (NSSF)**.
- **Slice 1 (Throughput-Oriented / eMBB):**
  - `SST = 1, SD = 0x000001` (decimal `1`), DNN: `default`.
  - Served by `oai-smf-slice1` and `oai-upf-slice1` (`192.168.70.142`).
  - Standardized SST `1` is allocated internationally for Enhanced Mobile Broadband (eMBB).
- **Slice 2 (Low-Latency / Mission-Critical):**
  - `SST = 222 (0xDE), SD = 0x00007B` (decimal `123`), DNN: `lowlatency`.
  - Served by `oai-smf-slice2` and `oai-upf-slice2` (`192.168.70.143`).
  - SST `222` falls within the operator-specific range (`128–255`), representing customized QoS and low-latency scheduling.
  *(Note: An alternative standard profile `SST = 1, SD = 0x000002` is also supported if using the basic OAI demonstration schema).*
- **SD Representation Rule:** In 3GPP ASN.1 and OAI configuration files, SD is 24 bits. It can be formatted as hexadecimal (`0x000001` / `0x00007B`) or integer (`1` / `123`). The value must match identically between AMF, SMF, gNB CU, and the MySQL subscriber database.

### 3.2 PLMN Identity & Tracking Area Code
- **Standard:** **3GPP TS 38.413 (NGAP)** and **3GPP TS 23.003**.
- **Values:** `MCC = 208`, `MNC = 95`, `TAC = 0xa000` (decimal `40960`).
- **Rationale:** Standard OAI testbed PLMN. The AMF validates the PLMN and TAC advertised by gNB CU during the `NGSetupRequest`. If any parameter is unlisted, AMF responds with `NGSetupFailure`.

### 3.3 Security & Authentication Credentials (5G AKA)
- **Standard:** **3GPP TS 33.501** (Security architecture and procedures for 5G System).
- **Values:**
  - `IMSI / SUPI`: `208950000000031` (first 5 digits encode MCC `208` and MNC `95`).
  - Secret Key (`Ki`): `0C0A34601D4F07677303652C0462535B` (128-bit key).
  - Operator Code (`OPc`): `63bfa50ee6523365ff14c1f45f88737d` (derived from OP and Ki).
  - Authentication Algorithm: Milenage.
- **Constraint:** Must match the SIM parameters configured on VM-5 (`oai-nrue`).

### 3.4 Multi-UPF User-Plane Routing (Avoiding Port Collisions)
- **Standard:** **3GPP TS 29.281** (GTP-U protocol).
- **Design:** Each slice runs a dedicated UPF container:
  - `oai-upf-slice1`: IP `192.168.70.142`, UDP port `2152`.
  - `oai-upf-slice2`: IP `192.168.70.143`, UDP port `2152`.
- **Conflict Resolution:** If both UPFs published port `2152` directly on VM-3's physical IP (`10.10.10.13`), Docker would fail with `port already allocated`. Hence, user plane GTP-U packets are routed from VM-4 directly to container IPs via the Docker bridge network `192.168.70.0/24`.

---

## 4. Parameter Customization Reference Guide

| Parameter | Current Value | Classification | Customization Rules & Impact |
|---|---|---|---|
| `MCC` | `208` | `[MANDATORY MATCH RAN/UE]` | Mobile Country Code across AMF, gNB CU, and UE SIM. |
| `MNC` | `95` | `[MANDATORY MATCH RAN/UE]` | Mobile Network Code across AMF, gNB CU, and UE SIM. |
| `TAC` | `0xa000` (40960) | `[MANDATORY MATCH RAN]` | Tracking Area Code in AMF `slicing_base_config.yaml`. |
| `SST_0` / `SD_0` | `1` / `1` (`0x000001`) | `[MANDATORY MATCH RAN/UE]` | Slice 1 identifier (eMBB). |
| `SST_1` / `SD_1` | `222` / `123` (`0x00007B`) | `[MANDATORY MATCH RAN/UE]` | Slice 2 identifier (Low Latency). |
| `DNN_0` | `default` | `[CUSTOMIZABLE]` | Data Network Name for Slice 1. |
| `DNN_1` | `lowlatency` | `[CUSTOMIZABLE]` | Data Network Name for Slice 2. |
| `IMSI` / `SUPI` | `208950000000031` | `[MANDATORY MATCH UE]` | UE subscription identifier stored in MySQL `oai_db2.sql`. |
| `Ki` / `OPc` | `0C0A...` / `63bf...` | `[MANDATORY MATCH UE]` | UE cryptographic authentication keys. |
| `AMF_NGAP_PORT` | `38412` | `[FIXED / ARCHITECTURE]` | 3GPP standard N2 NG-AP SCTP port. |
| `UPF_GTPU_PORT` | `2152` | `[FIXED / ARCHITECTURE]` | 3GPP standard N3 GTP-U UDP port. |
| `DOCKER_BRIDGE_SUBNET` | `192.168.70.0/24` | `[FIXED / ARCHITECTURE]` | Internal container network routed from VM-4. |

---

## 5. Directory Layout

Working directories on VM-3:

```text
/opt/oran/5gc/
└── oai-cn5g-fed/
    ├── docker-compose/
    │   ├── docker-compose-slicing-basic-nrf.yaml
    │   ├── database/
    │   │   └── oai_db2.sql
    │   └── conf/
    │       ├── slicing_base_config.yaml
    │       └── nssf_slice_config.yaml
```

---

## 6. Prerequisites: Host Setup & Kernel SCTP

### Step 1: Install Kernel Module & Dependencies
```bash
sudo apt update && sudo apt install -y libsctp-dev lksctp-tools iproute2 net-tools

# Load SCTP kernel module
sudo modprobe sctp
echo "sctp" | sudo tee -a /etc/modules-load.d/sctp.conf
lsmod | grep sctp
```

### Step 2: Configure Host IP Forwarding & Firewall
Enable forwarding so VM-4 can reach the container bridge network (`192.168.70.0/24`):

```bash
# Enable IPv4 forwarding immediately
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv4.conf.all.forwarding=1
sudo sysctl -w net.ipv4.conf.all.rp_filter=0

# Persist sysctl across reboots
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.d/99-5gc.conf
echo "net.ipv4.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.d/99-5gc.conf

# Allow forwarding in iptables
sudo iptables -P FORWARD ACCEPT
sudo iptables -I DOCKER-USER 1 -j ACCEPT
```

---

## 7. Clone the Official OAI 5GC Federation Repository

```bash
sudo mkdir -p /opt/oran/5gc
sudo chown -R "$USER":"$USER" /opt/oran/5gc
cd /opt/oran/5gc
git clone https://github.com/OPENAIRINTERFACE/oai-cn5g-fed.git
cd oai-cn5g-fed
git checkout v2.1.0
git rev-parse HEAD > /opt/oran/5gc/oai-cn5g-fed.commit
```

---

## 8. Configuration Snippets with Parameter Annotations

### 1. N2 Control Plane in `docker-compose-slicing-basic-nrf.yaml`
```yaml
    oai_amf:
        container_name: "oai-amf"
        image: oaisoftwarealliance/oai-amf:v2.1.0
        # [FIXED / ARCHITECTURE] N2 port exposed to VM-3 host interface
        ports:
            - "38412:38412/sctp"
        environment:
            - TZ=Europe/Paris
            - MCC=208                     # [MANDATORY MATCH RAN/UE]
            - MNC=95                      # [MANDATORY MATCH RAN/UE]
            - REGION_ID=128               # [CUSTOMIZABLE] AMF Region ID
            - AMF_SET_ID=1                # [CUSTOMIZABLE] AMF Set ID
            - SERVED_GUAMI_MCC_0=208      # [MANDATORY MATCH RAN]
            - SERVED_GUAMI_MNC_0=95       # [MANDATORY MATCH RAN]
            - PLMN_SUPPORT_MCC=208        # [MANDATORY MATCH RAN]
            - PLMN_SUPPORT_MNC=95         # [MANDATORY MATCH RAN]
            - PLMN_SUPPORT_TAC=0xa000     # [MANDATORY MATCH RAN] (40960)
            - SST_0=1                     # [MANDATORY MATCH RAN/UE] Slice 1 SST
            - SD_0=1                      # [MANDATORY MATCH RAN/UE] Slice 1 SD (0x000001)
            - SST_1=222                   # [MANDATORY MATCH RAN/UE] Slice 2 SST (0xDE)
            - SD_1=123                    # [MANDATORY MATCH RAN/UE] Slice 2 SD (0x00007B)
```

### 2. Subscriber Database in `database/oai_db2.sql`
```sql
-- [MANDATORY MATCH UE] Test UE Subscription Registration
INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `sequenceNumber`, `sst`, `sd`, `dnisArray`)
VALUES
  ('208950000000031', '20895', 1, 1, '000001', '{\"default\":{\"dnn\": \"default\"}}'),
  ('208950000000031', '20895', 2, 222, '00007B', '{\"lowlatency\":{\"dnn\": \"lowlatency\"}}');
```

---

## 9. Pull Images and Staged Startup

### Step 1: Pull Validated Images
```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
docker compose -f docker-compose-slicing-basic-nrf.yaml pull
```

### Step 2: Start MySQL Database
```bash
docker compose -f docker-compose-slicing-basic-nrf.yaml up -d mysql

until [ "$(docker inspect -f '{{.State.Health.Status}}' mysql)" = "healthy" ]; do
  echo "Waiting for MySQL database to initialize..."
  sleep 3
done
echo "MySQL is healthy."
```

### Step 3: Start Common Control Plane
```bash
docker compose -f docker-compose-slicing-basic-nrf.yaml up -d oai_nrf_slice12 oai_udr oai_udm oai_ausf oai-nssf
sleep 5
```

### Step 4: Start AMF, SMF Slice 1 & 2, and UPF Slice 1 & 2
```bash
docker compose -f docker-compose-slicing-basic-nrf.yaml up -d oai_amf oai_smf_slice1 oai_upf_slice1 oai_smf_slice2 oai_upf_slice2 oai_ext_dn
```

---

## 10. Acceptance Criteria & Validation

All acceptance checks have passed on VM-3:

1. **All Containers Running [VALIDATED]:**
   ```bash
   docker compose -f docker-compose-slicing-basic-nrf.yaml ps
   # Result: 12 containers Up (healthy)
   ```

2. **AMF Listening on N2 SCTP Port [VALIDATED]:**
   ```bash
   sudo docker exec oai-amf netstat -l --sctp || sudo docker exec oai-amf cat /proc/net/sctp/eps
   # Result: 192.168.70.138:38412 LISTEN (and 10.10.10.13:38412 on host)
   ```

3. **Multi-Slice UPF IP Endpoints [VALIDATED]:**
   - Slice 1 UPF: `192.168.70.142` (GTP-U port `2152`)
   - Slice 2 UPF: `192.168.70.143` (GTP-U port `2152`)

4. **NSSF Slices Loaded [VALIDATED]:**
   ```bash
   docker logs oai-nssf | grep -i "slice"
   # Result: Slices [SST: 1, SD: 1] and [SST: 222, SD: 123] successfully registered.
   ```

---

## References
- 3GPP TS 23.501: System Architecture for the 5G System
- 3GPP TS 38.413: NG Application Protocol (NGAP)
- 3GPP TS 33.501: Security Architecture and Procedures for 5G
- OAI CN5G Federation: https://github.com/OPENAIRINTERFACE/oai-cn5g-fed
