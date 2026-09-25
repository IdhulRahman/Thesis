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
| IP address | `10.10.10.11` |
| Subnet | `10.10.10.0/24` |
| Main role | Non-RT RIC |
| Main component | O-RAN SC A1 Policy Management Service |
| Container runtime | Docker |

The Near-RT RIC is deployed separately on:

```text
VM-2
Hostname : near-rt-ric
IP       : 10.10.10.12
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

> The project initially tested newer PMS versions, but the final validated deployment uses `2.6.0` together with the OSC A1 client compatibility path described in [A1 Integration](a1-integration.md).

---

## 3. Directory Layout

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

## 4. Docker Access

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

## 5. Create the Docker Network

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

## 6. Pull the A1 PMS Image

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

## 7. Verify Connectivity to VM-2

Before starting PMS, verify that VM-1 can reach the A1 compatibility endpoint on VM-2:

```bash
curl -i \
  http://10.10.10.12:10001/a1-p/healthcheck
```

Expected:

```text
HTTP/1.1 200 OK
```

The compatibility endpoint on port `10001` is described in:

[docs/a1-integration.md](a1-integration.md)

---

## 8. Configure A1 PMS

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
        "baseUrl": "http://10.10.10.12:10001",
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

## 9. Prepare Persistent PMS Storage

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

## 10. Start A1 PMS

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

## 11. PMS Health Check

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

## 12. Verify Near-RT RIC Synchronization

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

## 13. Verify Persistent Policy-Type Storage

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

## 14. Inspect the Live PMS OpenAPI Schema

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

## 15. Create a Test Policy through PMS

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

## 16. Query the Policy from PMS

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

[docs/a1-integration.md](a1-integration.md)

---

## 17. Useful Operational Commands

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

## 18. Acceptance Criteria

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

## 19. Troubleshooting

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
  http://10.10.10.12:10001/a1-p/healthcheck
```

Then inspect:

```bash
docker logs --since=5m policy-agent-container
```

The final deployment should use:

```text
baseUrl            = http://10.10.10.12:10001
customAdapterClass = ...OscA1Client
```

Do not point the final PMS configuration directly to the A1 Mediator `/A1-P/v2` endpoint.

The compatibility reason is documented separately in:

[docs/a1-integration.md](a1-integration.md)

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

## 20. Final VM-1 Data Path

```text
Custom rApp
    │
    │ policy request
    ▼
A1 PMS :8081
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
    │
    │ RMR 20010
    ▼
xApp
```

VM-1 is therefore the entry point for long-timescale QoS policy control in the experimental platform.

---

## References

Official references used for this deployment:

- O-RAN SC — A1 Policy Management Service release notes  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/en/latest/release-notes.html

- O-RAN SC — A1 Policy Management Service documentation  
  https://docs.o-ran-sc.org/projects/o-ran-sc-nonrtric-plt-a1policymanagementservice/

- Docker — Bind mounts  
  https://docs.docker.com/engine/storage/bind-mounts/

- Docker — `docker run` reference  
  https://docs.docker.com/reference/cli/docker/container/run/

For the cross-VM A1 compatibility and RMR path, see:

[docs/a1-integration.md](a1-integration.md)
