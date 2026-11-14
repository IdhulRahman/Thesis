# Project Rules, Repository Constraints, and Academic Context

## 1. Fokus Penelitian Tesis
- **Judul:** *Bottleneck-Aware Closed-Loop Traffic Steering via O-RAN RIC–NWDAF Coordination in Multi-Slice 5G Networks*
- **Tujuan Utama:** Mengatasi domain observability silos antara RAN (O-RAN) dan 5G Core user plane (UPF) menggunakan koordinasi MAPE-K multi-timescale (Non-RT RIC rApp $\to$ A1 Policy $\to$ Near-RT RIC xApp $\to$ E2 Control) dan 3GPP NWDAF analytics.
- **Skema 10 Fitur Telemetri Baku:**
  - *RAN (DU-1):* scheduled uplink PRB (`ran_prb_cell1`), uplink MCS index (`ran_mcs_cell1`), uplink SNR (`ran_snr_cell1`), uplink BLER (`ran_bler_cell1`).
  - *Core (UPF):* qdisc backlog bytes (`upf_backlog_bytes_embb`), qdisc drops (`upf_drops_embb`), estimated load (`estimated_load_embb`).
  - *End-to-End:* slice-1 offered throughput (`e2e_slice1_tput_mbps`), slice-1 RTT (`e2e_slice1_rtt_ms`), slice-2 RTT (`e2e_slice2_rtt_ms`).
  *(Catatan: Istilah CQI, egress throughput, packet rate, buffer drops, jitter, dan probe loss TIDAK digunakan).*

## 2. Aturan Ketat Git & Repositori GitHub
1. **Pengecualian .gitignore:**
   Folder `/data/`, `/experiments/`, dan `/research/` WAJIB diabaikan oleh `.gitignore`. Jangan pernah melakukan git commit/push untuk ketiga folder tersebut.
2. **Kerahasiaan README.md:**
   Berkas `README.md` root repositori yang tampil di GitHub TIDAK BOLEH memuat referensi atau tautan apa pun ke folder `data/`, `experiments/`, dan `research/`.
3. **Workspace Path & Shell Environment:**
   Mount filesystem lokal berada di `/mnt/external-disk/Projects/Thesis`. Jika mengeksekusi script/alat otomatis, pastikan working directory selalu mengarah ke `/mnt/external-disk/Projects/Thesis`.

## 3. Status Naskah Paper (IEEEtran LaTeX)
- Berkas `research/papers/latex/main.tex` telah disesuaikan dan dikunci pada:
  - Maksimal tepat **6 halaman** (tidak tumpah ke halaman 7).
  - 15 referensi terverifikasi dengan pembagian kolom seimbang di Halaman 6: Referensi [1]--[7] di kolom kiri dan [8]--[15] di kolom kanan menggunakan `\IEEEtriggeratref{8}`.
  - Bebas dari compiler warning (*undefined reference `tab:features` telah dihapus; underfull hbox badness 10000 telah diselesaikan dengan notasi slash compact*).
  - Mengakomodasi 6 poin perbaikan dosen secara objektif dan proporsional.
