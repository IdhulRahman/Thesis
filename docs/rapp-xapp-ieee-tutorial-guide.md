# Penjelasan rApp dan xApp dalam Arsitektur O-RAN

Dokumen ini berisi penjelasan komprehensif mengenai **rApp** dan **xApp** serta koordinasi *Multi-Timescale Control Loop* pada arsitektur O-RAN 5G/6G, yang bersumber langsung dari standar O-RAN Alliance dan publikasi **IEEE Communications Surveys & Tutorials (2026)**.

---

## Sitasi Referensi IEEE Utama

> [!NOTE]
> **Referensi Utama**:
> - **Judul Paper**: *A Tutorial on O-RAN Deployment Solutions for 5G: From Simulation to Emulated and Real Testbeds*
> - **Jurnal**: IEEE Communications Surveys & Tutorials (Volume 28, 2026)
> - **Penulis**: Juan Luis Herrera, Sofia Montebugnoli, Domenico Scotece, Luca Foschini, dan Paolo Bellavista
> - **DOI**: `10.1109/COMST.2025.3577687`
> - **Penerbit**: IEEE (Institute of Electrical and Electronics Engineers)

---

## Daftar Isi
1. [Pengenalan Arsitektur Kontrol O-RAN](#1-pengenalan-arsitektur-kontrol-o-ran)
2. [Konsep dan Peran rApp (Non-RT RIC)](#2-konsep-dan-peran-rapp-non-rt-ric)
3. [Konsep dan Peran xApp (Near-RT RIC)](#3-konsep-dan-peran-xapp-near-rt-ric)
4. [Matriks Perbandingan rApp vs xApp](#4-matriks-perbandingan-rapp-vs-xapp)
5. [Mekanisme Koordinasi Multi-Timescale (A1 & E2)](#5-mekanisme-koordinasi-multi-timescale-a1--e2)
6. [Implementasi pada Proyek Tesis Anda](#6-implementasi-pada-proyek-tesis-anda)

---

## 1. Pengenalan Arsitektur Kontrol O-RAN

Dalam arsitektur O-RAN Alliance, kecerdasan jaringan (*RAN Intelligence*) dipisahkan dari perangkat keras fisik dan dibagi menjadi dua tingkatan pengontrol cerdas (*RAN Intelligent Controller / RIC*) berdasarkan skala waktu (*timescale*):

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      Non-Real-Time RIC (VM-1 / Host)                   │
 │  ┌──────────────────────────────────────────────────────────────────┐  │
 │  │                         Custom rApp                              │  │
 │  │ • Skala Waktu : > 1 detik hingga Menit / Jam                     │  │
 │  │ • Tugas       : Analisis Statistik, ML Model, Adaptasi Kebijakan │  │
 │  └────────────────────────────────┬─────────────────────────────────┘  │
 └───────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ Antarmuka A1 (A1 Policy Guidance)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      Near-Real-Time RIC (VM-2 / Host)                  │
 │  ┌──────────────────────────────────────────────────────────────────┐  │
 │  │                         Custom xApp                              │  │
 │  │ • Skala Waktu : Near-Real-Time (10 ms < Δt < 1 detik)            │  │
 │  │ • Tugas       : Traffic Steering, Handover, E2 Control Loop    │  │
 │  └────────────────────────────────┬─────────────────────────────────┘  │
 └───────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ Antarmuka E2 (E2 KPM & E2 Control)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        O-RAN Centralized / Distributed Unit            │
 │                        (OAI gNB CU / DU-1 / DU-2)                      │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Konsep dan Peran rApp (Non-RT RIC)

### 2.1 Definisi
**rApp** adalah aplikasi modular yang berjalan di dalam **Non-Real-Time RIC (Non-RT RIC)**. rApp bertindak sebagai pusat pengambil keputusan makro jangka panjang (*Long-Timescale Intelligence*).

### 2.2 Fitur dan Karakteristik Utama rApp
1. **Skala Waktu Execusi**: $\Delta t \ge 1\text{ detik}$ (dapat berjalan interval menit, jam, atau harian).
2. **Input Data**: Mengambil data statistik histori jangka panjang dari data lake, Prometheus, atau SMO (Service Management and Orchestration).
3. **Output Utama**: Menghasilkan batasan kebijakan adaptif (**A1 Policy Instance**) yang dikirimkan ke Near-RT RIC melalui **Antarmuka A1**.
4. **Penggunaan AI/ML**: Menjadi tempat pelatihan (*training*) dan penyempurnaan model Machine Learning / Deep Reinforcement Learning (DRL) tanpa mengganggu lalu lintas real-time jaringan.

---

## 3. Konsep dan Peran xApp (Near-RT RIC)

### 3.1 Definisi
**xApp** adalah aplikasi mikro terorganisasi yang berjalan di dalam **Near-Real-Time RIC (Near-RT RIC)**. xApp berfungsi mengeksekusi kontrol real-time jaringan berdasarkan panduan dari rApp.

### 3.2 Fitur dan Karakteristik Utama xApp
1. **Skala Waktu Execusi**: Near-Real-Time ($10\text{ ms} \le \Delta t < 1\text{ detik}$).
2. **Input Data**: Membaca indikator telemetri real-time dari stasiun pemancar 5G (gNB) melalui antarmuka **E2** (seperti RSRP, SINR, PRB usage per cell/slice) serta menerima batasan A1 Policy dari rApp.
3. **Output Utama**: Mengirimkan perintah kontrol (*E2 Control Message*) seperti instruksi *Handover*, *Traffic Steering*, atau pembagian alokasi radio per *slice*.
4. **Mekanisme Pesan**: Menggunakan **RMR (RIC Message Router)** untuk komunikasi antar-komponen di Near-RT RIC (Message Type `20010` untuk penerimaan A1 Policy dan `20011` untuk balasan ACK).

---

## 4. Matriks Perbandingan rApp vs xApp

Berdasarkan publikasi IEEE Survey (Herrera et al., 2026):

| Elemen Perbandingan | rApp (Non-RT RIC) | xApp (Near-RT RIC) |
|---|---|---|
| **Lokasi Platform** | Non-RT RIC / SMO | Near-RT RIC Framework |
| **Skala Waktu (Timescale)** | Jangka Panjang ($\ge 1\text{ detik}$ s.d. jam) | Near-Real-Time ($10\text{ ms} - 1\text{ detik}$) |
| **Antarmuka Komunikasi** | **Antarmuka A1** (REST / HTTP) | **Antarmuka E2** (ASN.1 / SCTP) & **RMR** |
| **Tujuan Utama** | Optimasi kebijakan makro & ML Training | Eksekusi mikro, *Traffic Steering*, *Handover* |
| **Respon Latensi** | Toleran terhadap latensi tinggi | Membutuhkan latensi sangat rendah (< 1 detik) |
| **Sumber Data Utama** | Prometheus / Database Histori (VM-6) | E2 Telemetry / E2 KPM Report dari gNB |

---

## 5. Mekanisme Koordinasi Multi-Timescale (A1 & E2)

Koordinasi dua tingkat (*Multi-Timescale Coordination*) bekerja dengan prinsip berikut:

```text
[rApp (Non-RT)] ──(1. Evaluasi Histori)──► [Update A1 Policy]
                                                │
                                                ▼ (2. Antarmuka A1)
[xApp (Near-RT)] ◄──(3. Terima Policy)──── [A1 Mediator / Shim]
       │
       ├────► (4. Baca E2 Telemetry Real-Time dari gNB)
       │
       └────► (5. Eksekusi Traffic Steering / Handover via E2)
```

1. **rApp** mendeteksi bahwa rata-rata penurunan QoS jaringan selama 5 menit meningkat $\rightarrow$ rApp menurunkan ambang batas (*threshold*) pada kebijakan A1 via HTTP REST `PUT`.
2. **A1 Mediator** menyalurkan pembaruan kebijakan tersebut ke **xApp** melalui RMR Message Type `20010`.
3. **xApp** menerima *threshold* baru dari rApp. Ketika beban PRB sel melampaui *threshold* baru ini, xApp langsung memicu perintah *Traffic Steering* ke gNB melalui antarmuka **E2**.

---

## 6. Implementasi pada Proyek Tesis Anda

Dalam proyek Tesis Anda (*Multi-Timescale QoS-Aware Traffic Steering in Multi-Slice O-RAN*):

1. **File Skrip rApp**: `qos_policy_rapp.py` / `native_rapp.py`
   - Mengambil metrik histori drop rate / packet loss dari Prometheus.
   - Mengubah parameter `threshold` kebijakan A1 secara otomatis.
2. **File Skrip xApp**: `a1_policy_xapp.py` / `native_xapp.py`
   - Berjalan menggunakan framework `ricxappframe` Python.
   - Mendengarkan RMR Port `4560` untuk pesan A1 `20010`.
   - Menjaga SLA QoS pada skenario *Multi-Slice* (misal memindahkan UE dari Sel-1 ke Sel-2 saat overload).

---

## Sitasi Siap Pakai untuk Bab 2 Naskah Tesis Anda

> Anda dapat mengutip paragraf berikut pada **BAB 2 (Tinjauan Pustaka / Landasan Teori)** naskah tesis Anda:

```text
Berdasarkan standar O-RAN Alliance dan penelitian komprehensif oleh Herrera et al. (2026), kecerdasan pengontrol jaringan O-RAN terbagi menjadi dua tingkatan utama, yaitu Non-Real-Time RIC (Non-RT RIC) dan Near-Real-Time RIC (Near-RT RIC). Non-RT RIC menampung rApp yang beroperasi pada skala waktu jangka panjang (>= 1 detik) untuk analisis statistik dan adaptasi kebijakan melalui antarmuka A1. Sementara itu, Near-RT RIC menampung xApp yang beroperasi pada skala waktu near-real-time (10 ms hingga < 1 detik) untuk mengeksekusi keputusan kontrol mikroskopis seperti traffic steering dan handover melalui antarmuka E2. Koordinasi multi-timescale antara rApp dan xApp ini menjadi landasan utama dalam menjaga Kualitas Layanan (QoS) pada jaringan multi-slice O-RAN.
```
