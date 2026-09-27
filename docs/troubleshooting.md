# Troubleshooting

This document collects the main issues encountered while deploying and integrating the current O-RAN experimental platform.

Only issues that were actually observed during the VM-1 and VM-2 deployment are included here. The purpose is to preserve the validated fixes so the environment can be reproduced without repeating the same debugging process.

---

## 1. Quick Diagnostic Flow

When the A1 path is not working, check the system in this order:

```text
VM-1 PMS
  │
  ▼
PMS health
  │
  ▼
RIC state = AVAILABLE?
  │
  ▼
VM-2 compatibility shim
  │
  ▼
A1 Mediator health
  │
  ▼
DBaaS
  │
  ▼
RMR route 20010
  │
  ▼
xApp runtime
  │
  ▼
RMR 20011 acknowledgement
```

This order helps isolate whether the problem is:

```text
PMS
network / compatibility
A1 Mediator
DBaaS
RMR
or xApp
```

---

# VM-1 — A1 PMS

## 2. Docker Permission Denied

### Symptom

```text
permission denied while trying to connect to the Docker daemon socket
```

### Cause

The current Linux user does not have permission to access:

```text
/var/run/docker.sock
```

### Fix

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

Verify:

```bash
docker ps
```

If the group change is not active yet, log out and log back in.

As a temporary workaround:

```bash
sudo docker ...
```

---

## 3. PMS RIC State Is `UNAVAILABLE`

### Check

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/rics \
  | jq
```

Problem state:

```json
{
  "state": "UNAVAILABLE"
}
```

### Inspect Logs

```bash
docker logs --since=5m policy-agent-container 2>&1 \
  | grep -Ei 'error|warn|sync|policySchema'
```

If the logs contain:

```text
JSONObject["policySchema"] not found
```

the issue is the A1 client compatibility path.

### Validated Configuration

The PMS configuration must use:

```json
{
  "name": "near-rt-ric-1",
  "baseUrl": "http://10.10.10.12:10001",
  "customAdapterClass": "org.onap.ccsdk.oran.a1policymanagementservice.clients.OscA1Client"
}
```

The validated path is:

```text
PMS
 │
 │ OscA1Client
 ▼
10.10.10.12:10001
 │
 ▼
A1 compatibility shim
 │
 ▼
A1 Mediator
```

Do not use the direct A1 Mediator endpoint as the final PMS `baseUrl`.

---

## 4. `JSONObject["policySchema"] not found`

### Symptom

PMS logs contain:

```text
JSONObject["policySchema"] not found
```

### Observed Cause

The A1 Mediator returns policy type information containing:

```json
{
  "create_schema": {
    "...": "..."
  }
}
```

while the PMS standard A1 v2 parser path expected:

```text
policySchema
```

The network connection itself was healthy.

### Validated Fix

Use:

```text
OscA1Client
+
A1 compatibility shim
```

Final configuration:

```text
customAdapterClass =
org.onap.ccsdk.oran.a1policymanagementservice.clients.OscA1Client
```

and:

```text
baseUrl = http://10.10.10.12:10001
```

The compatibility shim only maps URI paths. It does not rewrite the policy JSON.

See:

[A1 Integration](a1-integration.md)

---

## 5. PMS Database Write Errors

### Symptoms

Logs may contain messages similar to:

```text
Could not create directory
Could not write file
```

under:

```text
/var/policy-management-service/database
```

### Check Container User

```bash
docker exec policy-agent-container id
```

Validated values:

```text
uid=999(nonrtric)
gid=1000(nonrtric)
```

### Fix Host Permissions

```bash
sudo mkdir -p /opt/oran/nonrt/a1pms/database
sudo chown -R 999:1000 /opt/oran/nonrt/a1pms/database
sudo chmod 755 /opt/oran/nonrt/a1pms/database
```

The directory must be bind-mounted into:

```text
/var/policy-management-service/database
```

### Validate Persistence

```bash
find /opt/oran/nonrt/a1pms/database \
  -maxdepth 3 \
  -type f \
  -printf '%u:%g %p\n'
