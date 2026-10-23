# 6-VM Testbed Deployment & Operations Guide

This directory provides the authoritative, step-by-step deployment, configuration, startup, and operational procedures for each virtual machine in the 6-VM experimental testbed.

**Thesis Research Title:**  
*Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*

---

## 1. Virtual Machine Deployment Index

| Guide | Target Node | Subnet IP | Architectural Role | Core Software Framework |
|---|---|---|---|---|
| [`vm-01-non-rt-ric.md`](vm-01-non-rt-ric.md) | **VM-1** | `10.102.0.168` | Non-RT RIC & SMO Host | O-RAN SC A1 PMS v2.6.0, rApp Execution Environment |
| [`vm-02-near-rt-ric.md`](vm-02-near-rt-ric.md) | **VM-2** | `10.102.0.66` | Near-RT RIC Platform | O-RAN SC Dawn (A1 Mediator, E2Term, E2Mgr, DBaaS, xApp) |
| [`vm-03-5g-core.md`](vm-03-5g-core.md) | **VM-3** | `10.102.0.164` | Multi-Slice 5GC & NWDAF | OAI 5GC v2.1.0, OAI NWDAF (AnLF), Core Telemetry Adapter v9 |
| [`vm-04-ran.md`](vm-04-ran.md) | **VM-4** | `10.102.0.167` | Split 5G RAN | OAI gNB CU-CP/UP, DU-1 (Cell-1), DU-2 (Cell-2), RAN Adapter |
| [`vm-05-ue.md`](vm-05-ue.md) | **VM-5** | `10.102.0.165` | Multi-UE Emulator | OAI nrUE Emulator (netns: `ue1`, `ue2`), Multi-Slice TrafGen |
| [`vm-06-monitoring.md`](vm-06-monitoring.md) | **VM-6** | `10.102.0.67` | Telemetry & Observability | Telemetry Collector (:9100), Prometheus, Grafana, Recorder |

---

## 2. Deterministic Startup & Verification Sequence

To ensure proper cross-VM signaling binding (N2 SCTP, N4 PFCP, E2 SCTP, and A1 HTTP), start the nodes strictly in the following sequence:

```text
Step 1: VM-3 (5G Core) ──► Step 2: VM-4 (Split RAN) ──► Step 3: VM-1 (Non-RT RIC)
                                                                 │
Step 6: VM-6 (Monitor) ◄── Step 5: VM-5 (nrUE)      ◄── Step 4: VM-2 (Near-RT RIC)
```

1. **Step 1 — VM-3 (5G Core Bring-Up):**  
   Start MySQL, NRF, NSSF, AMF, SMF-1, SMF-2, UPF-1, UPF-2, Ext-DN, and the 8 NWDAF microservices. Verify AMF port `38412` and Kong port `8080` are listening. Launch `core_adapter.py`.
2. **Step 2 — VM-4 (Split RAN Bring-Up):**  
   Start CU softmodem (`cu_gnb.conf`). Confirm N2 association with AMF (`associated AMF 1`). Start DU-1 (`du_gnb1.conf`, port `4043`) and DU-2 (`du_gnb2.conf`, port `4044`). Launch `ran_adapter.py`.
3. **Step 3 — VM-1 (Non-RT RIC Bring-Up):**  
   Start A1 Policy Management Service (A1 PMS v2.6.0). Confirm REST API is healthy at `http://10.102.0.168:8081/actuator/health`.
4. **Step 4 — VM-2 (Near-RT RIC Bring-Up):**  
   Start DBaaS (Redis 5.0.9), E2Mgr, E2Term, Subscription Manager, A1 Mediator, and Traffic Steering xApp. Confirm E2 SCTP port `36421` is listening and A1 Mediator passes `/a1-p/healthcheck`.
5. **Step 5 — VM-5 (nrUE Bring-Up & Canary Validation):**  
   Execute `spawn_multi_ue.sh -s1 1 -s2 1`. Verify `oaitun_ue1` inside `ue1` (`12.1.1.2`) and `ue2` (`12.1.2.2`). Run ping canary to `192.168.70.145` confirming 0% packet loss. Start `trafgen.sh`.
6. **Step 6 — VM-6 (Monitoring & Telemetry Pipeline):**  
   Start `telemetry_collector.py` on port `9100`. Verify Prometheus scrapes `:9100/metrics`. Execute `record_experiment.py` to record single-scenario experimental runs.

---

## 3. Standard Operating Procedure (SOP): Topological System Bring-up & Outage Recovery

### 3.1 Architectural Invariant: Why Topological Sequencing is Mandatory

In 3GPP and O-RAN split architectures, session and state synchronization flow downstream:

```text
┌─────────────────────────┐       N2 SCTP       ┌─────────────────────────┐      RFsim TCP      ┌─────────────────────────┐
│     VM-3: 5G Core       │ ◄────────────────── │     VM-4: Split RAN     │ ◄────────────────── │      VM-5: nrUE         │
│ (AMF / SMF / UPF / UDM) │                     │ (CU-CP / DU-1 / DU-2)   │                     │ (netns ue1 / ue2)       │
└─────────────────────────┘                     └─────────────────────────┘                     └─────────────────────────┘
```

1. **State Dependency:**  
   * The gNodeB CU cannot register tracking areas without an active AMF N2 SCTP association.
   * nrUE cannot complete cell acquisition (PBCH), contention resolution (RACH), and PDU Session Establishment without both CU and DU being `in service`.
2. **Socket Severance Cascades:**  
   * **If RAN restarts:** Connected UEs lose their RFsimulator TCP socket (`:4043` / `:4044`). In OAI, the `nr-uesoftmodem` client does not automatically re-acquire the cell; it hangs or moves into `RRC moved into IDLE state` and deletes `oaitun_ue1`. **Whenever RAN restarts, UEs MUST be re-spawned.**
   * **If Core restarts:** The CU loses its N2 SCTP association and in-memory PDU session contexts are cleared. Even if UEs remain running, upstream routing fails. **Whenever Core restarts, the sequence Core ──► RAN ──► UE MUST be executed.**

