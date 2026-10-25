# VM-1 — Non-RT RIC

This document describes the deployment of **VM-1 (`nonrt-ric`)**, which hosts the Non-RT RIC-side components used in this project.

VM-1 provides the northbound policy-management side of the multi-timescale control loop:

```text
Custom rApp
    │
    ▼
A1 Policy Management Service
    │
    │ A1
    ▼
VM-2 Near-RT RIC
```

The custom rApp will be added later. At the current implementation stage, VM-1 hosts the **O-RAN SC A1 Policy Management Service (A1 PMS)** and provides the interface used to create, update, query, and delete A1 policies.

---

## 1. VM Specification

| Parameter | Value |
|---|---|
| VM | VM-1 |
| Hostname | `nonrt-ric` |
| IP address | `10.102.0.168` |
| Subnet | `10.102.0.0/24` |
| Main role | Non-RT RIC |
| Main component | O-RAN SC A1 Policy Management Service |
| Container runtime | Docker |

The Near-RT RIC is deployed separately on:

```text
VM-2
Hostname : near-rt-ric
IP       : 10.102.0.66
```

---

## 2. Software Version

The final validated deployment uses:

| Component | Version |
|---|---|
| A1 Policy Management Service | `2.6.0` |
| Release family | O-RAN SC H Release |
| Container image | `nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.6.0` |

A1 PMS `2.6.0` is listed by O-RAN SC as the H Release version.

> The project initially tested newer PMS versions, but the final validated deployment uses `2.6.0` together with the OSC A1 client compatibility path described in [A1 Integration](../integration/a1-integration.md).

---

## 3. Theoretical & Architectural Rationale for Non-RT RIC Configurations

### 3.1 Hierarchical Multi-Timescale Control Loop
- **Standard:** **O-RAN Alliance Working Group 2 (WG2) A1 Interface Specification**.
- **Control Timescales:**
  - **Non-RT RIC (VM-1):** Operates on non-real-time timescales ($> 1\text{ second}$). In this thesis platform, the custom rApp formulates declarative high-level traffic steering guidance and slice QoS priorities based on long-term telemetry trends.
  - **Near-RT RIC (VM-2):** Operates on near-real-time timescales ($10\text{ ms} - 1\text{ second}$). The xApp ingests policies delivered via A1 and executes sub-second radio resource optimization over E2.
- **Role of A1 PMS:** A1 Policy Management Service maintains the canonical lifecycle and repository of active policy types, policy instances, and target Near-RT RIC statuses.

### 3.2 O-RAN SC Adapter Selection (`OscA1Client`)
- **Adapter Mechanism:** A1 PMS supports multiple backend adapter protocols (`StdA1ClientVersion1`, `StdA1ClientVersion2`, `OscA1Client`, `SdncOscA1Client`).
- **Rationale for `OscA1Client`:** The O-RAN Software Community (OSC) Near-RT RIC A1 Mediator implements the OSC dialect of A1AP (RFC 6838 JSON media types and REST endpoints). Specifying:
  ```json
  "customAdapterClass": "org.onap.ccsdk.oran.a1policymanagementservice.clients.OscA1Client"
  ```
  instructs PMS to bypass generic A1 protocol discovery and directly use the validated OSC client, avoiding compatibility mismatches.

### 3.3 Managed Elements Association (`managedElementIds`)
- **Concept:** Under 3GPP TS 28.532 and O-RAN WG2 architecture, a Near-RT RIC controls specific Radio Network Functions (Managed Elements).
- **Mapping:** In `application_configuration.json`, the logical identifiers:
  ```json
  "managedElementIds": ["oai-cu-cp", "oai-du-1", "oai-du-2"]
  ```
  bind the OAI gNB Centralized Unit and Distributed Units to `near-rt-ric-1`. When an rApp posts a policy targeting a specific cell or node, A1 PMS routes the policy to the Near-RT RIC responsible for those managed elements.

---

## 4. Parameter Customization Reference Guide

