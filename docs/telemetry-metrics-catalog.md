# Katalog Telemetri & Panduan Ekstraksi Metrik 5G O-RAN

Dokumen ini merupakan katalog otoritatif yang merinci seluruh metrik telemetri yang dapat diekstrak dari testbed multi-slice 5G O-RAN, lokasi sumber data, formula perhitungan, serta cara ekstraksinya baik secara manual (shell command) maupun otomatis melalui daemon adapter Python.

---

## 1. Arsitektur Aliran Telemetri

Telemetri dikumpulkan secara kontinu pada frekuensi **1.000 Hz (1 sampel per detik)** melintasi lima domain arsitektur:

```text
[ VM-5: nrUE ]             [ VM-4: Split RAN ]          [ VM-3: 5G Core ]
  (iperf3 / ping)            (gNB DU Scheduler)           (UPF Container)
        │                            │                            │
        ▼                            ▼                            ▼
  trafgen.sh                  ran_adapter.py               core_adapter.py
        │                            │                            │
        └────────────────────┬───────┴────────────────────────────┘
                             │ POST :9100/report
                             ▼
                 [ VM-6: Monitoring Host ]
                   telemetry_collector.py  ──►  Prometheus (:9100/metrics)
                             │
                             ▼
                   record_dual_stream.py  ──►  telemetry_raw_<RUN_ID>.csv
```

---

## 2. Ringkasan Katalog Metrik

