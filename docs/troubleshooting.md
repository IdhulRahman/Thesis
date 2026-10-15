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
  "baseUrl": "http://10.102.0.66:10001",
  "customAdapterClass": "org.onap.ccsdk.oran.a1policymanagementservice.clients.OscA1Client"
}
```

The validated path is:

```text
PMS
 │
 │ OscA1Client
 ▼
10.102.0.66:10001
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
baseUrl = http://10.102.0.66:10001
```

The compatibility shim only maps URI paths. It does not rewrite the policy JSON.

See:

[A1 Integration](integration/a1-integration.md)

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
10.102.0.66:10001
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
A1 target        : http://10.102.0.66:10001
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
10.102.0.66:10000

A1 compatibility API:
10.102.0.66:10001

E2:
10.102.0.66:36421/SCTP

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
On VM-4 (`10.102.0.167`), `ping 10.102.0.164` (VM-3 host) succeeds with 0% packet loss, but `ping 192.168.70.138` (AMF container) fails with 100% packet loss:

```text
PING 192.168.70.138 (192.168.70.138) 56(84) bytes of data.
--- 192.168.70.138 ping statistics ---
2 packets transmitted, 0 received, 100% packet loss, time 1004ms
```

### Cause
Four distinct factors can block external routed traffic between VM-4 and the VM-3 5GC containers:
1. **Missing Static Route on VM-4:** If `192.168.70.0/24 via 10.102.0.164` is not present in VM-4's routing table (`ip route show`), VM-4 falls back to its default gateway, dropping the packets before reaching VM-3.
2. **Accidental Static Route on VM-3 Host:** If `ip route add 192.168.70.0/24 via 10.102.0.164` was mistakenly executed on VM-3 itself, a duplicate conflicting route (`192.168.70.0/24 via 10.102.0.164 dev ens33`) is created that takes precedence over `192.168.70.0/24 dev demo-oai`. This loops traffic back to `ens33` causing `Destination Host Unreachable`.
3. **Docker `FORWARD` Filter Chain & Bridge Policy:** Docker defaults the `FORWARD` iptables chain policy to `DROP`. Unless explicitly accepted at rule position 1 of `FORWARD` or permitted in `DOCKER-USER`, Docker drops routed ingress packets between `ens33` and `demo-oai`.
4. **Docker `raw` Table PREROUTING Anti-Spoofing Rule (Root Cause for Zero FORWARD Packets):** When creating user-defined bridge networks, Docker daemon installs anti-spoofing packet filtering rules in the netfilter `raw` table:
   ```text
   -A PREROUTING -d 192.168.70.138/32 ! -i demo-oai -j DROP
   -A PREROUTING -d 192.168.70.142/32 ! -i demo-oai -j DROP
   -A PREROUTING -d 192.168.70.143/32 ! -i demo-oai -j DROP
   ```
   Because routed packets from VM-4 arrive via physical NIC `ens33` (`! -i demo-oai`), the Linux kernel silently drops the packets in the `raw` table **before the packets ever reach the routing decision or the `FORWARD` filter chain** (causing `FORWARD` packet counters to show `pkts = 0` and `tcpdump -i any` to show packets on `ens33` but never on `demo-oai`).

### Solution

#### On VM-4 (`oai-ran`):
Ensure the static route to VM-3 5GC is present:
```bash
sudo ip route add 192.168.70.0/24 via 10.102.0.164
ip route show | grep 192.168.70
```

#### On VM-3 (`oai-5gc`):

```bash
# 1. Bypass Docker raw table PREROUTING anti-spoofing drop rule
sudo iptables -t raw -I PREROUTING 1 -i ens33 -d 192.168.70.0/24 -j ACCEPT

# 2. Allow routed forwarding across ens33 and demo-oai
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv4.conf.all.forwarding=1
sudo sysctl -w net.ipv4.conf.ens33.forwarding=1
echo 1 | sudo tee /proc/sys/net/ipv4/conf/demo-oai/forwarding 2>/dev/null || true

sudo iptables -I FORWARD 1 -i ens33 -o demo-oai -j ACCEPT
sudo iptables -I FORWARD 2 -i demo-oai -o ens33 -j ACCEPT

# 3. Add MASQUERADE on demo-oai so container returns traffic to host gateway
sudo iptables -t nat -I POSTROUTING -o demo-oai -j MASQUERADE

# 4. Remove any accidental static route on VM-3 itself if present
sudo ip route del 192.168.70.0/24 via 10.102.0.164 2>/dev/null || true
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

## 30. F1-U GTP-U Socket Bind Collision on VM-4 (`bind: Address already in use: 127.0.0.1 2153`)

### Symptom
When starting DU-1 (`du_gnb1.conf`) after CU (`cu_gnb.conf`) is already active on VM-4:

```text
[GTPU]   Initializing UDP for local address 127.0.0.1 with port 2153
[GTPU]   bind: Address already in use
[GTPU]   failed to bind socket: 127.0.0.1 2153 
[GTPU]   can't create GTP-U instance

Assertion (gtpInst > 0) failed!
In F1AP_DU_task() /opt/oran/ran/openairinterface5g/openair2/F1AP/f1ap_du_task.c:121
cannot create DU F1-U GTP module
```

### Cause
CU (`cu_gnb.conf`), DU-1 (`du_gnb1.conf`), and DU-2 (`du_gnb2.conf`) run as separate Linux processes on the same host (VM-4) using the local loopback interface (`127.0.0.1`).  
Because CU binds to `127.0.0.1:2153` (`local_s_portd = 2153`), DU-1 cannot bind to the exact same UDP port on `127.0.0.1` (`local_n_portd = 2153`).  
DU-2 does not experience this error because it uses port `2154` (`local_n_portd = 2154`).

### Solution
Differentiate the F1-U listening UDP ports across all three nodes:
- **CU:** listens on `127.0.0.1:2153` (`local_s_portd = 2153`)
- **DU-1:** binds to `127.0.0.1:2155` (`local_n_portd = 2155`, sending to CU at `remote_n_portd = 2153`)
- **DU-2:** binds to `127.0.0.1:2154` (`local_n_portd = 2154`, sending to CU at `remote_n_portd = 2153`)

Update `/opt/oran/ran/conf/du_gnb1.conf`:
```bash
sed -i 's/local_n_portd.*=.*2153/local_n_portd   = 2155/g' /opt/oran/ran/conf/du_gnb1.conf
```

Verify the setting:
```bash
grep -E "local_n_portd|remote_n_portd" /opt/oran/ran/conf/du_gnb1.conf
# Output:
# local_n_portd   = 2155;
# remote_n_portd  = 2153;
```

---

## 31. Docker Compose Network Collision & Undefined Network during NWDAF Merge

### Symptom
When merging `docker-compose-nwdaf-cn-http1.yaml` into `docker-compose-slicing-basic-nrf.yaml` on VM-3:
1. `service "oai-nwdaf-engine" refers to undefined network nwdaf_net: invalid compose project`
2. `failed to parse ... yaml: construct errors: line 1: line 486: mapping key "public_net" already defined at line 463`

### Cause
- NWDAF microservice definitions in `docker-compose-nwdaf-cn-http1.yaml` use the network key `nwdaf_net:` (with underscore `_`). If the network definition block defines it as `nwdaf-net:` (with hyphen `-`), Docker Compose cannot resolve the reference.
- Both `docker-compose-slicing-basic-nrf.yaml` and `docker-compose-nwdaf-cn-http1.yaml` define `public_net:` under their respective `networks:` blocks. Concatenating both files creates a duplicate mapping key error in YAML parser.

### Solution
In `docker-compose-slicing-basic-nrf.yaml`, retain the existing `public_net:` block and append **only** `nwdaf_net:`:

```yaml
networks:
    public_net:
        name: demo-oai-public-net
        ipam:
            config:
                - subnet: 192.168.70.0/24
    nwdaf_net:
        name: oai-nwdaf-net
        ipam:
            config:
                - subnet: 192.168.74.0/24
```

Validate YAML syntax before launching:
```bash
sudo docker compose -f docker-compose-slicing-basic-nrf.yaml config > /dev/null && echo "YAML SYNTAX VALID"
```

---

## 32. MySQL 8.0 Subscriber Initialization Failure on OAI v2.1.0 Schema (`ERROR 1054` & `ERROR 3140`)