```

Expected after synchronization:

```text
.../database/policytypes/20008.json
```

---

## 6. Host Shows Unexpected Owner Name for UID 999

### Symptom

The host may display a username such as:

```text
systemd-coredump
```

for files owned by numeric UID:

```text
999
```

### Explanation

Linux resolves numeric UIDs differently on the host and inside the container.

Inside the PMS container:

```text
999 = nonrtric
```

The important value is the numeric UID/GID, not the host-side username label.

### Check

```bash
ls -ln /opt/oran/nonrt/a1pms/database
```

Verify numeric ownership:

```text
999:1000
```

---

# VM-2 — Minimal Near-RT RIC

## 7. `docker compose` Cannot Find the Project

### Symptom

Commands are executed from another directory and Compose does not find the correct services.

### Fix

Use:

```bash
cd /opt/oran/nearrt/oran-sc-ric
```

before running:

```bash
docker compose ...
```

or explicitly specify:

```bash
docker compose \
  -f /opt/oran/nearrt/oran-sc-ric/docker-compose.yml \
  ...
```

---

## 8. E2Mgr / SubMgr Fails Because DBaaS Is Not Ready or Not Resolved

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

## 9. A1 Mediator Health Returns `500`

### Check

```bash
curl -i \
  http://127.0.0.1:10000/A1-P/v2/healthcheck
```

Problem:

```text
HTTP/1.1 500 Internal Server Error
```

### Check DBaaS

```bash
cd /opt/oran/nearrt/oran-sc-ric

docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

### Check A1 Mediator Environment

```bash
docker exec ric_a1mediator env \
  | grep -E 'DBAAS|RMR'
```

Validated DBaaS settings:

```text
DBAAS_SERVICE_HOST=10.0.2.12
DBAAS_SERVICE_PORT=6379
DBAAS_NODE_COUNT=1
```

Validated RMR settings:

```text
RMR_SEED_RT=/opt/route/local.rt
RMR_RTG_SVC=-1
RMR_SRC_ID=ric_a1mediator
RMR_LOG_VLEVEL=0
```

---

## 10. Legacy `/a1-p/...` Endpoints Return `404`

### Symptom

Direct requests to the A1 Mediator such as:

```text
/a1-p/healthcheck
```

return:

```text
404
```

while:

```text
/A1-P/v2/healthcheck
```

works.

### Validated Solution

Use the compatibility shim on:

```text
10.10.10.12:10001
```

Examples:

```bash
curl -i \
  http://127.0.0.1:10001/a1-p/healthcheck
```

and:

```bash
curl -s \
  http://127.0.0.1:10001/a1-p/policytypes \
  | jq
```

The shim translates:

```text
/a1-p/...
```

to:

```text
/A1-P/v2/...
```

---

## 11. Compatibility Shim Does Not Reach A1 Mediator

### Check Container

```bash
docker ps \
  --filter name=a1-compat
```

### Check Network

```bash
docker inspect a1-compat \
  --format '{{json .NetworkSettings.Networks}}' \
  | jq
```

It must be attached to:

```text
oran-sc-ric_ric_network
```

### Check Docker DNS

```bash
docker exec a1-compat \
  getent hosts ric_a1mediator
```

The NGINX configuration should use:

```text
ric_a1mediator
```

rather than a hard-coded dynamic Docker IP.

---

# RMR and xApp

## 12. xApp Does Not Receive A1 Policy

### Step 1 — Verify xApp Is Running

Expected xApp output:

```text
[A1-XAPP] Listening for A1 RMR mtype 20010 on port 4560
```

### Step 2 — Verify A1 Route

```bash
docker exec ric_a1mediator \
  cat /opt/route/local.rt
```

Expected:

```text
newrt | start
rte | 20010 | python_xapp_runner:4560
newrt | end
```

### Step 3 — Verify Docker DNS

```bash
docker exec ric_a1mediator \
  getent hosts python_xapp_runner
```

Validated address:

```text
10.0.2.20
```

### Step 4 — Verify Network Membership

```bash
docker network inspect oran-sc-ric_ric_network \
  --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
```

Both:

```text
ric_a1mediator
python_xapp_runner
```

must be on the same Docker network.

---

## 13. xApp Fails to Parse `payload`

### Example Message

The A1 Mediator sends:

```json
{
  "operation": "CREATE",
  "payload": "{\"threshold\":5}",
  "policy_instance_id": "ts-test-002",
  "policy_type_id": "20008"
}
```

### Important Detail

`payload` is:

```text
string
```

not:

```text
object
```

### Correct Parsing Logic

Conceptually:

```python
outer = json.loads(message)

payload_field = outer.get("payload", "")

if isinstance(payload_field, str) and payload_field:
    policy = json.loads(payload_field)
else:
    policy = {}
```

Then:

```python
threshold = policy.get("threshold")
```

For DELETE:

```json
"payload": ""
```

