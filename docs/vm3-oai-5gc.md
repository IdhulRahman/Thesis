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
| IP address | `10.102.0.164` | Static IP on thesis research subnet |
| Subnet | `10.102.0.0/24` | Main inter-VM communication network |
| Main role | 5G Core Network (Multi-Slice) | Multi-slice 3GPP 5GC Control & User Plane |
| Container runtime | Docker & Docker Compose | Containerized Network Functions (NF) |
| Recommended resources | 4 vCPU, 8 GB RAM, 30 GB Disk | Host compute allocation |
| N2 external endpoint | `10.102.0.164:38412/SCTP` | AMF NG-AP interface published to VM-3 host |
| N3 external endpoint | `192.168.70.0/24` via `10.102.0.164` | Multi-UPF routed Docker bridge network |

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
| NWDAF | `v2.1.0` / Rel-17 | `oaisoftwarealliance/oai-nwdaf:v2.1.0` |
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
- **Conflict Resolution:** If both UPFs published port `2152` directly on VM-3's physical IP (`10.102.0.164`), Docker would fail with `port already allocated`. Hence, user plane GTP-U packets are routed from VM-4 directly to container IPs via the Docker bridge network `192.168.70.0/24`.

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
sudo sysctl -w net.ipv4.conf.default.forwarding=1
sudo sysctl -w net.ipv4.conf.all.rp_filter=0

# Persist sysctl across reboots
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.d/99-5gc.conf
echo "net.ipv4.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.d/99-5gc.conf

# Allow forwarding in iptables and bypass Docker raw PREROUTING anti-spoofing
sudo iptables -P FORWARD ACCEPT
sudo iptables -I FORWARD 1 -i ens33 -o demo-oai -j ACCEPT
sudo iptables -I FORWARD 2 -i demo-oai -o ens33 -j ACCEPT
sudo iptables -t raw -I PREROUTING 1 -i ens33 -d 192.168.70.0/24 -j ACCEPT
sudo iptables -t nat -I POSTROUTING -o demo-oai -j MASQUERADE
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

### 2. Slicing Configuration Files in `conf/`
In OAI CN5G Federation `v2.1.0`, container services mount configuration files from `conf/`. To ensure S-NSSAIs align with the thesis architecture (`SST: 1, SD: 1` eMBB and `SST: 222, SD: 123` URLLC), the following files must be updated:

1. **Slice 1 Configuration (`conf/slicing_slice1_config.yaml`):**
   - Configures `oai-smf-slice1`, `oai-upf-slice1`, and `oai-nrf-slice12`:
   - `snssais`: `sst: 1, sd: 000001` (hex), DNN: `default`, IPv4 subnet: `12.1.1.0/24`.

2. **Slice 2 Configuration (`conf/slicing_slice2_config.yaml`):**
   - Configures `oai-smf-slice2` and `oai-upf-slice2`:
   - `snssais`: `sst: 222, sd: 00007B` (hex), DNN: `lowlatency`, IPv4 subnet: `12.1.2.0/24`.

3. **NSSF Slice Mapping (`conf/nssf_slice_config.yaml`):**
   - Routes slice selection queries from AMF to the appropriate NRF/SMF instance:
   - `[SST: 1, SD: '000001']` -> `nsiId: '11'` (`oai-nrf-slice12`).
   - `[SST: 222, SD: '00007B']` -> `nsiId: '12'` (`oai-nrf-slice12`).

4. **Base Configuration (`conf/slicing_base_config.yaml`):**
   - Contains AMF configuration, PLMN support list, and SBI interface endpoints.
   - Defines `nfs.nrf` pointing to `oai-nrf-slice12` for AMF NF registration.

### 3. Subscriber Database Pre-Provisioning (`database/oai_db2.sql`)

To support multi-UE testing and prevent future database modifications during baseline evaluations, VM-3 uses a batch pre-provisioning script that registers 50 UEs (`208950000000001` to `208950000000050`). Each UE is pre-authorized for both Slice 1 (eMBB) and Slice 2 (URLLC):