### Symptom
When initializing the MySQL subscriber database (`mysql:8.0`) with custom or legacy provisioning scripts:
1. `ERROR 1054 (42S22) at line 429: Unknown column 'vectorAlgorithm' in 'field list'`
2. `ERROR 3140 (22032) at line 429: Invalid JSON text: "The document root must not be followed by other values." at position 1 in value for column 'AuthenticationSubscription.sequenceNumber'`

The `mysql` container exits immediately with code `1`.

### Cause
In OAI 5GC `v2.1.0`, the MySQL database schema in `database/oai_db2.sql` changed from legacy versions:
- In `AuthenticationSubscription`, the algorithm column is named `algorithmId` (not `vectorAlgorithm`).
- The column `sequenceNumber` is defined as `JSON DEFAULT NULL` in MySQL 8.0, requiring strict JSON string formatting:
  `'{"sqn": "000000000020", "sqnScheme": "NON_TIME_BASED", "lastIndexes": {"ausf": 0}}'`
  Inserting a raw hex/binary string like `'000000000000'` fails JSON validation.
- In `SessionManagementSubscriptionData`, the columns are `(ueid, servingPlmnid, singleNssai, dnnConfigurations)` where `singleNssai` is a JSON string: `'{"sst": 1, "sd": "000001"}'` or `'{"sst": 222, "sd": "00007B"}'`.

### Solution
1. Remove failed container and its anonymous volume:
   ```bash
   sudo docker rm -f -v mysql
   ```
2. Insert records matching the exact OAI v2.1.0 schema:
   ```sql
   INSERT INTO `AuthenticationSubscription` (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`, `n5gcAuthMethod`, `rgAuthenticationInd`, `supi`)
   VALUES ('208950000000031', '5G_AKA', '0C0A34601D4F07677303652C0462535B', '0C0A34601D4F07677303652C0462535B', '{\"sqn\": \"000000000020\", \"sqnScheme\": \"NON_TIME_BASED\", \"lastIndexes\": {\"ausf\": 0}}', '8000', 'milenage', '63bfa50ee6523365ff14c1f45f88737d', NULL, NULL, NULL, NULL, '208950000000031')
   ON DUPLICATE KEY UPDATE `ueid` = `ueid`;

   INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `singleNssai`, `dnnConfigurations`)
   VALUES ('208950000000031', '20895', '{\"sst\": 1, \"sd\": \"000001\"}', '{\"default\":{\"pduSessionTypes\":{ \"defaultSessionType\": \"IPV4\"},\"sscModes\": {\"defaultSscMode\": \"SSC_MODE_1\"},\"5gQosProfile\": {\"5qi\": 6,\"arp\":{\"priorityLevel\": 1,\"preemptCap\": \"NOT_PREEMPT\",\"preemptVuln\":\"NOT_PREEMPTABLE\"},\"priorityLevel\":1},\"sessionAmbr\":{\"uplink\":\"100Mbps\", \"downlink\":\"100Mbps\"}}}')
   ON DUPLICATE KEY UPDATE `ueid` = `ueid`;
   ```
3. Restart MySQL: `sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d mysql`.

---

## 33. Kong API Gateway 404 Not Found on Physical Host IP (`http://10.102.0.164:8080`)

### Symptom
Sending standard `Nnwdaf_AnalyticsInfo` queries to Kong via physical host IP returns `HTTP/1.1 404 Not Found`, while direct queries to `http://127.0.0.1:6059` return HTTP 200 or 400.

### Cause
The default declarative config `/opt/oran/5gc/oai-cn5g-nwdaf/docker-compose/conf/kong.yml` restricts routing with `hosts: - oai-nwdaf-nbi-gateway`.  
HTTP clients (such as Python `requests` or `curl`) calling `http://10.102.0.164:8080/...` send the header `Host: 10.102.0.164:8080`. Kong does not match this host header and rejects the request with a 404.

### Solution
Remove the restrictive `hosts:` filter from `kong.yml` so that Kong routes purely by URL path:

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

Restart Kong:
```bash
sudo docker restart oai-nwdaf-nbi-gateway
```

---

## 34. Transient Docker Hub Timeout during Large Image Pulls (`net/http: timeout awaiting response headers`)

### Symptom
During `docker compose pull` or `docker compose up -d` on VM-3:
```text
failed to copy: httpReadSeeker: failed open: failed to do request: Get "https://registry-1.docker.io/v2/oaisoftwarealliance/oai-amf/blobs/...": net/http: timeout awaiting response headers
```

### Cause
Transient network latency or Docker Hub rate limiting while downloading multi-hundred-megabyte layers (`oai-amf`, `oai-upf-vpp`, `mysql`).

### Solution
Docker natively caches already-downloaded layers. Simply re-execute:
```bash
sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
```
Docker will resume from cached layers and download only remaining uncompleted blobs without re-downloading finished images.

---

## 35. Near-RT RIC E2Mgr / SubMgr Container Exit on Startup due to Missing DBaaS Environment Variables

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

## 36. E2Term SCTP Port 36421 Inaccessible from External RAN Node (`Connection refused`)

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

## 37. Packet Drop / Ping Timeout from RAN (VM-4) to 5GC Docker Subnet (`192.168.70.0/24`) via Host VM-3

### Symptom
When testing reachability from VM-4 (`oai-ran` — `10.102.0.167`) to the 5G Core AMF container (`192.168.70.138`) or UPF containers:
```bash
ping -c 2 192.168.70.138
# Output:
# 2 packets transmitted, 0 received, 100% packet loss, time 1020ms
```
However, ping from VM-4 to the physical host VM-3 (`10.102.0.164`) succeeds with 0% packet loss.

### Cause
By default on Ubuntu and Docker:
1. **Docker FORWARD Chain Rejection:** Docker inserts a default `-j DROP` rule at the bottom of the `FORWARD` filter chain. Forwarded IP packets arriving on external host interfaces (e.g. `ens33`) destined for internal container bridge networks (`192.168.70.0/24`) are discarded.
2. **Reverse Path Filtering (`rp_filter`):** The Linux kernel performs strict reverse-path checks. Because the source address belongs to `10.102.0.0/24` and enters an interface with a different local subnet routing, the kernel flags it as a martian/spoofed packet and drops it silently.
3. **UFW / Firewall Rules:** Active firewall configurations reject forwarded inter-subnet packets by default.

### Solution
Apply the following routing and forwarding configuration on **VM-3 (`10.102.0.164`)**:

```bash
# 1. Disable UFW if active
sudo ufw disable 2>/dev/null || true

# 2. Enable kernel forwarding and disable reverse-path filtering across all interfaces
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv4.conf.all.rp_filter=0
sudo sysctl -w net.ipv4.conf.default.rp_filter=0
for f in /proc/sys/net/ipv4/conf/*/rp_filter; do echo 0 | sudo tee $f > /dev/null; done

# 3. Allow packet forwarding in DOCKER-USER and FORWARD iptables chains
sudo iptables -I DOCKER-USER 1 -j ACCEPT
sudo iptables -I FORWARD 1 -j ACCEPT

# 4. Enable bidirectional NAT masquerading for the container bridge network
sudo iptables -t nat -I POSTROUTING 1 -d 192.168.70.0/24 -j MASQUERADE
sudo iptables -t nat -I POSTROUTING 2 -s 192.168.70.0/24 -j MASQUERADE
```

On **VM-4 (`10.102.0.167`)**, ensure the static route exists:
```bash
sudo ip route replace 192.168.70.0/24 via 10.102.0.164
ping -c 2 192.168.70.138
# Expected: 2 packets transmitted, 2 received, 0% packet loss
```

---

## 38. OAI gNB CU E2 Agent Inactive / Disabled (`E2 agent is DISABLED`)

### Symptom
When starting OAI CU softmodem with `sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf`, CU connects to 5GC AMF via N2, but no E2 connection is initiated toward Near-RT RIC (`ric_e2term`).  
Alternatively, the logs show:
```text
E2 agent is DISABLED (for activation, define .e2_agent.{near_ric_ip_addr,sm_dir} parameters)
```
And `ric_e2term` on VM-2 does not receive any SCTP connection.

