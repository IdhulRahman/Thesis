# VM-2 — Near-RT RIC

This document describes the deployment of **VM-2 (`near-rt-ric`)**, which hosts the Near-RT RIC-side components used in this project.

VM-2 provides the near-real-time control side of the multi-timescale architecture:

```text
VM-1 Non-RT RIC
      │
      │ A1
      ▼
VM-2 Near-RT RIC
      │
      ├── A1 Mediator
      ├── A1 Compatibility Shim
      ├── Python xApp Runtime
      ├── E2Term
      ├── E2Mgr
      ├── SubMgr
      ├── AppMgr
      ├── DBaaS
      └── RMR
      │
      │ E2
      ▼
VM-4 OAI RAN
```

At the current implementation stage, the **A1 policy distribution path** (from A1 PMS on VM-1 to the Python xApp on VM-2) and the **E2 Setup & Service Model Registration handshake** (from OAI RAN on VM-4 to `ric_e2term` on VM-2 with 8 Service Models) have been **empirically validated**. Closed-loop E2SM-RC control actuation and dynamic serving-cell handover remain **planned research work (Phase B)**.

---

## 1. VM Specification

| Parameter | Value | Description |
|---|---|---|
| VM | VM-2 | Virtual Machine index |
| Hostname | `near-rt-ric` | Host identifier |
| IP address | `10.102.0.66` | Static IP on thesis research subnet |
| Subnet | `10.102.0.0/24` | Main inter-VM communication network |
| Main role | Near-RT RIC | O-RAN Near-Real-Time RIC control plane |
| Container runtime | Docker | Minimal O-RAN SC containers |
| A1 external endpoint | `10.102.0.66:10000/TCP` | Native A1 Mediator endpoint |
| A1 compatibility endpoint | `10.102.0.66:10001/TCP` | A1 Compatibility Shim for Non-RT RIC |
| E2 external endpoint | `10.102.0.66:36421/SCTP` | O-RAN E2Term SCTP listening port |

---

## 2. Software Components

The validated deployment uses the minimal O-RAN SC RIC packaging provided by the official srsRAN repository:

| Component | Version / Tag | Description |
|---|---|---|
| Minimal O-RAN SC RIC | `i-release` | Docker Compose platform bundle |
| E2Term | `6.0.4` | O-RAN E2 termination daemon (SCTP & ASN.1) |
| E2Mgr | `6.0.4` | NodeB inventory and E2 setup coordinator |
| DBaaS | `0.5.7` | Shared Data Layer (SDL) on Redis 5.0.9 |
| SubMgr | `0.10.1` | E2 Subscription Manager |
| AppMgr | `0.5.7` | xApp lifecycle and onboarding manager |
| Route Manager simulator | `i-release` | Static RMR routing policy distributor |
| Python xApp runner | `i-release` | Execution container for Python xApps |
| A1 Mediator | `3.2.2` | A1 policy interface implementation |
| A1 policy baseline | `20008` | Traffic steering policy type schema |

Pinned minimal RIC repository commit used during deployment:
```text
621ade26251f69a4ad079ba98bb708d8e5aeeb98
```

Pinned A1 Mediator repository commit used during deployment:
```text
09a757b4fd63198d8690d50b52bfd04552d47f1f
```

---

## 3. Theoretical & Technical Rationale for Near-RT RIC Configurations

### 3.1 DBaaS Redis 5.0.9 Downgrade (`0.5.7` vs `latest`)
- **Root Cause & Protocol Mismatch:** O-RAN SC E2Mgr (`6.0.4`) and the Shared Data Layer (`libsdl-go`) use an older `go-redis` v6 client implementing the Redis Serialization Protocol (RESP2). When connecting to Redis 6+ or Redis 7 (`latest`), `go-redis` issues a `COMMAND` query to discover cluster capabilities. Redis 7 returns a 7-element (or 8-element) array for each command description, whereas `go-redis` v6 strictly expects a 6-element array, triggering a fatal panic:
  ```text
  panic: redis: got 7 elements in COMMAND reply, wanted 6
  ```
- **Solution:** Pinning `DBAAS_VER=0.5.7` deploys `nexus3.o-ran-sc.org:10002/o-ran-sc/ric-plt-dbaas:0.5.7`, which runs Redis 5.0.9. Redis 5.0.9 conforms strictly to the 6-element RESP2 specification, allowing E2Mgr to connect and initialize the `rnibWriter` without panics.

### 3.2 E2Manager Keepalive Timeout Tuning
- **Standard Issue in Static Testbeds:** By default in `ric/configs/e2mgr.yaml`, `keepAliveResponseTimeoutMs` is set to `4500` ms (4.5 seconds) and `e2tInstanceDeletionTimeoutMs` to `15000` ms (15 seconds). If E2Term does not respond to keepalive pings within 4.5s (due to missing route manager hooks or static testbed architecture), E2Mgr triggers an automated deletion:
  ```text
  DELETE /ric/v1/handles/e2t
  ```
  Once deleted, incoming `E2SetupRequest` messages from gNodeBs are discarded because E2Mgr considers the termination instance offline.