| Parameter | Current Value | Classification | Customization Rules & Impact |
|---|---|---|---|
| `name` | `near-rt-ric-1` | `[CUSTOMIZABLE]` | Logical identifier for the target Near-RT RIC in PMS registry. |
| `baseUrl` | `http://10.102.0.66:10001` | `[MANDATORY MATCH NEAR-RT]` | Endpoint of VM-2 A1 compatibility shim. |
| `customAdapterClass` | `...OscA1Client` | `[FIXED / ARCHITECTURE]` | Client adapter required to communicate with OSC A1 Mediator. |
| `managedElementIds` | `["oai-cu-cp", ...]` | `[CUSTOMIZABLE]` | Target RAN network function identifiers managed by this RIC. |
| `A1_PMS_HTTP_PORT` | `8081` | `[FIXED / ARCHITECTURE]` | Northbound REST API port of A1 PMS container. |

---

## 5. Directory Layout

Create the VM-1 working directories:

```bash
sudo mkdir -p /opt/oran/nonrt/a1pms
sudo mkdir -p /opt/oran/nonrt/rapp
sudo mkdir -p /opt/oran/nonrt/test
sudo chown -R "$USER":"$USER" /opt/oran/nonrt
```

The resulting layout is:

```text
/opt/oran/nonrt/
├── a1pms/
│   ├── application_configuration.json
│   └── database/
├── rapp/
└── test/
```

---

## 6. Docker Access

Verify Docker:

```bash
docker --version
docker compose version
```

If the current user cannot access `/var/run/docker.sock`, add it to the Docker group:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

Verify:

```bash
docker ps
```

> If group membership is not active yet, either log out and log back in or temporarily prefix Docker commands with `sudo`.

---

## 7. Create the Docker Network

Create a dedicated Docker network for the Non-RT RIC components:

```bash
docker network create nonrtric-docker-net
```

If the network already exists, verify it with:

```bash
docker network ls | grep nonrtric-docker-net
```

Expected:

```text
nonrtric-docker-net
```

---

## 8. Pull the A1 PMS Image

Pull the validated A1 PMS image:

```bash
docker pull \
  nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.6.0
```

Verify:

```bash
docker images | grep a1policymanagementservice
```

Expected image tag:

```text
2.6.0
```

---

## 9. Verify Connectivity to VM-2

Before starting PMS, verify that VM-1 can reach the A1 compatibility endpoint on VM-2:

```bash
curl -i \
  http://10.102.0.66:10001/a1-p/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

The compatibility endpoint on port `10001` is described in:

[A1 Integration Guide](../integration/a1-integration.md)

---

## 10. Configure A1 PMS

Create:

```bash
nano /opt/oran/nonrt/a1pms/application_configuration.json
```

Use the following configuration:

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

Validate the JSON:

```bash
jq . /opt/oran/nonrt/a1pms/application_configuration.json
```

The important parameters are:

| Parameter | Purpose |
|---|---|
| `name` | Logical Near-RT RIC identifier used by PMS |
| `baseUrl` | A1 compatibility endpoint on VM-2 |
| `customAdapterClass` | Forces PMS to use the OSC A1 client |
| `managedElementIds` | RAN elements associated with this Near-RT RIC |

The `managedElementIds` values are deployment identifiers and may be updated later when the final OAI RAN configuration is frozen.

---

## 11. Prepare Persistent PMS Storage

The PMS container runs using:

```text
uid=999(nonrtric)
gid=1000(nonrtric)
```

Create a persistent database directory:

```bash
sudo mkdir -p /opt/oran/nonrt/a1pms/database
sudo chown -R 999:1000 /opt/oran/nonrt/a1pms/database
sudo chmod 755 /opt/oran/nonrt/a1pms/database
```

This directory is bind-mounted into:

```text
/var/policy-management-service/database
```

Without this writable directory, PMS may log errors such as:

```text
Could not create directory: /var/policy-management-service/database/...
Could not write file: /var/policy-management-service/database/...
```

---

## 12. Start A1 PMS

Run:

```bash
docker run -d \
  --name policy-agent-container \
  --restart unless-stopped \
  --network nonrtric-docker-net \
  -p 8081:8081 \
  -p 8433:8433 \
  -v /opt/oran/nonrt/a1pms/application_configuration.json:/opt/app/policy-agent/data/application_configuration.json:ro \
  -v /opt/oran/nonrt/a1pms/database:/var/policy-management-service/database \
  nexus3.o-ran-sc.org:10002/o-ran-sc/nonrtric-plt-a1policymanagementservice:2.6.0
