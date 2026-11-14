# 7-VM Disaggregated O-RAN & 5G Core Architecture & IP Mapping

## 1. Topologi Testbed (Host IP Allocation)
Seluruh node berjalan pada private network `10.102.0.0/24` berbasis Virtual Machine:

| VM | Host IP | Peran Fungsional & Komponen Utama | Port Kunci & Protokol |
|---|---|---|---|
| **VM-1** | `10.102.0.168` | Non-RT RIC & SMO (A1 PMS v2.6.0, rApp Coordinator) | HTTP `:8081` |
| **VM-2** | `10.102.0.232` | Near-RT RIC (O-RAN SC Dawn: E2Term, E2Mgr, A1 Mediator, xApp) | SCTP `:36421`, HTTP `:10001` (A1-P) |
| **VM-3** | `10.102.0.246` | OAI 5G Core Multi-Slice (AMF, SMF-1/2, UPF-1/2, NRF, EXT-DN) | SCTP `:38412` (N2), UDP `:2152` (N3) |
| **VM-4** | `10.102.0.167` | OAI Split RAN (CU-CP, CU-UP, DU-1 Cell-1, DU-2 Cell-2, FlexRIC E2 Agent) | TCP `:4043`/`:4044` (RFsim), Telnet `:9090` |
| **VM-5** | `10.102.0.165` | OAI nrUE Emulator (`ue1` eMBB, `ue2` URLLC, TrafGen) | Linux Netns `ue1` & `ue2` |
| **VM-6** | `10.102.0.67` | Observability Host (Collector `:9100`, Prometheus TSDB `:9090`, Grafana `:3000`) | HTTP `:9100`, `:9090`, `:3000` |
| **VM-07** | `10.102.0.233` | Standalone 3GPP Rel-17 NWDAF (AnLF Engine, Kong Gateway, MongoDB) | HTTP `:8080` (NBI), TCP `:27017` (Mongo) |

## 2. Alokasi Subnet Internal & Routing Invariant
1. **Subnet Kontainer 5GC (VM-3):** `192.168.70.0/24`
   - NRF: `192.168.70.136:8080`
   - UDR: `192.168.70.137:8080`
   - AMF: `192.168.70.138:38412` (N2 SCTP)
   - SMF-1 (eMBB): `192.168.70.139`
   - SMF-2 (URLLC): `192.168.70.140`
   - UPF-1 (eMBB, simpleswitch URR): `192.168.70.142`
   - UPF-2 (URLLC, stock): `192.168.70.143`
   - EXT-DN (Data Network): `192.168.70.145`
2. **Subnet IP UE:**
   - `ue1` (eMBB, SST=1, SD=0x01): `12.1.1.2/24` via UPF-1
   - `ue2` (URLLC, SST=2, SD=0x7b): `12.1.2.2/24` via UPF-2
3. **Kaidah Rute Statis Mutlak (Static Routing Invariant):**
   Setiap node yang perlu berkomunikasi dengan kontainer 5GC (VM-07 NWDAF, VM-4 RAN, VM-5 UE) WAJIB memiliki rute statis:
   ```bash
   sudo ip route replace 192.168.70.0/24 via 10.102.0.246
   ```

## 3. Disagregasi NWDAF (VM-07)
NWDAF berdiri sendiri pada VM-07 (`10.102.0.233`), mengonsumsi Nsmf event exposure dari SMF-1 di VM-3, menyimpan histori URR ke MongoDB lokal, dan mengekspos endpoint analytics standar 3GPP via Kong Gateway pada `http://10.102.0.233:8080/nnwdaf-analyticsinfo/v1/analytics`.
