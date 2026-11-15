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
5. **Host Telemetry Daemon:**
   - `scripts/core_adapter.py` v9 diunduh ke `/opt/oran/5gc/scripts/core_adapter.py`.
   - Daemon aktif berjalan di background (PID terverifikasi via `ps aux`).

Status saat ini: Lanjut ke **FASE 2: Bring-Up VM-07 (Standalone 3GPP NWDAF: 10.102.0.233)**.
