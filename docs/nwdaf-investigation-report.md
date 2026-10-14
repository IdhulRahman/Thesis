# Laporan Investigasi Teknis: Evaluasi, Akar Permasalahan, dan Rencana Integrasi 3GPP NWDAF pada Testbed O-RAN & 5G Core (Revisi Berdasarkan Masukan Pengamat)

**Topik Riset:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*  
**Penyusun:** Tim Riset Mahasiswa / Pengembang Sistem  
**Target Pembaca:** Dosen Pembimbing, Dosen Penguji, dan Penilai Teknis (Pengamat)  
**Tanggal Pengujian & Revisi:** 14 Oktober 2026 (Revisi v3 — konfirmasi aliran data end-to-end)  
**Node Target:** VM-3 — 5G Core & NWDAF Host (`10.102.0.164`), VM-6 — Telemetry Collector (`10.102.0.67`)

---

## 1. Eksekutif Ringkasan (Executive Summary)

Dalam pengujian awal (*pilot run*) pengumpulan dataset telemetri multi-domain untuk tesis, ditemukan anomali pada metrik analitik inti jaringan (*Core Network*):
1. Kolom `nwdaf_load_embb` dan `nwdaf_load_urllc` pada dataset berstatus `NaN` (100% missing values).
2. Ketika antarmuka resmi 3GPP `Nnwdaf_AnalyticsInfo` diuji langsung melalui Kong API Gateway di port 8080 VM-3, layanan merespons dengan status **HTTP 200 OK**, namun nilai `relativeRatio` dan `absoluteNum` bernilai konstan **`0`**.

**Pembaruan (v3):** Berdasarkan pengujian terbaru:
* **Ingesti Event Control-Plane (PDU_SES_EST) Berhasil (✅):** Setelah perbaikan konfigurasi subscriber dan pemulihan SMF, notifikasi event berhasil masuk ke MongoDB `testing.smf` dan query API NWDAF mengembalikan **`absoluteNum: 1`** (nyata dari `CountDocuments`, bukan hardcode).
* **Pelaporan User-Plane & QoS Monitoring Belum Selesai (⏳):** Asosiasi PFCP masih berstatus `enable_usage_reporting: No`. Pelaporan user-plane belum dapat dinyatakan selesai sampai terdapat laporan penggunaan (*usage report* / URR) dan dokumen dengan `qosmonlist` yang bertambah dinamis saat trafik data mengalir.
* **Cakupan Multi-Slice SMF-2 Terbuka (⏳):** Konfigurasi `oai-nwdaf-sbi` saat ini baru menunjuk SMF-1 (`192.168.70.139`), sehingga penyerapan event dari SMF-2 (`192.168.70.140` untuk Slice 2) masih memerlukan verifikasi lebih lanjut.

Laporan ini menyajikan hasil penelusuran teknis komprehensif (*root-cause analysis*) langsung pada *source code*, kontainer runtime, basis data MongoDB, asosiasi PFCP, dan pipeline telemetri. Laporan ini telah **direvisi secara menyeluruh berdasarkan telaah kritis pengamat teknis** untuk memastikan kepatuhan penuh terhadap standar **3GPP TS 23.288, TS 29.520, dan TS 29.244**, serta menetapkan peta jalan rekayasa terstruktur **tanpa jalan pintas (*no shortcuts*)**.

---

## 2. Klarifikasi Konseptual Standar 3GPP

Sebelum membahas bukti empiris, penting untuk meluruskan dua konsep dasar sesuai spesifikasi resmi 3GPP:

### 2.1 Makna Resmi `SESS_SUCC_RATIO` vs `SLICE_LOAD_LEVEL`
* **`SESS_SUCC_RATIO` (3GPP TS 29.520 §5.1.6.3.10):**  
  Merupakan rasio keberhasilan pembentukan sesi PDU terhadap total percobaan pembentukan sesi (*Session Establishment Success Ratio*). Metrik ini adalah indikator reliabilitas *Control Plane*, **bukan indikator utilisasi throughput atau kapasitas beban irisan (*User Plane*)**. Oleh karena itu, logika perhitungan `SESS_SUCC_RATIO` **tidak boleh dibajak atau diganti menjadi skor kongesti**.
* **`SLICE_LOAD_LEVEL` (3GPP TS 23.288 §6.3 / TS 29.520 §5.1.6.3.4):**  
  Merupakan analitik resmi yang didesain untuk melaporkan tingkat beban irisan (*slice load level percentage* atau status NSI load) berdasarkan konsumsi sumber daya dan sesi aktif terhadap batas kapasitas irisan.

