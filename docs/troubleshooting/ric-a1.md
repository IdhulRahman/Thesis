# Near-RT & Non-RT RIC (A1 / RMR / xApp) Troubleshooting

This document contains validated diagnostic procedures, root-cause analyses, and resolutions for issues in the **ric-a1** domain.

---

## Case 02 — Docker Permission Denied

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

## Case 03 — PMS RIC State Is `UNAVAILABLE`

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

## Case 04 — `JSONObject["policySchema"] not found`

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

[A1 Integration](../integration/a1-integration.md)

---

## Case 05 — PMS Database Write Errors

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

## Case 06 — Host Shows Unexpected Owner Name for UID 999

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

---

## Case 07 — `docker compose` Cannot Find the Project

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

## Case 09 — A1 Mediator Health Returns `500`

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

## Case 10 — Legacy `/a1-p/...` Endpoints Return `404`

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

## Case 11 — Compatibility Shim Does Not Reach A1 Mediator

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

---

## Case 12 — xApp Does Not Receive A1 Policy

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

## Case 13 — xApp Fails to Parse `payload`

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

<a id="case-14"></a>
## Case 14 — xApp Receives CREATE but A1 Does Not Become `ENFORCED`

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

## Case 15 — No `20010` / `20011` Lines in A1 Logs

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

## Case 16 — xApp Registration Warning

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

## Case 17 — xApp Shutdown Attempts Kubernetes AppMgr Hostname

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

---

## Case 18 — Direct A1 Policy Is Unexpectedly Deleted

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

## Case 19 — Direct A1 PUT Returns `202 Accepted`

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

## Case 20 — PMS Policy Creation Response

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

---

## Case 21 — SDNC Does Not Solve the Schema Mismatch

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

---

## Case 22 — VM-1 Quick Checks

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

## Case 23 — VM-2 Quick Checks

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

---

## Case 24 — VM-1

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

## Case 25 — VM-2

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

## Case 26 — Known-Good End-to-End Result

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

---
