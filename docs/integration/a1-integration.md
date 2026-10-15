# A1 Integration — Non-RT RIC to Near-RT RIC

This document describes the validated **A1 integration path between VM-1 and VM-2**.

The goal of this integration is to allow the Non-RT RIC side to create and update A1 policies through the A1 Policy Management Service (A1 PMS), deliver those policies to the Near-RT RIC A1 Mediator, and finally forward them to the xApp through RMR.

The validated end-to-end path is:

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
Traffic-Steering xApp :4560
   │
   │ RMR RTS 20011
   ▼
A1 Mediator
```

The current baseline policy type is:

```text
Policy Type ID: 20008
```

with the example policy:

```json
{
  "threshold": 5
}
```

---

## 1. Components

| Component | VM | Address / Interface |
|---|---|---|
| A1 Policy Management Service | VM-1 | `10.102.0.168:8081` |
| A1 Compatibility Shim | VM-2 | `10.102.0.66:10001` |
| A1 Mediator | VM-2 | `10.102.0.66:10000` |
| Python xApp Runtime | VM-2 | RMR `4560` |
| DBaaS | VM-2 | Docker network `10.0.2.12:6379` |

Validated software versions:

| Component | Version |
|---|---|
| A1 PMS | `2.6.0` |
| A1 Mediator | `3.2.2` |
| Minimal Near-RT RIC | `i-release` |
| Python xApp Framework | `i-release` image |
| Baseline policy type | `20008` |

---

## 2. Why a Compatibility Shim Is Required

The initial direct integration was:

```text
A1 PMS
   │
   ▼
A1 Mediator /A1-P/v2
```

Network connectivity was correct and the A1 Mediator returned:

```text
200 OK
```

for:

```text
/A1-P/v2/healthcheck
/A1-P/v2/policytypes/
/A1-P/v2/policytypes/20008
```

However, A1 PMS marked the Near-RT RIC as:

```text
UNAVAILABLE
```

The PMS logs showed:

```text
Unexpected response for policy type ...
JSONObject["policySchema"] not found.
Synchronization failure for ric: near-rt-ric-1
```

The A1 Mediator returned the policy type using:

```json
{
  "create_schema": {
    "...": "..."
  }
}
```

while the PMS `StdA1ClientVersion2` expected:

```text
policySchema
```

The policy type itself was valid and reachable. The problem was therefore not transport connectivity, but a mismatch between the client/parser selected by PMS and the payload representation returned by the A1 Mediator.

The validated solution is:

```text
A1 PMS
   │
   │ OscA1Client
   ▼
/a1-p/...
   │
   ▼
A1 Compatibility Shim
   │
   │ path translation only
   ▼
/A1-P/v2/...
   │
   ▼
A1 Mediator
```

The shim does **not** modify the JSON policy payload. It only maps the OSC-style URI path expected by `OscA1Client` to the URI exposed by the A1 Mediator image.

> The compatibility shim is an implementation workaround for component interoperability. It is not part of the proposed research mechanism and should not be presented as an O-RAN standard component.

---

## 3. A1 Compatibility Shim

The shim runs on VM-2 using NGINX.

Create:

```bash
mkdir -p /opt/oran/nearrt/a1-compat
nano /opt/oran/nearrt/a1-compat/nginx.conf
```

Configuration:

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
curl -i \
  http://127.0.0.1:10001/a1-p/healthcheck
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

Check the policy type:

```bash
curl -s \
  http://127.0.0.1:10001/a1-p/policytypes/20008 \
  | jq
```

Expected content includes:

```json
{
  "name": "tsapolicy",
  "policy_type_id": 20008,
  "create_schema": {
    "type": "object"
  }
}
```

---

## 4. Configure A1 PMS to Use `OscA1Client`

On VM-1, use:

```text
/opt/oran/nonrt/a1pms/application_configuration.json
```

Validated configuration:

```json
{
  "config": {
    "ric": [
      {
        "name": "near-rt-ric-1",
        "baseUrl": "http://10.102.0.66:10001",
        "customAdapterClass": "org.onap.ccsdk.oran.a1policymanagementservice.clients.OscA1Client",
        "managedElementIds": [
          "oai-cu-cp",
          "oai-du-1",
          "oai-du-2"
        ]
      }
    ]
  }
}
```

Validate:

```bash
jq . \
  /opt/oran/nonrt/a1pms/application_configuration.json
