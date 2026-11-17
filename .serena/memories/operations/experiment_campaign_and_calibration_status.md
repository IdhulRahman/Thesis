# Status Kampanye Eksperimen, Kalibrasi RF, dan Hardening Skrip (17 November 2026)

## 1. Protokol Pengambilan Data Kontinu 600-Detik
Setiap run eksperimen dijalankan di bawah protokol kontinu 600 detik:
- **$t = -30\text{ s}$:** Peluncuran beban trafik di VM-5 (`trafgen.sh start 660 <rate>`) dan canary ping Slice 2 (100 ms).
- **$t = 0\text{ s}$:** Perekam telemetri aktif di VM-6 (`record_experiment.py <SCENARIO> --duration 600`) pada scraping cadence 1.000 Hz.
- **$t = 120\text{ s}$:** Injeksi gangguan nominal (atenuasi RF via Telnet di VM-4 atau rate-limiting TBF di VM-3).
- **$t = 420\text{ s}$:** Pelepasan gangguan nominal (reset atenuasi RF ke 0.0 dB atau penghapusan qdisc TBF).
- **$t = 600\text{ s}$:** Perekam selesai otomatis, menulis dataset 40-kolom CSV dan `manifest.json`.
- **$t = 630\text{ s}$:** Ekspor ringkasan iperf receiver di VM-3 (`receiver_iperf.sh export`) untuk ground-truth *arrival goodput*.

## 2. Temuan Sesi Kalibrasi Atenuasi RF (5 dB s.d. 40 dB)
- **Unit BLER:** `ran_cell_bler` adalah rasio dimensionless $[0, 1]$; nilai `0.1000` = 10% BLER.
- **25 dB (Step 5):** Kondisi radio tertekan (*stressed radio*), MCS turun ke 17, PRB 100%, BLER ~10%. Status *binding* ditangguhkan (*pending receiver evidence*) hingga bukti defisit *arrival goodput* EXT-DN terkumpul.
- **30 dB (Step 6):** Kandidat *RAN-binding*, MCS anjlok ke 0–1, BLER mencapai 0.62.
- **35 dB (Step 7):** Memicu Radio Link Failure (RLF) pada softmodem (bukan stable operating point).
- **40 dB (Step 8):** Bukan pengamatan independen; softmodem telah crash/RLF dari step 35 dB.

## 3. Hasil Audit & Hardening Tooling Operasional (Commit `3cc8a1b`)
1. **`scripts/trafgen.sh` (VM-5):**
   - Parsing throughput sender dan receiver dipisahkan secara independen.
   - Jika receiver summary belum tersedia, dilaporkan `N/A`.
2. **`scripts/receiver_iperf.sh` (VM-3):**
   - Timeout export (15s) bersifat non-destruktif (`status: pending`, `session_complete: false`, exit code 2).
   - Ditambahkan perintah eksplisit `abort` (`./receiver_iperf.sh abort [RUN_ID] [SESSION_ID] [PORT]`).
   - Persistensi state abort: file summary mempertahankan `aborted: true` dan `session_complete: false` saat diekspor ulang.
   - Penolakan error payload: error di dalam `{"event":"end","data":{"error":...}}` menolak status COMPLETE dan menandai sesi aborted.
3. **`scripts/analyze_dataset.py` (VM-6):**
   - Logika SLA URLLC: RTT normal (<= 20 ms) dengan Loss `NaN` diklasifikasikan sebagai `Unknown / Unk` (SLA Viol = `N/A`, bukan false `0.0%`).
   - Segmentasi fase dinamis: Anotasi kejadian aktual (seperti `PHASE_2_ACTUAL_FAULT`) diutamakan di atas jadwal nominal. S1/S2 ditetapkan sebagai `1_REFERENCE_STEADY`, S5 sebagai `1_SATURATED_STEADY`, dan skenario gangguan memakai jadwal nominal `[0-120s]`, `[120-420s]`, `[420-600s]`.
4. **`tests/test_quality_gates.py`:**
   - 50 unit dan end-to-end integration tests berbasis CSV fixtures dan mock receiver logs (100% PASS).

## 4. Alur Sinkronisasi VM (Sesuai `mem:project/user_workflow_and_agent_role`)
Sinkronisasi ke target VM selalu menggunakan perintah `curl` dari GitHub raw publik (`https://raw.githubusercontent.com/IdhulRahman/Thesis/main/...`) dan dieksekusi langsung oleh peneliti di terminal masing-masing VM.

## 5. Log Run Eksperimen Formal (Kampanye Dataset)
- **EXP_S1_20261117_165322**: Run 1 S1 (`S1_NORMAL_LIGHT`) 600.0s (600 sampel). eMBB: 5.00 Mbps, RTT 15.83 ms, Loss 0.0%. URLLC: RTT 14.64 ms, Loss 0.0%, SLA Viol 6.3%. RAN: PRB 55.0%, MCS 28.0, BLER 0.00%, SNR 26.8 dB. Core: Backlog 0 B, Drops 0.0 pkt/s. NWDAF AnLF: API Status 100.0%, Freshness 96.8%, 20 URR updates, UL 382.55 MB, 298 raw JSONL polls tersimpan.
- **EXP_S1_20261117_174739**: Run 2 S1 (`S1_NORMAL_LIGHT`) 600.0s (600 sampel). eMBB: 5.00 Mbps, RTT 15.81 ms, Loss 0.0%. URLLC: RTT 15.00 ms, Loss 0.0%, SLA Viol 7.2%. RAN: PRB 53.7%, MCS 28.0, BLER 0.00%, SNR 26.7 dB. Core: Backlog 0 B, Drops 0.0 pkt/s. NWDAF AnLF: API Status 100.0%, Freshness 99.3%, 20 URR updates, UL 382.22 MB, 298 raw JSONL polls.