| No | Nama Kolom CSV | Prometheus Metric Name | Domain Asal | Host / Sumber | Satuan |
|---|---|---|---|---|---|
| 1 | `timestamp_utc` | *(Metadata baris)* | Pipeline | System Clock UTC | ISO-8601 |
| 2 | `elapsed_sec` | *(Metadata baris)* | Pipeline | Monotonic Clock | Detik |
| 3 | `run_id` | *(Metadata baris)* | Pipeline | Sesi CLI / Argumen | String |
| 4 | `scrape_ok` | *(Internal logger)* | Pipeline | HTTP Status :9100 | Boolean (0/1) |
| 5 | `scrape_latency_ms` | *(Internal logger)* | Pipeline | Scrape Duration | ms |
| 6 | `e2e_slice1_tput_mbps` | `e2e_slice1_throughput_mbps` | UE Experience | VM-5 `ue1` ns | Mbps |
| 7 | `e2e_slice1_jitter_ms` | `e2e_slice1_jitter_ms` | UE Experience | VM-5 `ue1` ns | ms |
| 8 | `e2e_slice2_rtt_ms` | `e2e_slice2_latency_rtt_ms` | UE Experience | VM-5 `ue2` ns | ms |
| 9 | `e2e_slice2_loss_pct` | `e2e_slice2_packet_loss_pct` | UE Experience | VM-5 `ue2` ns | % |
| 10 | `nwdaf_load_embb` | `nwdaf_slice_load_level{snssai="01000001"}` | 5G Core / NWDAF | VM-3 5GC / UPF | % (0–100) |
| 11 | `nwdaf_load_urllc` | `nwdaf_slice_load_level{snssai="de00007b"}` | 5G Core / NWDAF | VM-3 5GC / UPF | % (0–100) |
| 12 | `upf_backlog_bytes_embb` | `upf_queue_backlog_bytes{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Bytes |
| 13 | `upf_backlog_bytes_urllc` | `upf_queue_backlog_bytes{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Bytes |
| 14 | `upf_drops_embb` | `upf_packet_drops{snssai="01000001"}` | 5G Core UPF | VM-3 `oai-upf-slice1` | Drops / s |
| 15 | `upf_drops_urllc` | `upf_packet_drops{snssai="de00007b"}` | 5G Core UPF | VM-3 `oai-upf-slice2` | Drops / s |
| 16 | `ran_prb_cell1` | `ran_cell_prb_utilization{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | % (0–100) |
| 17 | `ran_prb_cell2` | `ran_cell_prb_utilization{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | % (0–100) |
| 18 | `ran_mcs_cell1` | `ran_cell_mcs{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Index (0–28) |
| 19 | `ran_mcs_cell2` | `ran_cell_mcs{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Index (0–28) |
| 20 | `ran_bler_cell1` | `ran_cell_bler{cell_id="1"}` | Split RAN L2 | VM-4 DU-1 (:4043) | Rasio (0.0–1.0) |
| 21 | `ran_bler_cell2` | `ran_cell_bler{cell_id="2"}` | Split RAN L2 | VM-4 DU-2 (:4044) | Rasio (0.0–1.0) |
| 22 | `ran_snr_cell1` | `ran_cell_snr_db{cell_id="1"}` | Split RAN L1/L2 | VM-4 DU-1 (:4043) | dB |
| 23 | `ran_snr_cell2` | `ran_cell_snr_db{cell_id="2"}` | Split RAN L1/L2 | VM-4 DU-2 (:4044) | dB |
| 24 | *(Ekstra Prom)* | `ran_cell_rssi_dbm{cell_id="X"}` | Split RAN L1 | VM-4 DU-X | dBm |
| 25 | *(Ekstra Prom)* | `ran_cell_ulsch_errors{cell_id="X"}` | Split RAN L2 | VM-4 DU-X | Counter |
| 26 | `rapp_diagnosed_bottleneck` | `rapp_diagnosed_bottleneck` | RIC Intelligence | VM-1 / VM-2 RIC | Enum (0–3) |
| 27 | `rapp_confidence` | `rapp_confidence` | RIC Intelligence | VM-1 / VM-2 RIC | Score (0.0–1.0) |
| 28 | *(Ekstra Prom)* | `a1_policy_threshold` | RIC Intelligence | VM-1 Non-RT RIC | ms |
| 29 | `event_scenario` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum |
| 30 | `event_domain` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum |
| 31 | `event_component` | *(Dataset Label)* | Ground Truth | VM-6 Operator | String Enum |

---

## 3. Detail Ekstraksi per Domain

---

### Domain 1: End-to-End UE QoS Experience (VM-5 `oai-ue`)

#### 1.1 Metrik yang Tersedia
1. **`e2e_slice1_throughput_mbps`**: Bitrate riil aplikasi UDP eMBB yang terkirim dari UE1 ke EXT-DN.
2. **`e2e_slice1_jitter_ms`**: Variasi keterlambatan paket UDP pada Slice 1.
3. **`e2e_slice2_latency_rtt_ms`**: Latensi pulang-pergi (Round-Trip Time) ICMP dari UE2 ke EXT-DN (`192.168.70.145`).
4. **`e2e_slice2_packet_loss_pct`**: Persentase kehilangan paket probe Slice 2.

#### 1.2 Cara Ekstraksi Manual di Shell (VM-5)
```bash
# Uji Throughput Slice 1 (eMBB) via iperf3 di namespace ue1:
sudo ip netns exec ue1 iperf3 -c 192.168.70.145 -u -b 25M -t 5 -i 1

# Uji Latensi Slice 2 (URLLC) via ICMP Canary di namespace ue2:
sudo ip netns exec ue2 ping -I oaitun_ue1 -c 4 -i 0.2 192.168.70.145
```

#### 1.3 Cara Ekstraksi Otomatis di Script
Dijalankan oleh [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh):
```bash
# Menjalankan trafik eMBB (iperf3 25M) dan URLLC (ping interval 100ms) simultan 30 detik:
cd /opt/oran/ue/scripts
sudo ./trafgen.sh start 30 25
```
*Mekanisme Pengiriman:* Di background, `trafgen.sh` mengekstrak hasil iperf/ping dan melakukan HTTP POST ke VM-6:
```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"slice": 1, "throughput_mbps": 23.4, "jitter_ms": 1.25}' \
  http://10.102.0.67:9100/report
```

---

### Domain 2: Split-RAN Radio & MAC Layer (VM-4 `oai-ran`)

#### 2.1 Metrik yang Tersedia
1. **`ran_cell_prb_utilization`**: Persentase utilisasi Resource Block MAC scheduler:
   $$\text{PRB Utilization (\%)} = \frac{\text{NPRB}}{106.0} \times 100\%$$
   *(106 PRB = Kapasitas bandwidth 40 MHz pada Subcarrier Spacing 30 kHz).*
2. **`ran_cell_mcs`**: Modulation and Coding Scheme aktif (0 s.d. 28) per UE per Cell.
3. **`ran_cell_bler`**: Block Error Rate (0.00000 s.d. 1.00000) pada kanal UL-SCH.
4. **`ran_cell_snr_db`**: Signal-to-Noise Ratio (dB) yang terukur pada antena penerima gNB.
5. **`ran_cell_rssi_dbm`**: Received Signal Strength Indicator (dBm).
6. **`ran_cell_ulsch_errors`**: Akumulasi kegagalan transmisi/dekode MAC layer.

#### 2.2 Cara Ekstraksi Manual di Shell (VM-4)
Tiap proses DU OAI (`du1` pada port `:4043` dan `du2` pada port `:4044`) mencetak statistik scheduler tiap detik ke logfile:
```bash
# Melihat baris telemetri radio terbaru pada Cell-1 (DU-1):
grep "NPRB" /opt/oran/ran/du1.log | tail -n 5

# Format baris asli OAI DU:
# UE 82c3: ulsch_rounds 3455040/0/0/0, ulsch_errors 0, ulsch_DTX 0, BLER 0.00000 MCS (0) 14 (Qm 4 deltaMCS 0) NPRB 51 SNR 25.7 (+2.7) RSSI -42.0 CCE fail 0
```

#### 2.3 Cara Ekstraksi Otomatis di Script
Dijalankan oleh daemon [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py):
```python
# Polling tail log du1.log & du2.log menggunakan regex:
RADIO_STATS_PATTERN = re.compile(
    r'ulsch_errors\s+(?P<errors>\d+).*?'
    r'BLER\s+(?P<bler>[0-9.]+).*?'
    r'MCS\s*(?:\([^)]*\))?\s*(?P<mcs>\d+).*?'
    r'NPRB\s+(?P<nprb>\d+).*?'
    r'SNR\s+(?P<snr>[-0-9.]+).*?'
    r'RSSI\s+(?P<rssi>[-0-9.]+)'
)
```
*Eksekusi di VM-4:*
```bash
cd /opt/oran/ran/scripts
python3 ran_adapter.py > ran_adapter.log 2>&1 &
```
*Payload yang dikirimkan ke `:9100/report`:*
```json
{
  "ran_cell_prb_utilization": {"1": 48.72, "2": 4.72},
  "ran_cell_radio_stats": {
    "1": {"nprb": 51, "mcs": 14, "bler": 0.0, "snr_db": 25.7, "rssi_dbm": -42.0, "ulsch_errors": 0},
    "2": {"nprb": 5, "mcs": 0, "bler": 0.0, "snr_db": 25.0, "rssi_dbm": -42.0, "ulsch_errors": 0}
  }
}
```

---

### Domain 3: 5G Core User-Plane & NWDAF (VM-3 `oai-core`)

#### 3.1 Metrik yang Tersedia
1. **`upf_interface_tx_mbps` / `rx_mbps`**: Throughput jaringan L3/IP pada interface UPF per slice.
2. **`upf_bytes_sent`**: Akumulasi total volume byte egress (sesuai 3GPP TS 28.552).
3. **`upf_queue_backlog_bytes`**: Kedalaman buffer antrian qdisc kernel pada interface egress UPF (dalam byte).
4. **`upf_packet_drops`**: Laju paket dibuang akibat antrian penuh atau pembatas trafik TBF (drops/detik).
5. **`nwdaf_slice_load_level`**: Skor utilisasi beban slice (0–100%) sesuai 3GPP TS 23.288 §6.3.

#### 3.2 Cara Ekstraksi Manual di Shell (VM-3)
```bash
# 1. Baca counter volume byte interface Linux di dalam container UPF Slice 1:
docker exec oai-upf-slice1 cat /proc/net/dev | grep eth0

# 2. Baca antrian qdisc, backlog buffer, dan packet drops:
docker exec oai-upf-slice1 tc -j -s qdisc show dev eth0
```
*Contoh output JSON dari `tc -j -s qdisc show`:*
```json
[
  {
    "kind": "tbf",
    "handle": "1:",
    "root": true,
    "bytes": 2854910,
    "packets": 1952,
    "drops": 145,
    "backlog": 124500,
    "qlen": 83
  }
]
```

#### 3.3 Cara Ekstraksi Otomatis di Script
Dijalankan oleh daemon [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py):
* Membaca counter dengan bracket timestamp presisi tinggi (monotonic midpoint).
* Menghitung rate delta:
  $$\Delta \text{rate} = \frac{\text{counter}_t - \text{counter}_{t-1}}{\Delta t_{\text{monotonic}}}$$
* Menyimpan rekaman lokal ke `./upf-telemetry/<RUN_ID>/telemetry.jsonl` dan `./telemetry.csv`.
* Mengirimkan laporan periodik secara asinkron ke `http://10.102.0.67:9100/report`.

*Eksekusi di VM-3:*
```bash
cd /opt/oran/5gc/scripts
python3 core_adapter.py --run-id PILOT_TEST > core_adapter.log 2>&1 &
```

---

### Domain 4: O-RAN RIC Intelligence (VM-1 & VM-2)

#### 4.1 Metrik yang Tersedia
1. **`rapp_diagnosed_bottleneck`**: Hasil klasifikasi inferensi model sequential rApp (Non-RT RIC VM-1):
   * `0`: **NORMAL** (Kondisi beban sehat, SLA terpenuhi).
   * `1`: **RAN Bottleneck** (Saturasi alokasi PRB / degradasi radio link).
   * `2`: **CORE Bottleneck** (Saturasi antrian buffer UPF / drop antrian qdisc).
   * `3`: **JOINT Bottleneck** (RAN dan Core mengalami kongesti secara simultan).
2. **`rapp_confidence`**: Nilai probabilitas/keyakinan model terhadap diagnosis (0.00 s.d. 1.00).
3. **`a1_policy_threshold`**: Ambang batas latensi SLA yang didefinisikan pada A1 Policy Type 20008 (ms).

#### 4.2 Cara Ekstraksi / Interaksi Manual
```bash
# Query A1 Policy aktif dari Non-RT RIC (VM-1):
curl -s http://10.102.0.166:8080/A1-P/v2/policytypes/20008/policies

# Response JSON A1 Policy Type 20008:
# {
#   "policy_ratio_id": "slice-steering-policy-01",
#   "urllc_sla_latency_threshold_ms": 20.0,
#   "target_cell_id": "Cell-1"
# }
```

---

### Domain 5: Ingesti, Prometheus Exporter & Dataset Logger (VM-6 `monitor`)

#### 5.1 Daemon Pengumpul ([`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py))
Berjalan pada port `:9100`:
* Endpoint Ingesti: `POST http://10.102.0.67:9100/report` (Menerima payload JSON dari VM-3, VM-4, VM-5).
* Endpoint Metrik: `GET http://10.102.0.67:9100/metrics` (Mengekspos format standar Prometheus).

*Cara Ekstraksi / Pengecekan Cepat di VM-6:*
```bash
# Periksa metrik radio:
curl -s http://127.0.0.1:9100/metrics | grep ran_cell

# Periksa metrik Core UPF & NWDAF:
curl -s http://127.0.0.1:9100/metrics | grep -E "upf_|nwdaf_"

# Periksa metrik End-to-End UE QoS:
curl -s http://127.0.0.1:9100/metrics | grep e2e_slice
```

#### 5.2 Pencatat Dataset Presisi ([`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py))
* Mengambil data dari `http://127.0.0.1:9100/metrics` setiap 1.000 detik menggunakan `time.monotonic()` (zero time drift).
* Menggabungkan anotasi skenario aktif dari `/opt/oran/monitoring/data/active_event.json`.
* Menyimpan secara instan (`flush=True`) ke `/opt/oran/monitoring/data/telemetry_raw_<RUN_ID>_<PID>.csv`.

*Cara Eksekusi Perekaman:*
```bash
cd /opt/oran/monitoring/scripts
python3 record_dual_stream.py RUN_01_TRAIN
```

#### 5.3 Anotator Skenario ([`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py))
* Digunakan untuk mencatat label *ground-truth* saat skenario dimulai:
```bash
# Injeksi label skenario:
python3 log_event.py S1 "Normal Beban Ringan"
python3 log_event.py S3 "Injeksi RAN Overload 40 Mbps"
python3 log_event.py S6 "Injeksi Core TBF Rate Limit 12 Mbps"
python3 log_event.py CLEAR "Kembali ke Normal"
```

#### 5.4 Auditor Statistik ([`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py))
* Menganalisis file dataset CSV terbaru berdasarkan `mtime`:
```bash
python3 analyze_dataset.py
```

---

## 4. Matriks Diagnostik Bottleneck (Korelasi Antar-Metrik)

Tabel berikut menunjukkan tanda fisik (*physical signature*) yang membedakan setiap kelas bottleneck berdasarkan metrik yang diekstrak:

| Kondisi Jaringan | Kelas Label | PRB C1 (`ran_prb`) | Radio MCS (`ran_mcs`) | Radio BLER (`ran_bler`) | Buffer UPF (`upf_backlog`) | Drops UPF (`upf_drops`) | URLLC RTT (`e2e_rtt`) |
|---|---|---|---|---|---|---|---|
| **Normal Ringan** (`S1`) | `NORMAL` (0) | $\approx 48\%$ | Tinggi ($\ge 14$) | $\approx 0.0$ | **`0 B`** | **`0`** | $< 15\text{ ms}$ (Aman) |
| **Normal Tinggi** (`S2`) | `NORMAL` (0) | $\approx 67\%$ | Tinggi ($\ge 14$) | $\approx 0.0$ | **`0 B`** | **`0`** | $\approx 20\text{ ms}$ (Mendekati limit) |
| **RAN Overload** (`S3`) | `RAN` (1) | **Jenuh ($\approx 100\%$)** | Turun / Tertekan | Positif / Error | **`0 B`** | **`0`** | $> 25\text{ ms}$ (SLA Terlanggar) |
| **Core TBF Congestion** (`S6`) | `CORE` (2) | Rendah ($< 25\%$) | Normal | $\approx 0.0$ | **Melonjak ($> 100\text{ KB}$)** | **Positif ($> 0$)** | $> 25\text{ ms}$ (SLA Terlanggar) |
| **Joint Overload** (`S9`) | `JOINT` (3) | **Jenuh ($\approx 100\%$)** | Turun | Positif | **Melonjak ($> 100\text{ KB}$)** | **Positif ($> 0$)** | $> 35\text{ ms}$ (Kritis) |

---

## 5. Ringkasan Lokasi File Skrip di Repository

* Script Adapter RAN: [`scripts/ran_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/ran_adapter.py)
* Script Adapter Core: [`scripts/core_adapter.py`](file:///d:/Idhul/Program/Thesis/scripts/core_adapter.py)
* Script Generator Trafik UE: [`scripts/trafgen.sh`](file:///d:/Idhul/Program/Thesis/scripts/trafgen.sh)
* Script Collector Telemetri: [`scripts/telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py)
* Script Perekam Dataset: [`scripts/record_dual_stream.py`](file:///d:/Idhul/Program/Thesis/scripts/record_dual_stream.py)
* Script Event Logger: [`scripts/log_event.py`](file:///d:/Idhul/Program/Thesis/scripts/log_event.py)
* Script Analisis Dataset: [`scripts/analyze_dataset.py`](file:///d:/Idhul/Program/Thesis/scripts/analyze_dataset.py)