- **Solution:** Relaxing `keepAliveResponseTimeoutMs: 3600000` (1 hour) and `keepAliveDelayMs: 3600000` stabilizes the E2Term instance permanently, ensuring immediate E2 connection acceptance.

### 3.3 A1 Compatibility Shim Architecture
- **Protocol Gap:** A1 PMS v2.6.0 (H-Release on VM-1) uses the standard ONAP/OSC A1 client (`OscA1Client`), which queries `/a1-p/healthcheck` and sends REST requests expecting specific HTTP response semantics. A1 Mediator v3.2.2 on VM-2 exposes endpoints under `/A1-P/v2/...` with strict case sensitivity.
- **Solution:** The NGINX reverse-proxy shim listening on port `10001` bridges URL prefixes, normalizes headers, and exposes `/a1-p/healthcheck`, allowing complete interoperability between Non-RT RIC and Near-RT RIC.

### 3.4 Global gNB Identity, Service Models, and Implementation Milestones
- **Identity Formation:** When VM-4 (`oai-ran`) initiates E2 Setup, it sends `Global gNB ID` composed of PLMN `208.95` and gNB ID `0xe00` (`3584`), resulting in identity:
  ```text
  gnb_208_095_00000e00
  ```
- **Service Models:** E2Mgr registers all 8 Service Models embedded in the RAN context into DBaaS Redis, enabling any xApp to interact with E2SM-KPM (ID: 2) and E2SM-RC (ID: 3).

#### Verifiable O-RAN Milestone Status & Demarcation:
1. **Milestone 1 — E2 Setup Handshake (`Validated`):** SCTP connection over port `36421` and bidirectional E2 Setup Request / Response successfully establish node association with DBaaS.
2. **Milestone 2 — Service Model Registration (`Validated`):** All 8 Service Models successfully exposed by OAI CU and registered in Near-RT RIC DBaaS Redis.
3. **Milestone 3 — A1 Policy Delivery & Feedback (`Validated`):** A1 PMS (VM-1) dispatches Policy Type `20008` to A1 Mediator; A1 Mediator forwards via RMR to `a1_policy_xapp.py`; xApp responds with RMR message `20011` (`ENFORCED`).
4. **Milestone 4 — E2 Subscription & Indication (`Historical / Standalone Prototype`):** Ingested in standalone FlexRIC tests; primary 1.000 Hz logging pipeline for the cross-domain thesis dataset currently ingests MAC scheduler logs via `ran_adapter.py`.
5. **Milestone 5 — E2SM-RC Control Request & Acknowledgment (`Planned — Phase B`):** Real-time generation and transmission of E2 Control messages from xApp to OAI CU softmodem.
6. **Milestone 6 — Serving-Cell Handover & Traffic Continuity (`Planned — Phase B`):** Closed-loop handover of the same UE instance between Cell-1 and Cell-2 with continuous PDU session dataflow and SLA evaluation.
   > [!IMPORTANT]
   > **RFsim Testbed Demarcation:** In the current baseline testbed, UE-1 (port `4043`) and UE-2 (port `4044`) are statically bound to distinct RFsim DU instances. This validates multi-cell coexistence and RF separation, but does **not** constitute proof of active dynamic inter-cell handover or serving-cell steering. Serving-cell switching remains a Phase B milestone.

---

## 4. Parameter Customization Reference Guide

| Parameter | Current Value | Classification | Customization Rules & Impact |
|---|---|---|---|
| `RIC_ID` | `7b0000-000000/18` | `[CUSTOMIZABLE]` | Unique identifier for this Near-RT RIC instance in the PLMN. |
| `RIC_SUBNET` | `10.0.2.0/24` | `[CUSTOMIZABLE]` | Internal Docker bridge network for RIC containers. |
| `E2TERM_SCTP_PORT` | `36421` | `[MANDATORY MATCH RAN]` | O-RAN standard E2 SCTP port. Must match `cu_gnb.conf` `near_ric_ip_addr`. |
| `A1_MEDIATOR_PORT` | `10000` | `[FIXED / ARCHITECTURE]` | Native A1 REST port internal to VM-2. |
| `A1_COMPAT_PORT` | `10001` | `[MANDATORY MATCH NON-RT]`| Compatibility port queried by A1 PMS on VM-1. |
| `DBAAS_VER` | `0.5.7` | `[FIXED / ARCHITECTURE]` | Must remain `0.5.7` (Redis 5.0.9) to prevent RESP2 panic. |
| `E2TERM_VER` / `E2MGR_VER` | `6.0.4` | `[FIXED / ARCHITECTURE]` | Validated O-RAN SC i-release binaries. |
| `loglevel` (e2mgr / e2term) | `4` / `debug` | `[CUSTOMIZABLE]` | Log verbosity (1=error, 2=warn, 3=info, 4=debug). |
| `keepAliveResponseTimeoutMs`| `3600000` | `[FIXED / ARCHITECTURE]` | Relaxed timeout to prevent automated E2T instance deletion. |