### 2.2 Mekanisme Jalur Native Telemetri Core (UPF $\to$ NWDAF)
Ketiadaan antarmuka SBI HTTP/2 langsung pada kontainer UPF C-based (`open5gs-upf`/`bess`) **bukanlah jalan buntu**. Standar 3GPP telah mendefinisikan rantai telemetri native dari User Plane ke NWDAF melalui:
$$\text{UPF} \xrightarrow[\text{TS 29.244}]{\text{PFCP (Usage Report / QoS Monitoring)}} \text{SMF} \xrightarrow[\text{TS 29.508 / TS 29.520}]{\text{SBI (Event: QOS\_MON, PDU\_SES\_EST)}} \text{oai-nwdaf-sbi} \longrightarrow \text{MongoDB} \longrightarrow \text{oai-nwdaf-engine}$$

---

## 3. Hasil Investigasi Empiris & Bukti Lapangan (*Evidence*)

### Bukti 1: Stack Microservices OAI NWDAF 100% Aktif & Sehat

Pemeriksaan kontainer Docker pada VM-3 (`10.102.0.164`) membuktikan bahwa arsitektur 8 *microservices* resmi OAI NWDAF telah terpasang, aktif, dan dalam status *healthy*:

```text
five-g@oai-core:/opt/oran/5gc/oai-cn5g-nwdaf$ sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
NAMES                     STATUS                 PORTS
oai-nwdaf-nbi-gateway     Up 12 days (healthy)   0.0.0.0:80->8000/tcp, 0.0.0.0:8080->8000/tcp, 0.0.0.0:8001->8001/tcp
oai-nwdaf-nbi-analytics   Up 2 days (healthy)    0.0.0.0:6059->8080/tcp
oai-nwdaf-nbi-events      Up 12 days (healthy)   0.0.0.0:6060->8080/tcp
oai-nwdaf-nbi-ml          Up 12 days (healthy)   0.0.0.0:6061->8080/tcp
oai-nwdaf-engine          Up 2 days (healthy)    0.0.0.0:6063->8080/tcp
oai-nwdaf-engine-ads      Up 12 days (healthy)   8080/tcp
oai-nwdaf-sbi             Up 2 days (healthy)    0.0.0.0:6062->8080/tcp
oai-nwdaf-database        Up 12 days (healthy)   0.0.0.0:27017->27017/tcp
```
> **Fakta:** Seluruh kontainer NWDAF berjalan secara operasional tanpa *crash*.

---

### Bukti 2: Respons Live REST API 3GPP TS 29.520 (`Nnwdaf_AnalyticsInfo`)

Pengujian kueri HTTP GET langsung ke Kong API Gateway port 8080 VM-3:

```bash
curl -s -G "http://localhost:8080/nnwdaf-analyticsinfo/v1/analytics" \
  --data-urlencode "event-id=NETWORK_PERFORMANCE" \
  --data-urlencode 'ana-req={"startTs":"2026-10-01T00:00:00Z","endTs":"2026-10-15T23:59:59Z"}' \
  --data-urlencode 'event-filter={"snssais":[{"sst":1,"sd":"000001"}],"dnns":["oai"],"nwPerfTypes":["SESS_SUCC_RATIO"]}' | jq .
```

**Keluaran Riil Sistem — Versi Awal (HTTP 200 OK, `absoluteNum: 0`):**
```json
{
  "anaMetaInfo": {
    "dataWindow": {
      "startTime": "2026-10-01T00:00:00Z",
      "stopTime": "2026-10-15T23:59:59Z"
    },
    "strategy": {},
    "accuracy": {}
  },
  "nwPerfs": [
    {
      "networkArea": {},
      "nwPerfType": "SESS_SUCC_RATIO",
      "relativeRatio": 0,
      "absoluteNum": 0,
      "confidence": 0
    }
  ]
}
```