### Cause
In the OpenAirInterface `develop` branch, the E2 agent argument parser (`openair2/E2AP/e2_agent_arg.c`) checks parameter readiness using `config_isparamset()`. If the configuration file structure uses nested syntax or if the config loader initializes before the main RRC context is populated, `config_isparamset()` may evaluate to false, keeping `oai_args.enabled = false` and disabling the E2 agent thread.

### Solution
Pass the E2 agent parameters explicitly via command-line arguments when launching `nr-softmodem`:

```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build

sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf \
  --e2_agent.near_ric_ip_addr 10.102.0.66 \
  --e2_agent.sm_dir /usr/local/lib/flexric/ \
  2>&1 | tee /opt/oran/ran/cu.log
```

Expected output verifying active E2 initialization:
```text
After RCconfig_NR_E2agent /usr/local/lib/flexric/ 10.102.0.66
[E2 NODE]: mcc = 208 mnc = 95 mnc_digit = 2 nb_id = 3584
[E2 NODE]: Args 10.102.0.66 /usr/local/lib/flexric/
```

And in `ric_e2mgr` logs on VM-2:
```bash
#RanConnectStatusChangeManager.ChangeStatus - RAN name: gnb_208_095_00000e00, currentStatus: UNKNOWN_CONNECTION_STATUS, nextStatus: CONNECTED
```

---

## 39. OAI nrUE Softmodem Immediate Abort on Deprecated Command-Line Option `--sa`

### Symptom
When starting `nr-uesoftmodem` with the flag `--sa`:
```text
[CONFIG] unknown option: --sa
[ENB_APP] [CONFIG] 1 unknown option(s) in command line starting with  (section ALLSECTIONS)
[NR_PHY] called by: config_check_unknown_cmdlineopt() Exiting OAI softmodem: exit_fun
[NR_PHY] UE main thread is ending
```
The softmodem performs radio cell detection, RACH, and RRC connection, but immediately aborts and exits.

### Cause
In the OpenAirInterface `develop` branch, Standalone (SA) mode has been set as the default operation mode for `nr-uesoftmodem`. The `--sa` command-line flag was deprecated and removed from the active parameter definition list. The strict option validator in `config_cmdline.c` treats `--sa` as an unknown command-line option and forcefully terminates the softmodem.

### Solution
Remove the `--sa` flag from the command line invocation. `nr-uesoftmodem` automatically defaults to Standalone mode:

```bash
cd /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build

sudo ./nr-uesoftmodem \
  -r 106 \
  --numerology 1 \
  --band 78 \
  -C 3619200000 \
  --rfsim \
  --rfsimulator.serveraddr 10.102.0.167 \
  --rfsimulator.serverport 4043 \
  -O /opt/oran/ue/conf/ue_slice1.conf
```

---

## 40. PDU Session Establishment Stuck / Ignored: Mismatch in 5GC Slicing YAML Configurations

### Symptom
On VM-5, `nr-uesoftmodem` successfully connects to gNB DU/CU via RFsimulator, executes 4-Step RACH, passes 5G-AKA authentication, and reaches `5GMM-REGISTERED` state on AMF.  
However, when the UE sends `NAS_UPLINK_DATA_REQ (PduSessionEstablishRequest)` with `NSSAI 1.1 DNN default`:
```text
[NAS]    requested PDU session ID 10 type 1 NSSAI 1.1 DNN default
[NAS]    Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
```
The UE hangs waiting indefinitely for `PduSessionEstablishAccept`, and no TUN interface (`oaitun_ue1`) is created.

On VM-3 (`oai-core`), `oai-smf-slice1` logs show no PDU session requests received, only NRF and PFCP heartbeats:
```text
[smf_n4 ] [info] PFCP HEARTBEAT PROCEDURE starting
[smf_sbi] [debug] Send NF Update to NRF (HTTP version 2)
```

In `oai-amf` logs, AMF queries NSSF for network slice selection:
```text
[amf_sbi] [debug] Send Network Slice Information Retrieval, URI http://oai-nssf:8080/nnssf-nsselection/v1/network-slice-information?nf-type=AMF&...&slice-info-request-for-pdu-session={"roamingIndication":"NON_ROAMING","sNssai":{"sd":"000001","sst":1}}
```
And NSSF responds with SMF candidates supporting only default tutorial slices:
```json
{"nfInstances":[{"nfInstanceName":"OAI-SMF","sNssais":[{"sd":"000080","sst":128}]},{"nfInstanceName":"OAI-SMF","sNssais":[{"sd":"FFFFFF","sst":1}]}]}
```
Because neither SMF supports the requested S-NSSAI `[SST: 1, SD: 000001]`, AMF cannot route the PDU session creation context, dropping the session setup.

Additionally, AMF logs periodic warnings:
```text
[amf_sbi] [info] Send HTTP message to 
[amf_sbi] [info] Cannot get response when calling
[amf_app] [warning] NF Instance Registration, got issue when registering to NRF, try again ...
```
caused by a missing `nfs.nrf` endpoint definition in `conf/slicing_base_config.yaml`.

### Cause
In OpenAirInterface `cn5g-fed` v2.1.0, container services in `docker-compose-slicing-basic-nrf.yaml` mount YAML files from `./conf/`:
- `oai-smf-slice1`, `oai-upf-slice1`, `oai-nrf-slice12` mount `conf/slicing_slice1_config.yaml`
- `oai-smf-slice2`, `oai-upf-slice2` mount `conf/slicing_slice2_config.yaml`
- `oai-nssf` mounts `conf/nssf_slice_config.yaml`
- `oai-amf` mounts `conf/slicing_base_config.yaml`

By default, OAI upstream ships these files preconfigured for tutorial slice parameters (`SST: 128, SD: 000080` for Slice 1, `SST: 1, SD: none` for Slice 2). If these YAML files are not aligned with the thesis architecture (`SST: 1, SD: 1` eMBB, `SST: 222, SD: 123` URLLC), NSSF and NRF will not recognize the SMF instances as candidates for the requested S-NSSAI.

### Solution
On VM-3 (`oai-core`), update the configuration files to match the thesis multi-slice architecture:

1. Update `conf/slicing_slice1_config.yaml`:
   - Set `snssais`: `sst: 1`, `sd: 000001`
   - Set `dnn`: `default`, subnet `12.1.1.0/24`
2. Update `conf/slicing_slice2_config.yaml`:
   - Set `snssais`: `sst: 222`, `sd: 00007B`
   - Set `dnn`: `lowlatency`, subnet `12.1.2.0/24`
3. Update `conf/nssf_slice_config.yaml`:
   - Map `sst: 1, sd: '000001'` to `nsiId: '11'` with `nrfId: http://192.168.70.136:8080/nnrf-disc/v1/nf-instances` and `nrfNfMgtUri: http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances`.
   - Map `sst: 222, sd: '00007B'` to `nsiId: '12'` with `nrfId: http://192.168.70.136:8080/nnrf-disc/v1/nf-instances` and `nrfNfMgtUri: http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances`.
   - **Crucial:** In `configuration.nsiInfoList`, each slice must define `nrfNfMgtUri` alongside `nrfId`. When AMF has `enable_nssf: yes`, it retrieves the NRF Management URI from NSSF's `NsiInformation` response (3GPP TS 29.531 §6.1.6.2.3). If omitted, AMF registers toward an empty URI string (`Send HTTP message to <empty>`), triggering repeated registration warnings.
   - **Critical:** Preserve mandatory sections `taInfoList` (PLMN 208/95, TAC 40960) and `amfInfoList`, otherwise NSSF fails on startup with `[nssf_app] [error] Error parsing section : taInfoList`.
4. In `conf/slicing_base_config.yaml`:
   - Add `nrf: host: oai-nrf-slice12` under `nfs:` so AMF successfully registers its NF profile.
5. In `docker-compose-slicing-basic-nrf.yaml`:
   - Update `oai_ext_dn` routes to `12.1.1.0/24 via 192.168.70.142` and `12.1.2.0/24 via 192.168.70.143`.
6. Apply compose changes and restart containers to reload mounted configs:
   ```bash
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
   sudo docker restart oai-nrf-slice12 oai-nssf oai-amf oai-smf-slice1 oai-smf-slice2 oai-upf-slice1 oai-upf-slice2
   ```

---

## 41. User-Plane Packet Drop on F1-U: Stale TEID Mapping in gNB CU (`no tunnel mapping, drop`)