---

## 5. Directory Layout

The main VM-2 paths are:

```text
/opt/oran/nearrt/
├── oran-sc-ric/
│   ├── docker-compose.yml
│   ├── ric/
│   │   └── configs/
│   │       ├── routes.rtg
│   │       ├── e2mgr.yaml
│   │       └── e2term.conf
│   └── xApps/
│       └── python/
│           └── a1_policy_xapp.py
│
├── a1/
│   ├── ric-plt-a1/
│   │   └── local.rt
│   └── policies/
│       └── ts-policy-type-20008.json
│
└── a1-compat/
    └── nginx.conf
```

---

## 6. Clone the Minimal Near-RT RIC

Create the working directory:

```bash
sudo mkdir -p /opt/oran/nearrt
sudo chown -R "$USER":"$USER" /opt/oran/nearrt
cd /opt/oran/nearrt
```

Clone and pin the validated commit:

```bash
git clone https://github.com/srsran/oran-sc-ric.git
cd oran-sc-ric
git checkout 621ade26251f69a4ad079ba98bb708d8e5aeeb98
git rev-parse HEAD > /opt/oran/nearrt/oran-sc-ric.commit
```

---

## 7. Minimal RIC Environment (`.env`)

The validated `.env` contains:

```text
# [FIXED / ARCHITECTURE] Release and system naming
SC_RIC_VERSION=i-release
SYSTEM_NAME=oran_sc_ric

# [CUSTOMIZABLE] Near-RT RIC Global Identifier
RIC_ID=7b0000-000000/18

# [CUSTOMIZABLE] RMR logging verbosity (0 = fatal, 1 = error, 2 = warn, 3 = info)
RMR_LOG_VLEVEL=0

# [CUSTOMIZABLE] Internal Docker network for RIC components
RIC_SUBNET=10.0.2.0/24

# [FIXED / ARCHITECTURE] E2Term component settings
E2TERM_VER=6.0.4
E2TERM_NAME=e2term
E2TERM_IP=10.0.2.10
E2TERM_SCTP_PORT=36421              # [MANDATORY MATCH RAN] E2 SCTP port

# [FIXED / ARCHITECTURE] E2 Manager settings
E2MGR_VER=6.0.4
E2MGR_NAME=e2mgr
E2MGR_IP=10.0.2.11

# [FIXED / ARCHITECTURE] DBaaS - pinned to 0.5.7 for Redis 5 RESP2 compatibility
DBAAS_VER=0.5.7
DBAAS_IP=10.0.2.12
DBAAS_PORT=6379

# [FIXED / ARCHITECTURE] Subscription Manager settings
SUBMGR_VER=0.10.1
SUBMGR_NAME=submgr
SUBMGR_IP=10.0.2.13

# [FIXED / ARCHITECTURE] Application Manager settings
APPMGR_VER=0.5.7
APPMGR_NAME=appmgr
APPMGR_IP=10.0.2.14

# [FIXED / ARCHITECTURE] Route Manager Simulator settings
RTMGR_SIM_VER=i-release
RTMGR_SIM_NAME=rtmgr_sim
RTMGR_SIM_IP=10.0.2.15
RTMGR_SIM_PORT=12020

# [FIXED / ARCHITECTURE] Python xApp framework runner
XAPP_PY_FRAME_VER=i-release
XAPP_PY_RUNNER_IP=10.0.2.20
```

---

## 8. Configure Docker Compose (SCTP Port & DBaaS Environment) & Tune E2Manager

To ensure all RIC platform components resolve DBaaS correctly (preventing `Failed to connect to Redis` panics) and allow external RAN nodes (VM-4) to establish SCTP associations, run this automated patching script:

```bash
cd /opt/oran/nearrt/oran-sc-ric

python3 - << 'EOF'
compose_file = "docker-compose.yml"
with open(compose_file, "r") as f:
    lines = f.readlines()

new_lines = []
target_services = ["rtmgr_sim", "submgr", "e2term", "e2mgr"]
current_service = None
env_injected = set()

for i, line in enumerate(lines):
    # 1. Uncomment E2Term external SCTP port mapping
    if '#ports:' in line:
        line = '    ports:\n'
    elif '#  - "36421:36421/sctp"' in line:
        line = '      - "36421:36421/sctp"\n'
        
    new_lines.append(line)
    
    # 2. Track target services to inject DBAAS environment variables
    for srv in target_services:
        if line.strip().startswith(f"{srv}:") or line.strip().startswith(f"container_name: ric_{srv}"):
            current_service = srv
            break
    
    if current_service and line.strip() == "environment:" and current_service not in env_injected:
        new_lines.append("      - DBAAS_SERVICE_HOST=${DBAAS_IP}\n")
        new_lines.append("      - DBAAS_SERVICE_PORT=${DBAAS_PORT}\n")
        env_injected.add(current_service)
        current_service = None

with open(compose_file, "w") as f:
    f.writelines(new_lines)

print("Configured docker-compose.yml with DBAAS environment and E2Term SCTP port.")
EOF
```