the xApp should use an empty object.

---

## 14. xApp Receives CREATE but A1 Does Not Become `ENFORCED`

### Verify xApp Response

The xApp must send an acknowledgement such as:

```json
{
  "policy_type_id": 20008,
  "policy_instance_id": "ts-test-002",
  "handler_id": "qos-ts-xapp",
  "status": "OK"
}
```

using:

```text
RMR message type 20011
```

### Current Validated Behavior

The smoke-test xApp uses:

```text
RMR return-to-sender (RTS)
```

for the `20011` response via `ricxappframe`. Note that the method expects `new_payload`, not `payload`:

```python
self.rmr_rts(sbuf, new_payload=ack_body, new_mtype=20011)
self.rmr_free(sbuf)
```

Check status:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002/status \
  | jq
```

Validated result:

```json
{
  "enforceStatus": "ENFORCED"
}
```

---

## 15. No `20010` / `20011` Lines in A1 Logs

### Symptom

A command such as:

```bash
docker logs ric_a1mediator 2>&1 \
  | grep -E '20010|20011'
```

returns nothing even though policy enforcement succeeds.

### Interpretation

This is not sufficient evidence of failure.

The current A1 Mediator log level does not necessarily print the message-type numbers for every successful RMR exchange.

Use functional validation instead:

```text
xApp receives CREATE
+
xApp prints 20011 response
+
A1 status = ENFORCED
```

These are stronger indicators that the RMR round trip succeeded.

---

## 16. xApp Registration Warning

### Symptom

The smoke-test xApp may show:

```text
Cannot Read config file for xapp Registration
```

### Current Status

This does not prevent:

```text
RMR 20010 receive
RMR 20011 response
```

during the current smoke test.

The xApp is not yet packaged with the final AppMgr onboarding configuration.

### Final Cleanup

Before the final research deployment is frozen, replace the smoke-test workaround with proper:

```text
AppMgr registration
xApp descriptor/configuration
clean shutdown behavior
```

---

## 17. xApp Shutdown Attempts Kubernetes AppMgr Hostname

### Symptom

On shutdown, the framework may attempt to reach:

```text
service-ricplt-appmgr-http.ricplt:8080
```

and fail.

### Current Smoke-Test Workaround

The temporary xApp uses:

```python
os._exit(0)
```

instead of the framework shutdown path.

### Important

This is only a smoke-test workaround.

It should not be retained as the final production-quality xApp shutdown mechanism.

---

# Policy Testing

## 18. Direct A1 Policy Is Unexpectedly Deleted

### Observed Behavior

During an earlier direct A1 test, a manually created policy was received by the xApp and then deleted shortly afterward.

### Likely Cause in the Tested Setup

A1 PMS was running simultaneously and performing policy consistency synchronization.

A policy created directly at the A1 Mediator was not managed by PMS.

### Safe Smoke-Test Procedure

For an isolated direct A1 test, temporarily stop PMS:

```bash
docker stop policy-agent-container
```

Then test the A1 Mediator directly.

After the test:

```bash
docker start policy-agent-container
```

For final integrated operation, create policies through PMS instead of bypassing it.

---

## 19. Direct A1 PUT Returns `202 Accepted`

### Test

```bash
curl -i \
  -X PUT \
  -H "Content-Type: application/json" \
  -d '{"threshold":5}' \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002
```

Expected:

```text
HTTP/1.1 202 Accepted
```

This means the policy request was accepted for processing.

Final success is confirmed by:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002/status \
  | jq
```

Expected:

```json
{
  "enforceStatus": "ENFORCED"
}
```

---

## 20. PMS Policy Creation Response

Create through PMS:

```bash
curl -i \
  -X PUT \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "ts-pms-001",
    "policytype_id": "20008",
    "ric_id": "near-rt-ric-1",
    "policy_data": {
      "threshold": 5
    },
    "service_id": "rapp-qos-ts",
    "transient": false
  }' \
  http://127.0.0.1:8081/a1-policy/v2/policies
```

Expected for a new policy:

```text
201 Created
```

For an existing policy update:

```text
200 OK
```

---

# SDNC A1 Controller

## 21. SDNC Does Not Solve the Schema Mismatch

An SDNC A1 Controller was tested during troubleshooting.

The controller successfully reached the A1 Mediator and returned:

```text
http-status = 200
```

for policy-type retrieval.

However, it did not transform:

```text
create_schema
```

into:

```text
policySchema
```

Therefore it did not solve the PMS parser mismatch.

