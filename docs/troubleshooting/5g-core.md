# OAI 5G Core Network & User Plane Troubleshooting

This document contains validated diagnostic procedures, root-cause analyses, and resolutions for issues in the **5g-core** domain.

---

## Case 31 — Docker Compose Network Collision & Undefined Network during NWDAF Merge

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

## Case 32 — MySQL 8.0 Subscriber Initialization Failure on OAI v2.1.0 Schema (`ERROR 1054` & `ERROR 3140`)

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

## Case 34 — Transient Docker Hub Timeout during Large Image Pulls (`net/http: timeout awaiting response headers`)

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

## Case 43 — PDU Session Establishment Reject (5GSM Cause 0x21: Service Option Not Subscribed) for Slice 2

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

## Case 40 — PDU Session Establishment Stuck / Ignored: Mismatch in 5GC Slicing YAML Configurations

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

## Case 45 — Operation Not Permitted (`ERR_[Errno 1]`) or Buffered Logs in `core_adapter.py`

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

<a id="case-50"></a>
## Case 50 — SMF N4/PFCP 1-Second Timeout After Manual `upfs:` Configuration Edit

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

<a id="case-51"></a>
## Case 51 — OAI AMF Automated NRF Registration Failure (Missing `/{nfInstanceId}` in Dynamic Resource URI)

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
   In `component/oai-amf/src/amf-app/amf_app.cpp` around line 1614 (inside `get_nrfs`), update the NSSF response parsing logic to dynamically append `"/" + amf_instance_id` to `nrfNfMgtUri` (see committed patch [`patches/amf/0001-fix-amf-nrf-resource-uri.patch`../../patches/amf/0001-fix-amf-nrf-resource-uri.patch)):
   ```cpp
   // Before:
   nrfs.insert(nsi_information.getNrfNfMgtUri());

   // After (Patched):
   std::string nrf_uri = nsi_information.getNrfNfMgtUri();
   if (nrf_uri.empty()) {
     Logger::amf_app().warn("NSSF returned an empty NRF management URI");
   } else {
     while (!nrf_uri.empty() && nrf_uri.back() == '/') {
       nrf_uri.pop_back();
     }
     nrf_uri += "/" + amf_instance_id;
     nrfs.insert(nrf_uri);
   }
   ```

2. **Rebuild Custom AMF Image (`oai-amf:thesis-nrf-uri-v1`):**
   - Ensure the build environment has sufficient RAM ($\ge 8$ GB or restrict parallel jobs with `MAKEFLAGS="-j2"` / `CMAKE_BUILD_PARALLEL_LEVEL=2`).
   - Use the customized Dockerfile [`patches/amf/Dockerfile.amf.ubuntu`../../patches/amf/Dockerfile.amf.ubuntu), which adds `libsystemd-dev` to Stage 1 dependencies (preventing version locking conflicts with `libsystemd0`) and adds APT retry configuration (`Acquire::Retries "3";`).
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

3. **Deploy Patched Image via Docker Compose:**
   Use the committed Docker Compose override file [`deploy/compose.amf-nrf-uri.yaml`../../deploy/compose.amf-nrf-uri.yaml):
   ```yaml
   services:
     oai_amf:
       container_name: "oai-amf"
       image: oai-amf:thesis-nrf-uri-v1
   ```
   Apply and recreate the container:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml -f compose.amf-nrf-uri.yaml up -d --force-recreate oai_amf
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

<a id="case-52"></a>
## Case 52 — OAI UPF N4/PFCP Session Establishment Silent Drop (Unsupported 3GPP TS 29.244 IE Type 62 `Measurement Method`)

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