```

Verify:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Expected:

```text
policy-agent-container   Up   ...8081...8433...
```

---

## 13. PMS Health Check

Check PMS status:

```bash
curl -s \
  http://127.0.0.1:8081/a1-policy/v2/status \
  | jq
```

The validated deployment returns:

```json
{
  "status": "hunky dory"
}
```

---

## 14. Verify Near-RT RIC Synchronization

Wait for PMS synchronization:

```bash
sleep 60
```

Then run:

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

The key acceptance criteria are:

```text
state          = AVAILABLE
policytype_ids = ["20008"]
```

---

## 15. Verify Persistent Policy-Type Storage

Check the host-side PMS database:

```bash
find /opt/oran/nonrt/a1pms/database \
  -maxdepth 3 \
  -type f \
  -printf '%u:%g %p\n'
```

After synchronization, the policy-type database should contain:

```text
/opt/oran/nonrt/a1pms/database/policytypes/20008.json
```

On Ubuntu, UID `999` may be displayed using the host-side username associated with that numeric UID. This does not affect the container as long as the numeric UID/GID permissions are correct.

---

## 16. Inspect the Live PMS OpenAPI Schema

The running PMS exposes an OpenAPI description.

Check the create/update policy endpoint:

```bash
curl -s \
  http://127.0.0.1:8081/v3/api-docs \
  | jq '.paths["/a1-policy/v2/policies"].put'
```

Inspect the policy object:

```bash
curl -s \
  http://127.0.0.1:8081/v3/api-docs \
  | jq '.components.schemas.policy_info_v2'
```

The required fields in the validated PMS version are:

```text
policy_id
policytype_id
ric_id
policy_data
```

---

## 17. Create a Test Policy through PMS

Before running this test, ensure the A1-aware xApp on VM-2 is running.

Create:

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

For a new policy, expected response:

```text
HTTP/1.1 201 Created
```

An update to an existing policy may return:

```text
HTTP/1.1 200 OK
```

---

## 18. Query the Policy from PMS

Retrieve the policy:

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

The same policy should be visible at the A1 Mediator on VM-2 and delivered to the xApp using RMR.

See:

[A1 Integration Guide](../integration/a1-integration.md)

---

## 19. Useful Operational Commands

### Show container status

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Show recent PMS logs

```bash
docker logs --since=2m policy-agent-container
```

### Check synchronization errors

```bash
docker logs --since=2m policy-agent-container 2>&1 \
  | grep -Ei 'error|warn|sync|policySchema|FileStore'
```

### Restart PMS

```bash
docker restart policy-agent-container
```

### Stop PMS

```bash
docker stop policy-agent-container
```

### Start PMS

```bash
docker start policy-agent-container
```

---

## 20. Acceptance Criteria

VM-1 is considered correctly deployed when all of the following are true:

```text
[✓] policy-agent-container is running
[✓] /a1-policy/v2/status is healthy
[✓] near-rt-ric-1 is AVAILABLE
[✓] policy type 20008 is discovered
[✓] policy type state is persisted to disk
[✓] a policy can be created through PMS
[✓] the policy reaches the xApp through VM-2
```

---

## 21. Troubleshooting

### Docker permission denied

Symptom:

```text
permission denied while trying to connect to the Docker daemon socket
```

Fix:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

---

### RIC becomes `UNAVAILABLE`

Check:

```bash
curl -i \
  http://10.102.0.66:10001/a1-p/healthcheck
```

Then inspect:

```bash
docker logs --since=5m policy-agent-container
```

The final deployment should use:

```text
baseUrl            = http://10.102.0.66:10001
customAdapterClass = ...OscA1Client
```

Do not point the final PMS configuration directly to the A1 Mediator `/A1-P/v2` endpoint.

The compatibility reason is documented separately in:

[A1 Integration Guide](../integration/a1-integration.md)

---

### `policySchema not found`

A previously tested direct configuration produced:

```text
JSONObject["policySchema"] not found
```

The validated deployment resolves this by using:

```text
PMS OscA1Client
        +