The final architecture does not require:

```text
SDNC A1 Controller
MariaDB for SDNC
```

The final path remains:

```text
PMS
 │
 ▼
OscA1Client
 │
 ▼
compatibility shim
 │
 ▼
A1 Mediator
```

---

# Diagnostic Commands

## 22. VM-1 Quick Checks

### PMS Health

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/status \
  | jq
```

### RIC State

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/rics \
  | jq
```

### Recent PMS Logs

```bash
docker logs --since=2m policy-agent-container
```

### Filter Important Errors

```bash
docker logs --since=5m policy-agent-container 2>&1 \
  | grep -Ei 'error|warn|sync|policySchema|FileStore'
```

---

## 23. VM-2 Quick Checks

### Running Containers

```bash
docker ps \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### DBaaS

```bash
cd /opt/oran/nearrt/oran-sc-ric

docker compose exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

### A1 Mediator

```bash
curl -i \
  http://127.0.0.1:10000/A1-P/v2/healthcheck
```

### Compatibility Shim

```bash
curl -i \
  http://127.0.0.1:10001/a1-p/healthcheck
```

### Policy Types

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

### Docker Network

```bash
docker network inspect oran-sc-ric_ric_network \
  --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}' \
  | sort
```

### RMR Route

```bash
docker exec ric_a1mediator \
  cat /opt/route/local.rt
```

---

# Known-Good State

## 24. VM-1

The validated state is:

```text
A1 PMS version   : 2.6.0
Container        : policy-agent-container
Port             : 8081
RIC ID           : near-rt-ric-1
RIC state        : AVAILABLE
Policy type      : 20008
A1 target        : http://10.10.10.12:10001
Client           : OscA1Client
```

---

## 25. VM-2

The validated state is:

```text
Near-RT RIC repository:
srsran/oran-sc-ric

Commit:
621ade26251f69a4ad079ba98bb708d8e5aeeb98

A1 Mediator:
3.2.2

A1 Mediator commit:
09a757b4fd63198d8690d50b52bfd04552d47f1f

A1 API:
10.10.10.12:10000

A1 compatibility API:
10.10.10.12:10001

E2:
10.10.10.12:36421/SCTP

Python xApp RMR:
4560

RMR policy request:
20010

RMR policy response:
20011
```

---

## 26. Known-Good End-to-End Result

The complete A1 path is considered healthy when:

```text
PMS status
    =
healthy
```

```text
near-rt-ric-1
    =
AVAILABLE
```

```text
policytype_ids
    contains
20008
```

```text
xApp
    receives
CREATE / UPDATE / DELETE
```

and:

```text
A1 policy status
    =
ENFORCED
```

Validated flow:

```text
VM-1 A1 PMS
      │
      ▼
VM-2 Compatibility Shim
      │
      ▼
A1 Mediator
      │
      │ RMR 20010
      ▼
xApp
      │
      │ RMR RTS 20011
      ▼
A1 Mediator
      │
      ▼
ENFORCED
---

# VM-3 & VM-4 — Core to RAN Networking

## 23. VM-4 Cannot Reach VM-3 5GC Containers (100% Packet Loss on 192.168.70.x)

### Symptom
On VM-4 (`10.10.10.14`), `ping 10.10.10.13` (VM-3 host) succeeds with 0% packet loss, but `ping 192.168.70.138` (AMF container) fails with 100% packet loss:

```text
PING 192.168.70.138 (192.168.70.138) 56(84) bytes of data.
--- 192.168.70.138 ping statistics ---
2 packets transmitted, 0 received, 100% packet loss, time 1004ms
```

### Cause
Three factors can block external routed traffic between VM-4 and the VM-3 5GC containers:
1. **Missing Static Route on VM-4:** If `192.168.70.0/24 via 10.10.10.13` is not present in VM-4's routing table (`ip route show`), VM-4 falls back to its default gateway (`10.10.10.1 dev enp0s3`), which drops the packets (0 packets reach VM-3).
2. **Accidental Static Route on VM-3 Host:** If `ip route add 192.168.70.0/24 via 10.10.10.13` was mistakenly executed on VM-3 itself, a duplicate conflicting route (`192.168.70.0/24 via 10.10.10.13 dev enp0s3`) is created that takes precedence over `192.168.70.0/24 dev demo-oai`. This loops traffic to `enp0s3` causing `Destination Host Unreachable`.
3. **Docker `FORWARD` Policy & Bridge NAT:** Docker sets the default policy of the `FORWARD` iptables chain to `DROP`. Unless explicitly permitted in `DOCKER-USER` and masqueraded on `demo-oai`, Docker drops packets arriving from outside the host aimed at container IP addresses.

### Solution

#### On VM-4 (`oai-ran`):
Ensure the static route to VM-3 5GC is present:
```bash
sudo ip route add 192.168.70.0/24 via 10.10.10.13 dev enp0s3
ip route show | grep 192.168.70
```

#### On VM-3 (`oai-5gc`):

```bash
# 1. Remove the accidental static route on VM-3 itself if present
sudo ip route del 192.168.70.0/24 via 10.10.10.13 dev enp0s3 2>/dev/null || true
sudo rm -f /etc/network/interfaces.d/5gc-route

