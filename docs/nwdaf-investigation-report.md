# Laporan Investigasi Teknis: Evaluasi, Akar Permasalahan, dan Bukti Empiris Modul 3GPP NWDAF pada Testbed O-RAN & 5G Core

**Topik Riset:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*  
**Penyusun:** Tim Riset Mahasiswa / Pengembang Sistem  
**Target Pembaca:** Dosen Pembimbing, Dosen Penguji, dan Penilai Teknis (Pengamat)  
**Tanggal Pengujian:** 14 Oktober 2026  
**Node Target:** VM-3 — 5G Core & NWDAF Host (`10.102.0.164`), VM-6 — Telemetry Collector (`10.102.0.67`)

---

## 1. Eksekutif Ringkasan (Executive Summary)

Dalam pengujian awal (*pilot run*) pengumpulan dataset telemetri multi-domain untuk tesis, ditemukan anomali pada kolom analitik inti jaringan (*Core Network*):
1. Kolom `nwdaf_load_embb` dan `nwdaf_load_urllc` pada dataset berstatus `NaN` (100% missing values).
2. Ketika antarmuka resmi 3GPP `Nnwdaf_AnalyticsInfo` diuji langsung melalui Kong API Gateway di port 8080, layanan mengembalikan status **HTTP 200 OK**, namun nilai analitik performa jaringan (*relativeRatio*) selalu bernilai konstan **`0`**.

Laporan ini menyajikan hasil penelusuran teknis komprehensif (*root-cause analysis*) langsung pada *source code*, container runtime, basis data MongoDB, dan pipeline telemetri. Ditemukan bukti tak terbantahkan (*smoking gun*) bahwa kendala ini bersumber dari **keterbatasan implementasi internal upstream OpenAirInterface (OAI) NWDAF branch `develop` terbaru**, serta ketidakcocokan URL pada skrip kolektor telemetri. Laporan ini juga menguraikan solusi berstandar 3GPP **tanpa jalan pintas (*no shortcuts*)** untuk menyempurnakan modul analitik OAI NWDAF secara sah di level kode sumber.

---

## 2. Latar Belakang & Peran NWDAF dalam Tesis

Berdasarkan judul tesis, arsitektur koordinasi melibatkan dua entitas analitik utama:
* **O-RAN Non-RT RIC / Near-RT RIC:** Mengamati beban dan kualitas kanal akses radio (RAN) melalui antarmuka E2 (`E2SM-KPM v2.03`).
* **3GPP NWDAF (Network Data Analytics Function):** Mengamati beban, performa, dan kongesti pada level irisan jaringan 5G Core (*Core User Plane & Control Plane*) melalui antarmuka standar 3GPP Rel-17 `Nnwdaf`.

Jika fungsi NWDAF tidak beroperasi atau sekadar di-*bypass* dengan skrip lokal semata, maka pilar **"NWDAF Coordination"** dalam riset ini kehilangan validitas ilmiahnya. Oleh karena itu, investigasi ini dilakukan untuk memastikan modul NWDAF beroperasi secara otentik.

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
> **Kesimpulan Bukti 1:** Seluruh komponen NWDAF (API Gateway, SBI, NBI, Analytics Engine, Database) berjalan normal tanpa crash sistem.

---

### Bukti 2: Respons Live REST API 3GPP TS 29.520 (`Nnwdaf_AnalyticsInfo`)

Pengujian panggilan HTTP GET langsung ke Kong API Gateway port 8080 VM-3 dengan filter 3GPP resmi:

```bash
curl -s -G "http://localhost:8080/nnwdaf-analyticsinfo/v1/analytics" \
  --data-urlencode "event-id=NETWORK_PERFORMANCE" \
  --data-urlencode 'ana-req={"startTs":"2026-10-01T00:00:00Z","endTs":"2026-10-15T23:59:59Z"}' \
  --data-urlencode 'event-filter={"snssais":[{"sst":1,"sd":"000001"}],"dnns":["oai"],"nwPerfTypes":["SESS_SUCC_RATIO"]}' | jq .
```

