# O-RAN E2 Termination & RIC Networking Troubleshooting

This document contains validated diagnostic procedures, root-cause analyses, and resolutions for issues in the **e2-networking** domain.

---

## Case 08 — E2Mgr / SubMgr Fails Because DBaaS Is Not Ready or Not Resolved

### Symptom

E2Mgr or SubMgr logs may show:

```text
dial tcp 10.0.2.12:6379: connect: connection refused
```

or:

```text
dial tcp [::1]:6379: connect: connection refused
```

and SubMgr may report:

```text
SDL: ReadAllSubscriptionsFromSdl(), GetAll(). Error while reading E2 subscriptions keys from DBAAS dial tcp [::1]:6379: connect: connection refused
```

### Cause

1. E2Mgr or SubMgr starts before DBaaS is ready, or
2. `DBAAS_SERVICE_HOST` is not explicitly passed to `e2mgr` and `submgr` in `docker-compose.yml`, causing the O-RAN SC SDL library to fall back to `localhost` (`[::1]`).

### Fix

Ensure the `environment:` section of `e2mgr`, `submgr`, and `appmgr` in `docker-compose.yml` includes:

```yaml
- DBAAS_SERVICE_HOST=${DBAAS_IP}
- DBAAS_SERVICE_PORT=${DBAAS_PORT}
```

### Validated Startup Order

```bash
cd /opt/oran/nearrt/oran-sc-ric

docker compose up -d dbaas rtmgr_sim
```

Verify:

```bash
docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

Then:

```bash
docker compose up -d e2mgr
```

Finally:

```bash
docker compose up -d e2term appmgr submgr python_xapp_runner
```

---

## Case 28 — `redis: got 7 elements in COMMAND reply, wanted 6` on `ric_e2mgr` with `ric-plt-dbaas:0.6.4`

### Symptom
When starting the Near-RT RIC platform on VM-2, `ric_e2mgr` stops during startup with the error:

```text
#app.main - Configuration {logging.logLevel: debug, http.port: 3800, ...}
Using config file: /opt/E2Manager/resources/configuration.yaml
redis: got 7 elements in COMMAND reply, wanted 6
```

`e2mgr` terminates or aborts RNIB database connectivity, leading to cascading failures in E2 node association.

### Cause
`ric-plt-dbaas:0.6.4` is built on top of **Redis 6.2.14**. Starting in Redis 6.2, the response to the internal Redis `COMMAND` metadata command was expanded from 6 elements to 7 elements (introducing ACL category metadata). The older `go-redis` v7 client bundled within `ric-plt-e2mgr` hardcodes an assertion expecting exactly 6 elements.

### Solution
Downgrade the DBaaS container image in `/opt/oran/nearrt/oran-sc-ric/.env` to the official O-RAN SC release:
```text
DBAAS_VER=0.5.7
```
`ric-plt-dbaas:0.5.7` uses **Redis 5.0.9-alpine**, which returns exactly 6 elements for `COMMAND`, while preserving the exact same custom O-RAN Shared Data Layer (SDL) module (`/usr/local/libexec/redismodule/libredismodule.so`) and `sdlcli` binary.

Pull and apply:
```bash
cd /opt/oran/nearrt/oran-sc-ric
sed -i 's/DBAAS_VER=0.6.4/DBAAS_VER=0.5.7/g' .env
sudo docker pull nexus3.o-ran-sc.org:10002/o-ran-sc/ric-plt-dbaas:0.5.7
```

---

## Case 29 — E2T Instance Prematurely Deleted by `e2mgr` Keepalive Timeout (4.5s)

### Symptom
E2Term decodes incoming SCTP packets from OAI CU (`ranName = gnb_208_095_00000e00`), but the CU logs report continuous timeout retries:

```text
[E2 AGENT]: E2 SETUP REQUEST timeout. Resending again (tx)
```

In `ric_rtmgr_sim` logs on VM-2:
```text
POST /ric/v1/handles/e2t  body: {"E2TAddress":"10.0.2.10:38000"}
DELETE /ric/v1/handles/e2t  body: {"E2TAddress":"10.0.2.10:38000"}
```
And `curl http://10.0.2.11:3800/v1/e2t/list` returns an empty array `[]`.

### Cause
By default in `ric/configs/e2mgr.yaml`, `keepAliveResponseTimeoutMs` is set to `4500` (4.5 seconds) and `e2tInstanceDeletionTimeoutMs` is set to `15000`. If E2Term does not acknowledge keepalive requests within 4.5 seconds, E2Manager triggers `E2TShutdownManager.Shutdown()`, sending `DELETE /ric/v1/handles/e2t` to Route Manager and removing E2T from DBaaS. When CU initiates `E2SetupRequest`, E2Manager drops the message because E2T is already marked inactive/deleted.

