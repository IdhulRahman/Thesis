# VM-07 — Standalone 3GPP NWDAF (Analytics Logical Function)

This document describes the deployment of **VM-07 (`oai-nwdaf`)**, which hosts the standalone 3GPP Network Data Analytics Function (NWDAF) microservice stack in the experimental platform.

VM-07 operates as an independent analytics node decoupled from 5G Core control and user planes:

```text
       VM-3: 5G Core (10.102.0.246)
        │
        │ Nsmf_EventExposure (QOS_MON HTTP/2 notifications)
        ▼
┌────────────────────────────────────────────────────────┐
│ VM-07: Standalone 3GPP NWDAF (10.102.0.233)            │
│                                                        │
│  ┌──────────────────┐          ┌────────────────────┐  │
│  │  oai-nwdaf-sbi   │ ───────► │ MongoDB: testing   │  │
│  │  (Notification)  │          │ (collection: smf)  │  │
│  └──────────────────┘          └─────────┬──────────┘  │
│                                          │             │
│  ┌──────────────────┐          ┌─────────▼──────────┐  │
│  │ Kong API Gateway │ ◄─────── │  oai-nwdaf-engine  │  │
│  │ (Port :8080)     │          │  (Analytics Info)  │  │
│  └────────┬─────────┘          └────────────────────┘  │
└───────────┼────────────────────────────────────────────┘
            │
            │ Nnwdaf_AnalyticsInfo (GET /analytics)
            ▼
VM-6: Telemetry Collector (10.102.0.67:9100)
```

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| VM | VM-07 | Virtual Machine index |
| Hostname | `oai-nwdaf` | Host identifier |
| IP address | `10.102.0.233` | Static IP on thesis research subnet (`10.102.0.0/24`) |
| Subnet | `10.102.0.0/24` | Main inter-VM communication network |
| Main role | Standalone 3GPP NWDAF (AnLF) | Service-Based Analytics Logical Function |
| Container runtime | Docker & Docker Compose | Containerized NWDAF microservices |
| Recommended resources | 4 vCPU, 8 GB RAM, 30 GB Disk | Host compute allocation |
| Northbound NBI endpoint | `http://10.102.0.233:8080` | Kong API Gateway exposing `Nnwdaf_AnalyticsInfo` |
| Kong Admin endpoint | `http://10.102.0.233:8001` | Kong internal administration port |
| MongoDB Datastore | `10.102.0.233:27017` | Persistent analytics datastore |

---

## 2. Theoretical & Architectural Rationale

### 2.1 Decoupled Standalone Deployment
- **Why Separate NWDAF from 5G Core:**  
  In earlier testbed iterations, NWDAF was colocated with the 5G Core on VM-3. Disaggregating NWDAF into VM-07 provides two key advantages:
  1. **Compute Isolation:** Eliminates CPU contention between UPF datapath processing (simpleswitch/qdisc) and NWDAF analytics engine/MongoDB ingestion.
  2. **True SBA Conformance:** Enforces strict adherence to 3GPP Release 16/17 Service-Based Architecture (SBA), where NWDAF interacts with Core NFs (NRF, SMF, AMF) purely over routed network interfaces.

### 2.2 Analytics Logical Function (AnLF) vs. Model Training Logical Function (MTLF)
- Under **3GPP TS 23.288**, NWDAF comprises AnLF (analytics generation and exposure) and MTLF (machine learning model training).
- In our research architecture, VM-07 functions strictly as an **AnLF**. It ingests standard `QOS_MON` event exposure notifications from SMF-1, stores URR records in MongoDB, and exposes analytics via Northbound REST API. Offline model training and predictive inference are executed externally in the O-RAN Non-RT RIC rApp on VM-1 (`10.102.0.168`).

---

## 3. Host Setup & Routing to VM-3 Core Network

### Step 1: Install Docker & Dependencies on VM-07
```bash
sudo apt update && sudo apt install -y \
  docker.io docker-compose-v2 git curl jq net-tools iproute2

# Enable and start Docker
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

### Step 2: Configure Static Route to 5GC Subnet
VM-07 must communicate with Core NFs (NRF at `192.168.70.136` and SMF-1 at `192.168.70.139`) hosted inside Docker on VM-3 (`10.102.0.246`):

```bash
# Add route to 5GC bridge subnet via VM-3
sudo ip route add 192.168.70.0/24 via 10.102.0.246

# Persist route across reboots
echo "up ip route add 192.168.70.0/24 via 10.102.0.246" | sudo tee -a /etc/network/interfaces.d/5gc-route || true
```

### Step 3: Verify Inter-VM Reachability
```bash
# Ping VM-3 host interface
ping -c 2 10.102.0.246

# Ping NRF container on VM-3 (via routed bridge)
ping -c 2 192.168.70.136

# Test NRF HTTP SBI endpoint
curl -i http://192.168.70.136:8080/nnrf-disc/v1/nf-instances?nf-type=SMF
```

---

## 4. Directory Layout & Repository Setup

Create the working directories on VM-07:

```bash
sudo mkdir -p /opt/oran/nwdaf
sudo chown -R "$USER":"$USER" /opt/oran/nwdaf
cd /opt/oran/nwdaf

git clone https://github.com/OPENAIRINTERFACE/oai-cn5g-nwdaf.git
cd oai-cn5g-nwdaf
git checkout develop
```

Target directory layout:
```text
/opt/oran/nwdaf/oai-cn5g-nwdaf/
└── docker-compose/
    ├── docker-compose-nwdaf-standalone.yaml
    └── conf/
        └── kong.yml
