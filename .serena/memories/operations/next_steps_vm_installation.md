# Roadmap & SOP Instalasi Testbed Pasca-Crash (VM-3, VM-07, VM-2)

## Status Awal
VM-3 (Core), VM-07 (NWDAF), dan VM-2 (Near-RT RIC) baru saja diinstal ulang (*fresh install* OS Linux), bersih dari file konfigurasi dan kontainer. Dokumen acuan lengkap berada di `docs/deployment/`.

---

## Urutan Eksekusi Bring-Up (Deterministic 5-Phase Sequence)

### FASE 1: Bring-Up VM-3 — OAI 5G Core Multi-Slice (`10.102.0.246`)
*Dokumentasi Acuan:* `docs/deployment/vm-03-5g-core.md`

1. **Persiapan Sistem & Dependensi Kernel:**
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 net-tools tshark iproute2
   sudo modprobe gtp && sudo modprobe sctp
   echo -e "gtp\nsctp" | sudo tee -a /etc/modules
   sudo sysctl -w net.ipv4.ip_forward=1
   sudo usermod -aG docker $USER
   ```
2. **Deploy OAI 5GC Multi-Slice Stack:**
   - Clone / navigasi ke direktori compose 5GC:
     ```bash
     cd /opt/oran/5gcore/docker-compose
     docker compose -f docker-compose-slicing-basic-nrf.yaml up -d
     ```
   - Komponen aktif: `mysql`, `oai-nrf`, `oai-amf` (N2 binding `:38412`), `oai-smf-slice1` (eMBB), `oai-smf-slice2` (URLLC), `oai-upf-slice1` (simpleswitch URR pada `192.168.70.142`), `oai-upf-slice2` (`192.168.70.143`), dan `oai-ext-dn` (`192.168.70.145`).
3. **Konfigurasi NAT External Data Network:**
   ```bash
   docker exec -it oai-ext-dn iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
   ```
4. **Deploy Host Telemetry Daemon:**
   - Salin dan jalankan `core_adapter.py` v9:
     ```bash
     sudo nohup python3 -u /opt/oran/5gcore/scripts/core_adapter.py > /dev/null 2>&1 &
     ```
5. **Verifikasi:**
   - `docker ps` (pastikan 8 kontainer status `healthy`/`Up`).
   - `ping -c 2 192.168.70.138` (AMF reachable di subnet internal).

---

### FASE 2: Bring-Up VM-07 — Standalone 3GPP NWDAF (`10.102.0.233`)
*Dokumentasi Acuan:* `docs/deployment/vm-07-nwdaf.md`

1. **Rute Statis ke Subnet 5GC VM-3 (WAJIB):**
   ```bash
   sudo ip route add 192.168.70.0/24 via 10.102.0.246
   ping -c 2 192.168.70.136  # Uji konektivitas ke NRF di VM-3
   ```
2. **Deploy Database & Gateway:**
   - Setup MongoDB `:27017` (database `testing.smf`, collection `qosmonlist`).
   - Setup Kong API Gateway `:8080` dengan file deklaratif `conf/kong.yml`.
3. **Deploy 8 Microservices OAI NWDAF:**
   ```bash
   cd /opt/oran/nwdaf/docker-compose
   docker compose -f docker-compose-nwdaf-cn-http1.yaml up -d
   ```
4. **Verifikasi NBI Analytics:**
   ```bash
   curl -s -i "http://10.102.0.233:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION"
   ```
   *Expected:* HTTP 200 dengan payload JSON `UE_COMMUNICATION`.

---

### FASE 3: Bring-Up VM-2 — O-RAN Near-RT RIC (`10.102.0.232`)
*Dokumentasi Acuan:* `docs/deployment/vm-02-near-rt-ric.md`

1. **Deploy O-RAN SC Dawn Near-RT RIC Stack:**
   ```bash
   cd /opt/oran/near-rt-ric/docker-compose
   docker compose up -d
   ```
2. **Komponen Aktif:**
   - `ric_e2term` (Port SCTP `:36421`).
   - `ric_e2mgr` & `ric_dbaas` (Redis `:6379`).
   - `ric_a1mediator` & Nginx Shim (Port HTTP `:10001` & `:10000`).
   - `python_xapp_runner` (menjalankan xApp Traffic Steering).
3. **Verifikasi:**
   ```bash
   ss -tulpn | grep 36421               # Pastikan E2Term SCTP listening
   curl -s http://10.102.0.232:10001/a1-p/healthcheck  # Expected: HTTP 200
   ```

---

### FASE 4: Penyelarasan Rute & Uji Interkoneksi RAN & UE

1. **VM-4 (Split RAN - `10.102.0.167`):**
   - Update rute statis: `sudo ip route replace 192.168.70.0/24 via 10.102.0.246`
   - Jalankan RAN:
     ```bash
     sudo /opt/oran/ran/start_ran.sh
     sudo nohup python3 -u /opt/oran/ran/scripts/ran_adapter.py > /dev/null 2>&1 &
     ```
   - Cek log CU: pastikan N2 Setup ke AMF sukses dan E2 Setup ke `10.102.0.232:36421` sukses.
2. **VM-5 (nrUE Emulator - `10.102.0.165`):**
   - Update rute statis: `sudo ip route replace 192.168.70.0/24 via 10.102.0.246`
   - Spawn UEs: `sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1`
   - Tes canary ping: `sudo ip netns exec ue1 ping -c 3 192.168.70.145` (0% packet loss).
   - Mulai generator beban: `sudo nohup /opt/oran/ue/scripts/trafgen.sh start 60 25 > /dev/null 2>&1 &`

---

### FASE 5: Validasi Telemetri End-to-End (VM-6 — `10.102.0.67`)
1. Jalankan Telemetry Collector:
   ```bash
   export NWDAF_HOST=10.102.0.233
   python3 /opt/oran/monitoring/collector/telemetry_collector.py &
   ```
2. Pastikan scrape 40-kolom menghasilkan telemetri yang valid tanpa nilai drop:
   ```bash
   python3 /opt/oran/monitoring/scripts/record_experiment.py S1 --duration 60 --notes "Uji Validasi 7 VM Baru"
   ```

## Status Eksekusi Live (15 November 2026)
### VM-3 (5G Core Multi-Slice: 10.102.0.246) — STATUS: OPERATIONAL (BERHASIL)
1. **Host & Kernel:** Docker CE, Compose v2, SCTP/GTP kernel modules aktif, sysctl net.ipv4.ip_forward=1 aktif & persisten.
2. **Database:** Pre-provisioning 50 UE (IMSI 208950000000001 s/d 050) pada database/oai_db2.sql sukses.
3. **Penyelarasan Slicing (Case #40/#49):**
   - conf/nssf_slice_config.yaml: Dipetakan ke Slice 1 (SST 1, SD 000001) dan Slice 2 (SST 222, SD 00007B) dengan nrfNfMgtUri dan TAC 40960.
   - conf/slicing_base_config.yaml: Ditambahkan nrf under nfs, daftar plmn_support_list dibersihkan dari slice tutorial lama (128/130).
   - conf/slicing_slice1_config.yaml: Subnet 12.1.1.0/24, SST 1, SD 000001.
   - conf/slicing_slice2_config.yaml: Subnet 12.1.2.0/24, SST 222, SD 00007B, DNN lowlatency.
   - docker-compose-slicing-basic-nrf.yaml: Routing oai-ext-dn diperbarui ke 12.1.1.0/24 dan 12.1.2.0/24.
4. **Patching AMF (Case #51):**
   - Git submodule component/oai-amf diperbarui secara rekursif (termasuk build/common-build).
   - Patch 0001-fix-amf-nrf-resource-uri.patch diterapkan pada src/amf-app/amf_app.cpp.
   - Docker image oai-amf:thesis-nrf-uri-v1 berhasil di-build dan di-deploy via compose.amf-nrf-uri.yaml.
   - AMF terdaftar sukses ke NRF (HTTP 201 Created, HeartBeat timer: 10).
   - SCTP Port 38412 listening pada 192.168.70.138:38412.
5. **Implementasi Native 3GPP Rel-16 URR PoC pada UPF-1:**
   - Image `oai-upf:poc-develop-ie43-compat-v1` dibangun dari commit upstream `c51cae2` dengan patch `0001-fix-upf-pfcp-ie43-rel16-compat.patch` (clamping IE 43 ke 6 oktet).
   - `enable_usage_reporting: yes` diaktifkan di SMF-1 dan `enable_urr: yes` di UPF-1.
   - UPF-1 periodic reporting loop (30s) terbukti memancarkan N4 Session Report Request (`msg type 56`), SMF-1 memetakan ke Event 98 `QOS_MON`, dan mentransmisikan notifikasi HTTP/2 ke NWDAF.
6. **Host Telemetry Daemon:**
   - `scripts/core_adapter.py` v9 diunduh ke `/opt/oran/5gc/scripts/core_adapter.py`.
   - Daemon aktif berjalan di background (PID terverifikasi via `ps aux`).

### VM-07 (Standalone 3GPP NWDAF: 10.102.0.233) — STATUS: OPERATIONAL (BERHASIL)
1. **Host Routing & Netfilter Ingress:**
   - Rute statis `192.168.70.0/24 via 10.102.0.246` aktif dan dipersistensikan via systemd `5gc-route.service`.
   - VM-3 netfilter di-bypass (raw PREROUTING anti-spoofing + FORWARD + MASQUERADE) sehingga ping dan HTTP/2 tembus ke NRF (`192.168.70.136`).
2. **Microservices Stack (7 Kontainer Up & Healthy):**
   - `oai-nwdaf-mongodb`, `oai-nwdaf-sbi`, `oai-nwdaf-engine`, `oai-nwdaf-nbi-analytics`, `oai-nwdaf-nbi-events`, `oai-nwdaf-nbi-ml`, dan `oai-nwdaf-nbi-gateway` (Kong 3.3.0).
3. **Penyelarasan SBI & Subscription (Case #33 & Case #47):**
   - `oai-nwdaf-sbi` berhasil terhubung ke MongoDB `testing` dan mendaftarkan event subscription ke AMF (`192.168.70.138:8080`) via HTTP/2 (`HTTP/2.0 201 Created`).
   - Berhasil mendaftarkan event subscription ke SMF-1 (`192.168.70.139:8080`) untuk event `PDU_SES_EST`, `UE_IP_CH`, `PLMN_CH`, `DDDS`, `PDU_SES_REL`, dan `QOS_MON`.
   - `EVENT_NOTIFY_URI` terkonfigurasi ke `http://10.102.0.233:6062`.