```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose

python3 - << 'EOF'
db_file = "database/oai_db2.sql"

print("Pre-provisioning 50 UEs in database/oai_db2.sql...")
sql_entries = ["\n-- ====================================================",
               "-- BATCH PRE-PROVISIONING 50 UEs (IMSI ...001 s/d ...050)",
               "-- ===================================================="]

sqn_json = '{\\"sqn\\": \\"000000000020\\", \\"sqnScheme\\": \\"NON_TIME_BASED\\", \\"lastIndexes\\": {\\"ausf\\": 0}}'
dnn_default = '{\\"default\\":{\\"pduSessionTypes\\":{ \\"defaultSessionType\\": \\"IPV4\\"},\\"sscModes\\": {\\"defaultSscMode\\": \\"SSC_MODE_1\\"},\\"5gQosProfile\\": {\\"5qi\\": 6,\\"arp\\":{\\"priorityLevel\\": 1,\\"preemptCap\\": \\"NOT_PREEMPT\\",\\"preemptVuln\\":\\"NOT_PREEMPTABLE\\"},\\"priorityLevel\\":1},\\"sessionAmbr\\":{\\"uplink\\":\\"100Mbps\\", \\"downlink\\":\\"100Mbps\\"}}}'
dnn_lowlat = '{\\"lowlatency\\":{\\"pduSessionTypes\\":{ \\"defaultSessionType\\": \\"IPV4\\"},\\"sscModes\\": {\\"defaultSscMode\\": \\"SSC_MODE_1\\"},\\"5gQosProfile\\": {\\"5qi\\": 6,\\"arp\\":{\\"priorityLevel\\": 1,\\"preemptCap\\": \\"NOT_PREEMPT\\",\\"preemptVuln\\":\\"NOT_PREEMPTABLE\\"},\\"priorityLevel\\":1},\\"sessionAmbr\\":{\\"uplink\\":\\"100Mbps\\", \\"downlink\\":\\"100Mbps\\"}}}'

for i in range(1, 51):
    imsi = f"2089500000000{i:02d}"
    
    # 1. AuthenticationSubscription (3GPP 5G-AKA credentials)
    auth_sql = f"""INSERT INTO `AuthenticationSubscription` (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`, `n5gcAuthMethod`, `rgAuthenticationInd`, `supi`)
VALUES ('{imsi}', '5G_AKA', '0C0A34601D4F07677303652C0462535B', '0C0A34601D4F07677303652C0462535B', '{sqn_json}', '8000', 'milenage', '63bfa50ee6523365ff14c1f45f88737d', NULL, NULL, NULL, NULL, '{imsi}')
ON DUPLICATE KEY UPDATE `ueid` = `ueid`;"""

    # 2. SessionManagementSubscriptionData (Slice 1: SST 1, SD 000001)
    sm1_sql = f"""INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `singleNssai`, `dnnConfigurations`)
VALUES ('{imsi}', '20895', '{{"sst": 1, "sd": "000001"}}', '{dnn_default}')
ON DUPLICATE KEY UPDATE `ueid` = `ueid`;"""

    # 3. SessionManagementSubscriptionData (Slice 2: SST 222, SD 00007B)
    sm2_sql = f"""INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `singleNssai`, `dnnConfigurations`)