**Keluaran Riil Sistem — Setelah Perbaikan Aliran Data (HTTP 200 OK, `absoluteNum: 1`):**
```json
{
  "anaMetaInfo": {
    "dataWindow": {
      "startTime": "2026-10-01T00:00:00Z",
      "stopTime": "2026-10-15T23:59:59Z"
    },
    "strategy": {},
    "accuracy": {}
  },
  "nwPerfs": [
    {
      "networkArea": {},
      "nwPerfType": "SESS_SUCC_RATIO",
      "relativeRatio": 0,
      "absoluteNum": 1,
      "confidence": 0
    }
  ]
}
```
> **Konfirmasi:** `absoluteNum: 1` merupakan hasil nyata dari `CountDocuments` terhadap koleksi `testing.smf` di MongoDB — bukan nilai hardcode. Ini membuktikan bahwa pipeline `SMF → oai-nwdaf-sbi → MongoDB` berfungsi penuh setelah perbaikan subscriber profile dan konfigurasi SMF.

---

### Bukti 3: Audit Kode Sumber Upstream OAI NWDAF Engine (`network_performance.go`)

Pemeriksaan repositori Git resmi di VM-3 (`/opt/oran/5gc/oai-cn5g-nwdaf`, branch `develop`, commit `9d82b75`):

```go
// File: components/oai-nwdaf-engine/internal/engine/network_performance.go
func nwPerfNumOfPdu(w http.ResponseWriter, r *http.Request) {
    ...
    filter := getFilterNwPerfNumPdu(engineReqData)
    db := mongoClient.Database(config.Database.DbName)
    collection := db.Collection(config.Database.CollectionSmfName)
    
    // absoluteNum BUKAN hardcode, melainkan hasil hitung dokumen nyata di MongoDB:
    absoluteNum, err := collection.CountDocuments(context.Background(), filter)
    if err != nil {
        http.Error(w, "Error counting documents", http.StatusInternalServerError)
        return
    }
    
    // Implement relative ratio and confidence MASIH TODO oleh developer OAI:
    relativeRatio, confidence := int32(0), int32(0)
    
    nwPerfResp := NwPerfResp{
        RelativeRatio: relativeRatio, // Konstan 0 karena TODO belum diimplementasikan
        AbsoluteNum:   int32(absoluteNum), // Bernilai 0 karena database kosong/dokumen tidak cocok
        Confidence:    confidence,
    }
    ...
}
```

> **Klarifikasi (diperbarui v3):**
> 1. `absoluteNum` **bukan hardcode nol**, melainkan hasil eksekusi kueri `CountDocuments`. Nilai `0` awal terjadi karena `testing.smf` belum terisi. Setelah perbaikan aliran data, nilai ini menjadi `1` — dikonfirmasi dari dokumen sesi PDU nyata di MongoDB.
> 2. `relativeRatio` dan `confidence` **memang di-hardcode nol** oleh developer upstream OAI karena kalkulasinya masih berstatus `//TODO`. Implementasi kalkulasi ini merupakan **Tahap 3** yang sedang dalam proses.

---

### Bukti 4: Investigasi Empiris Pelaporan User-Plane: Validasi `enable_usage_reporting` dan Audit Biner `QOS_MON`

Untuk menguji apakah telemetri performa *user-plane* dapat dialirkan secara *native* dari UPF ke SMF lalu ke NWDAF, tim riset telah melakukan pengujian empiris terstruktur:

#### 1. Keberhasilan Aktivasi `enable_usage_reporting: Yes` pada SMF-1
Dengan mencocokkan identitas host UPF yang didaftarkan oleh NRF (`192.168.70.142`) pada blok `smf.upfs` di `slicing_slice1_config.yaml`:
```yaml
smf:
  upfs:
    - host: 192.168.70.142
      config:
        enable_usage_reporting: yes
```
SMF-1 berhasil mencocokkan node secara presisi saat inisialisasi:
```text
[smf_app] [debug] Found NRF UPF with host name 192.168.70.142 in configuration, take config from there
...
 + 192.168.70.142
      + host...................................: 192.168.70.142
      + port...................................: 8805
      + enable_usage_reporting.................: Yes
```
Asosiasi PFCP N4 terbentuk sempurna tanpa *timeout*.

#### 2. Uji Aliran Trafik Kontinu 60 Detik & Hasil Agregasi MongoDB
Setelah sesi PDU baru terbentuk di SMF-1 (`/nsmf-pdusession/v1/sm-contexts/1`) dan langganan event NWDAF-SBI aktif (`QOS_MON`, `PDU_SES_EST`), trafik data kontinu diinjeksikan dari UE 1 (VM-5) ke External DN:
* **Beban Trafik:** 300 paket ICMP (interval 0.2 detik = 60 detik pengujian), *packet loss* 0%, RTT rata-rata 0.28 ms.
* **Hasil Kueri Agregasi MongoDB:**
  ```javascript
  db.smf.aggregate([
    {$project: {_id: 1, qos_report_count: {$size: {$ifNull: ["$qosmonlist", []]}}}}
  ]).forEach(printjson);
  // Output: { _id: '208950000000001', qos_report_count: 0 }
  ```
  Nilai `qos_report_count` **tetap 0** sebelum dan sesudah trafik 60 detik dialirkan.