```

---

## 5. Configuration Files Setup

### 5.1 Configure Kong API Gateway Declarative Routing (`conf/kong.yml`)
Configure `/opt/oran/nwdaf/oai-cn5g-nwdaf/docker-compose/conf/kong.yml`:

```yaml
_format_version: '1.1'
_transform: true

services:
- name: oai-nwdaf-nbi-analytics
  url: http://oai-nwdaf-nbi-analytics:8080/nnwdaf-analyticsinfo/v1/analytics
  routes:
    - name: oai-nwdaf-nbi-analytics-route
      paths:
      - /nnwdaf-analyticsinfo/v1/analytics

- name: oai-nwdaf-nbi-events
  url: http://oai-nwdaf-nbi-events:8080/nnwdaf-eventssubscription/v1
  routes:
    - name: oai-nwdaf-nbi-events-route
      paths:
      - /nnwdaf-eventssubscription/v1

- name: oai-nwdaf-nbi-ml
  url: http://oai-nwdaf-nbi-ml:8080/nnwdaf-mlmodelprovision/v1
  routes:
    - name: oai-nwdaf-nbi-ml-route
      paths:
      - /nnwdaf-mlmodelprovision/v1
```

### 5.2 Standalone Docker Compose (`docker-compose-nwdaf-standalone.yaml`)
Create `/opt/oran/nwdaf/oai-cn5g-nwdaf/docker-compose/docker-compose-nwdaf-standalone.yaml`:

```yaml
version: '3.8'

services:
    mongodb:
        image: mongo:4.4
        container_name: oai-nwdaf-mongodb
        restart: always
        ports:
            - "27017:27017"
        environment:
            - MONGO_INITDB_DATABASE=testing
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.150

    oai-nwdaf-sbi:
        image: oaisoftwarealliance/oai-nwdaf-sbi:develop
        container_name: oai-nwdaf-sbi
        depends_on:
            - mongodb
        environment:
            - AMF_IP_ADDR=http://192.168.70.138:8080
            - AMF_HTTP_VERSION=2
            - SMF_IP_ADDR=http://192.168.70.139:8080
            - SMF_HTTP_VERSION=2
            - MONGODB_IP_ADDR=192.168.74.150
            - MONGODB_PORT=27017
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.154

    oai-nwdaf-engine:
        image: oaisoftwarealliance/oai-nwdaf-engine:develop
        container_name: oai-nwdaf-engine
        depends_on:
            - mongodb
        environment:
            - MONGODB_IP_ADDR=192.168.74.150
            - MONGODB_PORT=27017
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.155

    oai-nwdaf-nbi-analytics:
        image: oaisoftwarealliance/oai-nwdaf-nbi-analytics:develop
        container_name: oai-nwdaf-nbi-analytics
        depends_on:
            - oai-nwdaf-engine
        environment:
            - NWDAF_ENGINE_IP_ADDR=192.168.74.155
            - NWDAF_ENGINE_PORT=8080
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.151

    oai-nwdaf-nbi-events:
        image: oaisoftwarealliance/oai-nwdaf-nbi-events:develop
        container_name: oai-nwdaf-nbi-events
        depends_on:
            - oai-nwdaf-engine
        environment:
            - NWDAF_ENGINE_IP_ADDR=192.168.74.155
            - NWDAF_ENGINE_PORT=8080
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.152

    oai-nwdaf-nbi-gateway:
        image: kong:3.3.0
        container_name: oai-nwdaf-nbi-gateway
        depends_on:
            - oai-nwdaf-nbi-analytics
            - oai-nwdaf-nbi-events
        ports:
            - "8080:8000"
            - "8001:8001"
        environment:
            - KONG_DATABASE=off
            - KONG_DECLARATIVE_CONFIG=/conf/kong.yml
            - KONG_PROXY_ACCESS_LOG=/dev/stdout
            - KONG_ADMIN_ACCESS_LOG=/dev/stdout
            - KONG_PROXY_ERROR_LOG=/dev/stderr
            - KONG_ADMIN_ERROR_LOG=/dev/stderr
            - KONG_ADMIN_LISTEN=0.0.0.0:8001
        volumes:
            - ./conf/kong.yml:/conf/kong.yml:ro
        networks:
            nwdaf_net:
                ipv4_address: 192.168.74.156

networks:
    nwdaf_net:
        name: oai-nwdaf-net
        ipam:
            config:
                - subnet: 192.168.74.0/24
```

---

## 6. Startup & Verification Procedures

### Step 1: Start NWDAF Stack
```bash
cd /opt/oran/nwdaf/oai-cn5g-nwdaf/docker-compose
sudo docker compose -f docker-compose-nwdaf-standalone.yaml up -d
```

### Step 2: Verify Container Health
```bash
sudo docker compose -f docker-compose-nwdaf-standalone.yaml ps
```
Ensure all containers are running and healthy.

### Step 3: Test Kong Gateway Endpoint
```bash
curl -i http://localhost:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION
```
Expected response: HTTP 200 OK or structured JSON payload from AnLF.

### Step 4: Verify Remote Access from VM-6
From VM-6 (`10.102.0.67`), test reachability to VM-07 NWDAF NBI:
```bash
curl -s "http://10.102.0.233:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION" | jq .
```