VALUES ('{imsi}', '20895', '{{"sst": 222, "sd": "00007B"}}', '{dnn_lowlat}')
ON DUPLICATE KEY UPDATE `ueid` = `ueid`;"""

    sql_entries.extend([auth_sql, sm1_sql, sm2_sql])

with open(db_file, "a") as f:
    f.write("\n" + "\n".join(sql_entries) + "\n")

print(f"Pre-provisioned 50 subscribers into {db_file}.")
EOF
```

---

## 9. Integration of NWDAF Microservices & Full Stack Startup

### Step 1: Merge NWDAF into Core Compose (`docker-compose-slicing-basic-nrf.yaml`)
To avoid network key collisions (`public_net` duplication and `nwdaf_net` resolution), run this automated merge script:

```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose

python3 - << 'EOF'
fed_file = "docker-compose-slicing-basic-nrf.yaml"
nwdaf_file = "/opt/oran/5gc/oai-cn5g-nwdaf/docker-compose/docker-compose-nwdaf-cn-http1.yaml"

with open(fed_file, "r") as f:
    fed_text = f.read()

with open(nwdaf_file, "r") as f:
    nwdaf_text = f.read()

# Set absolute path for kong declarative configuration
nwdaf_text = nwdaf_text.replace("./conf/kong.yml", "/opt/oran/5gc/oai-cn5g-nwdaf/docker-compose/conf/kong.yml")
nwdaf_text = nwdaf_text.replace("192.168.70.132", "192.168.70.138")
nwdaf_text = nwdaf_text.replace('"8001:8001"', '"8001:8001"\n            - "8080:8000"')

# Extract services from NWDAF compose
nwdaf_services = nwdaf_text.split("\nnetworks:\n")[0].split("services:\n")[1]

# Split fed compose services and networks
fed_parts = fed_text.split("\nnetworks:\n")
fed_services = fed_parts[0]
fed_networks = fed_parts[1]

# Append ONLY nwdaf_net (retaining existing public_net)
nwdaf_net_def = """
    nwdaf_net:
        name: oai-nwdaf-net
        ipam:
            config:
                - subnet: 192.168.74.0/24
