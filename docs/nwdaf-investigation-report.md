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

**Pembaruan (v3):** Setelah perbaikan aliran data NWDAF (Tahap 1 & 2 selesai), `absoluteNum` kini mengembalikan **`1`** — dikonfirmasi berasal dari dokumen nyata di MongoDB `testing.smf`. Nilai `relativeRatio` dan `confidence` masih `0` karena kalkulasinya berstatus `//TODO` dalam kode sumber upstream OAI (Tahap 3 — dalam proses).

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

### Bukti 4: Status Pelaporan Beban User-Plane: `enable_usage_reporting: No` pada PFCP Asosiasi UPF

Pada penelusuran status asosiasi PFCP antara SMF dan UPF di VM-3:
* Teramati bahwa asosiasi UPF memiliki parameter operasional: **`enable_usage_reporting: No`**.
* **Implikasi Nyata:** Ketika *usage reporting* bernilai `No`, UPF tidak akan mengirimkan Usage Reports (URR) maupun metrik volume data ke SMF melalui antarmuka PFCP (N4).
* Hal ini menjelaskan mengapa metrik *load user-plane* (volume/throughput dinamis) tidak tersedia melalui pipeline SMF-NWDAF. Namun untuk **notifikasi siklus hidup sesi bidang kendali (*control-plane session establishment*)**, SMF menanganinya secara mandiri via layanan `Nsmf_EventExposure` tanpa bergantung pada URR UPF.

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
[Tahap 1: Hulu UPF-SMF] ✅   [Tahap 2: Ingesti Data] ✅   [Tahap 3: Engine Analitik] 🔄   [Tahap 4: Konsumsi] ⏳
N4 PFCP berfungsi,        ->  SMF → MongoDB terisi     ->  Implementasi relativeRatio  ->  rApp & Collector
subscriber profile benar      (testing.smf: 1 doc)         dan confidence (TODO)           (Korelasi Bottleneck)
```

### Tahap 1: Aktifkan dan Buktikan Pelaporan Native di Hulu (UPF & SMF via PFCP) ✅ SELESAI

**Status:** Selesai. N4/PFCP association antara SMF dan UPF berfungsi penuh setelah:
- Subscriber profile UE 2 di MySQL dikoreksi (S-NSSAI mismatch → [Kasus #49](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#49-ue-2-pdu-session-establishment-rejected--mysql-s-nssai-subscriber-profile-mismatch)).
- Konfigurasi SMF dipulihkan ke upstream default tanpa `upfs:` block manual (→ [Kasus #50](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#50-smf-n4pfcp-1-second-timeout--manual-upfs-block-conflicts-with-nrf-discovery)).
- `oai-nwdaf-sbi` dikonfigurasi dengan port dan HTTP version yang benar (→ [Kasus #47](file:///d:/Idhul/Program/Thesis/docs/troubleshooting.md#47-oai-nwdaf-sbi-fails-subscribing-to-smf-due-to-incorrect-port-or-http-version)).

**Bukti:** UE 1 berhasil mendapatkan `oaitun_ue1` dengan IP `12.1.1.4/24` dan ping ke External DN (`192.168.70.145`) dengan packet loss 0%.

### Tahap 2: Pastikan Data Mengalir dan Masuk ke Basis Data NWDAF ✅ SELESAI

**Status:** Selesai. Terkonfirmasi:
1. `oai-nwdaf-sbi` menerima notifikasi dari AMF (`Namf_EventExposure`) dan SMF (`Nsmf_EventExposure`) untuk event `PDU_SES_EST`.
2. Database `testing` telah terbuat di MongoDB. Koleksi `testing.amf` dan `testing.smf` terisi dokumen event.
3. Query `Nnwdaf_AnalyticsInfo` via Kong Gateway mengembalikan `absoluteNum: 1` — diambil dari `CountDocuments` pada `testing.smf`.

### Tahap 3: Implementasikan Analitik Core yang Sesuai & Terapkan dengan Benar
1. **Pemisahan Semantik Analitik:**
   * Jangan mengubah makna `SESS_SUCC_RATIO` (tetap sebagai rasio sukses sesi PDU).
   * Implementasikan handler analitik yang relevan untuk performa irisan (misalnya mengaktifkan atau melengkapi analitik `SLICE_LOAD_LEVEL` sesuai **3GPP TS 23.288 §6.3** atau mengekstrak performa latensi/beban dari dokumen `QOS_MON` di database).
2. **Prosedur Pembaruan Kontainer Docker yang Benar:**
   Setelah kode Go pada `oai-nwdaf-engine` dikompilasi ulang menjadi image baru, kontainer **harus dibuat ulang (*recreate*)**, bukan sekadar di-restart:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-nwdaf
   sudo docker build -t oai-nwdaf-engine:latest -f components/oai-nwdaf-engine/docker/Dockerfile.engine components/oai-nwdaf-engine/
   
   # Gunakan force-recreate agar kontainer baru memuat image baru:
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate oai-nwdaf-engine
   ```

### Tahap 4: Konsumsi dan Validasi End-to-End
1. Perbarui fungsi `poll_external_nfs` di [`telemetry_collector.py`](file:///d:/Idhul/Program/Thesis/scripts/telemetry_collector.py) agar memanggil endpoint resmi yang diekspos dan mem-parsing skema respons JSON dengan benar.
2. Hubungkan metrik analitik NWDAF ini ke Non-RT RIC rApp (VM-1) untuk dikorelasikan dengan utilisasi PRB RAN (dari E2SM-KPM Near-RT RIC) dalam pengambilan keputusan *closed-loop traffic steering*.

---

## 5. Ringkasan Evaluasi untuk Pengamat / Penguji

Laporan revisi v3 ini menegaskan bahwa:
1. Analisis awal telah diperbaiki: `SESS_SUCC_RATIO` tidak lagi disalahartikan sebagai beban slice, dan `absoluteNum` diklarifikasi bersumber dari `CountDocuments`.
2. **Tahap 1 & 2 telah selesai:** Aliran data end-to-end dari 5GC (UE → SMF → oai-nwdaf-sbi → MongoDB) terkonfirmasi berfungsi. `absoluteNum` mengembalikan nilai nyata `1` dari database, bukan hardcode.
3. **Masalah yang diselesaikan dalam iterasi ini:** (a) Subscriber profile UE 2 di MySQL dikoreksi; (b) Konfigurasi SMF dipulihkan dari `.bak` untuk menghapus `upfs:` block yang menyebabkan konflik N4 topology; (c) Semua core service di-restart untuk membersihkan state stale.
4. **Tahap 3 (dalam proses):** Implementasi kalkulasi `relativeRatio` (Session Establishment Success Ratio nyata) dan `confidence` pada `network_performance.go`, diikuti rebuild image Docker dan validasi akhir.
5. Rencana rekayasa tidak lagi mengasumsikan "cukup ganti TODO dan URL", melainkan mengikuti alur 4 tahap komprehensif: **Mengaktifkan & memvalidasi N4 PFCP $\to$ Memvalidasi ingesti di MongoDB ✅ $\to$ Mengimplementasikan analitik dan me-recreate kontainer 🔄 $\to$ Mengonsumsi hasil di rApp ⏳.**