**Keluaran Riil Sistem (HTTP 200 OK):**
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
> **Kesimpulan Bukti 2:** Layanan NBI Analytics merespons secara valid dan sesuai format JSON 3GPP TS 29.520. Namun, parameter `relativeRatio` (indikator beban irisan) dan `absoluteNum` mengembalikan nilai konstan `0`.

---

### Bukti 3: Audit Kode Sumber Upstream OAI NWDAF Branch `develop` ("The Smoking Gun")

Untuk memastikan apakah kendala nilai `0` tersebut karena bug konfigurasi atau kode program, dilakukan audit langsung pada repositori Git resmi di VM-3 (`/opt/oran/5gc/oai-cn5g-nwdaf`):

* **Status Branch:**
  ```text
  Branch: develop (Up to date with origin/develop)
  Commit Terakhir: 9d82b75 chore(license): change OAI license PLv1.1 to CSSLv1.0
  ```

* **Inspeksi Kode Sumber Go pada Engine Analitik:**  
  File: `components/oai-nwdaf-engine/internal/engine/network_performance.go` (Baris 45–65 dan 95–115):

```go
// ------------------------------------------------------------------------------
// nwPerfNumOfUe - get the number of Ue.
func nwPerfNumOfUe(w http.ResponseWriter, r *http.Request) {
    ...
    absoluteNum, err := collection.CountDocuments(context.Background(), filter)
    if err != nil {
        http.Error(w, "Error counting documents", http.StatusInternalServerError)
        return
    }
    //TODO - Implement relative ratio and confidence
    relativeRatio, confidence := int32(0), int32(0)
    
    // Prepare http response body
    nwPerfResp := NwPerfResp{
        RelativeRatio: relativeRatio, // DI-HARDCODE KE 0 OLEH PENGEMBANG OAI
        AbsoluteNum:   int32(absoluteNum),
        Confidence:    confidence,    // DI-HARDCODE KE 0 OLEH PENGEMBANG OAI
    }
    ...
}

// ------------------------------------------------------------------------------
// nwPerfNumOfPdu - Get the number of PDU sessions.
func nwPerfNumOfPdu(w http.ResponseWriter, r *http.Request) {
    ...
    absoluteNum, err := collection.CountDocuments(context.Background(), filter)
    if err != nil {
        http.Error(w, "Error counting documents", http.StatusInternalServerError)
        return
    }
    //Implement relative ratio and confidence
    relativeRatio, confidence := int32(0), int32(0)
    
    // prepare http response body
    nwPerfResp := NwPerfResp{
        RelativeRatio: relativeRatio, // DI-HARDCODE KE 0 OLEH PENGEMBANG OAI
        AbsoluteNum:   int32(absoluteNum),
        Confidence:    confidence,    // DI-HARDCODE KE 0 OLEH PENGEMBANG OAI
    }
    ...
}
```

> **Kesimpulan Bukti 3:** Terbukti secara definitif bahwa pada rilis upstream OAI NWDAF branch `develop` paling mutakhir sekalipun, tim pengembang OpenAirInterface **belum mengimplementasikan kalkulasi matematis untuk `relativeRatio` dan `confidence`**, melainkan sengaja menandainya dengan komentar `//TODO` dan memberikan nilai konstan `0`.

---

### Bukti 4: Status Database MongoDB & Ingesti SBI Event