### Symptom
On VM-5, `nr-uesoftmodem` successfully establishes a PDU session, and `oaitun_ue1` is configured with IP `12.1.1.2`. On VM-3, `oai-upf-slice1` confirms active PDR/FAR rules for `12.1.1.2`.  
However, pinging from UE (`ping -I oaitun_ue1 -c 4 192.168.70.145`) or gateway `12.1.1.1` results in 100% packet loss.

On VM-4 (`oai-ran`), `cu.log` repeatedly floods with GTP-U drop messages from DU-1:
```text
[GTPU]   [81] GTP Error Indication TEID-I 0x99b867eb: no tunnel mapping, drop
[GTPU]   [81] Sent GTP Error Indication TEID-I 0x99b867eb to 127.0.0.1:2153
[GTPU]   [81] Received a incoming packet on unknown TEID (0x99b867eb) Dropping!
[GTPU]   [81] GTP Error Indication TEID-I 0x99b867eb GTP-U Peer Address 127.0.0.1 UDP-from 127.0.0.1
```

### Cause
In OAI Split-RAN (CU + DU), the user plane uses F1-U (GTP-U over local port `2153/2152`) to transport data radio bearer (DRB) packets between DU and CU.  
When an nrUE instance is aborted abruptly (e.g. via `Ctrl+C`) or when prior connection attempts failed during 5GC debugging, DU and CU retain orphaned F1-U bearer mappings. When the UE reconnects and initiates user plane traffic, DU forwards packets using a stale or out-of-sync TEID that CU no longer maps to an active N3 GTP-U session, causing CU to drop all uplink traffic.

### Solution
Restart the RAN components on **VM-4** to clear all orphaned GTP-U and F1-U context tables, then relaunch the UE:

1. On **VM-4 (`oai-ran`)**, restart the clean background daemons:
   ```bash
   sudo /opt/oran/ran/start_ran.sh
   ```
2. Verify CU and DU are running fresh:
   ```bash
   pgrep nr-softmodem
   tail -n 15 /opt/oran/ran/cu.log | grep -i "associated"
   ```
3. On **VM-5 (`ue-emulator`)**, restart UE 1:
   ```bash
   cd /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build
   sudo ./nr-uesoftmodem \
     -r 106 \
     --numerology 1 \
     --band 78 \
     -C 3619200000 \
     --rfsim \
     --rfsimulator.serveraddr 10.102.0.167 \
     --rfsimulator.serverport 4043 \
     -O /opt/oran/ue/conf/ue_slice1.conf
   ```
4. Verify user plane ping from VM-5:
   ```bash
   ping -I oaitun_ue1 -c 4 192.168.70.145
   ping -I oaitun_ue1 -c 4 12.1.1.1
   ```

---

## 42. F1-U Downlink Self-Loop Drop when CU and DU Bind to `127.0.0.1` (`Sent GTP Error Indication ... to 127.0.0.1:2153: no tunnel mapping, drop`)

### Symptom
When UE on VM-5 pings an external Data Network (`192.168.70.145`) or UPF gateway (`12.1.1.1`):
- `tcpdump` on VM-3 confirms that the ICMP echo request reaches UPF-1, EXT-DN replies with ICMP echo reply, and UPF-1 encapsulates the reply into N3 GTP-U and sends it back to gNB CU (`10.102.0.167:2152`).
- However, the UE on VM-5 experiences 100% packet loss.
- On VM-4 (`oai-ran`), `cu.log` logs:
  ```text
  [GTPU]   [81] Sent GTP Error Indication TEID-I 0x... to 127.0.0.1:2153
  [GTPU]   [81] Received a incoming packet on unknown TEID (0x...) Dropping!
  [GTPU]   [81] GTP Error Indication TEID-I 0x... GTP-U Peer Address 127.0.0.1 UDP-from 127.0.0.1
  [GTPU]   [81] GTP Error Indication TEID-I 0x...: no tunnel mapping, drop
  ```

### Cause
In `cu_gnb.conf`, `local_s_address` is set to `127.0.0.1` and `local_s_portd` is `2153`. Because `remote_s_portd` is also configured as `2153`, when CU prepares to send downlink F1-U packets to DU-1, it sends them to destination `127.0.0.1:2153`.  
Because CU itself is listening on `127.0.0.1:2153`, CU receives its own downlink packet on its F1-U listening socket. It attempts to treat the packet as an uplink packet from DU, fails to find an uplink tunnel mapping for the downlink TEID, and forcefully drops it. DU-1 never receives the packet.

### Solution
Use loopback aliases within the standard Linux `127.0.0.0/8` subnet to give CU and each DU distinct IP addresses on port `2153`:
- **CU (`cu_gnb.conf`):** `local_s_address = "127.0.0.3";`
- **DU-1 (`du_gnb1.conf`):** `local_n_address = "127.0.0.4"; remote_n_address = "127.0.0.3"; local_n_portd = 2153; remote_n_portd = 2153;`
- **DU-2 (`du_gnb2.conf`):** `local_n_address = "127.0.0.5"; remote_n_address = "127.0.0.3"; local_n_portd = 2153; remote_n_portd = 2153;`

Apply the fix on VM-4:
```bash
python3 - << 'EOF'
# 1. Update cu_gnb.conf
with open("/opt/oran/ran/conf/cu_gnb.conf", "r") as f:
    cu = f.read()
cu = cu.replace('local_s_address  = "127.0.0.1";', 'local_s_address  = "127.0.0.3";')
cu = cu.replace('local_s_address = "127.0.0.1";', 'local_s_address = "127.0.0.3";')
with open("/opt/oran/ran/conf/cu_gnb.conf", "w") as f:
    f.write(cu)

# 2. Update du_gnb1.conf
with open("/opt/oran/ran/conf/du_gnb1.conf", "r") as f:
    du1 = f.read()
du1 = du1.replace('local_n_address = "127.0.0.1";', 'local_n_address = "127.0.0.4";')
du1 = du1.replace('remote_n_address = "127.0.0.1";', 'remote_n_address = "127.0.0.3";')
du1 = du1.replace('local_n_portd   = 2155;', 'local_n_portd   = 2153;')
du1 = du1.replace('local_n_portd = 2155;', 'local_n_portd = 2153;')
with open("/opt/oran/ran/conf/du_gnb1.conf", "w") as f:
    f.write(du1)

# 3. Update du_gnb2.conf
with open("/opt/oran/ran/conf/du_gnb2.conf", "r") as f:
    du2 = f.read()
du2 = du2.replace('local_n_address = "127.0.0.1";', 'local_n_address = "127.0.0.5";')
du2 = du2.replace('remote_n_address = "127.0.0.1";', 'remote_n_address = "127.0.0.3";')
du2 = du2.replace('local_n_portd   = 2154;', 'local_n_portd   = 2153;')
du2 = du2.replace('local_n_portd = 2154;', 'local_n_portd = 2153;')
with open("/opt/oran/ran/conf/du_gnb2.conf", "w") as f:
    f.write(du2)

print("Loopback aliases configured successfully.")
EOF

sudo /opt/oran/ran/start_ran.sh
```

---

## 43. PDU Session Establishment Reject (5GSM Cause 0x21: Service Option Not Subscribed) for Slice 2

### Symptom
UE requests PDU session establishment for Slice 2 (`NSSAI: SST 222, SD 00007B`, DNN `lowlatency`), but the Core Network immediately returns `FGS_PDU_SESSION_ESTABLISHMENT_REJ`:
```text
[NAS] requested PDU session ID 10 type 1 NSSAI 222.123 DNN lowlatency
[NAS] Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
[NAS] Received NAS_DOWNLINK_DATA_IND type FGS_PDU_SESSION_ESTABLISHMENT_REJ with length 21
[NAS] Received PDU Session Establishment reject
```
In `oai-amf` logs:
```text
[amf_server] Received N1 SM: 2e 0a 01 c3 21 f1
```
Here `c3` corresponds to `PDU SESSION ESTABLISHMENT REJECT` and `21` corresponds to 3GPP 5GSM Cause `#33 (0x21)`: **Service option not subscribed**.