4. **Kong Gateway HTTP/2 Termination (Terobosan Arsitektur SBI):**
   - Mengatasi limitasi Go `http.ListenAndServe` internal `oai-nwdaf-sbi` yang hanya mendukung HTTP/1.1.
   - Port 6062 dialihkan ke Kong Gateway (`8002 http2`) dengan rute ke `oai-nwdaf-sbi:8080/test/smf` via HTTP/1.1.
   - SMF-1 memancarkan notifikasi QoS Monitoring / URR periodik via native HTTP/2 dan menerima `HTTP/2 200 OK`.
   - Ingesti MongoDB terbukti 100% aktif: dokumen `testing.smf` berhasil mengakumulasi byte riil dari UPF-1 (`qosmonlist` berisi >55 MB / 38,000 paket).
5. **Verifikasi Northbound API (NBI):**
   - Query `http://127.0.0.1:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=UE_COMMUNICATION` menghasilkan `HTTP/1.1 200 OK` dengan payload JSON valid.

### VM-2 (O-RAN Near-RT RIC: 10.102.0.232) — STATUS: OPERATIONAL (BERHASIL)
1. **Host & Modul Kernel:**
   - Modul kernel `sctp` aktif dan persisten di `/etc/modules`.
2. **Platform Minimal O-RAN SC (7 Kontainer Up):**
   - `ric_dbaas` (Redis 5.0.9 / DBAAS 0.5.7 - Fix Case #28), `ric_rtmgr_sim`, `ric_e2mgr` (keepalive timeout tuned 3600s - Fix Case #29), `ric_e2term` (SCTP port 36421 exposed - Fix Case #36), `ric_submgr`, `ric_appmgr`, `python_xapp_runner`.
3. **A1 Mediation & Compatibility Layer (2 Kontainer Up):**
   - `ric_a1mediator` running pada port 10000 dengan RMR route table `local.rt`.
   - Baseline A1 Policy Type 20008 terdaftar (`HTTP/1.1 201 Created`).
   - `a1-compat` (NGINX reverse proxy) running pada port 10001, respons healthcheck `HTTP/1.1 200 OK` dan policy query `[ 20008 ]`.
4. **Golden State Verification:**
   - Socket SCTP `36421` listening pada `0.0.0.0:36421`.
   - Seluruh 9 kontainer platform dan mediation aktif (`Up`).

Status saat ini: Lanjut ke **FASE 4: Penyelarasan Rute & Uji Interkoneksi RAN & UE (VM-4: `10.102.0.167` & VM-5: `10.102.0.165`)**.


### VM-4 (Split RAN: 10.102.0.167) & VM-5 (nrUE: 10.102.0.165) — STATUS: OPERATIONAL (BERHASIL)
1. **VM-4 Split RAN:**
   - CU, DU-1 (RFsim :4043, Telnet :9090, -E, 51 PRB, Cell ID 12345678, PCI 1), dan DU-2 (RFsim :4044, 106 PRB, Cell ID 11111111, PCI 2) aktif berjalan.
   - N2 association ke AMF sukses (`associated AMF 1`).
   - O-RAN E2 Setup sukses terhubung ke Near-RT RIC VM-2 (`10.102.0.232:36421`), 8 FlexRIC Service Models terdaftar ke DBaaS.
   - `ran_adapter.py` aktif melacak metrik radio uplink gNodeB.
2. **VM-5 nrUE Multi-Instance:**
   - Multi-UE netns isolation (`ue1`, `ue2`) aktif dan terverifikasi.
   - UE-1 (Slice 1 - eMBB, IMSI 208950000000001) terhubung ke DU-1 (:4043), 5GMM-REGISTERED, PDU Session ID 10 aktif, IP `12.1.1.2/24` pada `oaitun_ue1`.
   - UE-2 (Slice 2 - URLLC, IMSI 208950000000002) terhubung ke DU-2 (:4044), 5GMM-REGISTERED, PDU Session ID 10 aktif, IP `12.1.2.3/24` pada `oaitun_ue1`.
   - **Canary Ping End-to-End ke EXT-DN (192.168.70.145):**
     - Slice 1: 0% packet loss (RTT avg ~33 ms).
     - Slice 2: 0% packet loss (RTT avg ~22.7 ms).

### VM-6 (Monitoring & TSDB: 10.102.0.67) — STATUS: OPERATIONAL (BERHASIL)
1. **Stack Pemantauan:**
   - Prometheus v2.47.0 (`:9090`) dan Grafana v10.1.0 (`:3000`) aktif berjalan via Docker Compose.
   - `telemetry_collector.py` daemon aktif (port `:9100`), scrape target Prometheus berstatus `UP` (1.000 Hz cadence).
2. **Uji Validasi Eksperimen S1 (Baseline Light Load):**
   - Run ID: `EXP_S1_20261116_132744` (Durasi: 60.7 detik, 60 sampel telemetri).
   - Scrape Status: 60/60 sukses (0 gagal, 100% telemetry coverage).
   - Arsip NWDAF NBI Riil: 15 poll responses sukses di-query dan disimpan ke `nwdaf_raw_poll_responses.jsonl` (0 gagal).
   - Hasil Metrik Jaringan:
     - Slice 1 (eMBB): Throughput mean 15.00 Mbps (100% target rate), RTT mean 46.42 ms, Packet loss 1.0%.
     - Slice 2 (URLLC): RTT mean 17.14 ms (< 20 ms SLA threshold), Packet loss 0.0%.
     - RAN Cell-1: PRB usage avg 91.9%, MCS avg 28.0, BLER 0.00%, SNR 26.2 dB.
     - UPF-1 Core: Backlog 0 B, Drops 0 pkt.
3. **Hardening Lifecycle UE (Graceful Teardown):**
   - `stop_multi_ue.sh` diperbarui menggunakan graceful shutdown dua tahap (`SIGINT` -> sleep 2 -> `SIGKILL`) untuk mencegah orphaned bearer F1-U (Case 41) pada DU-1 gNodeB.

---

## Kesimpulan Status Akhir
Seluruh 7 Virtual Machine (VM-2 Near-RT RIC, VM-3 5G Core, VM-4 Split RAN, VM-5 nrUE, VM-6 Monitoring & TSDB, VM-07 Standalone NWDAF) **RESMI 100% PULIH, OPERASIONAL, DAN TERINTEGRASI END-TO-END PASCA-CRASH**. Sistem siap untuk kampanye pengambilan dataset eksperimen S1 hingga S10.