# 2. Allow routed forwarding in Docker's DOCKER-USER filter chain
sudo iptables -P FORWARD ACCEPT
sudo iptables -I DOCKER-USER -s 10.10.10.0/24 -d 192.168.70.0/24 -j ACCEPT
sudo iptables -I DOCKER-USER -s 192.168.70.0/24 -d 10.10.10.0/24 -j ACCEPT

# 3. Add MASQUERADE on demo-oai interface so container receives local-bridge source IP
sudo iptables -t nat -I POSTROUTING -o demo-oai -j MASQUERADE
```

---

# VM-4 — OAI RAN

## 24. Git Clone Failed with RPC failed; curl 92 HTTP/2 stream CANCEL / early EOF

### Symptom
When cloning the official `openairinterface5g` repository:

```text
error: RPC failed; curl 92 HTTP/2 stream 0 was not closed cleanly: CANCEL (err 8)
error: RPC failed; curl 56 GnuTLS recv error (-9): Error decoding the received TLS packet.
error: 5 bytes of body are still expected
fetch-pack: unexpected disconnect while reading sideband packet
fatal: early EOF
fatal: fetch-pack: invalid index-pack output
```

### Cause
Ubuntu's default `git` package is linked against `libcurl-gnutls`. GnuTLS has known issues decoding compressed TLS sideband packets on large git pack transfers when network latency or MTU fragmentation occurs.

### Solution
1. Use tarball download via `wget` (~25 MB):
   ```bash
   cd /opt/oran/ran
   wget -c https://github.com/duranta-project/openairinterface5g/archive/refs/heads/develop.tar.gz -O oai-develop.tar.gz
   mkdir -p openairinterface5g
   tar -xzf oai-develop.tar.gz -C openairinterface5g --strip-components=1
   ```
2. Or use shallow git clone with buffer optimizations:
   ```bash
   git config --global core.compression 0
   git config --global http.postBuffer 524288000
   git config --global http.version HTTP/1.1
   git clone --depth 1 -b develop https://github.com/OPENAIRINTERFACE/openairinterface5g.git
   ```

---

## 25. FlexRIC Tarball Download Fails with HTTP 429 Too Many Requests

### Symptom
When downloading the FlexRIC archive from GitLab EURECOM:

```text
--2026-09-27 10:11:07--  https://gitlab.eurecom.fr/mosaic5g/flexric/-/archive/master/flexric-master.tar.gz
Resolving gitlab.eurecom.fr (gitlab.eurecom.fr)... 193.55.113.249
Connecting to gitlab.eurecom.fr (gitlab.eurecom.fr)|193.55.113.249|:443... connected.
HTTP request sent, awaiting response... 429 Too Many Requests
2026-09-27 10:11:07 ERROR 429: Too Many Requests.
gzip: stdin: unexpected end of file
tar: Child returned status 1
```

### Cause
GitLab EURECOM has an automated rate-limiting policy on dynamic on-the-fly archive generation (`/-/archive/master/...tar.gz`) to protect server CPU resources, returning HTTP 429 for archive generation requests.

### Solution
Do not download the archive tarball. Use a shallow `git clone` directly from the Git repository endpoint, which is lightweight (~8.5 MB) and not subject to the archive generator rate limit:

```bash
cd /opt/oran/ran
rm -rf openairinterface5g/openair2/E2AP/flexric
git clone --depth 1 https://gitlab.eurecom.fr/mosaic5g/flexric.git openairinterface5g/openair2/E2AP/flexric
```

---

## 26. SIMDE Installation Fails with Git Timeout (curl 28) during `./build_oai -I`

### Symptom
During the `./build_oai -I` dependency installation step:

```text
Installing SIMDE from source without test cases (header files only)
Cloning into '/tmp/simde'...
remote: Enumerating objects: 12918, done.
remote: Counting objects: 100% (579/579), done.
remote: Compressing objects: 100% (304/304), done.
error: RPC failed; curl 28 Operation too slow. Less than 1000 bytes/sec transferred the last 600 seconds
error: 487 bytes of body are still expected
fetch-pack: unexpected disconnect while reading sideband packet
fatal: early EOF
fatal: fetch-pack: invalid index-pack output
/opt/oran/ran/openairinterface5g/cmake_targets/tools/build_helper: line 492: cd: /tmp/simde: No such file or directory
fatal: not a git repository (or any of the parent directories): .git
cp: cannot stat '../simde': No such file or directory
BUILD SHOULD BE SUCCESSFUL
```

### Cause
OAI's `cmake_targets/tools/build_helper` attempts to clone the full repository of `simde-no-tests` without `--depth 1`. On networks with higher latency or packet filtering, the un-shallow transfer times out after 600 seconds (`curl 28 Operation too slow`). Although the script concludes with `BUILD SHOULD BE SUCCESSFUL`, the header files in `/usr/include/simde` are missing, which breaks the subsequent `nr-softmodem` build.

### Solution
SIMDe (SIMD Everywhere) is a **header-only** library. Either install the distro package or perform a shallow clone manually:

#### Option 1: Install official package (instant)
```bash
sudo apt update && sudo apt install -y libsimde-dev
```

#### Option 2: Shallow clone manual copy
```bash
sudo rm -rf /tmp/simde
git clone --depth 1 https://github.com/simd-everywhere/simde-no-tests.git /tmp/simde
sudo cp -r /tmp/simde/simde /usr/include/
```

Verify the header installation:
```bash
ls -d /usr/include/simde
# Expected: /usr/include/simde
```

---

## 27. GCC 11 Internal Compiler Error (Segmentation fault) on FlexRIC `kpm_sm` `_Generic` Macro

### Symptom
When compiling FlexRIC Service Models with `gcc-11` (Ubuntu 22.04 default compiler) under `-O2`:

```text
FAILED: openair2/E2AP/flexric/src/sm/kpm_sm/kpm_sm_v02.03/CMakeFiles/kpm_sm.dir/kpm_sm_ric.c.o 
during RTL pass: expand
/opt/oran/ran/openairinterface5g/openair2/E2AP/flexric/src/sm/kpm_sm/kpm_sm_v02.03/dec/kpm_dec_generic.h:38:33: internal compiler error: Segmentation fault
   38 | #define kpm_dec_func_def(T,U,V) _Generic ((T), \