### Cause
In the 5GC database (`oai_db.SessionManagementSubscriptionData`), subscriber profiles for `singleNssai = '{"sd": "00007B", "sst": 222}'` were provisioned with `dnnConfigurations` containing only `"default"`. Because the DNN `"lowlatency"` was missing from the subscription data, `oai-smf-slice2` rejected the PDU session establishment request.

### Solution
1. Execute the following SQL statement in the MySQL container on VM-3 (`oai-core`) to append `lowlatency` configurations to `dnnConfigurations` for all subscribers:
   ```bash
   sudo docker exec -i mysql mysql -u root -plinux oai_db -e "
   UPDATE SessionManagementSubscriptionData 
   SET dnnConfigurations = JSON_SET(
     dnnConfigurations,
     '$.lowlatency', JSON_EXTRACT(dnnConfigurations, '$.default')
   );
   "
   ```
2. Verify that both `"default"` and `"lowlatency"` are present:
   ```bash
   sudo docker exec -i mysql mysql -u root -plinux oai_db -e \
     "SELECT ueid, singleNssai, JSON_KEYS(dnnConfigurations) FROM SessionManagementSubscriptionData WHERE ueid = '208950000000032';"
   ```
3. Restart `oai-smf-slice2` to reload subscription contexts:
   ```bash
   sudo docker restart oai-smf-slice2
   ```

---

## 44. Static NWDAF SliceLoadLevel (5.00%) During Core UPF Impairment / Fault Injection

### Symptom
When fault injection (`tc netem delay 50ms loss 5%`) is applied to `oai-upf-slice2` on VM-3, E2E URLLC latency at UE spikes from ~16 ms to >120 ms. However, querying Prometheus (`http://10.102.0.67:9100/metrics`) still displays `nwdaf_slice_load_level{snssai="de00007b"} 5.00` (unchanged default fallback).

### Cause
In the OpenAirInterface CN5G v2.0.0 software stack, the C-based UPF containers do not natively stream real-time Linux kernel `tc` queuing latency or packet drops to the `oai-nwdaf-sbi` microservice. Additionally, Kong API Gateway routes queries matching standard 3GPP endpoints, but without an active kernel exporter, NWDAF retains static or unpopulated load metrics.

### Solution
Deploy and run `/opt/oran/5gc/scripts/core_adapter.py` on VM-3 (`oai-core`):
1. The adapter inspects the physical `qdisc` and packet drops on `oai-upf-slice1` and `oai-upf-slice2` every 1 second.
2. When netem delay, queue backlog, or active packet drops are detected, it dynamically elevates `nwdaf_slice_load_level` to `88.5%` (above the 80% 3GPP TS 23.288 congestion threshold).
3. When `tc qdisc del dev eth0 root` is executed, the metric instantly drops back to `5.0%` (normal baseline).

---

## 45. Operation Not Permitted (`ERR_[Errno 1]`) or Buffered Logs in `core_adapter.py`

### Symptom
1. `core_adapter.log` displays `5.0% (ERR_[Errno 1] )`.
2. Or running `tail -f core_adapter.log` appears stuck and stops writing new log entries after several seconds.

### Cause
1. `ERR_[Errno 1]` occurs when `core_adapter.py` invokes `sudo docker exec` inside Python subprocesses while running as a regular user, and the system's `sudo` password credential cache expires after a few minutes.
2. Buffered logs occur because standard Python buffers stdout into 4KB blocks when redirected to a file (`> core_adapter.log`), or duplicate instances spawned in the background hold conflicting file descriptors.

### Solution
1. Add the host user to the Linux `docker` group so container commands do not require `sudo`:
   ```bash
   sudo usermod -aG docker $USER
   ```
2. In `/opt/oran/5gc/scripts/core_adapter.py`, invoke `["docker", "exec", ...]` directly without the `"sudo"` wrapper, and ensure `print(..., flush=True)` is used.
3. Terminate any duplicate background instances:
   ```bash
   sudo pkill -f core_adapter.py
   ```
4. Launch the daemon with unbuffered Python output (`-u` flag):
   ```bash
   sudo nohup python3 -u /opt/oran/5gc/scripts/core_adapter.py > /opt/oran/5gc/scripts/core_adapter.log 2>&1 &
   ```

---

## 46. Stale NRF Session & Cross-VM Split-RAN Desynchronization

### Symptom
1. In `oai-smf-slice1` logs:
   ```text
   [smf_sbi] Response data {"cause":"RESOURCE_URI_STRUCTURE_NOT_FOUND"}
   [smf_sbi] NF Instance Registration, response from NRF, HTTP Code: 404
   [smf_sbi] NF Update, could not get response from NRF
   ```
2. In `oai-amf` logs:
   ```text
   [amf_sbi] Cannot get response when calling
   [amf_app] [warning] NF Instance Registration, got issue when registering to NRF, try again ...
   ```
3. In `ue1.log` on VM-5:
   ```text
   [NAS] requested PDU session ID 10 type 1 NSSAI 1.1 DNN default
   [NAS] Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
   [NAS] Received NAS_DOWNLINK_DATA_IND type FGS_PDU_SESSION_ESTABLISHMENT_REJ with length 21
   [NAS] Received PDU Session Establishment reject
   ```
4. After restarting `oai-amf`, both UE 1 and UE 2 show `Tunnel IP: DOWN` and `Ping: FAIL`.
5. Running `ip a | grep tun` on the root host of VM-5 returns nothing.

### Cause
1. **NRF SBI Expiry:** When 5GC Network Functions (`oai-amf`, `oai-smf-slice1`) run continuously across days without a coordinated restart, internal HTTP/2 SBI client handles or NRF instance registration URIs expire. AMF cannot resolve SMF endpoints, immediately returning `FGS_PDU_SESSION_ESTABLISHMENT_REJ` to the UE.
2. **Split-RAN CU N2/F1-U Orphan:** When `oai-amf` restarts, the N2 SCTP socket to gNB-CU on VM-4 drops. OAI `nr-softmodem` CU does not automatically rebind its F1-C and GTP-U TEID mappings cleanly, preventing subsequent UE registrations from completing.
3. **Network Namespace Isolation:** VM-5 uses Linux Network Namespaces (`ue1` and `ue2`). Interfaces `oaitun_ue1` exist exclusively inside their respective namespaces, never appearing on the host's root network stack.

### Solution
Follow the strict 3-VM startup sequence to achieve complete end-to-end synchronization:
1. **VM-3 (`oai-core`):** Synchronously restart the core slicing services:
   ```bash
   sudo docker restart oai-nrf-slice12 oai-nssf oai-amf oai-smf-slice1 oai-smf-slice2 oai-upf-slice1 oai-upf-slice2
   ```
2. **VM-4 (`oai-ran`):** Restart the split CU and multi-DU processes to rebind N2 and F1:
   ```bash
   sudo /opt/oran/ran/stop_ran.sh
   sleep 2
   sudo /opt/oran/ran/start_ran.sh
   sleep 4
   grep -E "associated AMF|is in service" /opt/oran/ran/cu.log | tail -n 5
   ```
3. **VM-5 (`nrue`):** Spawn the isolated multi-UE instances and verify tunnel IPs inside each netns:
   ```bash
   sudo /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
   sudo ip netns exec ue1 ip addr show oaitun_ue1
   sudo ip netns exec ue2 ip addr show oaitun_ue1
   sudo /opt/oran/ue/scripts/trafgen.sh ping
   ```

---

## 47. OAI NWDAF SBI Subscription `connection refused` on Multi-Slice Core

### Symptom
In `oai-nwdaf-sbi` container logs on VM-3:
```text
Error when calling SubscriptionsCollectionCollectionApi.CreateSubscription: Post "http://192.168.70.138/namf-evts/v1/subscriptions": dial tcp 192.168.70.138:80: connect: connection refused
Error when calling SubscriptionsCollectionApi.CreateIndividualSubcription: Post "http://192.168.70.133/nsmf_event-exposure/v1/subscriptions": dial tcp 192.168.70.133:80: connect: connection refused
```
The NWDAF SBI consumer repeatedly fails to register event subscriptions with AMF and SMF, leaving MongoDB collections (`testing.amf`, `testing.smf`) empty.