A1 compatibility shim on VM-2
```

Do not modify the official policy type `20008` schema to work around this parsing mismatch.

---

### PMS database write errors

Symptoms:

```text
Could not create directory
Could not write file
```

Verify container UID/GID:

```bash
docker exec policy-agent-container id
```

Validated values:

```text
uid=999(nonrtric)
gid=1000(nonrtric)
```

Then fix ownership:

```bash
sudo chown -R 999:1000 /opt/oran/nonrt/a1pms/database
```

---

## 22. Final VM-1 Cross-Domain Data Path

```text
VM-3 (5GC / NWDAF)             VM-6 (Prometheus TSDB / RAN KPM)
        │ Nnwdaf HTTP/2                        │ HTTP Metrics Pull
        └───────────────┬──────────────────────┘
                        ▼
            Custom rApp Coordinator
          [Bottleneck Classification]
          (NORMAL | RAN | CORE | JOINT)
                        │
                 Action Selector
                        │ policy request
                        ▼
                  A1 PMS :8081
                        │
                  OscA1Client
                        ▼
                10.102.0.66:10001
                        │
               A1 compatibility shim
                        │
                    A1 Mediator
                        │
                    RMR 20010
                        ▼
                      xApp
```

In the research architecture design, VM-1 is designated as the Non-RT RIC coordination hub: hosting the A1 Policy Management Service (PMS) container (`:8081`) for policy lifecycle management, with autonomous rApp analytics ingestion, bottleneck classification, and policy dispatch designed as Phase B closed-loop evaluation specifications.

---

## 23. Planned Phase B Evaluation Modes (Research Design Specification)

> [!NOTE]
> **Operational Testbed Status vs. Phase B Evaluation Design:**  
> On the currently operational testbed, VM-1 operates the validated A1 Policy Management Service container (`:8081`) and interface shim. Autonomous rApp classification loops and programmatic policy dispatch are defined as **Planned Phase B research specifications**. In baseline telemetry recording runs (B0 through B3), no automated rApp closed loop operates in the background. The matrix below defines the planned operational modes and A1 policy payloads designed for subsequent Phase B comparative evaluation.

| Baseline ID | Evaluation Mode | Planned rApp Operational State & Behavior | Planned A1 Policy Payload Dispatched |
|---|---|---|---|
| **B0** | Static Default | **Inactive.** No active policy instances created in PMS. | None (`DELETE` all policy instances via PMS `:8081`). |
| **B1** | RAN-Only Control | **Planned Static Threshold.** Ingests only RAN metrics; NWDAF consumer inactive. | Planned static dummy threshold (`{"threshold": 80}`) without bottleneck metadata. |
| **B2** | Core-Only Control | **Inactive.** Core adaptation is handled strictly within VM-3. | None. |
| **B3** | Decoupled | **Inactive.** Near-RT xApp and Core adapter act without Non-RT RIC coordination. | None. |
| **B4** | Fixed-Sequence Coordination | **Planned Fixed Action Sequence.** Designed to ingest both NWDAF and RAN metrics but bypass classifier; planned to dispatch static handover authorization regardless of bottleneck origin. | Planned unclassified handover authorization payload. |
| **Proposed** | Bottleneck-Aware Closed-Loop | **Planned Closed-Loop Coordination.** Designed to evaluate Rule-Based / Decision Tree classifier on synchronized telemetry, dispatch targeted A1 policy guidance, and verify SLA restoration across subsequent stability window. | Planned targeted policy: `{"bottleneck_location": "RAN"|"CORE"|"JOINT", "target_cell": 2, "handover_allowed": true/false}`. |

---

## References

Official references used for this deployment:

- O-RAN SC — A1 Policy Management Service release notes  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/en/latest/release-notes.html

- O-RAN SC — A1 Policy Management Service documentation  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/

- O-RAN Alliance WG2 — Non-RT RIC Architecture v03.00 & A1 Interface Specification v03.01

- 3GPP TS 23.288 — Architecture for 5G System Network Data Analytics Function (NWDAF)

- Docker — Bind mounts  
  https://docs.docker.com/engine/storage/bind-mounts/

- Docker — `docker run` reference  
  https://docs.docker.com/reference/cli/docker/container/run/

For the cross-VM A1 compatibility and RMR path, see:

[A1 Integration Guide](../integration/a1-integration.md)