### Tune E2Manager Keepalive and Log Level

By default in `ric/configs/e2mgr.yaml`, `keepAliveResponseTimeoutMs` is set to `4500` (4.5 seconds). If E2Term does not acknowledge a keepalive within 4.5 seconds, E2Mgr triggers an automatic shutdown of E2T (`DELETE /ric/v1/handles/e2t`), which causes incoming `E2SetupRequest` messages from RAN nodes to be dropped.

Relax the keepalive timeout and enable integer `loglevel: 4` (DEBUG):

```bash
cd /opt/oran/nearrt/oran-sc-ric

python3 - << 'EOF'
with open("ric/configs/e2mgr.yaml", "r") as f:
    content = f.read()

content = content.replace("keepAliveResponseTimeoutMs: 4500", "keepAliveResponseTimeoutMs: 3600000")
content = content.replace("keepAliveDelayMs: 1500", "keepAliveDelayMs: 3600000")
content = content.replace("e2tInstanceDeletionTimeoutMs: 15000", "e2tInstanceDeletionTimeoutMs: 3600000")

if "loglevel:" not in content:
    content = "loglevel: 4\n" + content

with open("ric/configs/e2mgr.yaml", "w") as f:
    f.write(content)
EOF

sed -i 's/loglevel=info/loglevel=debug/g' ric/configs/e2term.conf
```

Validate the Compose file:

```bash
docker compose config --services
```

Expected services:

```text
appmgr
dbaas
e2mgr
e2term
python_xapp_runner
rtmgr_sim
submgr
```

---

## 9. Pull and Build the RIC Containers

Pull the non-buildable images:

```bash
docker compose pull --ignore-buildable
```

Build the locally defined images:

```bash
docker compose build rtmgr_sim python_xapp_runner
```

The validated local images are:

```text
rtmgr_sim:i-release
python_xapp_runner:i-release
```

---

## 10. Start the RIC in Stages

Starting all services at once may cause E2Mgr to race DBaaS during startup.

Start DBaaS and the route manager simulator first:

```bash
docker compose up -d dbaas rtmgr_sim
```

Verify Redis:

```bash
docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

Start E2Mgr:

```bash
docker compose up -d e2mgr
```

Then start the remaining services:

```bash
docker compose up -d e2term appmgr submgr python_xapp_runner
```

Verify:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Expected containers include:

```text
ric_appmgr
ric_dbaas
ric_e2mgr
ric_e2term
ric_rtmgr_sim
ric_submgr
python_xapp_runner
```

E2Term should expose:

```text
0.0.0.0:36421->36421/sctp
```

---

## 11. Validate the Minimal RIC Platform

Check DBaaS:

```bash
docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

Check SubMgr logs:

```bash
docker logs --since=2m ric_submgr
```

A healthy startup includes:

```text
Serving xapp framework at http://[::]:8088
RMR is ready now
```

Check route-manager simulator:

```bash
docker logs --since=2m ric_rtmgr_sim
```

A healthy startup includes the E2Term registration.

---

## 12. Install the A1 Mediator

Create:

```bash
mkdir -p /opt/oran/nearrt/a1
cd /opt/oran/nearrt/a1
```

Pull the validated image:

```bash
docker pull \
  nexus3.o-ran-sc.org:10002/o-ran-sc/ric-plt-a1:3.2.2
```

Clone the official repository:

```bash
git clone https://github.com/o-ran-sc/ric-plt-a1.git
cd ric-plt-a1
```

Pin the validated commit:

```bash
git checkout 09a757b4fd63198d8690d50b52bfd04552d47f1f
git rev-parse HEAD
```

Store the commit:

```bash
git rev-parse HEAD > /opt/oran/nearrt/a1/ric-plt-a1.commit
```

---

## 13. Configure RMR Routing for A1

Create the A1 RMR route table:

```bash
cat > /opt/oran/nearrt/a1/ric-plt-a1/local.rt <<'EOF'
newrt | start
rte | 20010 | python_xapp_runner:4560
newrt | end
EOF
```

This route sends A1 policy messages to the xApp runtime.

The important A1 RMR message types are:

| Message Type | Direction | Purpose |
|---|---|---|
| `20010` | A1 Mediator → xApp | Policy CREATE / UPDATE / DELETE |
| `20011` | xApp → A1 Mediator | Policy response / acknowledgement |
| `20012` | xApp → A1 Mediator | Policy query / resend request |

The validated xApp smoke test uses **RMR return-to-sender (RTS)** for `20011`.

---

## 14. Start A1 Mediator with DBaaS and RMR

Run:

```bash
docker run -d \
  --name ric_a1mediator \
  --restart unless-stopped \
  --network oran-sc-ric_ric_network \
  -e DBAAS_SERVICE_HOST=10.0.2.12 \
  -e DBAAS_SERVICE_PORT=6379 \
  -e DBAAS_NODE_COUNT=1 \
  -e RMR_SEED_RT=/opt/route/local.rt \
  -e RMR_RTG_SVC=-1 \
  -e RMR_SRC_ID=ric_a1mediator \
  -e RMR_LOG_VLEVEL=0 \
  -p 10000:10000 \
  -v /opt/oran/nearrt/a1/ric-plt-a1/local.rt:/opt/route/local.rt:ro \
  nexus3.o-ran-sc.org:10002/o-ran-sc/ric-plt-a1:3.2.2
```

Verify the RMR environment:

```bash
docker exec ric_a1mediator env | grep -E '^RMR_'
```

Expected:

```text
RMR_LOG_VLEVEL=0
RMR_SEED_RT=/opt/route/local.rt
RMR_RTG_SVC=-1
RMR_SRC_ID=ric_a1mediator
```

Verify the mounted route:

```bash
docker exec ric_a1mediator cat /opt/route/local.rt
```

---

## 15. Validate A1 Mediator Health

Check:

```bash
curl -i \
  http://127.0.0.1:10000/A1-P/v2/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

Check from another VM using:

```bash
curl -i \
  http://10.102.0.66:10000/A1-P/v2/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

---

## 16. Create the Baseline A1 Policy Type

Create:

```bash
mkdir -p /opt/oran/nearrt/a1/policies
nano /opt/oran/nearrt/a1/policies/ts-policy-type-20008.json
```

Use:

```json
{
  "name": "tsapolicy",
  "description": "Bottleneck-aware traffic steering policy parameters",
  "policy_type_id": 20008,
  "create_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "threshold": {
        "type": "integer",
        "default": 0
      },
      "bottleneck_location": {
        "type": "string",
        "enum": ["NORMAL", "RAN", "CORE", "JOINT", "UNCERTAIN"],
        "default": "NORMAL"
      },
      "target_cell_preference": {
        "type": "integer",
        "default": 1
      },
      "handover_allowed": {
        "type": "boolean",
        "default": true
      },
      "slice_id": {
        "type": "object",
        "properties": {
          "sst": { "type": "integer" },
          "sd": { "type": "integer" }
        },
        "required": ["sst"]
      }
    },
    "additionalProperties": false
  }
}
```

Validate:

```bash
jq . /opt/oran/nearrt/a1/policies/ts-policy-type-20008.json
```

Register the type:

```bash
curl -i \
  -X PUT \
  -H "Content-Type: application/json" \
  --data-binary @/opt/oran/nearrt/a1/policies/ts-policy-type-20008.json \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008
```

Expected:

```text
HTTP/1.1 201 Created
```

Verify:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/ \
  | jq
```

Expected:

```json
[
  20008
]
```

---

## 17. A1 API Compatibility Shim

A1 PMS on VM-1 uses the O-RAN SC `OscA1Client`, which expects the OSC-style path:

```text
/a1-p/...
```

The A1 Mediator image used on VM-2 exposes:

```text
/A1-P/v2/...
```

The policy schema format remains OSC-style with:

```text
create_schema
```

To keep both components unchanged, VM-2 uses a small NGINX path-compatibility shim.

Create:

```bash
mkdir -p /opt/oran/nearrt/a1-compat
nano /opt/oran/nearrt/a1-compat/nginx.conf
```

Use:

```nginx
events {}

http {
    server {
        listen 8080;

        location = /a1-p/healthcheck {
            proxy_pass http://ric_a1mediator:10000/A1-P/v2/healthcheck;
        }

        location = /a1-p/policytypes {
            proxy_pass http://ric_a1mediator:10000/A1-P/v2/policytypes/;
        }

        location /a1-p/policytypes/ {
            proxy_pass http://ric_a1mediator:10000/A1-P/v2/policytypes/;
        }
    }
}
```

Start:

```bash
docker run -d \
  --name a1-compat \
  --restart unless-stopped \
  --network oran-sc-ric_ric_network \
  -p 10001:8080 \
  -v /opt/oran/nearrt/a1-compat/nginx.conf:/etc/nginx/nginx.conf:ro \
  nginx:alpine
```

Validate:

```bash
curl -i http://127.0.0.1:10001/a1-p/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

Check policy types:

```bash
curl -s \
  http://127.0.0.1:10001/a1-p/policytypes \
  | jq
```

Expected:

```json
[
  20008
]
```

> This shim is an implementation compatibility layer, not part of the research contribution.

### 17.1 Golden State Verification Checklist

Run these four validation commands on VM-2 to confirm that the Near-RT RIC platform is completely operational:

```bash
# 1. Verify E2Term SCTP listening socket on host port 36421
ss -l --sctp | grep 36421 || sudo netstat -l --sctp | grep 36421
# Expected output:
# LISTEN 0      4096         0.0.0.0:36421      0.0.0.0:*

# 2. Verify A1 Policy Type 20008 registration via A1 Compatibility Port 10001
curl -s http://127.0.0.1:10001/a1-p/policytypes | jq .
# Expected output:
# [
#   20008
# ]

# 3. Verify A1 healthcheck endpoint
curl -i http://127.0.0.1:10001/a1-p/healthcheck
# Expected output:
# HTTP/1.1 200 OK

# 4. Verify all 8 platform and mediation containers are UP
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# Expected containers (all status 'Up'):
# - a1-compat          (0.0.0.0:10001->8080/tcp)
# - ric_a1mediator     (0.0.0.0:10000->10000/tcp)
# - ric_e2term         (0.0.0.0:36421->36421/sctp, 38000/tcp)
# - python_xapp_runner
# - ric_rtmgr_sim
# - ric_submgr
# - ric_appmgr
# - ric_e2mgr          (3800/tcp)
# - ric_dbaas          (6379/tcp)
```

---

## 18. Verify Docker Network Resolution

Check the RIC network:

```bash
docker network inspect oran-sc-ric_ric_network \
  --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}' \
  | sort
```

Validated addresses include:

```text
python_xapp_runner 10.0.2.20/24
ric_appmgr         10.0.2.14/24
ric_dbaas          10.0.2.12/24
ric_e2mgr          10.0.2.11/24
ric_e2term         10.0.2.10/24
ric_rtmgr_sim      10.0.2.15/24
ric_submgr         10.0.2.13/24
```

The A1 Mediator and compatibility shim may receive dynamic addresses.

Use Docker DNS names rather than hard-coding those dynamic IPs.

Verify:

```bash
docker exec ric_a1mediator getent hosts python_xapp_runner
docker exec python_xapp_runner getent hosts ric_a1mediator
```

---

## 19. Python xApp Runtime

Verify that the O-RAN SC Python xApp framework is available:

```bash
cd /opt/oran/nearrt/oran-sc-ric

docker compose exec python_xapp_runner \
  python3 -c 'import ricxappframe; print("ricxappframe OK")'
```

Expected:

```text
ricxappframe OK
```

---

## 20. A1-Aware xApp Smoke Test

The current A1 smoke-test xApp is stored at:

```text
/opt/oran/nearrt/oran-sc-ric/xApps/python/a1_policy_xapp.py
```

Its purpose is to:

1. listen for RMR message type `20010`;
2. parse the A1 policy message;
3. read policy type `20008`;
4. read `threshold`;
5. send an acknowledgement with RMR `20011`.

A received CREATE message has the form:

```json
{
  "operation": "CREATE",
  "payload": "{\"threshold\":5}",
  "policy_instance_id": "ts-test-002",
  "policy_type_id": "20008"
}
```

Note that the A1 Mediator sends `payload` as a JSON string.

The xApp therefore parses the nested JSON before reading:

```text
threshold
```

---

## 21. Validate the xApp Script

Check syntax:

```bash
cd /opt/oran/nearrt/oran-sc-ric

docker compose exec python_xapp_runner \
  python3 -m py_compile /opt/xApps/a1_policy_xapp.py
```

If Docker group permissions are not active:

```bash
sudo docker compose exec python_xapp_runner \
  python3 -m py_compile /opt/xApps/a1_policy_xapp.py
```

No output means the Python syntax is valid.

---

## 22. Run the xApp

Run in foreground:

```bash
cd /opt/oran/nearrt/oran-sc-ric

sudo docker compose exec python_xapp_runner \
  /opt/xApps/a1_policy_xapp.py
```

Expected startup:

```text
RMR ... p=4560 ...
[A1-XAPP] Listening for A1 RMR mtype 20010 on port 4560
```

The current smoke-test may also show:

```text
Cannot Read config file for xapp Registration
```

This does not block the current RMR smoke test.

Proper AppMgr onboarding will be handled separately before the final xApp packaging is frozen.

---

## 23. Direct A1 Policy Smoke Test

With the xApp running, create:

```bash
curl -i \
  -X PUT \
  -H "Content-Type: application/json" \
  -d '{"threshold":5}' \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002
```

Expected HTTP response:

```text
HTTP/1.1 202 Accepted
```

Expected xApp output:

```text
[A1-XAPP] Received A1 policy:
...

[A1-XAPP] CREATE: type=20008 instance=ts-test-002 threshold=5

[A1-XAPP] Sent RMR 20011:
{"policy_type_id": 20008, "policy_instance_id": "ts-test-002", "handler_id": "qos-ts-xapp", "status": "OK"}
```

---

## 24. Verify A1 Enforcement Status

Check:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002/status \
  | jq
```

The validated A1 Mediator returns:

```json
{
  "enforceStatus": "ENFORCED"
}
```

Verify policy data:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002 \
  | jq
```

Expected:

```json
{
  "threshold": 5
}
```

---

## 25. End-to-End A1 Path

The validated final path is:

```text
VM-1
A1 PMS
   │
   │ OscA1Client
   ▼
VM-2 :10001
A1 Compatibility Shim
   │
   ▼
A1 Mediator :10000
   │
   │ RMR 20010
   ▼
Python xApp :4560
   │
   │ RMR RTS 20011
   ▼
A1 Mediator
```

This path has been validated with a policy created through A1 PMS on VM-1 and enforced by the xApp on VM-2.

---

## 26. E2 Interface Integration & Node Inventory [VALIDATED]

The Near-RT RIC exposes E2 through:

```text
10.102.0.66:36421/SCTP
```

This endpoint terminates O-RAN E2AP traffic from the OAI gNB CU on VM-4 (`10.102.0.167`).

Current E2Term port mapping:

```text
0.0.0.0:36421->36421/sctp
```

### E2 Connection Validation Status [100% VALIDATED]

The E2 connection from VM-4 (`oai-ran`) to VM-2 (`near-rt-ric`) has been fully established and registered in the Near-RT RIC inventory.

1. **Verify Registered RAN Nodes in E2T:**
   ```bash
   curl -s http://10.0.2.11:3800/v1/e2t/list | jq .
   ```
   **Output:**
   ```json
   [
     {
       "e2tAddress": "10.0.2.10:38000",
       "ranNames": [
         "gnb_208_095_00000e00"
       ]
     }
   ]
   ```

2. **Verify NodeB Connection Status via E2Mgr REST API:**
   ```bash
   curl -s http://10.0.2.11:3800/v1/nodeb/gnb_208_095_00000e00 | jq .
   ```
   **Output:**
   ```json
   {
     "connectionStatus": "CONNECTED",
     "globalNbId": {
       "nbId": "00000e00",
       "plmnId": "02F859"
     },
     "ip": "10.102.0.167",
     "port": 36421,
     "ranName": "gnb_208_095_00000e00"
   }
   ```

3. **Verify E2Mgr Logs:**
   ```text
   #RanConnectStatusChangeManager.ChangeStatus - RAN name: gnb_208_095_00000e00, currentStatus: UNKNOWN_CONNECTION_STATUS, nextStatus: CONNECTED
   #ranListManagerInstance.AddNbIdentity - RAN name: gnb_208_095_00000e00 - Successfully added nodeb identity
   #RmrSender.Send - RAN name: gnb_208_095_00000e00 , Message type: 12002 - Successfully sent RMR message
   ```

All 8 FlexRIC Service Models are operational on the gNB CU, enabling future xApps to subscribe to RAN metrics and execute traffic control policies.

---

## 27. Useful Operational Commands

### Show all VM-2 containers

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Check A1 health

```bash
curl -i http://127.0.0.1:10000/A1-P/v2/healthcheck
```

### Check compatibility shim

```bash
curl -i http://127.0.0.1:10001/a1-p/healthcheck
```

### Check registered policy types

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/ \
  | jq
```

### Check RIC Docker network

```bash
docker network inspect oran-sc-ric_ric_network \
  --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
```

### Check A1 Mediator logs

```bash
docker logs --since=2m ric_a1mediator
```

### Check E2Term logs

```bash
docker logs --since=2m ric_e2term
```

---

## 28. Acceptance Criteria

VM-2 is considered correctly deployed when all of the following are true:

```text
[✓] DBaaS returns PONG
[✓] E2Mgr is running
[✓] E2Term is running
[✓] SubMgr is running
[✓] AppMgr is running
[✓] Python xApp runner is running
[✓] A1 Mediator health returns 200 OK
[✓] A1 compatibility shim returns 200 OK
[✓] Policy type 20008 exists
[✓] A1 PMS discovers policy type 20008
[✓] RMR 20010 reaches the xApp
[✓] xApp reads threshold=5
[✓] xApp sends RMR 20011
[✓] A1 reports enforceStatus=ENFORCED
[✓] E2 SCTP port 36421 is exposed
```

---

## 29. Troubleshooting

### E2Mgr starts before DBaaS

Symptom:

```text
dial tcp 10.0.2.12:6379: connect: connection refused
```

Fix by starting DBaaS first:

```bash
docker compose up -d dbaas rtmgr_sim
docker compose exec dbaas redis-cli ping
docker compose up -d e2mgr
```

Then start the remaining services.

---

### A1 health returns `500`

If A1 Mediator cannot reach SDL/DBaaS, it may return:

```text
HTTP/1.1 500 Internal Server Error
```

Verify DBaaS:

```bash
docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