### Cause
1. **Port Mismatch & Protocol Version:** The default `oai-nwdaf-sbi` environment variables point to `http://192.168.70.138` without port specification (defaulting to HTTP/1.1 port 80). In OAI CN5G, Service-Based Interfaces (SBI) listen on port **8080** and require **HTTP/2 (h2c / HTTP/2 prior knowledge)** as defined in 3GPP TS 29.500.
2. **Multi-Slice Endpoint Mismatch:** The default single-slice compose specifies `SMF_IP_ADDR=http://192.168.70.133`. In a multi-slice slicing architecture (`docker-compose-slicing-basic-nrf.yaml`), SMF is split into dedicated instances: `oai-smf-slice1` (`192.168.70.139`) and `oai-smf-slice2` (`192.168.70.140`). Connecting to `.133` hits an unassigned IP.

### Solution
1. In `/opt/oran/5gc/oai-cn5g-fed/docker-compose/docker-compose-slicing-basic-nrf.yaml`, update the `oai-nwdaf-sbi` environment variables:
   ```yaml
   oai-nwdaf-sbi:
       environment:
           - AMF_IP_ADDR=http://192.168.70.138:8080
           - AMF_HTTP_VERSION=2
           - SMF_IP_ADDR=http://192.168.70.139:8080
           - SMF_HTTP_VERSION=2
   ```
2. Recreate the SBI container:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai-nwdaf-sbi
   ```
3. Verify subscription handshake in logs:
   ```bash
   docker logs --tail 25 oai-nwdaf-sbi
   ```
   Confirm `HTTP/2.0 201 Created` with Location header (e.g. `192.168.70.138:8080/namf-evts/v1/namf-evts/1`).

---

## 48. OAI NWDAF Analytics `"missing Network Performance Data"` vs Hardcoded Relative Ratio

### Symptom
Querying the NWDAF NBI Analytics endpoint via Kong Gateway:
```bash
curl -i "http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=NETWORK_PERFORMANCE"
```
returns:
```text
HTTP/1.1 400 Bad Request
"missing Network Performance Data"
```
Even when standard 3GPP query parameters (`ana-req`, `event-filter`) are passed, the response returns all-zero values:
```json
{
  "anaMetaInfo": { ... },
  "nwPerfs": [{ "nwPerfType": "SESS_SUCC_RATIO", "relativeRatio": 0, "absoluteNum": 0, "confidence": 0 }]
}
```

### Cause
1. **Missing 3GPP Query Filters:** OAI NWDAF NBI Analytics requires mandatory query parameters: `ana-req` (time window) and `event-filter` (S-NSSAI and metric type). Without them, the Go handler aborts before querying the engine.
2. **Empty Event Database:** NWDAF subscribes with `immediateFlag: false`. It only records events that occur *after* subscription startup. When no new PDU sessions have established or released, MongoDB contains 0 matching documents, resulting in `absoluteNum: 0`.
3. **Hardcoded Zero in Source Code (`//TODO`):** Inspection of the official OAI NWDAF Engine source code (`components/oai-nwdaf-engine/internal/engine/network_performance.go:53, 102`) reveals:
   ```go
   //TODO - Implement relative ratio and confidence
   relativeRatio, confidence := int32(0), int32(0)
   ```
   The OAI developers hardcoded `relativeRatio` and `confidence` to `0`. OAI NWDAF v2.1.0 does not calculate dynamic load percentages or user-plane buffer ratios.
4. **Absence of UPF Queue / Drop Telemetry:** OAI UPF is a C-based user-plane process with no HTTP/2 SBI interface. OAI NWDAF does not consume UPF kernel `tc qdisc` queues.

### Solution
1. **For Control Plane Queries (3GPP TS 29.520):** Always supply standard URL-encoded parameters:
   ```bash
   curl -s -G "http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics" \
     --data-urlencode "event-id=NETWORK_PERFORMANCE" \
     --data-urlencode 'ana-req={"startTs":"2026-10-01T00:00:00Z","endTs":"2026-10-12T23:59:59Z"}' \
     --data-urlencode 'event-filter={"snssais":[{"sst":1,"sd":"000001"}],"dnns":["default"],"nwPerfTypes":["SESS_SUCC_RATIO"]}'
   ```
2. **For User Plane Bottleneck Telemetry:** Do not rely on NWDAF `relativeRatio` for core congestion diagnosis. Use the dedicated UPF research telemetry collector (`core_adapter.py` v9) which measures physical kernel queue backlogs (`upf_queue_backlog_bytes`), packet drops (`upf_packet_drops_delta`), and interface throughput (`upf_interface_tx_mbps`) with calibrated monotonic timing.

---

## 49. UE 2 PDU Session Establishment Rejected — MySQL S-NSSAI Subscriber Profile Mismatch

### Symptom

UE 2 (`IMSI: 208950000000002`, Slice 2 URLLC) spawned via `spawn_multi_ue.sh` fails PDU Session Establishment. In `ue2.log`:

```text
[NAS] requested PDU session ID 10 type 1 NSSAI 222.123 DNN lowlatency
[NAS] Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
[NAS] Received NAS_DOWNLINK_DATA_IND type FGS_PDU_SESSION_ESTABLISHMENT_REJ with length 21
[NAS] Received PDU Session Establishment reject
```

Meanwhile UE 1 (`IMSI: 208950000000001`, Slice 1 eMBB) connects successfully with `oaitun_ue1` UP and ping to DN (`192.168.70.145`) succeeding.

### Cause

The MySQL subscriber database (`oai_db`) had conflicting S-NSSAI provisioning for UE 2's IMSI in the `SessionManagementSubscriptionData` table. Specifically:

1. The `singleNssai` column pointed to an incorrect slice ({SST: 1, SD: "000001"} — Slice 1 eMBB) instead of UE 2's intended Slice 2 ({SST: 222, SD: "00007B" / `123` decimal}).
2. Because the subscriber's session management data did not reference the correct `defaultSingleNssais` or `dnn-configurations`, `oai-smf-slice2` could not find a matching DNN profile and rejected the session immediately with `FGS_PDU_SESSION_ESTABLISHMENT_REJ`.

### Solution

1. Connect to the `mysql` container on VM-3:
   ```bash
   sudo docker exec -it mysql mysql -u root -plinux oai_db
   ```

2. Verify the current (incorrect) subscription:
   ```sql
   SELECT * FROM SessionManagementSubscriptionData
   WHERE ueid = '208950000000002' AND sst = 222;
   ```

3. Correct the `singleNssai` JSON and `dnn-configurations` to align with Slice 2 (SST: 222, SD: "00007B"):
   ```sql
   UPDATE SessionManagementSubscriptionData
   SET singleNssai = '{"sst":222,"sd":"00007B"}'
   WHERE ueid = '208950000000002' AND sst = 222;
   ```

4. Restart the affected core services to flush stale AMF/SMF state and allow re-registration:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml restart oai-amf oai-smf-slice1 oai-smf-slice2 oai-nwdaf-sbi
   ```

5. Re-run the UE spawner and verify UE 2 obtains `oaitun_ue1` inside namespace `ue2`:
   ```bash
   sudo ip netns exec ue2 ip -4 addr show oaitun_ue1
   ```

---

## 50. SMF N4/PFCP 1-Second Timeout After Manual `upfs:` Configuration Edit

### Symptom

After adding a manual `upfs:` block to SMF YAML config files (in an attempt to configure UPF parameters such as usage reporting), SMF logs showed repeated 1-second PFCP timeouts:

```text
[smf_n4] PFCP Association Response from 192.168.70.142 (oai-upf-slice1) FAILED
[smf_n4] TIME-OUT event timer id 1704
[smf_n4] Retry PFCP heartbeat request failed, UPF unreachable
```

Both `oai-smf-slice1` and `oai-smf-slice2` cycled in a permanent retry loop and failed to establish working N4 associations with their respective UPFs, causing all PDU Session Establishment attempts from UE 1 and UE 2 to fail.

### Cause

The manual `upfs:` entries added to `slicing_slice1_config.yaml` and `slicing_slice2_config.yaml` introduced configuration mismatches with the NRF-discovered UPF profiles. 

In OAI SMF ([`smf_app.cpp`](https://github.com/openairinterface/oai-cn5g-smf/blob/531b6d8755ee792e49122c57bbab047db88ec4b5/src/smf_app/smf_app.cpp) and [official SMF `config.yaml`](https://github.com/openairinterface/oai-cn5g-smf/blob/531b6d8755ee792e49122c57bbab047db88ec4b5/etc/config.yaml)), the `upfs:` block is designed to configure local parameters (such as `enable_usage_reporting`) even when dynamic UPF discovery via NRF is enabled, matching local entries against NRF profiles by host identifier. However, if the local declaration's host/IP/FQDN parameters do not resolve or match the NRF profile expected by the SMF state machine during startup, the PFCP Association Setup handshake times out after 1000ms (`TIME-OUT event timer id 1704`), leaving the UPF marked unreachable.

### Solution

1. **Root Cause Resolution (Permanent Configuration):**
   To configure UPF parameters such as `enable_usage_reporting: yes` alongside NRF dynamic discovery, the `host` parameter must match the exact host string registered in NRF (`192.168.70.142` for Slice 1 UPF) placed under `smf.upfs`:
   ```yaml
   smf:
     support_features:
       use_local_subscription_info: yes
       use_local_pcc_rules: yes
     upfs:
       - host: 192.168.70.142
         config:
           enable_usage_reporting: yes
   ```
   Apply via force-recreate of the service (`oai_smf_slice1`):
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai_smf_slice1
   ```
   Verify successful matching and activation in logs without PFCP timeout:
   ```bash
   sudo docker logs --tail 35 oai-smf-slice1 | grep -i -E "NRF UPF|take config|enable_usage_reporting"
   # Expected:
   # Found NRF UPF with host name 192.168.70.142 in configuration, take config from there
   # enable_usage_reporting.................: Yes
   ```

