# Studi Literatur & Komparasi: Rimedo Labs vs. Platform Tesis O-RAN Multi-Slice

Dokumen ini menyajikan analisis perbandingan komprehensif antara referensi industri dari **Rimedo Labs** (*Policy-based Traffic Steering xApp implementation within O-RAN*) dengan **Platform Tesis O-RAN Multi-Slice** yang sedang dikembangkan.

---

## Daftar Isi
1. [Ringkasan Makalah Rimedo Labs](#1-ringkasan-makalah-rimedo-labs)
2. [Matriks Komparasi Teknis](#2-matriks-komparasi-teknis)
3. [Kebaruan Riset (Novelty) Tesis Anda](#3-kebaruan-riset-novelty-tesis-anda)
4. [Draf Narasi Bab 2 Tesis (Related Work)](#4-draf-narasi-bab-2-tesis-related-work)
5. [Kesimpulan & Catatan untuk Tesis Anda](#5-kesimpulan--catatan-untuk-tesis-anda)

---

## 1. Ringkasan Makalah Rimedo Labs

- **Judul Artikel**: *Policy-based Traffic Steering xApp implementation within O-RAN*
- **Penulis**: Adam Samorzewski (Rimedo Labs)
- **Ringkasan Inti**: 
  - Mengembangkan *Traffic Steering (TS) xApp* di Near-RT RIC yang dikendalikan oleh kebijakan (*policy-driven*).
  - Kebijakan (A1 Policy) berasal dari Non-RT RIC berdasarkan analisis statistik / Machine Learning jangka panjang.
  - xApp membaca telemetri sinyal (RSRP, SINR) dan status UE dari E2 Nodes, kemudian mengeksekusi instruksi pengalihan sel (*handover command*) via antarmuka E2.

> [!NOTE]
> **Relevansi Utama**: Publikasi Rimedo Labs memvalidasi bahwa konsep *Policy-Based Traffic Steering* yang Anda gunakan adalah arsitektur standar yang diakui oleh O-RAN Alliance.

---

## 2. Matriks Komparasi Teknis

| Parameter / Fitur | Implementasi Rimedo Labs | Platform Tesis Anda (Multi-Slice O-RAN) |
|---|---|---|
| **Arsitektur Utama** | Standar O-RAN Alliance (Non-RT RIC + Near-RT RIC) | Standar O-RAN Alliance (6-VM Subnet `10.10.10.0/24`) |
| **Mekanisme Kontrol** | Policy-Based Traffic Steering | Policy-Based Traffic Steering |
| **Fokus Optimasi** | Pengalihan beban sel umum (*User-Centric Cell Selection*) | **Multi-Slice QoS-Aware Traffic Steering** (Penjagaan SLA/QoS per *slice*) |
| **Adaptasi Kebijakan rApp** | Analisis statistik offline / ML generik | **Custom rApp Aktif** yang membaca metrik Prometheus (VM-6) & memperbarui A1 PMS |
| **Skala Waktu Kontrol** | Policy Long-Timescale $\rightarrow$ Near-RT xApp | Long-Timescale (>1s - Menit) rApp $\rightarrow$ Near-RT (<1s) xApp |
| **Stack Perangkat Lunak** | Simulator internal / ONF RIC Framework | **O-RAN SC (A1 PMS + Minimal RIC) + OpenAirInterface (5GC + CU/DU + RFsim nrUE)** |

---

## 3. Kebaruan Riset (Novelty) Tesis Anda

Meskipun prinsip dasar *Policy-Based Traffic Steering* sama, tesis Anda memiliki 3 poin kebaruan utama (*novelty*):

1. **Spesifikasi Multi-Slice O-RAN**: Evaluasi keputusan *traffic steering* mempertimbangkan pemisahan *slice* (misal eMBB vs URLLC) dan batas QoS latensi/throughput dinamis.
2. **Integrasi End-to-End Otomatis**: Menghubungkan secara langsung *rApp* berbasis histori Prometheus dengan *A1 Policy Management Service (A1 PMS)*, Shim NGINX, *A1 Mediator*, dan *xApp Python (`ricxappframe`)*.
3. **Validasi Testbed OpenAirInterface (Software-Only)**: Menguji koordinasi kontrol *multi-timescale* menggunakan platform emulasi penuh OpenAirInterface (CU, DU-1, DU-2, nrUE RFsim) tanpa hardware SDR.

---

## 4. Draf Narasi Bab 2 Tesis (Related Work)

> [!TIP]
> Paragraf di bawah ini disiapkan untuk disalin (*copy-paste*) langsung ke **BAB 2 Naskah Tesis Anda (Tinjauan Pustaka / State of the Art)**:

```text
Konsep Policy-based Traffic Steering pada arsitektur O-RAN telah dibahas oleh Samorzewski et al. (Rimedo Labs), di mana xApp pada Near-RT RIC mengeksekusi keputusan pengalihan sel pengguna (handover) berdasarkan batasan kebijakan yang dikirimkan oleh Non-RT RIC melalui antarmuka A1. 

Meskipun demikian, implementasi tersebut umumnya berfokus pada pengalihan beban sel (cell load balancing) secara umum. Berbeda dengan penelitian tersebut, tesis ini mengembangkan mekanisme Traffic Steering yang secara spesifik mempertimbangkan kualitas layanan (QoS-aware) pada skenario Multi-Slice O-RAN. Selain itu, penelitian ini mengintegrasikan rApp otomatis di VM Non-RT RIC yang secara dinamis memperbarui kebijakan A1 PMS berdasarkan histori data Prometheus, serta memvalidasi koordinasi multi-timescale tersebut pada platform eksperimen berbasis OpenAirInterface (OAI) dan O-RAN Software Community (O-RAN SC).
```

---

## 5. Kesimpulan & Catatan untuk Tesis Anda

> [!IMPORTANT]
> **Kesimpulan Hubungan Penelitian**:

1. **Tidak Ada Masalah Duplikasi / Plagiarisme**:
   - Penelitian Anda **bukan penjiplakan**, melainkan **pengembangan lanjutan** yang lebih spesifik pada skenario *Multi-Slice* dan *QoS-awareness*.
2. **Penyokong Dasar Teori Tesis**:
   - Artikel Rimedo Labs justru memperkuat latar belakang tesis Anda. Ini membuktikan kepada dosen penguji bahwa arsitektur rApp/xApp yang Anda rancang sudah sesuai dengan acuan industri 5G/O-RAN dunia.
3. **Fokus Utama yang Harus Anda Tekankan Saat Ujian Tesis**:
   - Saat sidang/presentasi, tekankan bahwa keunggulan karya Anda ada pada **koordinasi dinamis rApp (Prometheus) ke xApp pada jaringan Multi-Slice**, bukan sekadar perpindahan sinyal sel biasa.
