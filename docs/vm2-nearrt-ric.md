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

At the current implementation stage, the A1 path has already been validated end-to-end from A1 PMS on VM-1 to the xApp on VM-2.

---

## 1. VM Specification

| Parameter | Value |
|---|---|
| VM | VM-2 |
| Hostname | `near-rt-ric` |
| IP address | `10.10.10.12` |
| Subnet | `10.10.10.0/24` |
| Main role | Near-RT RIC |
| Container runtime | Docker |
| A1 external endpoint | `10.10.10.12:10000/TCP` |
| A1 compatibility endpoint | `10.10.10.12:10001/TCP` |
| E2 external endpoint | `10.10.10.12:36421/SCTP` |

---

## 2. Software Components

The validated deployment uses the minimal O-RAN SC RIC packaging provided by the official srsRAN repository.

| Component | Version / Tag |
|---|---|
| Minimal O-RAN SC RIC | `i-release` |
| E2Term | `6.0.4` |
| E2Mgr | `6.0.4` |
| DBaaS | `0.6.4` |
| SubMgr | `0.10.1` |
| AppMgr | `0.5.7` |
| Route Manager simulator | `i-release` |
| Python xApp runner | `i-release` |
| A1 Mediator | `3.2.2` |
| A1 policy baseline | `20008` |

Pinned minimal RIC repository commit used during deployment:

```text
621ade26251f69a4ad079ba98bb708d8e5aeeb98
```

Pinned A1 Mediator repository commit used during deployment:

```text
09a757b4fd63198d8690d50b52bfd04552d47f1f
```

---

## 3. Directory Layout

The main VM-2 paths are:

```text
/opt/oran/nearrt/
├── oran-sc-ric/
│   ├── docker-compose.yml
│   ├── ric/
│   │   └── configs/
│   │       └── routes.rtg
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

## 4. Clone the Minimal Near-RT RIC

Create the working directory:

```bash
sudo mkdir -p /opt/oran/nearrt
sudo chown -R "$USER":"$USER" /opt/oran/nearrt
cd /opt/oran/nearrt
```

Clone:

```bash
git clone https://github.com/srsran/oran-sc-ric.git
cd oran-sc-ric
```

Pin the validated commit:

```bash
git checkout 621ade26251f69a4ad079ba98bb708d8e5aeeb98
git rev-parse HEAD
```

Store the commit for reproducibility:

```bash
git rev-parse HEAD > /opt/oran/nearrt/oran-sc-ric.commit
```

---

## 5. Minimal RIC Environment

The validated `.env` contains:

```text
SC_RIC_VERSION=i-release
SYSTEM_NAME=oran_sc_ric
RIC_ID=7b0000-000000/18
RMR_LOG_VLEVEL=0
RIC_SUBNET=10.0.2.0/24

E2TERM_VER=6.0.4
E2TERM_NAME=e2term
E2TERM_IP=10.0.2.10
E2TERM_SCTP_PORT=36421

E2MGR_VER=6.0.4
E2MGR_IP=10.0.2.11

DBAAS_VER=0.6.4
DBAAS_IP=10.0.2.12
DBAAS_PORT=6379

SUBMGR_VER=0.10.1
SUBMGR_IP=10.0.2.13

APPMGR_VER=0.5.7
APPMGR_IP=10.0.2.14

RTMGR_SIM_VER=i-release
RTMGR_SIM_IP=10.0.2.15
RTMGR_SIM_PORT=12020

XAPP_PY_FRAME_VER=i-release
XAPP_PY_RUNNER_IP=10.0.2.20
```

---

## 6. Expose the E2 SCTP Port

Edit:

```bash
nano /opt/oran/nearrt/oran-sc-ric/docker-compose.yml
```

For the E2Term service, expose:

```yaml
ports:
  - "36421:36421/sctp"
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

## 7. Pull and Build the RIC Containers

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

## 8. Start the RIC in Stages

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

## 9. Validate the Minimal RIC Platform

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

## 10. Install the A1 Mediator

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

## 11. Configure RMR Routing for A1

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

## 12. Start A1 Mediator with DBaaS and RMR

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

## 13. Validate A1 Mediator Health

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
  http://10.10.10.12:10000/A1-P/v2/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

---

## 14. Create the Baseline A1 Policy Type

Create:

```bash
mkdir -p /opt/oran/nearrt/a1/policies
nano /opt/oran/nearrt/a1/policies/ts-policy-type-20008.json
```

Use:

```json
{
  "name": "tsapolicy",
  "description": "tsa parameters",
  "policy_type_id": 20008,
  "create_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "threshold": {
        "type": "integer",
        "default": 0
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

## 15. A1 API Compatibility Shim

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

---

## 16. Verify Docker Network Resolution

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

## 17. Python xApp Runtime

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

## 18. A1-Aware xApp Smoke Test

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

## 19. Validate the xApp Script

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

## 20. Run the xApp

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

## 21. Direct A1 Policy Smoke Test

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

## 22. Verify A1 Enforcement Status

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

## 23. End-to-End A1 Path

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

## 24. E2 Interface

The Near-RT RIC exposes E2 through:

```text
10.10.10.12:36421/SCTP
```

This will later be used by the OAI E2 Agent on VM-4.

Current E2Term port mapping:

```text
0.0.0.0:36421->36421/sctp
```

The next stage of the project will connect:

```text
VM-4 OAI E2 Agent
        │
        │ E2
        ▼
VM-2 E2Term
```

---

## 25. Useful Operational Commands

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

## 26. Acceptance Criteria

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

## 27. Troubleshooting

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

[docs/a1-integration.md](a1-integration.md)

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

## 28. Final VM-2 Data Paths

### A1

```text
VM-1 A1 PMS
      │
      ▼
10.10.10.12:10001
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
10.10.10.12:36421
      │
      ▼
E2Term
```

VM-2 therefore forms the central Near-RT control platform for the traffic-steering experiment.

---

## References

Official references used for this deployment:

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

[docs/a1-integration.md](a1-integration.md)