```

The important configuration is:

```text
baseUrl            = http://10.102.0.66:10001
customAdapterClass = ...OscA1Client
```

Do not use the direct A1 Mediator URL in the validated configuration:

```text
http://10.102.0.66:10000/
```

because that caused PMS to select the incompatible parser path during synchronization.

---

## 5. Validate PMS Synchronization

Check PMS:

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/status \
  | jq
```

Validated response:

```json
{
  "status": "hunky dory"
}
```

Check RIC state:

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/rics \
  | jq
```

Expected:

```json
{
  "rics": [
    {
      "ric_id": "near-rt-ric-1",
      "managed_element_ids": [
        "oai-cu-cp",
        "oai-du-1",
        "oai-du-2"
      ],
      "policytype_ids": [
        "20008"
      ],
      "state": "AVAILABLE"
    }
  ]
}
```

Acceptance condition:

```text
state          = AVAILABLE
policytype_ids = ["20008"]
```

---

## 6. Policy Type 20008

The baseline policy type is registered on the A1 Mediator.

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

Register:

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

## 7. A1 Mediator RMR Configuration

The A1 Mediator forwards policy changes to the xApp using RMR.

The validated route file is:

```text
/opt/oran/nearrt/a1/ric-plt-a1/local.rt
```

Content:

```text
newrt | start
rte | 20010 | python_xapp_runner:4560
newrt | end
```

Start A1 Mediator with:

```text
RMR_SEED_RT=/opt/route/local.rt
RMR_RTG_SVC=-1
RMR_SRC_ID=ric_a1mediator
RMR_LOG_VLEVEL=0
```

The validated container command is:

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

Verify:

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

---

## 8. A1 RMR Message Types

The current integration uses:

| RMR Message Type | Direction | Purpose |
|---|---|---|
| `20010` | A1 Mediator → xApp | Policy CREATE / UPDATE / DELETE |
| `20011` | xApp → A1 Mediator | Policy response / acknowledgement |
| `20012` | xApp → A1 Mediator | Policy query / resend request |

The current smoke-test xApp uses **return-to-sender (RTS)** for `20011`.

Therefore, the validated CREATE response does not require an explicit normal route for `20011` in the xApp route table.

---

## 9. A1-Aware xApp

The smoke-test xApp runs inside:

```text
python_xapp_runner
```

and listens on:

```text
RMR port 4560
```

The script is:

```text
/opt/oran/nearrt/oran-sc-ric/xApps/python/a1_policy_xapp.py
```

Its responsibilities are:

```text
receive RMR 20010
        │
        ▼
parse A1 message
        │
        ▼
read policy_type_id
        │
        ▼
read threshold
        │
        ▼
send RMR 20011
```

A received CREATE message looks like:

```json
{
  "operation": "CREATE",
  "payload": "{\"threshold\":5}",
  "policy_instance_id": "ts-pms-001",
  "policy_type_id": "20008"
}
```

Important:

```text
payload
```

is a JSON string, not an already-decoded JSON object.

The xApp therefore performs a second JSON decode before reading:

```text
threshold
```

For DELETE, the A1 Mediator may send:

```json
{
  "operation": "DELETE",
  "payload": ""
}
```

The empty payload is handled as an empty object.

---

## 10. xApp Response

For a successful CREATE, the xApp sends:

```json
{
  "policy_type_id": 20008,
  "policy_instance_id": "ts-pms-001",
  "handler_id": "qos-ts-xapp",
  "status": "OK"
}
```

using:

```text
RMR message type 20011
```

and return-to-sender.

Validated xApp output:

```text
[A1-XAPP] CREATE: type=20008 instance=ts-test-002 threshold=5
[A1-XAPP] Sent RMR 20011: ...
```

---

## 11. Direct A1 Smoke Test

Before testing through PMS, the A1 southbound path was validated directly.

Create:

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

The xApp receives:

```text
CREATE
```

and sends:

```text
RMR 20011
status = OK
```

Check enforcement:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-test-002/status \
  | jq
```

Validated response:

```json
{
  "enforceStatus": "ENFORCED"
}
```

Check policy:

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

This validates:

```text
A1 Mediator
      │
      │ RMR 20010
      ▼
xApp
      │
      │ RMR 20011
      ▼
A1 Mediator
      │
      ▼
ENFORCED
```

---