Pemeriksaan database MongoDB (`oai-nwdaf-database`, port 27017) menunjukkan:
```text
five-g@oai-core:/opt/oran/5gc/oai-cn5g-nwdaf$ sudo docker exec oai-nwdaf-database mongosh --eval "show dbs"
admin    40.00 KiB
config  228.00 KiB
local    40.00 KiB
```
Database yang dikonfigurasi (`testing`) belum terisi dokumen. Pada inspeksi log `oai-nwdaf-sbi` dan kode `components/oai-nwdaf-sbi/internal/sbi/amf_service.go` (baris 45–60):
```go
for _, report := range reportList {
    oid := report.GetSupi()
    if oid == "" {
        http.Error(w, "supi not found in report, cannot create object id", http.StatusBadRequest)
        return
    }
    ...
}
```
Ketika AMF mengirim notifikasi berkala tanpa menyertakan identifier SUPI pada payload tertentu, `oai-nwdaf-sbi` menolak event tersebut dengan status *Bad Request* sehingga dokumen PDU/UE belum tersimpan secara persisten ke database MongoDB.

---

### Bukti 5: Penyebab Nilai `NaN` pada Dataset Telemetri Pilot

Pada skrip pengumpul data di VM-6 (`telemetry_collector.py` baris 460–464):
```python
req = urllib.request.Request(
    "http://10.102.0.164:8080/nnwdaf-eventsubscription/v1/slice-load-level",
    headers={"User-Agent": "Thesis-Collector/1.0"}
)
```
1. Skrip memanggil URL yang salah: `/nnwdaf-eventsubscription/v1/slice-load-level`.
2. Kong API Gateway di VM-3 hanya memiliki aturan rute untuk:
   * `/nnwdaf-analyticsinfo/v1/analytics`
   * `/nnwdaf-eventssubscription/v1`
   * `/nnwdaf-mlmodelprovision/v1`
3. Akibatnya, Kong mengembalikan status **HTTP 404 Not Found**, fungsi kolektor menangkap *exception* koneksi, dan mengabaikannya (*pass*), sehingga variabel penampung telemetri tetap berada pada nilai default **`NaN`**.

---

## 4. Analisis Komparatif: Teori 3GPP vs Fakta Open Source

| Dimensi Parameter | Spesifikasi 3GPP (TS 23.288 & TS 29.520) | Kondisi Nyata OAI NWDAF v2.1.0 / `develop` |
| :--- | :--- | :--- |
| **Exposure Interface** | `Nnwdaf_AnalyticsInfo` & `Nnwdaf_EventsSubscription` | **Tersedia & Valid** melalui Kong Gateway port 8080. |
| **Kalkulasi Beban Irisan (`relativeRatio`)** | Dihitung dari rasio utilisasi beban terhadap batas kapasitas irisan (0–100%). | **Belum Diimplementasikan (`//TODO`)**, selalu menghasilkan nilai integer `0`. |
| **Visibilitas User Plane (UPF)** | Didukung melalui integrasi OAM atau DCCF (*Data Collection Coordination Function*). | **Tidak Ada SBI di UPF OAI**. UPF C-based tidak memiliki endpoint HTTP/2 ke NWDAF. |
| **Database Penyimpanan** | Menyimpan profil analitik dan histori telemetri. | MongoDB ada, namun penulisan dokumen bergantung pada format SUPI notifikasi AMF/SMF. |

---

## 5. Rencana Rekayasa & Solusi Tanpa Jalan Pintas (*Without Shortcuts*)

Untuk memastikan tesis berjalan dengan kepatuhan standar 3GPP penuh dan menjaga integritas akademis tanpa trik pintas, berikut rencana tindakan 3 tahap:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   VM-1: Non-RT RIC (rApp)                              │
│         Korelasi Bottleneck: RIC (PRB Radio) vs NWDAF (Core)           │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │                                │
    A1-EI / Metrics │                                │ 3GPP TS 29.520 Nnwdaf
                    │                                │ (Port 8080 via Kong)