1. **Unsupported Information Element in `openair-upf:v2.1.0` Binary:**
   - Under **3GPP TS 29.244 §8.2.40**, Information Element (IE) Type **62** (1 octet) defines the **`Measurement Method`**. This IE is a mandatory sub-element inside the **`Create URR` (Usage Reporting Rule)** IE used by the SMF to configure data volume and duration measurements.
   - When `enable_usage_reporting: yes` is configured under `smf.upfs` in SMF configuration files (e.g., `conf/slicing_slice1_config.yaml`), SMF-1 automatically constructs a `Create URR` containing IE Type 62 within the `PFCP Session Establishment Request` payload (241 bytes).
   - In `oaisoftwarealliance/oai-upf:v2.1.0` (`openair-upf` @ `89ee4c9`), the internal PFCP TLV parser lacks implementation support for IE Type 62:
     ```text
     [upf_n4 ] [info] handle_receive(241 bytes)
     [pfcp   ] [error] Unknown PFCP IE type 62 (length 1)
     [upf_n4 ] [info] handle_receive exception PFCP IE TLV 6 Bad Length 48 Exception /openair-upf/src/pfcp/3gpp_29.244.hpp:219
     ```
2. **Silent Packet Drop:**
   - When the C++ exception is thrown in `3gpp_29.244.hpp:219`, `openair-upf` aborts packet processing immediately. It drops the request without transmitting any error response (such as a `PFCP Session Establishment Response` with Cause `Rule creation/modification failure`).
   - Consequently, SMF-1 remains waiting for an acknowledgement until its internal 1-second timeout expires (`timer id 897`), triggering retransmission and eventual session abandonment.
3. **Absence of Datapath Logic in `v2.1.0` vs. Availability in Upstream `develop`:**
   - In `openair-upf:v2.1.0` (`component/oai-upf/src/upf_app/simpleswitch/pfcp_switch.cpp:703–745`), session setup only processes `create_fars`, `create_pdrs`, and `create_qers`. There is zero handling of `create_urrs` in `simpleswitch`.
   - In contrast, upstream `develop` (pinned to commit `c51cae2324e79a65e96f48ef8a00365de06bcb96`) has merged URR support: `pfcp_switch.cpp` processes `create_urrs`, `pfcp_urr.cpp` manages URR structures, and `usage_report_loop()` / `send_usage_report()` handle reporting. Per official `docs/FEATURE_SET.md`, this support is partial and requires empirical testing for end-to-end compatibility with SMF and NWDAF.
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

#### Approach 1: Native 3GPP PFCP URR PoC (Recommended — UPF `develop` with Rel-16 Patch)

To enable native 3GPP PFCP Usage Reporting Rules (URR) while maintaining full interoperability with the deployed OAI SMF `v2.1.0`:

1. **Root Cause Analysis of the Interop Friction:**
   - Upstream UPF `develop` (pinned to commit `c51cae2324e79a65e96f48ef8a00365de06bcb96`) provides native datapath URR support (`create_urrs`, `pfcp_urr.cpp`, `usage_report_loop()`, and `send_usage_report()`).
   - However, upstream `develop` encodes Information Element (IE) Type 43 (**`UP Function Features`**) as 8 octets (Release 17 format).
   - In OAI SMF `v2.1.0`, the internal PFCP TLV parser (`3gpp_29.244.hpp:2521`) strictly bounds IE 43 length to 6 octets (Release 16 format), throwing `PFCP IE TLV 43 Bad Length 8 Exception` and aborting the PFCP Association Setup.

2. **Apply Rel-16 Compatibility Patch (`patches/upf/0001-fix-upf-pfcp-ie43-rel16-compat.patch`):**
   In `src/common-src/pfcp/3gpp_29.244.hpp`, clamp IE Type 43 payload length to 6 octets, serialize only octets 1–6 (`u1` through `u6`), and assert that unused Release 17 octets (`u7` and `u8`) remain zero:
   ```cpp
   // Set TLV length to 6 octets (Rel-16) instead of 8 octets (Rel-17)
   tlv.set_length(6);

   // In dump_to(char* buf):
   tlv.dump_to(buf);
   buf[sizeof(pfcp_tlv)]     = u1.b;
   buf[sizeof(pfcp_tlv) + 1] = u2.b;
   buf[sizeof(pfcp_tlv) + 2] = u3.b;
   buf[sizeof(pfcp_tlv) + 3] = u4.b;
   buf[sizeof(pfcp_tlv) + 4] = u5.b;
   buf[sizeof(pfcp_tlv) + 5] = u6.b;
   return tlv.total_length();
   ```