### Solution
Relax the keepalive timeout in `ric/configs/e2mgr.yaml` so E2T remains permanently active, and configure `loglevel: 4` (DEBUG):

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

Restart services with DBaaS started first to avoid startup race conditions:
```bash
sudo docker compose stop e2term e2mgr rtmgr_sim dbaas
sudo docker compose up -d dbaas rtmgr_sim
sudo docker compose exec dbaas redis-cli ping
sudo docker compose up -d e2mgr
sleep 2
sudo docker compose up -d e2term
```

---

## Case 35 — Near-RT RIC E2Mgr / SubMgr Container Exit on Startup due to Missing DBaaS Environment Variables

### Symptom
On VM-2 (`near-rt-ric`), after launching the RIC platform with `docker compose up -d`, `ric_e2mgr` or `ric_submgr` exits immediately with status `Exited (1)` or `Exited (2)`.
Viewing the logs:
```bash
sudo docker logs ric_e2mgr
```
Shows errors such as:
```text
{"ts":...,"crit":"ERROR","id":"e2mgr","mdc":{"PID":1},"msg":"Failed to connect to Redis"}
panic: dial tcp: lookup service-ricplt-dbaas-tcp.ricplt: no such host
```
Or connection refused attempting to dial `127.0.0.1:6379`.

### Cause
In the minimal `oran-sc-ric` Docker Compose deployment, services such as `e2mgr`, `submgr`, and `rtmgr_sim` use the Shared Data Layer (`libsdl-go` / `libsdl-cpp`). By default, SDL attempts to resolve the standard Kubernetes service name `service-ricplt-dbaas-tcp.ricplt` or `localhost:6379` unless overridden by explicit environment variables:
- `DBAAS_SERVICE_HOST`
- `DBAAS_SERVICE_PORT`

Although `.env` defines `DBAAS_IP=10.0.2.12` and `DBAAS_PORT=6379`, the default `docker-compose.yml` does not declare `DBAAS_SERVICE_HOST` or `DBAAS_SERVICE_PORT` inside the `environment:` blocks for `rtmgr_sim`, `submgr`, `e2mgr`, and `e2term`. Consequently, these containers fail to reach the DBaaS Redis container.

### Solution
Inject `DBAAS_SERVICE_HOST=${DBAAS_IP}` and `DBAAS_SERVICE_PORT=${DBAAS_PORT}` into the `environment:` blocks for all RIC services in `/opt/oran/nearrt/oran-sc-ric/docker-compose.yml`.

Run this automated Python patch script on VM-2:
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
    new_lines.append(line)
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

print("Injected DBAAS environment variables into docker-compose.yml successfully.")
EOF
```

Restart the affected containers:
```bash
sudo docker compose stop e2mgr submgr rtmgr_sim
sudo docker compose up -d e2mgr submgr rtmgr_sim
```

---

## Case 36 — E2Term SCTP Port 36421 Inaccessible from External RAN Node (`Connection refused`)

### Symptom
When VM-4 (`oai-ran`) starts CU (`cu_gnb.conf`) and initiates an E2 connection toward Near-RT RIC (`10.102.0.66:36421`):
```text
[E2AP] Failed to connect to Near-RT RIC at 10.102.0.66:36421 (Connection refused)
[E2AP] Reconnecting in 5 seconds...
```
Checking SCTP listening sockets on VM-2:
```bash
ss -l --sctp | grep 36421
# Returns no output
```

### Cause
In `oran-sc-ric/docker-compose.yml`, the `ports:` mapping for `e2term` is commented out by default:
```yaml
  e2term:
    container_name: ric_e2term
    hostname: e2term
    image: nexus3.o-ran-sc.org:10002/o-ran-sc/ric-plt-e2:${E2TERM_VER}
    #Uncomment ports to use the RIC from outside the docker network.
    #ports:
    #  - "36421:36421/sctp"
```
Because the port is not published to the host, external SCTP packets arriving at VM-2's physical network interface (`10.102.0.66:36421`) are rejected at the host kernel.

### Solution
Uncomment the `ports:` definition under `e2term` in `/opt/oran/nearrt/oran-sc-ric/docker-compose.yml`:

```bash
cd /opt/oran/nearrt/oran-sc-ric

python3 - << 'EOF'
with open("docker-compose.yml", "r") as f:
    content = f.read()

content = content.replace(
    '    #ports:\n    #  - "36421:36421/sctp"',
    '    ports:\n      - "36421:36421/sctp"'
)

with open("docker-compose.yml", "w") as f:
    f.write(content)

print("Exposed E2Term SCTP port 36421 on host.")
EOF

sudo docker compose up -d e2term
```

```bash
ss -l --sctp | grep 36421
# Expected output:
# LISTEN 0      4096         0.0.0.0:36421      0.0.0.0:*
```

---