## 12. End-to-End Test through A1 PMS

The final validation uses A1 PMS rather than creating the policy directly on the A1 Mediator.

First inspect the live PMS OpenAPI schema:

```bash
curl -s \
  http://127.0.0.1:8081/v3/api-docs \
  | jq '.components.schemas.policy_info_v2'
```

Required fields in the validated PMS version:

```text
policy_data
policy_id
policytype_id
ric_id
```

Create the policy on VM-1:

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
HTTP/1.1 201 Created
```

The xApp on VM-2 should receive:

```text
operation          = CREATE
policy_instance_id = ts-pms-001
policy_type_id     = 20008
threshold          = 5
```

and send:

```text
RMR 20011
status = OK
```

---

## 13. Query the Policy through PMS

On VM-1:

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/policies/ts-pms-001 \
  | jq
```

Expected content includes:

```json
{
  "policy_id": "ts-pms-001",
  "policytype_id": "20008",
  "ric_id": "near-rt-ric-1",
  "policy_data": {
    "threshold": 5
  }
}
```

---

## 14. Query the Policy at the A1 Mediator

On VM-2:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ \
  | jq
```

The policy list should include:

```text
ts-pms-001
```

Check policy data:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-pms-001 \
  | jq
```

Expected:

```json
{
  "threshold": 5
}
```

Check status:

```bash
curl -s \
  http://127.0.0.1:10000/A1-P/v2/policytypes/20008/policies/ts-pms-001/status \
  | jq
```

Expected on the validated image:

```json
{
  "enforceStatus": "ENFORCED"
}
```

---

## 15. Validated End-to-End Result

The following path has been validated:

```text
A1 PMS
   │
   │ HTTP
   ▼
A1 Compatibility Shim
   │
   │ HTTP
   ▼
A1 Mediator
   │
   │ RMR 20010
   ▼
A1-aware xApp
   │
   │ RMR RTS 20011
   ▼
A1 Mediator
   │
   ▼
ENFORCED
```

Acceptance criteria:

```text
[✓] PMS status healthy
[✓] RIC state AVAILABLE
[✓] Policy type 20008 synchronized
[✓] Policy created through PMS
[✓] A1 Mediator receives the policy
[✓] xApp receives RMR 20010
[✓] xApp parses threshold=5
[✓] xApp sends RMR 20011
[✓] A1 Mediator reports ENFORCED
```

---

## 16. SDNC A1 Controller Test

An SDNC A1 Controller was tested during troubleshooting.

The following path worked:

```text
SDNC A1 Controller
       │
       ▼
A1 Mediator
```

A `getA1PolicyType` request returned:

```text
http-status = 200
```

and the policy type body.

However, the controller forwarded the policy type body without converting:

```text
create_schema
```

to:

```text
policySchema
```

Therefore it did not solve the PMS parser mismatch.

The controller and its MariaDB container were removed from the final runtime:

```bash
docker compose down
```

Final runtime architecture therefore does not require:

```text
a1controller
sdncdb
```

---

## 17. Troubleshooting Summary

### PMS state changes to `UNAVAILABLE`

Check:

```bash
docker logs --since=5m policy-agent-container 2>&1 \
  | grep -Ei 'error|warn|policySchema|sync'
```

If the log contains:

```text
JSONObject["policySchema"] not found
```

verify that the PMS configuration uses:

```text
customAdapterClass = ...OscA1Client
baseUrl            = http://10.102.0.66:10001
```

---

### Policy type visible at A1 Mediator but not PMS

Verify the compatibility endpoint:

```bash
curl -s \
  http://10.102.0.66:10001/a1-p/policytypes \
  | jq
```

Expected:

```json
[
  20008
]
```

Then wait for the PMS synchronization cycle:

```bash
sleep 60
```

and recheck:

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/rics \
  | jq
```

---

### A1 Mediator health returns `500`

Check DBaaS:

```bash
docker compose \
  -f /opt/oran/nearrt/oran-sc-ric/docker-compose.yml \
  exec dbaas redis-cli ping
```

Expected:

```text
PONG
```

Verify:

```text
DBAAS_SERVICE_HOST=10.0.2.12
DBAAS_SERVICE_PORT=6379
DBAAS_NODE_COUNT=1
```

---

### xApp does not receive policy

Verify the A1 RMR route:

```bash
docker exec ric_a1mediator \
  cat /opt/route/local.rt