"""

merged_compose = fed_services + "\n" + nwdaf_services + "\nnetworks:\n" + fed_networks.rstrip() + "\n" + nwdaf_net_def

with open(fed_file, "w") as f:
    f.write(merged_compose)

print("Merged 8 NWDAF microservices into docker-compose-slicing-basic-nrf.yaml.")
EOF

# Validate syntax
sudo docker compose -f docker-compose-slicing-basic-nrf.yaml config > /dev/null && echo "YAML SYNTAX VALID"
```

### Step 2: Configure Kong Gateway Path-Based Routing
Configure `/opt/oran/5gc/oai-cn5g-nwdaf/docker-compose/conf/kong.yml` without restrictive host filters:

```yaml
_format_version: '1.1'
_transform: true

services:
- name: oai-nwdaf-nbi-analytics
  url: http://192.168.74.151:8080/nnwdaf-analyticsinfo/v1/analytics
  routes:
    - name: oai-nwdaf-nbi-analytics-route
      paths:
      - /nnwdaf-analyticsinfo/v1/analytics

- name: oai-nwdaf-nbi-events
  url: http://192.168.74.152:8080/nnwdaf-eventssubscription/v1
  routes:
    - name: oai-nwdaf-nbi-events-route
      paths:
      - /nnwdaf-eventssubscription/v1

- name: oai-nwdaf-nbi-ml
  url: http://192.168.74.153:8080/nnwdaf-mlmodelprovision/v1
  routes:
    - name: oai-nwdaf-nbi-ml-route
      paths:
      - /nnwdaf-mlmodelprovision/v1
```

### Step 3: Launch Full 25-Container Stack
```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose

# Start MySQL database first
sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d mysql

# Wait until MySQL is healthy
until [ "$(sudo docker inspect -f '{{.State.Health.Status}}' mysql 2>/dev/null)" = "healthy" ]; do
  echo "Waiting for MySQL database to initialize..."
  sleep 3
done
echo "MySQL is healthy."

# Launch remaining 24 Core & NWDAF containers
sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
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
   # Result: 192.168.70.138:38412 LISTEN (and 10.102.0.164:38412 on host)
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

## 11. Extension Guide: Adding a New Network Slice to 5GC

To add a 3rd network slice (e.g., **Slice 3 — Massive IoT**, `SST = 3`, `SD = 0x000003` / decimal `3`, DNN `iot`, UPF IP `192.168.70.144`, UE pool `12.1.3.0/24`), follow these steps on VM-3:

### Step 1: Provision Subscriber in MySQL Database
```sql
-- Connect to MySQL container
docker exec -it mysql mysql -uroot -plinux -D oai_db

-- Add Session Management Data for the UE
INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `sequenceNumber`, `sst`, `sd`, `dnisArray`)
VALUES ('208950000000033', '20895', 1, 3, '000003', '{"iot":{"dnn": "iot"}}');

-- (Optional) If using a new IMSI, insert authentication record into AuthenticationSubscription:
INSERT INTO `AuthenticationSubscription` (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`)
VALUES ('208950000000033', '5G_AKA', '0C0A34601D4F07677303652C0462535B', '0C0A34601D4F07677303652C0462535B', '000000000000', '8000', 'milenage', '63bfa50ee6523365ff14c1f45f88737d', NULL, 0);
```

### Step 2: Register Slice in AMF (`docker-compose-slicing-basic-nrf.yaml`)
Under `services.oai_amf.environment`, declare the 3rd slice:
```yaml
            - SST_2=3                     # [MANDATORY MATCH RAN/UE] Slice 3 SST
            - SD_2=3                      # [MANDATORY MATCH RAN/UE] Slice 3 SD (0x000003)
            - SERVED_GUAMI_SST_2=3
            - SERVED_GUAMI_SD_2=3
            - PLMN_SUPPORT_SST_2=3
            - PLMN_SUPPORT_SD_2=3
```

### Step 3: Register Slice in NSSF (`conf/nssf_slice_config.yaml`)
Add the S-NSSAI mapping entry:
```yaml
configuration:
  slices:
    - sst: 3
      sd: 3
      candidate_nssais:
        - sst: 3
          sd: 3
          dnn: "iot"
          default_smf_id: "smf-slice3"
```

### Step 4: Define Dedicated SMF and UPF Services
In `docker-compose-slicing-basic-nrf.yaml`, add the `oai_smf_slice3` and `oai_upf_slice3` container definitions:
- Assign static IP: `192.168.70.144` on `demo-net`.
- Configure DNN: `iot`.
- Allocate UE IP pool: `12.1.3.0/24`.
- Add `12.1.3.0/24` subnet routing rule to `oai_ext_dn`.

### Step 5: Restart Core Services & Verify
```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
docker logs oai-nssf | grep -i "3"
docker logs oai-amf | grep -i "SST"
```

---

## 12. NWDAF & Core Telemetry / Actuation Adapter

To support cross-domain closed-loop coordination with the O-RAN Non-RT RIC, VM-3 exposes standard-aligned Core analytics and provides user-plane actuation endpoints.

### 12.1 Standards Compliance
- **3GPP TS 23.288:** Architecture for 5G System Network Data Analytics Function (NWDAF).
- **3GPP TS 29.520:** 5G System; Network Data Analytics Services (`Nnwdaf_AnalyticsInfo`).

### 12.2 Native Microservices Deployment (`oai-cn5g-nwdaf`)

NWDAF is deployed natively using the official OpenAirInterface Rel-17 NWDAF implementation (`oai-cn5g-nwdaf`), integrated directly into `/opt/oran/5gc/oai-cn5g-fed/docker-compose/docker-compose-slicing-basic-nrf.yaml`. The NWDAF architecture comprises 8 microservice containers:

| Container Name | Service Role | Internal Port | Host Port / Access |
|---|---|---|---|
| `oai-nwdaf-nbi-gateway` | Kong API Gateway (Declarative reverse proxy) | `8000/tcp`, `8001/tcp` | `8080:8000` (NBI Proxy), `8001:8001` (Admin) |
| `oai-nwdaf-nbi-analytics` | NBI Analytics Info service (`Nnwdaf_AnalyticsInfo`) | `8080/tcp` | `6059:8080` (Direct) |
| `oai-nwdaf-nbi-events` | NBI Events Subscription service | `8080/tcp` | `6060:8080` (Direct) |
| `oai-nwdaf-nbi-ml` | NBI Machine Learning service | `8080/tcp` | `6061:8080` (Direct) |
| `oai-nwdaf-engine` | Core Analytics Engine | `8080/tcp` | `6063:8080` |
| `oai-nwdaf-engine-ads` | Anomaly Detection System (Python 3.6 ML) | `8080/tcp` | Internal bridge |
| `oai-nwdaf-sbi` | Service-Based Interface consumer to AMF/SMF | `8080/tcp` | `6062:8080` |
| `oai-nwdaf-database` | MongoDB analytics storage | `27017/tcp` | `27017:27017` |

### 12.3 Analytics Exposure (`Nnwdaf_AnalyticsInfo`)

The unified entry point for Core analytics exposure is Kong Gateway on VM-3:
```text
http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics
```

#### Query Parameters (3GPP TS 29.520 Standard)
- `event-id`: `NETWORK_PERFORMANCE` (supported values: `NETWORK_PERFORMANCE`, `UE_COMMUNICATION`, `UE_MOBILITY`)
- `ana-req`: JSON string specifying observation window, e.g. `{"startTs": "2026-10-01T00:00:00Z", "endTs": "2026-10-01T23:59:59Z"}`
- `event-filter`: JSON string specifying slice filter and metric type, e.g.:
  - **Slice 1 (eMBB):** `{"snssais": [{"sst": 1, "sd": "000001"}], "dnns": ["oai"], "nwPerfTypes": ["SESS_SUCC_RATIO"]}`
  - **Slice 2 (URLLC):** `{"snssais": [{"sst": 222, "sd": "00007B"}], "dnns": ["default"], "nwPerfTypes": ["SESS_SUCC_RATIO"]}`
- `supported-features`: `{}`
- `tgt-ue`: `{}`

#### Verified Response (HTTP 200 OK)
```json
{
  "anaMetaInfo": {
    "dataWindow": {
      "startTime": "2022-08-01T09:15:33.018Z",
      "stopTime": "2026-10-01T23:59:59Z"
    },
    "strategy": {},
    "accuracy": {}
  },
  "nwPerfs": [
    {
      "networkArea": {},
      "nwPerfType": "SESS_SUCC_RATIO",
      "relativeRatio": 0,
      "absoluteNum": 0,
      "confidence": 0
    }
  ]
}
```

### 12.4 Core Fault Injection Procedure (Simulating Core Bottleneck)
To trigger a controlled user-plane bottleneck during baseline evaluation:

```bash
# Inject 50ms queuing delay and 10% packet drop inside UPF-1 container (Slice 1)
sudo docker exec -it oai-upf-slice1 tc qdisc add dev eth0 root netem delay 50ms loss 10%

# Verify fault injection
sudo docker exec -it oai-upf-slice1 tc qdisc show dev eth0

# Clear fault injection (recovery phase)
sudo docker exec -it oai-upf-slice1 tc qdisc del dev eth0 root
```

---

## 13. VM-3 Baseline Configuration Modes

| Baseline ID | Mode Name | Core Adapter Behavior | User-Plane Adaptation Mechanism |
|---|---|---|---|
| **B0** | Static Default | Inactive. Static queues on both UPFs. | None. Unmitigated congestion under overload. |
| **B1** | RAN-Only Control | Telemetry logging only. No Core actuation. | None. UPF bottleneck is ignored; xApp steers blind. |
| **B2** | Core-Only Control | **Autonomous Core Shaping.** Directly throttles non-priority flows when UPF queue delay exceeds 30ms. | Dynamic rate shaping via `tc tbf` without radio coordination. |
| **B3** | Decoupled | Autonomous Core Shaping runs concurrently with independent xApp. | Operates without cross-domain synchronization (risks action churn). |
| **B4** | Coordinated (Fixed Heuristic) | Passive until commanded by rApp after radio handover timeout. | Applied as fallback step after radio steering timeout. |
| **Proposed** | Bottleneck-Aware Closed-Loop | **Targeted Actuation.** Activated immediately when `CORE_BOTTLENECK` or `JOINT_BOTTLENECK` is classified by rApp. | Targeted user-plane rate conditioning coordinated with RAN backpressure. |

---

## References
- 3GPP TS 23.501: System Architecture for the 5G System (Release 17)
- 3GPP TS 23.288: Architecture for 5G System Network Data Analytics Function (NWDAF)
- 3GPP TS 29.520: 5G System; Network Data Analytics Services (Release 17)
- 3GPP TS 38.413: NG Application Protocol (NGAP)
- 3GPP TS 33.501: Security Architecture and Procedures for 5G
- OAI CN5G Federation: https://github.com/OPENAIRINTERFACE/oai-cn5g-fed