2. **Rollback Procedure (Emergency Recovery):**
   If an invalid host string or conflicting interface block causes PFCP association failure, restore the clean upstream configuration from `.bak`:
   ```bash
   cp /opt/oran/5gc/oai-cn5g-fed/docker-compose/conf/slicing_slice1_config.yaml.bak \
      /opt/oran/5gc/oai-cn5g-fed/docker-compose/conf/slicing_slice1_config.yaml

   cp /opt/oran/5gc/oai-cn5g-fed/docker-compose/conf/slicing_slice2_config.yaml.bak \
      /opt/oran/5gc/oai-cn5g-fed/docker-compose/conf/slicing_slice2_config.yaml

   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai_smf_slice1 oai_smf_slice2
   ```

3. Verify end-to-end connectivity after PDU session re-establishment:
   ```bash
   sudo ip netns exec ue1 ping -c 5 192.168.70.145
   ```

> **Key Lesson:** The upstream OAI SMF `upfs:` block can be used alongside NRF discovery to configure advanced features like `enable_usage_reporting: yes`, provided that its `host` parameter matches the NRF-registered UPF profile string exactly (`192.168.70.142` instead of container names like `oai-upf-slice1`). Additionally, note that docker compose service names use underscores (`oai_smf_slice1`), distinct from container names (`oai-smf-slice1`).

---

## 51. OAI AMF Automated NRF Registration Failure (Missing `/{nfInstanceId}` in Dynamic Resource URI)

### Symptom
When `oai-amf` starts in slicing mode (`enable_nssf: yes`), it successfully queries NSSF and receives `nrfNfMgtUri` (e.g., `http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances`).  
However, AMF repeatedly logs registration failures after a 3000 ms timeout:
```text
[amf_sbi] [debug] Send NF Instance Registration to NRF, NRF URI (RegisterNFInstance API) http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances
[amf_sbi] [info] Send HTTP message to http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances
[amf_app] [warning] NF Instance Registration, got issue when registering to NRF, try again ...
```
Because AMF remains unregistered in NRF, it cannot be resolved for N11 PDU Session Handling, causing UE PDU session establishment (`requested PDU session ID 10`) to stall and preventing the creation of `oaitun_ue1`.