┌───────────────────┴──────────┐   ┌─────────────────┴───────────────────┐
│     VM-6: Telemetry          │   │         VM-3: OAI NWDAF             │
│   telemetry_collector.py     │   │   ┌─────────────────────────────┐   │
│   (Query resmi TS 29.520)    │───┼──►│ Kong API Gateway (:8080)    │   │
└──────────────────────────────┘   │   └──────────────┬──────────────┘   │
                                   │                  ▼                  │
                                   │   ┌─────────────────────────────┐   │
                                   │   │ oai-nwdaf-nbi-analytics     │   │
                                   │   └──────────────┬──────────────┘   │
                                   │                  ▼                  │
                                   │   ┌─────────────────────────────┐   │
                                   │   │ oai-nwdaf-engine (GO)       │   │
                                   │   │ [Logika relativeRatio diisi]│   │
                                   │   └─────────────────────────────┘   │
                                   └─────────────────────────────────────┘
```

### Tahap 1: Penyempurnaan Kode Sumber Go `oai-nwdaf-engine` (VM-3)
Alih-alih membuat skrip tiruan di luar, kita menyelesaikan implementasi fungsi `//TODO` langsung di dalam kode sumber `components/oai-nwdaf-engine/internal/engine/network_performance.go`:
* Memprogram formula analitik beban irisan (*slice load ratio*) secara dinamis berdasarkan kuota kapasitas nominal irisan (sesuai **3GPP TS 23.288 §6.3**).
* Mengompilasi ulang image kontainer menggunakan Dockerfile resmi:
  ```bash
  cd /opt/oran/5gc/oai-cn5g-nwdaf
  sudo docker build -t oai-nwdaf-engine:latest -f components/oai-nwdaf-engine/docker/Dockerfile.engine components/oai-nwdaf-engine/
  sudo docker restart oai-nwdaf-engine
  ```
* **Nilai Tambah Tesis:** Penyempurnaan ini menjadi **kontribusi rekayasa langsung** pada modul open-source OAI NWDAF yang dapat dibahas secara mendalam di Bab 3 dan Bab 4 buku tesis.

### Tahap 2: Koreksi Endpoint 3GPP pada Telemetry Collector (VM-6)
Memperbarui fungsi `poll_external_nfs` di `telemetry_collector.py` agar melakukan query HTTP GET standar ke:
```text
http://10.102.0.164:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=NETWORK_PERFORMANCE&ana-req=...&event-filter=...
```
Dengan perbaikan ini, respons analitik resmi dari NWDAF otomatis tersimpan ke kolom `nwdaf_load_embb` dan `nwdaf_load_urllc` tanpa nilai `NaN`.

### Tahap 3: Validasi Koordinasi Closed-Loop rApp (VM-1)
rApp di Non-RT RIC akan mengonsumsi metrik `relativeRatio` dari antarmuka Nnwdaf NWDAF dan metrik PRB dari Near-RT RIC (E2) secara seimbang:
* Jika PRB Radio tinggi (>85%) dan NWDAF Load rendah $\rightarrow$ Vonis: **Bottleneck RAN**.
* Jika PRB Radio rendah (<60%) dan NWDAF Load tinggi (>80%) $\rightarrow$ Vonis: **Bottleneck Core**.
* Jika keduanya tinggi $\rightarrow$ Vonis: **Joint Bottleneck**.

---

## 6. Pernyataan Penutup untuk Pengamat / Penguji

> *"Kegagalan pemunculan metrik NWDAF pada uji coba awal bukanlah kegagalan rancangan tesis atau ketiadaan modul, melainkan akibat dari (1) kesalahan path query REST pada skrip kolektor, dan (2) status kode sumber resmi OAI NWDAF v2.1.0 (bahkan pada branch develop terbaru) yang masih menyisakan catatan `//TODO` pada kalkulasi relativeRatio. Solusi yang diambil adalah menyempurnakan kode sumber engine Go OAI NWDAF secara langsung dan menghubungkannya via antarmuka standar 3GPP TS 29.520. Dengan demikian, arsitektur koordinasi O-RAN RIC–NWDAF tetap berdiri kokoh, berstandar industri, dan bebas dari jalan pintas (no shortcuts)."*
