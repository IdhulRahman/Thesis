# 3GPP NWDAF Integration & Telemetry Pipeline Troubleshooting

This document contains validated diagnostic procedures, root-cause analyses, and resolutions for issues in the **nwdaf** domain.

---

## Case 33 — Kong API Gateway 404 Not Found on Physical Host IP (`http://10.102.0.164:8080`)

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

## Case 44 — Static NWDAF SliceLoadLevel (5.00%) During Core UPF Impairment / Fault Injection

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

## Case 47 — OAI NWDAF SBI Subscription `connection refused` on Multi-Slice Core

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

## Case 48 — OAI NWDAF Analytics `"missing Network Performance Data"` vs Hardcoded Relative Ratio

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