```

Expected:

```text
rte | 20010 | python_xapp_runner:4560
```

Verify DNS:

```bash
docker exec ric_a1mediator \
  getent hosts python_xapp_runner
```

Expected:

```text
10.0.2.20
```

Verify xApp is running:

```text
[A1-XAPP] Listening for A1 RMR mtype 20010 on port 4560
```

---

### xApp fails with:

```text
'str' object has no attribute 'get'
```

The A1 Mediator sends policy data as:

```json
"payload": "{\"threshold\":5}"
```

Decode the nested JSON string before reading the policy fields.

---

### xApp registration warning

Current smoke-test runtime may show:

```text
Cannot Read config file for xapp Registration
```

This does not prevent the validated RMR smoke test.

Final xApp onboarding and AppMgr registration should be completed separately before the research implementation is frozen.

---

## 18. Configuration Files

Recommended repository files:

```text
configs/
├── vm1/
│   └── application_configuration.json
│
└── vm2/
    ├── local.rt
    ├── nginx.conf
    ├── policy-type-20008.json
    └── a1_policy_xapp.py
```

The deployment documentation should refer to these files instead of duplicating large configuration blocks once the repository is finalized.

---

## 19. Research Role of A1

In the final research framework, A1 is used to coordinate the two control timescales:

```text
Long-timescale rApp
        │
        │ adaptive QoS policy
        ▼
       A1
        │
        ▼
Near-real-time xApp
        │
        │ policy-constrained steering
        ▼
       E2
```

The baseline policy type `20008` is used only as the initial traffic-steering baseline.

The final proposed mechanism will replace the simple static threshold semantics with research-specific adaptive QoS policy content while preserving the same high-level A1 coordination role.

---

## 14. A1 Policy Schema Evolution for Bottleneck-Aware Steering

To support empirical evaluation across the baselines without breaking backward compatibility with the existing O-RAN SC A1 Mediator setup, Policy Type `20008` is structured to support both simple and bottleneck-aware payloads.

### 14.1 Baseline vs. Proposed Payload Comparison

#### Baseline Modes (B1 & B4) Payload
Uses the minimal integer threshold schema:
```json
{
  "threshold": 80
}
```

#### Proposed System (Bottleneck-Aware) Payload
Extends the schema with domain diagnosis metadata:
```json
{
  "threshold": 80,
  "bottleneck_location": "RAN",
  "target_cell_preference": 2,
  "handover_allowed": true,
  "slice_id": {
    "sst": 1,
    "sd": 1
  }
}
```

When `bottleneck_location` is `CORE`, the rApp sets:
```json
{
  "threshold": 80,
  "bottleneck_location": "CORE",
  "handover_allowed": false
}
```
### 14.2 Unified Policy Type 20008 JSON Schema

To allow A1 Mediator to validate both baseline minimal payloads and proposed metadata payloads without raising schema validation errors (`400 Bad Request: additional properties not allowed`), the registered schema in `/opt/oran/nearrt/a1/policies/ts-policy-type-20008.json` on VM-2 defines:

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

Because `bottleneck_location`, `target_cell_preference`, `handover_allowed`, and `slice_id` are explicitly declared with defaults, A1 Mediator accepts payloads with or without these fields.

---

## References

Official references:

- O-RAN Alliance WG2 — A1 Interface: Application Protocol v03.01 & Type Definitions
- O-RAN SC — A1 Policy Management Service  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/

- O-RAN SC — A1 Mediator  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-a1/

- O-RAN SC — A1 Mediator source  
  https://github.com/o-ran-sc/ric-plt-a1

- O-RAN SC — RMR  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-lib-rmr/

- O-RAN SC — Python xApp Framework  
  https://docs.o-ran-sc.org/projects/o-ran-sc-ric-plt-xapp-frame-py/

- srsRAN — Minimal O-RAN SC RIC deployment  
  https://github.com/srsran/oran-sc-ric

Related deployment guides:

- [VM-1 — Non-RT RIC](../deployment/vm-01-non-rt-ric.md)
- [VM-2 — Near-RT RIC](../deployment/vm-02-near-rt-ric.md)
- [E2 Integration Guide](e2-integration.md)
- [Baseline & Methodology Guide](../experiments/methodology.md)
- [System Architecture](../architecture.md)
- [Troubleshooting](../troubleshooting/README.md)