### Cause
1. **Standards Specification Violation in Upstream AMF Binary:**
   - Under **3GPP TS 29.510 §6.1.3.3.2**, the resource URI for an Individual NF Instance is:
     $$\texttt{http://<nrf>:<port>/nnrf-nfm/v1/nf-instances/\{nfInstanceId\}}$$
   - Under **3GPP TS 29.510 §6.1.3.3.3.2**, registration (`NFRegister`) strictly requires an HTTP `PUT` targeting this instance resource URI.
   - In OAI AMF v2.1.0 (`HEAD` hash `58f77cfb`), `amf_app.cpp` directly passes the `nrfNfMgtUri` string obtained from NSSF without dynamically appending the runtime UUID `/{nfInstanceId}`. The resulting HTTP `PUT` to `.../nf-instances` is invalid.
2. **Hash-Based NRF Iteration:**
   - Slices are stored internally in `std::unordered_set<std::string>`, resulting in non-deterministic iteration order when registering across multiple slice NRFs (e.g., Slice 3 `.137` followed by Slice 1-2 `.136`).

### Empirical Verification
Executing a manual HTTP/2 prior-knowledge `PUT` from VM-3 host with the complete instance URI:
```bash
UUID="9509d2b9-9049-4dc7-9243-a38c3b605c2f"
curl -v --http2-prior-knowledge -X PUT \
  -H "Content-Type: application/json" \
  -d '{"nfInstanceId":"'"$UUID"'", "nfType":"AMF", ...}' \
  "http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances/$UUID"
```
Returns **`HTTP/2 201 Created`** and `oai-nrf-slice12` logs:
```text
[nrf_app] [info] Added/Updated NF Instance, NF info: {"amfInfo": ..., "nfStatus": "REGISTERED", ...}
```
This confirms that NRF functions correctly and strictly adheres to 3GPP TS 29.510, accepting the AMF registration when the resource URI is well-formed.

### Solution

1. **Patch Upstream AMF Source Code (`amf_app.cpp`):**
   In `component/oai-amf/src/amf-app/amf_app.cpp` around line 1614 (inside `get_nrfs`), update the NSSF response parsing logic to dynamically append `"/" + amf_instance_id` to `nrfNfMgtUri`:
   ```cpp
   // Before:
   nrfs.insert(nsi_information.getNrfNfMgtUri());

   // After (Patched):
   nrfs.insert(nsi_information.getNrfNfMgtUri() + "/" + amf_instance_id);
   ```

2. **Rebuild Custom AMF Image (`oai-amf:thesis-nrf-uri-v1`):**
   - Ensure the build environment has sufficient RAM ($\ge 8$ GB or restrict parallel jobs with `MAKEFLAGS="-j2"` / `CMAKE_BUILD_PARALLEL_LEVEL=2`).
   - Add `libsystemd-dev` to Stage 1 dependencies in `docker/Dockerfile.amf.ubuntu` to prevent version locking conflicts with `libsystemd0`.
   - Add APT retry configuration (`Acquire::Retries "3";`) to handle transient DNS/network fluctuations.
   - Build using host network:
     ```bash
     cd /opt/oran/5gc/oai-cn5g-fed/component/oai-amf
     sudo docker build \
       --network=host \
       --progress=plain \
       --target oai-amf \
       -f docker/Dockerfile.amf.ubuntu \
       -t oai-amf:thesis-nrf-uri-v1 .
     ```

3. **Deploy Patched Image in Docker Compose:**
   In `/opt/oran/5gc/oai-cn5g-fed/docker-compose/docker-compose-slicing-basic-nrf.yaml`, update the `oai_amf` service definition:
   ```yaml
   oai_amf:
     container_name: "oai-amf"
     image: oai-amf:thesis-nrf-uri-v1
   ```
   Recreate the container:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai_amf
   ```

4. **Verification & Live Empirical Evidence:**
   Inspecting live AMF logs confirms that the dynamic UUID (`10846c59-0419-4e6b-ab0b-9e3a08780faa`) is successfully resolved from NSSF and appended to the registration resource URIs, receiving **`HTTP 201 Created`** from both slice NRFs:
   ```text
   [amf_sbi] [info] Get response with HTTP code (200)
   {"nsiInformation":{"nrfId":"http://192.168.70.136:8080/nnrf-disc/v1/nf-instances","nrfNfMgtUri":"http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances","nsiId":"11"}}
   [amf_sbi] [debug] Send NF Instance Registration to NRF, NRF URI (RegisterNFInstance API) http://192.168.70.137:8080/nnrf-nfm/v1/nf-instances/10846c59-0419-4e6b-ab0b-9e3a08780faa
   [amf_sbi] [info] Get response with HTTP code (201)
   [amf_sbi] [debug] NFRegistration, got successful response from NRF
   [amf_sbi] [debug] Send NF Instance Registration to NRF, NRF URI (RegisterNFInstance API) http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances/10846c59-0419-4e6b-ab0b-9e3a08780faa
   [amf_sbi] [info] Get response with HTTP code (201)
   [amf_sbi] [debug] NFRegistration, got successful response from NRF
   ```
   Furthermore, periodic heartbeats execute every 10 seconds targeting both NRF instances, consistently receiving **`HTTP 204 No Content`**:
   ```text
   [amf_sbi] [debug] Send NF Update to NRF, NRF URI http://192.168.70.136:8080/nnrf-nfm/v1/nf-instances/25315646-1c7b-4c23-959d-de175526acb9
   [amf_sbi] [info] Get response with HTTP code (204)
   ```
   This confirms 100% compliance with 3GPP TS 29.510 §6.1.3.3.2 and restores full automated AMF lifecycle management.

---

## 52. OAI UPF N4/PFCP Session Establishment Silent Drop (Unsupported 3GPP TS 29.244 IE Type 62 `Measurement Method`)

### Symptom

During 5G PDU Session Establishment from UE 1 (`nr-uesoftmodem` on VM-5), AMF successfully creates the SM context in SMF-1 (`oai-smf-slice1`), but the session establishment procedure stalls permanently. UE 1 fails to configure `oaitun_ue1`, and gNB CU (`cu.log` on VM-4) never receives a `PDUSessionResourceSetupRequest`.

SMF-1 logs report repeating 1-second PFCP request timeouts followed by retransmission timeouts:
```text
[smf_app] [info] Sending ITTI message 37itti_n4_session_establishment_request to task TASK_SMF_N4
[smf_n4 ] [info] TIME-OUT event timer id 897
[smf_n4 ] [info] TIME-OUT event timer id 898
```
Simultaneously, PFCP Heartbeat exchanges between SMF-1 and UPF-1 (`192.168.70.142`) execute every 10 seconds without any errors, confirming bidirectional socket connectivity on UDP port 8805.

### Root Cause

1. **Unsupported Information Element in `openair-upf` Binary:**
   - Under **3GPP TS 29.244 §8.2.40**, Information Element (IE) Type **62** (1 octet) defines the **`Measurement Method`**. This IE is a mandatory sub-element inside the **`Create URR` (Usage Reporting Rule)** IE used by the SMF to configure data volume and duration measurements.
   - When `enable_usage_reporting: yes` is configured under `smf.upfs` in SMF configuration files (e.g., `conf/slicing_slice1_config.yaml`), SMF-1 automatically constructs a `Create URR` containing IE Type 62 within the `PFCP Session Establishment Request` payload (241 bytes).
   - In `oaisoftwarealliance/oai-upf:v2.1.0` (`openair-upf`), the internal PFCP TLV parser lacks implementation support for IE Type 62:
     ```text
     [upf_n4 ] [info] handle_receive(241 bytes)
     [pfcp   ] [error] Unknown PFCP IE type 62 (length 1)
     [upf_n4 ] [info] handle_receive exception PFCP IE TLV 6 Bad Length 48 Exception /openair-upf/src/pfcp/3gpp_29.244.hpp:219
     ```
2. **Silent Packet Drop:**
   - When the C++ exception is thrown in `3gpp_29.244.hpp:219`, `openair-upf` aborts packet processing immediately. It drops the request without transmitting any error response (such as a `PFCP Session Establishment Response` with Cause `Rule creation/modification failure`).
   - Consequently, SMF-1 remains waiting for an acknowledgement until its internal 1-second timeout expires (`timer id 897`), triggering retransmission and eventual session abandonment.

### Empirical Verification

1. **Packet Capture (`tcpdump` on VM-3 bridge `any`):**
   ```text
   09:21:30.362960 veth02a45b9 P IP 192.168.70.139.8805 > 192.168.70.142.8805: UDP, length 241
   09:21:30.362964 veth4cace10 Out IP 192.168.70.139.8805 > 192.168.70.142.8805: UDP, length 241
   ```
   The 241-byte UDP packet egressed SMF-1's veth interface (`veth02a45b9`) and entered UPF-1's veth interface (`veth4cace10`). Zero reply packets were emitted by `192.168.70.142`, while preceding (`09:21:28`) and succeeding (`09:21:38`) 16-byte PFCP heartbeat requests were answered by UPF-1 within 0.18 ms.

2. **Historical Log Correlation:**
   Examining `oai-upf-slice1` historical logs confirmed that prior to enabling usage reporting (`2026-10-14 12:25:35`), UPF-1 processed baseline N4 session requests without exception:
   ```text
   [2026-10-14 12:25:35.870] [upf_app] [info] Received N4_SESSION_ESTABLISHMENT_REQUEST seid 0x2
   [2026-10-14 12:25:35.872] [upf_n4 ] [info] pfcp_session::add(far) seid 0x2
   [2026-10-14 12:25:35.872] [upf_n4 ] [info] pfcp_session::add(pdr) seid 0x2
   ```
   Every session attempt following `enable_usage_reporting: yes` triggered `Unknown PFCP IE type 62 (length 1)`.

### Solution

1. **Disable `enable_usage_reporting` in SMF Configuration:**
   Restore `conf/slicing_slice1_config.yaml` to the baseline configuration (or omit the manual `upfs:` block with `enable_usage_reporting: yes`):
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   cp conf/slicing_slice1_config.yaml.bak conf/slicing_slice1_config.yaml
   ```

2. **Restart SMF-1 and UPF-1 Containers:**
   ```bash
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml -f compose.amf-nrf-uri.yaml restart oai_smf_slice1 oai_upf_slice1
   ```

3. **Verification & End-to-End User Plane Activation:**
   Re-spawning UE 1 on VM-5 (`nrue`):
   ```bash
   sudo /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 0
   ```
   Confirms immediate tunnel activation and end-to-end routing to External DN (`192.168.70.145`):
   ```text
   PING 192.168.70.145 (192.168.70.145) from 12.1.1.2 oaitun_ue1: 56(84) bytes of data.
   64 bytes from 192.168.70.145: icmp_seq=1 ttl=63 time=16.1 ms
   64 bytes from 192.168.70.145: icmp_seq=2 ttl=63 time=30.2 ms
   64 bytes from 192.168.70.145: icmp_seq=3 ttl=63 time=22.7 ms
   64 bytes from 192.168.70.145: icmp_seq=4 ttl=63 time=23.5 ms
   64 bytes from 192.168.70.145: icmp_seq=5 ttl=63 time=19.6 ms

   --- 192.168.70.145 ping statistics ---
   5 packets transmitted, 5 received, 0% packet loss, time 4003ms
   rtt min/avg/max/mdev = 16.144/22.407/30.171/4.663 ms
   ```

### Architectural & Thesis Implications

This empirical discovery proves that native 3GPP User-Plane Usage Reporting (URR) via N4/PFCP to SMF and NWDAF is strictly bounded by the `openair-upf:v2.1.0` binary implementation (missing IE Type 62).  
This conclusively justifies the architectural design of the thesis platform, which leverages the dedicated **Core Telemetry Adapter (`core_adapter.py`)** to directly sample kernel socket statistics and interface `tc qdisc` queue telemetry on VM-3 for end-to-end multi-slice observability.

---

## Related Documentation

- [VM-1 — Non-RT RIC](vm/vm1-nonrt-ric.md)
- [VM-2 — Near-RT RIC](vm/vm2-nearrt-ric.md)
- [VM-3 — OAI 5GC](vm/vm3-oai-5gc.md)
- [VM-4 — OAI RAN](vm/vm4-oai-ran.md)
- [VM-5 — OAI nrUE](vm/vm5-nrue.md)
- [VM-6 — Monitoring & TSDB](vm/vm6-monitoring.md)
- [A1 Integration Guide](integration/a1-integration.md)
- [E2 Integration Guide](integration/e2-integration.md)
- [System Architecture](architecture.md)
- [System Technical Snapshot](thesis-system-technical-snapshot.md)
- [Regulatory Bottleneck Taxonomy](bottleneck-list-regulator.md)
- [Bottleneck Methodology](bottleneck-methodology.md)

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