Then ensure A1 Mediator has:

```text
DBAAS_SERVICE_HOST=10.0.2.12
DBAAS_SERVICE_PORT=6379
DBAAS_NODE_COUNT=1
```

---

### A1 policy type visible on VM-2 but PMS becomes `UNAVAILABLE`

A direct PMS → `/A1-P/v2` setup produced:

```text
JSONObject["policySchema"] not found
```

The validated solution is:

```text
PMS OscA1Client
        │
        ▼
A1 compatibility shim :10001
        │
        ▼
A1 Mediator /A1-P/v2
```

See:

[A1 Integration Guide](../integration/a1-integration.md)

---

### xApp receives policy but fails to parse `threshold`

The A1 Mediator sends:

```json
"payload": "{\"threshold\":5}"
```

The xApp must decode the nested JSON string first.

For DELETE:

```json
"payload": ""
```

The xApp should treat the empty string as an empty object.

---

### xApp registration error

The smoke-test xApp may show:

```text
Cannot Read config file for xapp Registration
```

and on shutdown may attempt to resolve a Kubernetes AppMgr hostname.

This is a packaging/onboarding issue, not an RMR delivery issue.

The validated smoke-test RMR path still works.

Proper xApp AppMgr registration should be completed before final production packaging.

---

### Docker permission denied

If:

```text
permission denied while trying to connect to the Docker daemon socket
```

either use:

```bash
sudo docker ...
```

or configure Docker group access:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

---

## 30. Final VM-2 Data Paths

### A1

```text
VM-1 A1 PMS
      │
      ▼
10.102.0.66:10001
A1 compatibility shim
      │
      ▼
A1 Mediator :10000
      │
      ▼
RMR 20010
      │
      ▼
xApp :4560
```

### E2

```text
VM-4 OAI RAN
      │
      │ SCTP / E2
      ▼
10.102.0.66:36421
      │
      ▼
E2Term
```

VM-2 therefore forms the central Near-RT control platform for the traffic-steering experiment.

---

---

## 31. xApp Baseline Operational Modes on VM-2

The Near-RT RIC xApp executes the near-real-time control loop ($10\text{ ms} - 1\text{ s}$). Depending on the evaluated baseline mode, the xApp operates under distinct behavioral rules:

| Baseline ID | Mode Name | xApp Execution Mode | Actuation Decision Logic |
|---|---|---|---|
| **B0** | Static 3GPP Default | **Monitor-Only.** Subscribes to E2SM-KPM; ignores E2SM-RC. | No RIC steering. Handover left entirely to gNB internal RRC A3 event. |
| **B1** | RAN-Only Control | **Autonomous Radio Steering.** Evaluates PRB and CQI per cell. | If $PRB_{cell1}^{slice1} > 80\%$, issues E2SM-RC Handover to Cell-2. Blind to Core UPF state. |
| **B2** | Core-Only Control | **Monitor-Only.** Steering disabled. | Handover prohibited. UEs remain on initial cell. |
| **B3** | Decoupled | **Autonomous Radio Steering.** Operates independently. | Aggressively steers UEs based on radio load, creating potential conflicts with Core rate-shaping. |
| **B4** | Coordinated (Fixed Heuristic) | **Command-Driven Steering.** | Always attempts inter-cell handover when instructed by rApp, regardless of Core state. |
| **Proposed** | Bottleneck-Aware Closed-Loop | **Constraint-Enforced Steering.** Parses A1 `bottleneck_location`. | • IF `RAN`: Execute E2SM-RC handover from Cell-1 to Cell-2.<br>• IF `CORE`: **Inhibit handover** (prevents futile ping-pong and protects Core UPF). |

---

## References

Official references used for this deployment:

- O-RAN Alliance WG3 — E2 Application Protocol (E2AP) v02.03 & E2SM-RC v01.03
- O-RAN Alliance WG2 — A1 Interface: Application Protocol v03.01
- srsRAN — Minimal O-RAN SC RIC deployment  
  https://github.com/srsran/oran-sc-ric

- O-RAN SC — A1 Mediator  
  https://github.com/o-ran-sc/ric-plt-a1

- O-RAN SC — A1 Mediator documentation  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-a1/

- O-RAN SC — RMR documentation  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-lib-rmr/

- O-RAN SC — Python xApp Framework  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-xapp-frame-py/

- Docker documentation  
  https://docs.docker.com/

For cross-VM A1 integration details, see:

[A1 Integration Guide](../integration/a1-integration.md)

