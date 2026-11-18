# Status Kampanye Eksperimen, Kalibrasi RF, dan Hardening Skrip (17 November 2026)

## 1. Protokol Pengambilan Data Kontinu 600-Detik
Setiap run eksperimen dijalankan di bawah protokol kontinu 600 detik:
- **$t = -30\text{ s}$:** Peluncuran beban trafik di VM-5 (`trafgen.sh start 660 <rate>`) dan canary ping Slice 2 (100 ms).
- **$t = 0\text{ s}$:** Perekam telemetri aktif di VM-6 (`record_experiment.py <SCENARIO> --duration 600`) pada scraping cadence 1.000 Hz.
- **$t = 120\text{ s}$:** Injeksi gangguan nominal (atenuasi RF via Telnet di VM-4 atau rate-limiting TBF di VM-3).
- **$t = 420\text{ s}$:** Pelepasan gangguan nominal (reset atenuasi RF ke 0.0 dB atau penghapusan qdisc TBF).
- **$t = 600\text{ s}$:** Perekam selesai otomatis, menulis dataset 40-kolom CSV dan `manifest.json`.
- **$t = 630\text{ s}$:** Ekspor ringkasan iperf receiver di VM-3 (`receiver_iperf.sh export`) untuk ground-truth *arrival goodput*.

## 2. Temuan & Penetapan Resmi Kalibrasi Atenuasi RF (4 Zona Operasional)
- **Unit BLER:** `ran_cell_bler` adalah rasio dimensionless $[0, 1]$; nilai `0.1000` = 10% BLER.
- **Zona 1: Dead Zone / Baseline ($0\text{–}10\text{ dB}$):** MCS tetap 28, BLER $0.00\%$, SNR $25\text{–}28\text{ dB}$. Redaman diserap sepenuhnya oleh link adaptation. Ditetapkan untuk **S1** dan **S2**.
- **Zona 2: Soft Degradation ($15.0\text{ dB}$):** *Inflection point* penurunan kualitas kanal pertama. MCS turun ke $23\text{–}27$ (mean $25.3$), BLER muncul di $4\%\text{–}17\%$ (mean $9.54\%$), PRB $\approx 73\%$ (puncak $100\%$). Koneksi $100\%$ stabil tanpa RLF, kapasitas $\approx 8\text{–}9\text{ Mbps}$. Terbukti pada dataset 7.200s S9. Ditetapkan untuk **S3** (`S3_RAN_SOFT`), **S8** (`S8_JOINT_SOFT`), dan komponen radio **S9** (`S9_JOINT_OVERLOAD`).
- **Zona 3: Hard Degradation ($20.0\text{ dB}$):** Modulasi anjlok ke 16-QAM (MCS $20\text{–}21$), BLER $10\%\text{–}15\%$, PRB terkunci di $100\%$, kapasitas radio terpangkas di bawah $7\text{ Mbps}$. Ditetapkan untuk **S4** (`S4_RAN_DEGRADATION`).
- **Zona 4: Instability / RLF Boundary ($\ge 25.0\text{ dB}$):** Di bawah beban kontinu 10 Mbps UDP, memicu buffer overflow MAC/RLC dan kegagalan Radio Link Failure (RLF) pada $t \approx 125\text{s}$ ($100\%$ loss). Dikeluarkan dari protokol pengambilan data tunak.

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

## 5. Log Run Eksperimen Formal (Kampanye Dataset 2 Jam / Tri-Partition)
- **S9 (`S9_JOINT_OVERLOAD`) — TUNTAS PENUH 100% (7.200 Sampel / 2 Jam):**
  - **Training Set (60m):** `EXP_S9_20261117_204800` (3.600 sampel, 100% scrape OK, 1.783 NWDAF raw polls). eMBB: 10.00M, RTT 444.56 ms, Loss 3.4%. URLLC: RTT 15.19 ms, Loss 0.0%, SLA Viol 9.3%. RAN: PRB 73.1% (peak 100%), MCS 25.3, BLER 9.54%, SNR 25.2 dB. Core: Backlog Max 109,635 B, Drop Rate Max 593.9 pkt/s. NWDAF AnLF: API 100%, Freshness 99.6%, 120 URR updates, UL 4,585.75 MB.
  - **Validation Set (30m):** `EXP_S9_20261117_223553` (1.800 sampel, 100% scrape OK, 891 NWDAF raw polls).
  - **Testing Set (30m):** `EXP_S9_20261117_232424` (1.800 sampel, 100% scrape OK, 890 NWDAF raw polls).
- **Log Pilot Sebelumnya (Pilot 600s):**
  - **EXP_S1_20261117_165322**: Pilot S1 600s (600 sampel).
  - **EXP_S1_20261117_174739**: Pilot S1 600s (600 sampel).
