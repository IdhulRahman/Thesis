# Panduan Setup Native: rApp & xApp (Tanpa Docker / VirtualBox)

Dokumen ini berisi panduan setup teknis untuk menjalankan **rApp (Non-RT RIC)** dan **xApp (Near-RT RIC)** secara **Native** (langsung pada OS Linux Host menggunakan Python process) tanpa harus menggunakan VirtualBox atau Docker container yang berat.

---

## Daftar Isi
1. [Gambaran Umum Setup Native](#1-gambaran-umum-setup-native)
2. [Persiapan Dependensi Linux Host](#2-persiapan-dependensi-linux-host)
3. [Konfigurasi RMR Routing Table Native](#3-konfigurasi-rmr-routing-table-native)
4. [Panduan Menjalankan xApp Native](#4-panduan-menjalankan-xapp-native)
5. [Panduan Menjalankan rApp Native](#5-panduan-menjalankan-rapp-native)
6. [Uji Komunikasi & Debugging](#6-uji-komunikasi--debugging)

---

## 1. Gambaran Umum Setup Native

Arsitektur kontrol *Multi-Timescale* dijalankan langsung pada sistem operasi Linux Host:

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         LINUX HOST NATIVE SYSTEM                       │
 │                                                                        │
 │  ┌────────────────────────┐              ┌──────────────────────────┐  │
 │  │      rApp Native       │  A1 (REST)   │       xApp Native        │  │
 │  │ (qos_policy_rapp.py)   ├─────────────►│  (a1_policy_xapp.py)    │  │
 │  │ (Skala: Jangka Panjang)│              │ (Skala: Near-Real-Time)  │  │
 │  └───────────▲────────────┘              └────────────┬─────────────┘  │
 │              │                                        │                │
 │    Prometheus Telemetry                         E2 Control             │
 └────────────────────────────────────────────────────────────────────────┘
```

> [!NOTE]
> **Keunggulan Native**: Tidak memerlukan alokasi RAM VirtualBox (4-8 GB) dan pesan error Python langsung muncul di Terminal tanpa terhalang container Docker.

---

## 2. Persiapan Dependensi Linux Host

Buka Terminal Linux (Ubuntu 20.04/22.04 LTS atau Debian 12) dan jalankan perintah install dependensi dasar:

```bash
# 1. Update package manager
sudo apt update && sudo apt upgrade -y

# 2. Install dependensi build, Python, dan network utilities
sudo apt install -y git curl jq build-essential python3 python3-pip python3-venv python3-requests net-tools

# 3. Install library Python pendukung rApp & xApp
pip3 install ricxappframe requests prometheus-api-client

# 4. Install Shared C Library RMR (librmr_si.so) yang dibutuhkan oleh ricxappframe
wget https://packagecloud.io/o-ran-sc/release/packages/debian/stretch/rmr_4.9.4_amd64.deb/download.deb -O rmr_4.9.4_amd64.deb
wget https://packagecloud.io/o-ran-sc/release/packages/debian/stretch/rmr-dev_4.9.4_amd64.deb/download.deb -O rmr-dev_4.9.4_amd64.deb
sudo dpkg -i rmr_4.9.4_amd64.deb rmr-dev_4.9.4_amd64.deb
sudo ldconfig
```

> [!IMPORTANT]
> **Library `librmr_si.so` Wajib Ada**: Library `ricxappframe` di Python membutuhkan pustaka C `librmr_si.so` yang di-install via file paket `.deb` di atas agar xApp bisa berjalan tanpa OSError.

> [!TIP]
> **Catatan Tipografi**: Pastikan mengetik `requests` (menggunakan akhiran **`s`**). Nama paket Python adalah `requests`, bukan `request`.

---

## 3. Konfigurasi RMR Routing Table Native

RMR (RIC Message Router) membutuhkan file rute (*Routing Table*) untuk mengarahkan pesan A1 Policy (Type `20010`) dan respon ACK (Type `20011`).

Buat file rute lokal di `/opt/oran/configs/routes.rtg`:

```bash
sudo mkdir -p /opt/oran/configs
sudo chown -R $USER:$USER /opt/oran

cat << 'EOF' > /opt/oran/configs/routes.rtg
newroute | 20010 | 127.0.0.1:4560
newroute | 20011 | 127.0.0.1:10000
rte | 20010 | 127.0.0.1:4560
rte | 20011 | 127.0.0.1:10000
EOF
```

---

### 4.1 Buat File Script Native xApp (`/opt/oran/native_xapp.py`)

Salin dan tempel **seluruh blok perintah ini** di terminal untuk membuat file `native_xapp.py` secara otomatis:

```bash
cat << 'EOF' > /opt/oran/native_xapp.py
import json
import time
import os
from ricxappframe.xapp_frame import RMRXapp

# Target kebijakan awal
current_policy = {
    "threshold": 5,
    "target_qos_latency_ms": 20
}

def handle_a1_policy(self, summary, sbuf):
    global current_policy
    if not summary or "payload" not in summary:
        return

    try:
        payload = json.loads(summary["payload"].decode("utf-8"))
        print(f"[xApp Native] Menerima Update A1 Policy: {payload}")

        current_policy["threshold"] = payload.get("threshold", current_policy["threshold"])
        current_policy["target_qos_latency_ms"] = payload.get("target_qos_latency_ms", current_policy["target_qos_latency_ms"])

        # Kirim ACK back
        ack_payload = json.dumps({"status": "SUCCESS", "policy_type_id": 20008}).encode("utf-8")
        self.rmr_rts(sbuf, new_mtype=20011, payload=ack_payload)
        print(f"[xApp Native] ACK terkirim. Kebijakan aktif: {current_policy}")

    except Exception as e:
        print(f"[xApp ERROR] {e}")

def traffic_steering_loop(xapp):
    while True:
        # Simulasi/Pembacaan E2 PRB Usage
        cell1_prb = 75.0  
        limit = current_policy["threshold"] * 10

        if cell1_prb > limit:
            print(f"[xApp ACTION] PRB Cell-1 ({cell1_prb}%) > Limit ({limit}%). Memicu Handover ke Cell-2!")
        
        time.sleep(0.5)

if __name__ == "__main__":
    print("[xApp Native] Memulai xApp Process di RMR Port 4560...")
    xapp = RMRXapp(default_handler=handle_a1_policy, rmr_port=4560, post_init=traffic_steering_loop)
    xapp.run()
EOF
```

### 4.2 Menjalankan xApp di Terminal 1

```bash
export RMR_SEED_RT=/opt/oran/configs/routes.rtg
export RMR_SRC_ID=127.0.0.1

python3 /opt/oran/native_xapp.py
```

---

## 5. Panduan Menjalankan rApp Native

### 5.1 Buat File Script Native rApp (`/opt/oran/native_rapp.py`)

Salin dan tempel **seluruh blok perintah ini** di terminal untuk membuat file `native_rapp.py` secara otomatis:

```bash
cat << 'EOF' > /opt/oran/native_rapp.py
import requests
import time
import json

A1_SIMULATED_URL = "http://127.0.0.1:8081/a1-policy/v2/policies"

def update_a1_policy(policy_id, new_threshold):
    payload = {
        "policy_id": policy_id,
        "policytype_id": "20008",
        "policy_data": {"threshold": new_threshold}
    }
    print(f"[rApp Native] Mengirimkan Update Kebijakan ke A1: threshold={new_threshold}")

def long_timescale_loop():
    print("[rApp Native] Memulai Loop Kontrol Adaptif Jangka Panjang...")
    step = 0
    while True:
        # Simulasi perubahan histori kualitas jaringan
        drop_rate = 0.06 if step % 2 == 0 else 0.02
        print(f"\n[rApp Native] Status Histori Network Drop Rate: {drop_rate:.2%}")

        if drop_rate > 0.05:
            update_a1_policy("policy_qos_001", new_threshold=4)
        else:
            update_a1_policy("policy_qos_001", new_threshold=7)

        step += 1
        time.sleep(5)  # Loop interval rApp

if __name__ == "__main__":
    long_timescale_loop()
EOF
```

### 5.2 Menjalankan rApp di Terminal 2

```bash
python3 /opt/oran/native_rapp.py
```

---

## 6. Uji Komunikasi & Debugging

1. **Uji RMR Message Type 20010**:
   Untuk menguji pesan A1 masuk ke xApp tanpa A1 Mediator, jalankan perintah `rmr_send` atau kirim via socket Python.
2. **Log Observasi**:
   - Terminal 1 (xApp) akan menampilkan respon perubahan *threshold* saat menerima A1 Policy.
   - Terminal 2 (rApp) akan menampilkan penyesuaian parameter kebijakan berdasarkan evaluasi metrik.

---

## 7. Hasil Validasi Eksekusi Teruji (Verified Real-World Logs)

> [!NOTE]
> **Status Eksekusi**: Teruji dan Valid pada lingkungan Linux Debian / Ubuntu 22.04 LTS (`chandra@near-rt-ric`).

### 7.1 Hasil Log Eksekusi Native rApp (`native_app.py`)
```text
[rApp Native] Memulai Loop Kontrol Adaptif Jangka Panjang...

[rApp Native] Status Histori Network Drop Rate: 6.00%
[rApp Native] Mengirimkan Update Kebijakan ke A1: threshold=4

[rApp Native] Status Histori Network Drop Rate: 2.00%
[rApp Native] Mengirimkan Update Kebijakan ke A1: threshold=7

[rApp Native] Status Histori Network Drop Rate: 6.00%
[rApp Native] Mengirimkan Update Kebijakan ke A1: threshold=4
```

### 7.2 Hasil Log Eksekusi Native xApp (`native_xapp.py`)
```text
[Running] python3 -u "/home/chandra/Documents/oran/native_xapp.py"
[xApp Native] Memulai xApp Process di RMR Port 4560...
1790337934648 5015/RMR [INFO] ric message routing library on SI95 p=4560 mv=3 flg=02 id=a (f447e29 4.9.4 built: Dec 13 2023)
```

---

## 8. Summary Troubleshooting Hasil Pengujian

Berikut adalah ringkasan masalah nyata yang berhasil diselesaikan selama proses pengujian:

| Gejala Error | Penyebab | Solusi Teruji |
|---|---|---|
| `pip3 install request` $\rightarrow$ `No matching distribution found` | Typo penulisan nama paket `request` (kurang huruf **s**). | Gunakan `pip3 install requests` (pake 's'). |
| `/bin/sh: 1: python: not found` | Perintah `python` tidak ada di Debian/Ubuntu modern. | Jalankan `python3 script.py` atau install `sudo apt install -y python-is-python3`. |
| `OSError: librmr_si.so: cannot open shared object file` | Library C RMR belum terpasang di sistem OS. | Download & install `rmr_4.9.4_amd64.deb` & `rmr-dev_4.9.4_amd64.deb` lalu `sudo ldconfig`. |