```

### Cause
GCC 11.4 (Ubuntu 22.04 default) has a known upstream bug in the RTL `expand` pass that segfaults when evaluating functions that return large ASN.1-generated structures under optimization (`-O2` / `-funroll-loops`). This bug is fixed upstream in **GCC 12.3+**.

### Solution
Install and activate **GCC 12** via `update-alternatives`:

```bash
# 1. Install GCC 12 & G++ 12 from official Ubuntu repositories
sudo apt update && sudo apt install -y gcc-12 g++-12

# 2. Configure GCC 12 as default system compiler
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 100 --slave /usr/bin/g++ g++ /usr/bin/g++-12
sudo update-alternatives --install /usr/bin/cc cc /usr/bin/gcc 100
sudo update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++ 100

# Verify active compiler version (should report GCC 12.3.0)
gcc --version
```

---

---

## 28. `redis: got 7 elements in COMMAND reply, wanted 6` on `ric_e2mgr` with `ric-plt-dbaas:0.6.4`

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

## 29. E2T Instance Prematurely Deleted by `e2mgr` Keepalive Timeout (4.5s)

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

## Related Documentation

- [VM-1 — Non-RT RIC](vm1-nonrt-ric.md)
- [VM-2 — Near-RT RIC](vm2-nearrt-ric.md)
- [A1 Integration](a1-integration.md)
- [E2 Integration](e2-integration.md)
- [System Architecture](architecture.md)

---

## References

Official documentation:

- O-RAN SC — A1 Policy Management Service  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/

- O-RAN SC — A1 Mediator  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-a1/

- O-RAN SC — RMR  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-lib-rmr/

- O-RAN SC — Python xApp Framework  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-xapp-frame-py/

- srsRAN — Minimal O-RAN SC RIC deployment  
  https://github.com/srsran/oran-sc-ric

- Docker Documentation  
  https://docs.docker.com/