---

### 3.2 Routine Clean Bring-up SOP

Execute commands across nodes in the following exact order:

#### Step 1: VM-3 (5G Core)
```bash
cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
sudo docker compose \
  -f docker-compose-slicing-basic-nrf.yaml \
  -f compose.amf-nrf-uri.yaml \
  -f compose.upf-poc.yaml \
  restart

# Wait 15 seconds for internal NRF and MySQL initialization
sleep 15

# Confirm all core functions are healthy:
sudo docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "mysql|amf|udm|ausf|upf"
```
*Verification requirement: Status must show `(healthy)`, not `(health: starting)`.*

#### Step 2: VM-4 (Split RAN)
```bash
# Launch CU, DU-1 with Telnet 9090, and DU-2 Baseline
bash /opt/oran/ran/scripts/start_ran.sh

# Confirm AMF association and both cell IDs are in service:
grep -E "associated AMF|is in service" /opt/oran/ran/cu.log | tail -n 5

# Confirm Telnet server is listening:
ss -tulpn | grep 9090
```
*Verification requirement: Must show `associated AMF 1`, `Cell ID 12345678 is in service`, `Cell ID 11111111 is in service`, and `0.0.0.0:9090 LISTEN`.*

#### Step 3: VM-5 (nrUE Emulator)
```bash
# Clean previous processes and spawn UEs
sudo bash /opt/oran/ue/scripts/stop_multi_ue.sh
sudo bash /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1

# Verify canary ping to Data Network (EXT-DN):
sudo ip netns exec ue1 ping -c 3 192.168.70.145
```
*Verification requirement: `oaitun_ue1` must be assigned IP `12.1.1.2`, and ping must achieve `0% packet loss`.*

#### Step 4: Data Traffic Flow (iperf3)
```bash
# On VM-3: Ensure iperf3 server daemon is active inside EXT-DN container
sudo docker exec -d oai-ext-dn iperf3 -s -p 5201

# On VM-5: Pump continuous 15 Mbps Uplink UDP stream
sudo ip netns exec ue1 iperf3 -c 192.168.70.145 -u -b 15M -t 600 -i 1
```

---

### 3.3 Outage & Interface Teardown Recovery SOP (`oaitun_ue1 DOWN` / `Fail`)

When a failure occurs (e.g., `iperf3: Network is unreachable` or `oaitun_ue1 DOWN` during experimental fault injections), apply the appropriate recovery level:

```text
┌─────────────────────────────────────────────────────────────┐
│ Failure Detected: oaitun_ue1 DOWN / Ping 100% Packet Loss   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            Is failure limited to UE radio impairment?
                               │
            ┌──────────────────┴──────────────────┐
           YES                                    NO (Core reject / N2 lost)
            ▼                                     ▼
   [Level 1: Quick UE Reset]             [Level 2: Full Topological Reset]
   1. Reset RFsim ploss on VM-4          1. Restart 5GC on VM-3 (wait healthy)
   2. Respawn UE on VM-5                 2. Restart RAN on VM-4 (verify cells)
   Time: ~15 seconds                     3. Respawn UE on VM-5 (verify tunnel)
                                         Time: ~45 seconds
```

#### Level 1: Quick Recovery (UE RLF or Channel Attenuation Outage — ~15s)
Use this when gNodeB and 5GC are healthy, but channel attenuation or radio stress triggered Radio Link Failure (RLF) or interface teardown:
1. **On VM-4:** Restore default RFsim channel parameters:
   ```bash
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
2. **On VM-5:** Respawn UEs and re-establish PDU sessions:
   ```bash
   sudo bash /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo bash /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
   sudo ip netns exec ue1 ping -c 3 192.168.70.145
   ```

#### Level 2: Full Topological Reset (5GC Out-of-Sync / `Illegal_UE` / N2 Drop — ~45s)
Use this when AMF rejects registrations, Docker containers stall, or SCTP associations drop:
1. **On VM-3:** Restart 5GC slicing containers and confirm healthy status:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml -f compose.amf-nrf-uri.yaml -f compose.upf-poc.yaml restart
   sleep 15
   sudo docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "mysql|amf|udm"
   ```
   > [!NOTE]
   > **Log Management Best Practice:**  
   > Do **not** manually truncate container `*-json.log` files during routine recovery. Direct file truncation deletes diagnostic history and can desynchronize Docker's logging driver handles. Manage container log volume sustainably using standard Docker log rotation via `/etc/docker/daemon.json` (`"max-size": "50m"`, `"max-file": "3"`).

2. **On VM-4:** Restart OAI Split RAN:
   ```bash
   bash /opt/oran/ran/scripts/start_ran.sh
   grep -E "is in service|associated AMF" /opt/oran/ran/cu.log | tail -n 5
   ```
3. **On VM-5:** Respawn UEs:
   ```bash
   sudo bash /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo bash /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
   sudo ip netns exec ue1 ping -c 3 192.168.70.145
   ```

---

## 4. Related Documentation

* **Software Manifest:** [docs/software-manifest.md](../software-manifest.md)
* **Integration Guides:** [docs/integration/README.md](../integration/README.md)
* **Metric Catalog:** [docs/telemetry/metric-catalog.md](../telemetry/metric-catalog.md)
* **Troubleshooting Index:** [docs/troubleshooting/README.md](../troubleshooting/README.md)
* **RAN & UE Troubleshooting:** [docs/troubleshooting/ran-ue.md](../troubleshooting/ran-ue.md)

