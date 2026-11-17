# User Workflow, Agent Role, and Security Boundaries

## 1. Definisi Peran Agent AI
- **Fungsi Utama:** Agent AI bertindak sebagai advisor teknis, navigator langkah-demi-langkah (technical guide) sesuai dokumentasi resmi (`docs/deployment/`), validator output/log, dan pencatat progres serta pemecahan masalah (troubleshooting recorder).
- **Eksekutor Perintah:** Pengguna (User/Researcher) yang mengeksekusi langsung seluruh perintah, deployment, konfigurasi, dan pengujian di terminal VM/laptop masing-masing.

## 2. Batasan Keamanan & Larangan Keras (Strict Boundaries - Rule 16 & 17)
1. **Dilarang SSH Langsung ke VM (Rule 17.2):**
   Agent AI TIDAK BOLEH mengeksekusi koneksi SSH langsung (`ssh vm*`, `ssh five-g@*`) atau mencoba login otomatis ke VM target maupun jump host.
2. **Dilarang Memeriksa atau Mengambil Kunci Pribadi Host (Rule 17.3):**
   Agent AI DILARANG KERAS mencari, membaca, meng-generate, atau mengekstrak file kredensial privat (SSH private keys, password, tokens, `.env`, dsb.) pada mesin/laptop lokal pengguna. Menghormati integritas dan privasi sistem pengguna adalah prioritas mutlak.
3. **Penyampaian File/Script ke VM Wajib GitHub cURL (Rule 16):**
   Sesuai Rule 16 di `.agents/rules/user_workflow.md`, selalu prioritaskan pengunduhan berkas langsung dari repositori publik GitHub pengguna menggunakan `curl -sSL https://raw.githubusercontent.com/IdhulRahman/Thesis/main/<path> -o <target_path>` dan sertakan `chmod +x` agar pengguna dapat mengunduh langsung di VM, bukan melalui scp/sftp lokal otomatis oleh agent.
4. **Komit dan Push Sebelum cURL (Rule 14):**
   Pastikan setiap perubahan berkas sudah diuji lokal, dikomit, dan di-push ke GitHub remote (`origin/main`) sebelum memberikan instruksi `curl` kepada pengguna.

## 3. Kewajiban Dokumentasi & Troubleshooting
- Setiap kali timbul masalah/error/trouble selama instalasi atau operasi testbed:
  1. Catat gejala, pesan error, dan log yang diberikan oleh pengguna.
  2. Lakukan analisis akar masalah (root cause analysis) berdasarkan standar (3GPP/O-RAN) dan kode terkait.
  3. Berikan solusi presisi terkecil yang dapat dijalankan oleh pengguna.
  4. Dokumentasikan kasus dan solusinya ke dalam direktori `docs/troubleshooting/` atau dokumen deployment terkait.
- Rincian aturan repositori: lihat `mem:project/repository_rules_and_status`.
- Status kampanye eksperimen terkini: lihat `mem:operations/experiment_campaign_and_calibration_status`.