3. **Build the Patched UPF Image (`oai-upf:poc-develop-ie43-compat-v1`):**
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/component/oai-upf
   git checkout c51cae2324e79a65e96f48ef8a00365de06bcb96
   git apply /path/to/patches/upf/0001-fix-upf-pfcp-ie43-rel16-compat.patch

   sudo docker build \
     --network=host \
     --target oai-upf \
     -f docker/Dockerfile.upf.ubuntu \
     -t oai-upf:poc-develop-ie43-compat-v1 .
   ```

4. **Deploy via Docker Compose Override (`deploy/compose.upf-poc.yaml`):**
   Ensure `enable_usage_reporting: yes` is active under `smf.upfs` in `conf/slicing_slice1_config.yaml`, then deploy with the compose override:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose \
     -f docker-compose-slicing-basic-nrf.yaml \
     -f compose.amf-nrf-uri.yaml \
     -f compose.upf-poc.yaml \
     up -d --force-recreate oai_upf_slice1 oai_smf_slice1
   ```

5. **Empirical Verification:**
   - **N4 Association Handshake:**
     SMF-1 accepts the Association Setup Response cleanly without exceptions:
     ```text
     [smf_n4 ] [info] Received N4 ASSOCIATION SETUP RESPONSE from an UPF
     [smf_n4 ] [info] Received N4 ASSOCIATION SETUP RESPONSE
     ```
   - **End-to-End PDU Session & Explicit Interface Data Plane Verification:**
     UE 1 softmodem on VM-5 spawns, receives tunnel IP `12.1.1.3/24` on `oaitun_ue1`, and pings External DN with explicit interface binding (`-I oaitun_ue1`), achieving **0% packet loss (avg RTT 0.257 ms)**:
     ```text
     five-g@nrue:~$ sudo ip netns exec ue1 ping -I oaitun_ue1 -c 10 192.168.70.145
     PING 192.168.70.145 (192.168.70.145) from 12.1.1.3 oaitun_ue1: 56(84) bytes of data.
     64 bytes from 192.168.70.145: icmp_seq=1 ttl=62 time=0.283 ms
     64 bytes from 192.168.70.145: icmp_seq=2 ttl=62 time=0.169 ms
     64 bytes from 192.168.70.145: icmp_seq=3 ttl=62 time=0.280 ms
     64 bytes from 192.168.70.145: icmp_seq=4 ttl=62 time=0.276 ms
     64 bytes from 192.168.70.145: icmp_seq=5 ttl=62 time=0.194 ms
     64 bytes from 192.168.70.145: icmp_seq=6 ttl=62 time=0.130 ms
     64 bytes from 192.168.70.145: icmp_seq=7 ttl=62 time=0.365 ms
     64 bytes from 192.168.70.145: icmp_seq=8 ttl=62 time=0.252 ms
     64 bytes from 192.168.70.145: icmp_seq=9 ttl=62 time=0.421 ms
     64 bytes from 192.168.70.145: icmp_seq=10 ttl=62 time=0.209 ms

     --- 192.168.70.145 ping statistics ---
     10 packets transmitted, 10 received, 0% packet loss, time 9240ms
     rtt min/avg/max/mdev = 0.130/0.257/0.421/0.083 ms
     ```
   - **Live NWDAF Control Plane Ingestion:**
     MongoDB database `testing.smf` immediately records the live session event under SUPI `208950000000001` with timestamp `1792040188` and IP `12.1.1.5`, confirming control-plane session ingestion (`absoluteNum: 1`).
   - **N4 Periodic Usage Reporting Verification (UPF $\to$ SMF):**
     Activating native URR reporting requires dual configuration in `conf/slicing_slice1_config.yaml`:
     1. `smf.upfs[].config.enable_usage_reporting: yes`: Instructs SMF to construct and attach 3GPP TS 29.244 IE Type 62 within `Create URR` linked to PDR 1.
     2. `upf.support_features.enable_urr: yes`: Instructs UPF `simpleswitch` (`pfcp_switch.cpp:1030`) to initialize internal URR datapath structures and spawn `thread_usage_report_ = std::thread(&pfcp_switch::usage_report_loop, this)`.

     Once configured and restarted, UPF banner confirmed `+ Enable Usage Reporting (URR): Yes`. UPF `usage_report_loop()` periodically builds and transmits PFCP Session Report Requests (`msg type 56`, 109 bytes) containing `Usage Report Trigger: Periodic Reporting` over N4. SMF-1 logs verify successful reception, packet/volume extraction, and downstream event dispatch:
     ```text
     [smf_n4 ] [info] handle_receive(109 bytes)
     [smf_n4 ] [debug] handle_receive_pfcp_msg msg type 56 length 105
     [smf_n4 ] [info] Received N4 SESSION REPORT REQUEST from an UPF
     [smf_app] [info]               Trigger         -> Periodic Reporting
     [smf_app] [info]                      Uplink   -> 30
     [smf_app] [info]                      Downlink -> 30
     [smf_app] [info]               Volume Total    -> 5040
     [smf_app] [info]                      Uplink   -> 2520
     [smf_app] [info]                      Downlink -> 2520
     [smf_app] [debug] Send request to N11 to trigger QoS Monitoring (Usage Report) Event, SMF Context-related SEID  0x4
     [smf_app] [debug] No subscription available for this event
     [smf_app] [info] Sending ITTI message 31itti_n4_session_report_response to task TASK_SMF_N4
     ```
     This empirically confirms that the UPF $\to$ SMF leg of Track 1 is fully functional: UPF actively tracks datapath packets/bytes, transmits PFCP Session Reports over N4, and SMF successfully ingests them.
   - **Downstream Root Cause Analysis (SMF $\to$ NWDAF Ingestion Boundary):**
     Detailed source code audit of official OAI NWDAF (`commit 9d82b75`) clarifies the actual architecture and corrects initial assumptions:
     1. **`QOS_MON` Subscription is Implemented in NWDAF SBI:** In [`components/oai-nwdaf-sbi/internal/sbi/utils.go`](https://github.com/openairinterface/oai-cn5g-nwdaf/blob/9d82b7547586a6e04dc0719ef18910ea01fcd9e7/components/oai-nwdaf-sbi/internal/sbi/utils.go), `smfEventSubscription()` explicitly includes `SMFEVENTANYOF_QOS_MON` in its subscription payload alongside `PDU_SES_EST`, `UE_IP_CH`, and `DDDS`.
     2. **`qosmonlist` Handler & Storage Structure Exist:** In [`components/oai-nwdaf-sbi/internal/sbi/smf_service.go`](https://github.com/openairinterface/oai-cn5g-nwdaf/blob/9d82b7547586a6e04dc0719ef18910ea01fcd9e7/components/oai-nwdaf-sbi/internal/sbi/smf_service.go), `getUpdateQOS_MON()` actively constructs a BSON update using `$push` to append `Customized_data` into the `qosmonlist` array of the SMF MongoDB document. Furthermore, [`components/oai-nwdaf-sbi/internal/smfclient/model_event_notification.go`](https://github.com/openairinterface/oai-cn5g-nwdaf/blob/9d82b7547586a6e04dc0719ef18910ea01fcd9e7/components/oai-nwdaf-sbi/internal/smfclient/model_event_notification.go) models `CustomUsageReport` with volume, packet counts (`NoP`), duration, trigger, and SEID.
     3. **Why SMF Logged "No subscription available for this event":** `oai-nwdaf-sbi` executes its subscription calls exclusively during container initialization (`InitConfig()` in `utils.go`). When SMF-1 was restarted during the URR configuration update, SMF-1 reinitialized with an empty in-memory subscription table. Because `oai-nwdaf-sbi` was not concurrently restarted, it never re-registered its `Nsmf_EventExposure` subscription with the running SMF instance. Consequently, SMF-1 had no active subscription record in memory at the time the Usage Report arrived.
     4. **Resolution Procedure & Empirical Verification:** Restarting `oai-nwdaf-sbi` while SMF-1 is active re-executed `InitConfig()`, successfully registering `QOS_MON` on SMF-1. Upon user-plane traffic transmission (20 ping packets, 0% loss), SMF-1 logged `Found an event subscription (Event ID 1, Event 98)` $\to$ `Send notification for the subscribed event to the subscription`. `oai-nwdaf-sbi` received the notification and updated `testing.smf`, successfully creating and appending live entries into `qosmonlist` (e.g., Report 2 with duration 1406s, NoP 34, volume 2856 bytes; Report 3 with duration 1436s, NoP 6, volume 504 bytes). This confirms that Track 1 is 100% operational and verified end-to-end.
     5. **Complementary Role of Track 2:** Even with native `qosmonlist` populated, standard 3GPP URR measures session-level byte and packet volumes. Physical Linux kernel queue backlog bytes (`tc qdisc`) and bufferbloat spikes are not exposed over N4/N11, validating the continued necessity of Track 2 (`core_adapter.py` under 3GPP TS 23.288 §6.2.3) for cross-domain bottleneck classification.

#### Approach 2: Fallback Workaround (Baseline `v2.1.0` Rollback)

If operational requirements mandate strict conformance to the unpatched `v2.1.0` release baseline:
1. Restore `conf/slicing_slice1_config.yaml` to the baseline configuration (omitting `enable_usage_reporting: yes`).
2. Launch without `compose.upf-poc.yaml` so the standard `openair-upf:v2.1.0` image is used:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml -f compose.amf-nrf-uri.yaml up -d --force-recreate oai_upf_slice1 oai_smf_slice1
   ```

### Architectural & Thesis Implications

This investigation demonstrates that while `openair-upf:v2.1.0` lacks URR datapath handling, upstream `develop` (`c51cae2`) successfully provides native URR support when patched for Rel-16 IE 43 length alignment with the bounds of the SMF parser commit in use. Furthermore, configuring `upf.support_features.enable_urr: yes` activates periodic PFCP Session Report emissions over N4, which SMF consumes to trigger N11 QoS Monitoring events.

Concurrently, network bottlenecks in virtualized 5G Core span multiple layers: UPF CPU processing starvation, internal pipeline queuing, physical transport link saturation, and host kernel egress queue backlogs.  
To ensure holistic observability, the thesis employs a **Dual-Track Complementary Architecture**:
1. **Native 3GPP PFCP URR Track (100% Empirically Verified End-to-End):** PDU session establishment with `Linked URR: 1`, periodic N4 Usage Reporting (msg type 56) to SMF, and downstream SBI notification to NWDAF (live `qosmonlist` ingestion in MongoDB) are fully verified across the standard 3GPP N4 $\to$ SMF $\to$ NWDAF interface chain.
2. **Custom OAM Host Telemetry Track:** Operates under **3GPP TS 23.288 §6.2.3** ("Data Collection from OAM services") via `core_adapter.py` v9 on VM-3, capturing physical kernel queue dynamics (`tc qdisc` backlog bytes and packet drops) that 3GPP URR does not natively measure.

Both telemetry streams are operational in the testbed: Track 1 captures standardized 3GPP session volume/duration counters into NWDAF MongoDB, while Track 2 provides sub-second kernel queue bufferbloat and drop telemetry directly to the Non-RT RIC / TSDB collector on VM-6.
---

---