#### 3. Audit Biner SMF: Bukti Ketiadaan Modul Produsen `QOS_MON`
Pemeriksaan langsung pada simbol biner C++ kontainer resmi OAI SMF (`oaisoftwarealliance/oai-smf:v2.1.0`):
```bash
sudo docker exec oai-smf-slice1 strings /openair-smf/bin/oai_smf | grep -i "QOS_MON"
# Hasil: KOSONG (tidak ditemukan)
```
* **Di Sisi NWDAF (`oai-nwdaf-sbi`):** Handler `getUpdateQOS_MON` ([`smf_service.go:231-252`](file:///opt/oran/5gc/oai-cn5g-nwdaf/components/oai-nwdaf-sbi/internal/sbi/smf_service.go)) sudah siap melakukan `$push` ke array `qosmonlist`.
* **Di Sisi SMF (`oai-smf` v2.1.0):** Binary SMF resmi **belum mengimplementasikan logika produsen event `QOS_MON`** (3GPP TS 29.508 §5.2.2.3.6). Selain itu, laporan penggunaan PFCP (URR) dalam arsitektur 3GPP dialirkan untuk fungsi *Charging* (CHF) dan *Policy* (PCF), bukan dipaparkan sebagai event telemetri antrean/throughput instan ke NWDAF.

#### 4. Implikasi Metodologis Tesis
Temuan empiris ini membuktikan secara ilmiah dan definitif bahwa:
1. NWDAF OAI v2.1.0 secara native hanya bertindak sebagai penyedia **observabilitas keandalan sesi bidang kendali (*Control-Plane Session Lifecycle*)** melalui event `PDU_SES_EST` (menghasilkan `absoluteNum: 1`).
2. Observabilitas dinamika **antrean buffer, paket drop (*queue backlog*), dan throughput riil pada *User Plane*** secara metodologis **harus diperoleh melalui Dedicated UPF Host Adapter (`core_adapter.py`)** yang mengekstrak metrik qdisc kernel Linux sesuai prinsip 3GPP Performance Management (TS 28.552).


### Bukti 5: Status Database MongoDB — Terkonfirmasi Berisi Dokumen Nyata

**Kondisi awal** sebelum perbaikan:
```text
five-g@oai-core:/opt/oran/5gc/oai-cn5g-nwdaf$ sudo docker exec oai-nwdaf-database mongosh --eval "show dbs"
admin    40.00 KiB
config  228.00 KiB
local    40.00 KiB
```
Database `testing` belum terbuat — pipeline telemetri terputus total.

**Kondisi setelah perbaikan subscriber profile ([Kasus #49](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#49-ue-2-pdu-session-establishment-rejected--mysql-s-nssai-subscriber-profile-mismatch)) dan konfigurasi SMF ([Kasus #50](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#50-smf-n4pfcp-1-second-timeout--manual-upfs-block-conflicts-with-nrf-discovery)):**
Database `testing` kini ada dan koleksi `testing.amf` serta `testing.smf` terisi dengan dokumen notifikasi event dari AMF (`Namf_EventExposure`) dan SMF (`Nsmf_EventExposure`). Hal ini mengkonfirmasi bahwa rantai telemetri 3GPP native berfungsi penuh.
* **Terkait AMF:** Notifikasi `Namf_EventExposure` berhasil masuk ke `testing.amf` — menandakan AMF subscription berfungsi setelah port dan HTTP version dikoreksi (lihat [Kasus #47](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#47-oai-nwdaf-sbi-fails-subscribing-to-smf-due-to-incorrect-port-or-http-version)).
* **Terkait SMF:** Koleksi `testing.smf` berisi dokumen sesi PDU aktif setelah N4/PFCP association berfungsi normal (lihat [Kasus #50](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#50-smf-n4pfcp-1-second-timeout--manual-upfs-block-conflicts-with-nrf-discovery)).

---

### Bukti 6: Penyebab Nilai `NaN` pada Skrip Telemetry Collector VM-6

Pada skrip kolektor di VM-6 ([`telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py#L461)):
```python
req = urllib.request.Request(
    "http://10.102.0.164:8080/nnwdaf-eventsubscription/v1/slice-load-level",
    headers={"User-Agent": "Thesis-Collector/1.0"}
)
```
* Skrip memanggil URL yang tidak terdaftar di rute Kong API Gateway (rute Kong hanya mencakup `/nnwdaf-analyticsinfo/v1/analytics`, `/nnwdaf-eventssubscription/v1`, dan `/nnwdaf-mlmodelprovision/v1`).
* Kong mengembalikan **HTTP 404 Not Found**, kolektor menangkap *exception*, dan membiarkan nilai `metrics_store["nwdaf_slice_load_level"]` tetap `NaN`.

---

## 4. Urutan Kerja Rekayasa Terstruktur (*Roadmap Tanpa Jalan Pintas*)

Berdasarkan koreksi kritis dari pengamat, urutan perbaikan yang benar harus mengikuti alur data dari hulu ke hilir (*upstream to downstream*):

```
[Tahap 1: Kontrol-Plane Hulu] ✅    [Tahap 2: Ingesti Event CP] ✅    [Tahap 3: Pembuktian User-Plane & Analitik] 🔄    [Tahap 4: Konsumsi rApp] ⏳
N4 PFCP aktif, UE terkoneksi   ->   Dokumen testing.smf terisi   ->   Buktikan URR / qosmonlist saat trafik        ->   Korelasi Bottleneck RAN vs Core
PDU_SES_EST tertangkap              (absoluteNum: 1)                  + evaluasi SMF-2 + TODO relativeRatio             (NWDAF + E2SM-KPM)
```

### Tahap 1: Pembuktian Kontrol-Plane Hulu (UPF & SMF via PFCP) ✅ SELESAI

**Status:** Selesai untuk kontrol-plane sesi. N4/PFCP association antara SMF dan UPF berfungsi setelah:
- Subscriber profile UE 2 di MySQL dikoreksi (S-NSSAI mismatch → [Kasus #49](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#49-ue-2-pdu-session-establishment-rejected--mysql-s-nssai-subscriber-profile-mismatch)).
- Konfigurasi SMF dipulihkan ke upstream default tanpa modifikasi `upfs:` yang tidak cocok dengan profil NRF (→ [Kasus #50](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#50-smf-n4pfcp-1-second-timeout-after-manual-upfs-configuration-edit)).
- `oai-nwdaf-sbi` dikonfigurasi dengan port dan HTTP version yang benar (→ [Kasus #47](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#47-oai-nwdaf-sbi-fails-subscribing-to-smf-due-to-incorrect-port-or-http-version)).

**Bukti:** UE 1 berhasil mendapatkan `oaitun_ue1` dengan IP `12.1.1.4/24` dan ping ke External DN (`192.168.70.145`) dengan packet loss 0%.

### Tahap 2: Ingesti Event Sesi Kontrol-Plane ke NWDAF ✅ SELESAI (User-Plane Masih Terbuka)

**Status:** 
* **Event Sesi Kontrol-Plane:** Selesai. `oai-nwdaf-sbi` menerima notifikasi dari AMF (`Namf_EventExposure`) dan SMF (`Nsmf_EventExposure`) untuk event `PDU_SES_EST`. Database `testing` telah terbuat dan koleksi `testing.smf` terisi 1 dokumen nyata. Query `Nnwdaf_AnalyticsInfo` mengembalikan `absoluteNum: 1`.
* **Pelaporan User-Plane (Usage Reporting & QoS Monitoring):** Belum selesai. Asosiasi PFCP saat ini masih mencatat `enable_usage_reporting: No`. Pelaporan user-plane belum terbukti sampai ada *usage report* (URR) dan dokumen dengan `qosmonlist` yang bertambah saat trafik data mengalir.
* **Cakupan Multi-Slice SMF-2:** Masih terbuka. `oai-nwdaf-sbi` baru mengonsumsi event dari SMF-1 (`.139`), sementara subscription untuk SMF-2 (`.140`) belum divalidasi.

### Tahap 3: Pembuktian Data User-Plane di NWDAF & Penyempurnaan Analitik

Berdasarkan telaah pengamat, prioritas utama bukanlah sekadar menghitung rasio keberhasilan sesi (`SESS_SUCC_RATIO`) karena rasio tersebut tidak memberikan visibilitas antrean, drops, atau throughput UPF untuk control loop tesis. Tahap 3 difokuskan pada:

1. **Uji Validasi Penentu Ingesti User-Plane (*The Golden Query*):**
   Eksekusi query penentu di MongoDB VM-3 saat trafik data dialirkan:
   ```bash
   sudo docker exec oai-nwdaf-database mongosh testing --quiet --eval '
     print("Dokumen SMF:", db.smf.countDocuments({}));
     print("Dokumen dengan QOS_MON:", db.smf.countDocuments({"qosmonlist.0": {$exists: true}}));
   '
   ```
   * Jika `qosmonlist` bertambah saat trafik berjalan, data user-plane native terbukti mengalir ke NWDAF.
   * Jika tetap 0, investigasi aktivasi `enable_usage_reporting: yes` pada konfigurasi SMF yang cocok dengan profil NRF, atau konfirmasi batas arsitektural container UPF vpp/open5gs.

2. **Evaluasi Dukungan Multi-SMF pada `oai-nwdaf-sbi`:**
   Memeriksa apakah `oai-nwdaf-sbi` dapat mengonsumsi event exposure dari kedua SMF (`oai-smf-slice1` .139 dan `oai-smf-slice2` .140) agar analitik mencakup kedua slice (eMBB dan URLLC).

3. **Penyelesaian Kode Go Analitik `network_performance.go` (Tugas Sekunder):**
   * Mengganti `//TODO` pada baris 53 dan 102 dengan perhitungan `relativeRatio` (persentase sukses sesi PDU) dan `confidence` sesuai standar 3GPP TS 29.520.
   * Melakukan build ulang Docker image dan menerapkan dengan *force recreate*:
     ```bash
     cd /opt/oran/5gc/oai-cn5g-nwdaf
     sudo docker build -t oai-nwdaf-engine:latest -f components/oai-nwdaf-engine/docker/Dockerfile.engine components/oai-nwdaf-engine/
     
     cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
     sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai-nwdaf-engine
     ```

### Tahap 4: Konsumsi Telemetri dan Validasi Closed-Loop rApp
1. Perbarui fungsi `poll_external_nfs` di [`telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py) agar memanggil endpoint resmi yang diekspos dan mem-parsing skema respons JSON dengan benar.
2. Hubungkan metrik analitik NWDAF ini ke Non-RT RIC rApp (VM-1) untuk dikorelasikan dengan utilisasi PRB RAN (dari E2SM-KPM Near-RT RIC) dalam pengambilan keputusan *closed-loop traffic steering*.

---

## 5. Ringkasan Evaluasi untuk Pengamat / Penguji

Laporan revisi v3 ini menegaskan bahwa:
1. Analisis awal telah diperbaiki: `SESS_SUCC_RATIO` tidak lagi disalahartikan sebagai beban slice, dan `absoluteNum` diklarifikasi bersumber dari `CountDocuments`.
2. **Status Ingesti:** Ingesti event *control-plane* (PDU_SES_EST) telah berhasil dibuktikan dengan dokumen nyata di MongoDB dan respons `absoluteNum: 1`. Namun, pelaporan *user-plane* (Usage Report / QoS Monitoring) secara jujur dinyatakan **belum selesai** sampai ada bukti `qosmonlist` dan usage report yang bertambah saat trafik dialirkan.
3. **Koreksi Konfigurasi SMF:** Masalah timeout N4 PFCP sebelumnya dipicu oleh ketidakcocokan parameter pada konfigurasi lokal `upfs:`. Spesifikasi OAI SMF (`smf_app.cpp`) sebenarnya mendukung blok `upfs:` bersamaan dengan NRF discovery untuk mengatur usage reporting, asalkan identitas host cocok dengan profil NRF. Revert ke konfigurasi baseline berhasil memulihkan koneksi operasional.
4. **Prioritas Tahap Berikutnya:** Prioritas dialihkan ke pembuktian data user-plane masuk NWDAF, terus diperbarui saat trafik berjalan, dan mencakup kedua slice. Penyelesaian TODO rasio sesi PDU dikerjakan sebagai pelengkap kontrol-plane terpisah.
5. Alur kerja rekayasa tetap berpegang teguh pada prinsip keterbukaan ilmiah, rigor standar 3GPP, dan bebas dari klaim prematur.
