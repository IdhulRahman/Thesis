# Troubleshooting Manual & Issue Resolution Index

This directory contains validated troubleshooting procedures, root-cause analyses, and reproduction fixes for issues encountered during testbed deployment and experimentation.

To ensure maintainability and eliminate unmanageable monolithic files, troubleshooting records are partitioned into **five domain-specific guides**:

| Domain File | Subsystems Covered | Target Virtual Machines |
|---|---|---|
| [`ric-a1.md`](ric-a1.md) | A1 PMS v2.6.0, A1 Mediator, RMR routing, xApp lifecycle | VM-1 & VM-2 |
| [`e2-networking.md`](e2-networking.md) | E2Term, E2Mgr, SCTP 36421, DBaaS Redis, inter-VM networking | VM-2 & VM-4 |
| [`ran-ue.md`](ran-ue.md) | OAI gNB CU/DU, F1-U, SIMDE/GCC, Softmodem, nrUE namespaces | VM-4 & VM-5 |
| [`5g-core.md`](5g-core.md) | 5GC NFs, MySQL subscriber schemas, Slicing YAML, AMF, UPF URR | VM-3 |
| [`nwdaf.md`](nwdaf.md) | OAI NWDAF SBI/NBI, Kong Gateway, MongoDB `qosmonlist`, telemetry | VM-3 & VM-6 |

---

## 1. Quick Diagnostic Flow (A1 / RIC Path)

```text
VM-1 PMS ──► PMS Health ──► RIC State AVAILABLE? ──► VM-2 Shim ──► A1 Mediator ──► DBaaS ──► RMR 20010 ──► xApp ──► RMR 20011 (ENFORCED)
```

---

## 2. Comprehensive Historical Case Cross-Reference Mapping

The table below maps all historical Case numbers from the monolithic log to their new modular locations:

| Historical Case | Resolution Guide | Domain Section Header | Issue Description |
|---|---|---|---|
| **Case 02** | [`ric-a1.md`](ric-a1.md) | `Docker Permission Denied` | Docker Permission Denied |
| **Case 03** | [`ric-a1.md`](ric-a1.md) | `PMS RIC State Is `UNAVAILABLE`` | PMS RIC State Is `UNAVAILABLE` |
| **Case 04** | [`ric-a1.md`](ric-a1.md) | ``JSONObject["policySchema"] not found`` | `JSONObject["policySchema"] not found` |
| **Case 05** | [`ric-a1.md`](ric-a1.md) | `PMS Database Write Errors` | PMS Database Write Errors |
| **Case 06** | [`ric-a1.md`](ric-a1.md) | `Host Shows Unexpected Owner Name for UID 999` | Host Shows Unexpected Owner Name for UID 999 |
| **Case 07** | [`ric-a1.md`](ric-a1.md) | ``docker compose` Cannot Find the Project` | `docker compose` Cannot Find the Project |
| **Case 09** | [`ric-a1.md`](ric-a1.md) | `A1 Mediator Health Returns `500`` | A1 Mediator Health Returns `500` |
| **Case 10** | [`ric-a1.md`](ric-a1.md) | `Legacy `/a1-p/...` Endpoints Return `404`` | Legacy `/a1-p/...` Endpoints Return `404` |
| **Case 11** | [`ric-a1.md`](ric-a1.md) | `Compatibility Shim Does Not Reach A1 Mediator` | Compatibility Shim Does Not Reach A1 Mediator |
| **Case 12** | [`ric-a1.md`](ric-a1.md) | `xApp Does Not Receive A1 Policy` | xApp Does Not Receive A1 Policy |
| **Case 13** | [`ric-a1.md`](ric-a1.md) | `xApp Fails to Parse `payload`` | xApp Fails to Parse `payload` |
| **Case 14** | [`ric-a1.md`](ric-a1.md) | `xApp Receives CREATE but A1 Does Not Become `` | xApp Receives CREATE but A1 Does Not Become `ENFORCED` |
| **Case 15** | [`ric-a1.md`](ric-a1.md) | `No `20010` / `20011` Lines in A1 Logs` | No `20010` / `20011` Lines in A1 Logs |
| **Case 16** | [`ric-a1.md`](ric-a1.md) | `xApp Registration Warning` | xApp Registration Warning |
| **Case 17** | [`ric-a1.md`](ric-a1.md) | `xApp Shutdown Attempts Kubernetes AppMgr Host` | xApp Shutdown Attempts Kubernetes AppMgr Hostname |
| **Case 18** | [`ric-a1.md`](ric-a1.md) | `Direct A1 Policy Is Unexpectedly Deleted` | Direct A1 Policy Is Unexpectedly Deleted |
| **Case 19** | [`ric-a1.md`](ric-a1.md) | `Direct A1 PUT Returns `202 Accepted`` | Direct A1 PUT Returns `202 Accepted` |
| **Case 20** | [`ric-a1.md`](ric-a1.md) | `PMS Policy Creation Response` | PMS Policy Creation Response |
| **Case 21** | [`ric-a1.md`](ric-a1.md) | `SDNC Does Not Solve the Schema Mismatch` | SDNC Does Not Solve the Schema Mismatch |
| **Case 22** | [`ric-a1.md`](ric-a1.md) | `VM-1 Quick Checks` | VM-1 Quick Checks |
| **Case 23** | [`ric-a1.md`](ric-a1.md) | `VM-2 Quick Checks` | VM-2 Quick Checks |
| **Case 24** | [`ric-a1.md`](ric-a1.md) | `VM-1` | VM-1 |
| **Case 25** | [`ric-a1.md`](ric-a1.md) | `VM-2` | VM-2 |
| **Case 26** | [`ric-a1.md`](ric-a1.md) | `Known-Good End-to-End Result` | Known-Good End-to-End Result |
| **Case 08** | [`e2-networking.md`](e2-networking.md) | `E2Mgr / SubMgr Fails Because DBaaS Is Not Rea` | E2Mgr / SubMgr Fails Because DBaaS Is Not Ready or Not Resolved |
| **Case 28** | [`e2-networking.md`](e2-networking.md) | ``redis: got 7 elements in COMMAND reply, want` | `redis: got 7 elements in COMMAND reply, wanted 6` on `ric_e2mgr` with `ric-plt-dbaas:0.6.4` |
| **Case 29** | [`e2-networking.md`](e2-networking.md) | `E2T Instance Prematurely Deleted by `e2mgr` K` | E2T Instance Prematurely Deleted by `e2mgr` Keepalive Timeout (4.5s) |
| **Case 35** | [`e2-networking.md`](e2-networking.md) | `Near-RT RIC E2Mgr / SubMgr Container Exit on ` | Near-RT RIC E2Mgr / SubMgr Container Exit on Startup due to Missing DBaaS Environment Variables |
| **Case 36** | [`e2-networking.md`](e2-networking.md) | `E2Term SCTP Port 36421 Inaccessible from Exte` | E2Term SCTP Port 36421 Inaccessible from External RAN Node (`Connection refused`) |
| **Case 23b** | [`ran-ue.md`](ran-ue.md) | `VM-4 Cannot Reach VM-3 5GC Containers (100% P` | VM-4 Cannot Reach VM-3 5GC Containers (100% Packet Loss on 192.168.70.x) |
| **Case 24b** | [`ran-ue.md`](ran-ue.md) | `Git Clone Failed with RPC failed; curl 92 HTT` | Git Clone Failed with RPC failed; curl 92 HTTP/2 stream CANCEL / early EOF |
| **Case 25b** | [`ran-ue.md`](ran-ue.md) | `FlexRIC Tarball Download Fails with HTTP 429 ` | FlexRIC Tarball Download Fails with HTTP 429 Too Many Requests |
| **Case 26b** | [`ran-ue.md`](ran-ue.md) | `SIMDE Installation Fails with Git Timeout (cu` | SIMDE Installation Fails with Git Timeout (curl 28) during `./build_oai -I` |
| **Case 27** | [`ran-ue.md`](ran-ue.md) | `GCC 11 Internal Compiler Error (Segmentation ` | GCC 11 Internal Compiler Error (Segmentation fault) on FlexRIC `kpm_sm` `_Generic` Macro |
| **Case 30** | [`ran-ue.md`](ran-ue.md) | `F1-U GTP-U Socket Bind Collision on VM-4 (`bi` | F1-U GTP-U Socket Bind Collision on VM-4 (`bind: Address already in use: 127.0.0.1 2153`) |
| **Case 37** | [`ran-ue.md`](ran-ue.md) | `Packet Drop / Ping Timeout from RAN (VM-4) to` | Packet Drop / Ping Timeout from RAN (VM-4) to 5GC Docker Subnet (`192.168.70.0/24`) via Host VM-3 |
| **Case 38** | [`ran-ue.md`](ran-ue.md) | `OAI gNB CU E2 Agent Inactive / Disabled (`E2 ` | OAI gNB CU E2 Agent Inactive / Disabled (`E2 agent is DISABLED`) |
| **Case 39** | [`ran-ue.md`](ran-ue.md) | `OAI nrUE Softmodem Immediate Abort on Depreca` | OAI nrUE Softmodem Immediate Abort on Deprecated Command-Line Option `--sa` |
| **Case 41** | [`ran-ue.md`](ran-ue.md) | `User-Plane Packet Drop on F1-U: Stale TEID Ma` | User-Plane Packet Drop on F1-U: Stale TEID Mapping in gNB CU (`no tunnel mapping, drop`) |
| **Case 42** | [`ran-ue.md`](ran-ue.md) | `F1-U Downlink Self-Loop Drop when CU and DU B` | F1-U Downlink Self-Loop Drop when CU and DU Bind to `127.0.0.1` (`Sent GTP Error Indication ... to 127.0.0.1:2153: no tunnel mapping, drop`) |
| **Case 46** | [`ran-ue.md`](ran-ue.md) | `Stale NRF Session & Cross-VM Split-RAN Desync` | Stale NRF Session & Cross-VM Split-RAN Desynchronization |
| **Case 49** | [`ran-ue.md`](ran-ue.md) | `UE 2 PDU Session Establishment Rejected — MyS` | UE 2 PDU Session Establishment Rejected — MySQL S-NSSAI Subscriber Profile Mismatch |
| **Case 31** | [`5g-core.md`](5g-core.md) | `Docker Compose Network Collision & Undefined ` | Docker Compose Network Collision & Undefined Network during NWDAF Merge |
| **Case 32** | [`5g-core.md`](5g-core.md) | `MySQL 8.0 Subscriber Initialization Failure o` | MySQL 8.0 Subscriber Initialization Failure on OAI v2.1.0 Schema (`ERROR 1054` & `ERROR 3140`) |
| **Case 34** | [`5g-core.md`](5g-core.md) | `Transient Docker Hub Timeout during Large Ima` | Transient Docker Hub Timeout during Large Image Pulls (`net/http: timeout awaiting response headers`) |
| **Case 43** | [`5g-core.md`](5g-core.md) | `PDU Session Establishment Reject (5GSM Cause ` | PDU Session Establishment Reject (5GSM Cause 0x21: Service Option Not Subscribed) for Slice 2 |
| **Case 40** | [`5g-core.md`](5g-core.md) | `PDU Session Establishment Stuck / Ignored: Mi` | PDU Session Establishment Stuck / Ignored: Mismatch in 5GC Slicing YAML Configurations |
| **Case 45** | [`5g-core.md`](5g-core.md) | `Operation Not Permitted (`ERR_[Errno 1]`) or ` | Operation Not Permitted (`ERR_[Errno 1]`) or Buffered Logs in `core_adapter.py` |
| **Case 50** | [`5g-core.md`](5g-core.md) | `SMF N4/PFCP 1-Second Timeout After Manual `up` | SMF N4/PFCP 1-Second Timeout After Manual `upfs:` Configuration Edit |
| **Case 51** | [`5g-core.md`](5g-core.md) | `OAI AMF Automated NRF Registration Failure (M` | OAI AMF Automated NRF Registration Failure (Missing `/{nfInstanceId}` in Dynamic Resource URI) |
| **Case 52** | [`5g-core.md`](5g-core.md) | `OAI UPF N4/PFCP Session Establishment Silent ` | OAI UPF N4/PFCP Session Establishment Silent Drop (Unsupported 3GPP TS 29.244 IE Type 62 `Measurement Method`) |
| **Case 33** | [`nwdaf.md`](nwdaf.md) | `Kong API Gateway 404 Not Found on Physical Ho` | Kong API Gateway 404 Not Found on Physical Host IP (`http://10.102.0.164:8080`) |
| **Case 44** | [`nwdaf.md`](nwdaf.md) | `Static NWDAF SliceLoadLevel (5.00%) During Co` | Static NWDAF SliceLoadLevel (5.00%) During Core UPF Impairment / Fault Injection |
| **Case 47** | [`nwdaf.md`](nwdaf.md) | `OAI NWDAF SBI Subscription `connection refuse` | OAI NWDAF SBI Subscription `connection refused` on Multi-Slice Core |
| **Case 48** | [`nwdaf.md`](nwdaf.md) | `OAI NWDAF Analytics `"missing Network Perform` | OAI NWDAF Analytics `"missing Network Performance Data"` vs Hardcoded Relative Ratio |
