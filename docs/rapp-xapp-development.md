# Panduan Pengembangan & Riset rApp dan xApp

Dokumen ini berisi panduan teknis dan referensi riset lengkap untuk mengembangkan komponen **rApp (Non-RT RIC)** dan **xApp (Near-RT RIC)** pada platform eksperimen tesis *Multi-Timescale QoS-Aware Traffic Steering in Multi-Slice O-RAN*.

---

## Daftar Isi
1. [Gambaran Umum & Arsitektur Kontrol](#1-gambaran-umum--arsitektur-kontrol)
2. [Panduan Pengembangan xApp (VM-2)](#2-panduan-pengembangan-xapp-vm-2)
3. [Panduan Pengembangan rApp (VM-1)](#3-panduan-pengembangan-rapp-vm-1)
4. [Kata Kunci Referensi Studi Literatur](#4-kata-kunci-referensi-studi-literatur)
5. [Checklist Verifikasi & Pengujian](#5-checklist-verifikasi--pengujian)
6. [Audit Potensi Kegagalan & Mitigasi Error](#6-audit-potensi-kegagalan--mitigasi-error)

---

## 1. Gambaran Umum & Arsitektur Kontrol

Mekanisme riset berpatokan pada koordinasi dua *control loop* dengan skala waktu berbeda:

```text
 ┌──────────────────────────────────────────────────────────────┐
 │                     rApp (VM-1: Non-RT RIC)                  │
 │ • Skala Waktu : Jangka Panjang (> 1 detik hingga menit/jam)  │
 │ • Input       : Metrik Histori QoS/KPI dari Prometheus       │
 │ - Output      : Pembaruan Kebijakan A1 Adaptif (Skema 20008) │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                │ Antarmuka A1 (A1 PMS / Shim / Mediator)
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                    xApp (VM-2: Near-RT RIC)                  │
 │ • Skala Waktu : Near-Real-Time (ms hingga < 1 detik)         │
 │ • Input       : Telemetri Real-Time E2 + Batasan Kebijakan A1│
 │ • Output      : Keputusan Traffic Steering / Handover via E2 │
 └──────────────────────────────┬───────────────────────────────┘
                                │
                                │ Antarmuka Kontrol E2 (E2Term / E2 Agent)
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                       OAI RAN (VM-4)                         │
 │ • gNB CU / DU-1 (Sel-1) & DU-2 (Sel-2)                       │
 └──────────────────────────────────────────────────────────────┘
```

> [!NOTE]
> **Kooperasi rApp & xApp**: rApp **bukan** pengganti xApp. rApp menetapkan batas aturan/kebijakan makro (*policy constraint*), sedangkan xApp mengeksekusi keputusan *steering* mikronya secara cepat berdasarkan aturan dari rApp tersebut.

---

## 2. Panduan Pengembangan xApp (VM-2)

### 2.1 Spesifikasi Lingkungan
| Parameter | Nilai / Konfigurasi |
|---|---|
| **Lokasi File Kode** | `/opt/oran/nearrt/oran-sc-ric/xApps/python/a1_policy_xapp.py` |
| **Framework** | `ricxappframe` (O-RAN SC Python xApp Framework) |
| **Protokol Komunikasi** | RMR (RIC Message Router) |
| **RMR Message Type Received** | `20010` (A1 Policy Instance Update) |
| **RMR Message Type Response** | `20011` (A1 Policy Response ACK/NACK) |

### 2.2 Skema Kebijakan Baseline (Policy Type ID 20008)
```json
{
  "threshold": 5,
  "target_qos_latency_ms": 20,
  "slice_priority": ["slice_1", "slice_2"]
}
```

### 2.3 Kode Skeleton xApp Python (`a1_policy_xapp.py`)
```python
import json
import time
from ricxappframe.xapp_frame import RMRXapp

# Cache kebijakan lokal
current_policy = {
    "threshold": 5,
    "target_qos_latency_ms": 20
}

def handle_a1_policy(self, summary, sbuf):
    """
    Callback function saat pesan A1 Policy (RMR 20010) diterima dari A1 Mediator.
    """
    global current_policy
    try:
        payload = json.loads(summary["payload"].decode("utf-8"))
        print(f"[xApp] Menerima Kebijakan A1 Baru: {payload}")

        # Perbarui variabel kebijakan lokal secara aman
        if "threshold" in payload:
            current_policy["threshold"] = payload["threshold"]
        if "target_qos_latency_ms" in payload:
            current_policy["target_qos_latency_ms"] = payload["target_qos_latency_ms"]

        # Kirim balasan konfirmasi ACK via RMR (Message Type 20011)
        ack_payload = json.dumps({"status": "SUCCESS", "policy_type_id": 20008}).encode("utf-8")
        self.rmr_rts(sbuf, new_mtype=20011, payload=ack_payload)
        print("[xApp OK] ACK Kebijakan A1 berhasil dikirim kembali ke A1 Mediator.")

    except Exception as e:
        print(f"[xApp ERROR] Gagal memproses Kebijakan A1: {e}")

def traffic_steering_loop(xapp):
    """
    Loop kontrol Near-Real-Time yang mengeksekusi logika traffic steering.
    """
    while True:
        # 1. Baca telemetri E2 real-time (Mockup / E2 Subscription)
        cell1_prb_utilization = fetch_e2_prb_usage(cell_id=1)
        
        # 2. Evaluasi kondisi steering berdasarkan batasan A1 Policy saat ini
        if cell1_prb_utilization > (current_policy["threshold"] * 10):
            print(f"[xApp ACTION] Beban Sel 1 tinggi ({cell1_prb_utilization}% > {current_policy['threshold']*10}%). Memicu steering ke Sel 2...")
            execute_e2_handover(target_cell_id=2)
            
        time.sleep(0.5)  # Eksekusi loop near-RT setiap 500 ms

def fetch_e2_prb_usage(cell_id):
    # Logika pembacaan metrik E2 (PRB utilization)
    return 75.0

def execute_e2_handover(target_cell_id):
    # Logika pengiriman perintah handover E2 ke gNB CU/DU
    pass

if __name__ == "__main__":
    xapp = RMRXapp(default_handler=handle_a1_policy, rmr_port=4560, post_init=traffic_steering_loop)
    xapp.run()
```

---

## 3. Panduan Pengembangan rApp (VM-1)

### 3.1 Spesifikasi Lingkungan
| Parameter | Nilai / Konfigurasi |
|---|---|
| **Lokasi File Kode** | `/opt/oran/nonrt/rApp/qos_policy_rapp.py` |
| **Layanan Tujuan** | A1 Policy Management Service (A1 PMS) pada `http://10.10.10.11:8081` |
| **Protokol Komunikasi** | HTTP / REST API (`PUT /a1-policy/v2/policies/{policy_id}`) |
| **Sumber Data Histori** | Prometheus pada `http://10.10.10.16:9090` |

### 3.2 Kode Skeleton rApp Python (`qos_policy_rapp.py`)
```python
import requests
import time
import json

A1_PMS_URL = "http://10.10.10.11:8081/a1-policy/v2/policies"
PROMETHEUS_URL = "http://10.10.10.16:9090/api/v1/query"

def get_historical_qos_drop_rate():
    """
    Mengambil data rata-rata penurunan QoS dari Prometheus di VM-6.
    """
    try:
        response = requests.get(PROMETHEUS_URL, params={'query': 'avg_over_time(ran_packet_loss[5m])'}, timeout=5)
        data = response.json()
        return float(data['data']['result'][0]['value'][1])
    except Exception:
        # Nilai metrik fallback jika Prometheus belum aktif
        return 0.03

def update_a1_policy(policy_id, new_threshold):
    """
    Mengirimkan pembaruan A1 Policy ke A1 PMS di VM-1.
    """
    payload = {
        "ric_id": "near-rt-ric-1",
        "policy_id": policy_id,
        "policytype_id": "20008",
        "policy_data": {
            "threshold": new_threshold
        }
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        res = requests.put(f"{A1_PMS_URL}/{policy_id}", json=payload, headers=headers, timeout=5)
        if res.status_code in [200, 201]:
            print(f"[rApp SUCCESS] Kebijakan A1 {policy_id} diperbarui dengan threshold={new_threshold}")
        else:
            print(f"[rApp ERROR] Gagal update policy: Status {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[rApp CRITICAL] Gagal menghubungi A1 PMS: {e}")

def long_timescale_control_loop():
    print("[rApp] Memulai Loop Adaptasi Kebijakan QoS Skala Waktu Panjang...")
    while True:
        drop_rate = get_historical_qos_drop_rate()
        print(f"[rApp METRIC] Drop rate QoS 5 menit: {drop_rate:.2%}")
        
        # Logika Adaptif Jangka Panjang
        if drop_rate > 0.05:
            # Jaringan terdegradasi -> perketat threshold agar xApp lebih agresif
            update_a1_policy(policy_id="policy_qos_001", new_threshold=4)
        else:
            # Jaringan normal -> threshold standar
            update_a1_policy(policy_id="policy_qos_001", new_threshold=7)
            
        time.sleep(30)  # Loop jangka panjang berjalan setiap 30 detik

if __name__ == "__main__":
    long_timescale_control_loop()
```

---

## 4. Kata Kunci Referensi Studi Literatur

Gunakan kata kunci bahasa Inggris berikut untuk pencarian jurnal di **IEEE Xplore**, **Google Scholar**, atau **ResearchGate**:

### 4.1 Topik Utama & Arsitektur
- `O-RAN traffic steering rApp xApp coordination`
- `Multi-timescale control O-RAN Non-RT RIC Near-RT RIC`
- `QoS-aware traffic steering multi-slice O-RAN`
- `A1 policy guided Near-RT RIC xApp`
- `Multi-slice resource allocation O-RAN E2 KPM`

### 4.2 Algoritma & Implementasi Riset
- `Deep Reinforcement Learning O-RAN traffic steering rApp xApp`
- `Heuristic traffic steering O-RAN A1 policy`
- `O-RAN SC xApp python ricxappframe traffic steering`
- `OpenAirInterface E2 agent traffic steering handover`
- `O-RAN A1 Policy Management Service A1PMS OSC`

---

## 5. Checklist Verifikasi & Pengujian

> [!TIP]
> Lakukan pengujian secara bertahap dari bawah ke atas (Bottom-Up Verification).

1. **Verifikasi A1 Compatibility Shim di VM-2**: Pastikan NGINX proxy berjalan di port `10001` dan mampu meneruskan request ke A1 Mediator di port `10000`.
2. **Kirim Kebijakan Uji dari rApp**: Jalankan `qos_policy_rapp.py` di VM-1 dan pastikan mendapat respon HTTP `200 OK` / `201 Created`.
3. **Cek Log xApp di VM-2**:
   ```bash
   docker logs -f python_xapp_container
   ```
   Pastikan log `[xApp] Menerima Kebijakan A1 Baru` muncul dan RMR ACK `20011` berhasil dikirim balik.
4. **Amati Aksi Traffic Steering**: Pastikan ketika pemanfaatan PRB berubah, xApp memicu fungsi *handover/steering* E2.

---

## 6. Audit Potensi Kegagalan & Mitigasi Error

Berikut adalah daftar audit kritis untuk mencegah kegagalan integrasi:

| Titik Potensi Kegagalan | Penyebab Utama | Solusi & Mitigasi Error |
|---|---|---|
| **1. xApp Tidak Menerima Pesan A1 (Message Type 20010)** | RMR Routing Table (`routes.rtg`) belum mendaftarkan rute xApp. | Tambahkan rute berikut di `routes.rtg` VM-2:<br>`newroute \| 20010 \| 10.0.2.12:4560`. |
| **2. State PMS `UNAVAILABLE` di VM-1** | A1 PMS memanggil A1 Mediator langsung tanpa melewati Shim Compatibility. | Gunakan `OscA1Client` dan arahkan `baseUrl` ke Shim NGINX `http://10.10.10.12:10001`. |
| **3. Container xApp Hang Saat Inisialisasi RMR** | Variable environment `RMR_SEED_RT` belum diset di Docker. | Set environment variable:<br>`RMR_SEED_RT=/opt/oran/nearrt/oran-sc-ric/ric/configs/routes.rtg`. |
| **4. xApp Crash Saat Reading Payload JSON** | Format JSON rApp tidak memiliki key yang di-expect (misal `KeyError`). | Gunakan metode aman `payload.get('threshold', default_val)` (Lihat contoh kode defensif di bawah). |
| **5. rApp Putus Koneksi ke Prometheus / A1 PMS** | Fluktuasi jaringan VM atau restart service. | Tambahkan parameter `timeout=5` dan penanganan `try-except` pada setiap HTTP request di rApp. |
| **6. Gagal Mengirim ACK 20011 ke A1 Mediator** | Port RMR sender terblokir atau buffer `sbuf` terdistorsi. | Panggil `self.rmr_rts(sbuf, new_mtype=20011, payload=...)` menggunakan `sbuf` asli dari callback. |

### Kode Python xApp Defensif (Anti-Crash Callback Example)
```python
def handle_a1_policy_safe(self, summary, sbuf):
    """
    Fungsi Callback defensif yang aman dari KeyError & Payload Corrupt.
    """
    global current_policy
    if summary is None or "payload" not in summary:
        print("[WARN] Menerima buffer RMR kosong.")
        return

    try:
        raw_payload = summary["payload"].decode("utf-8")
        payload = json.loads(raw_payload)
        
        # Pengaksesan nilai secara aman dengan default fallback
        threshold = payload.get("threshold", current_policy["threshold"])
        target_qos = payload.get("target_qos_latency_ms", current_policy["target_qos_latency_ms"])

        current_policy["threshold"] = threshold
        current_policy["target_qos_latency_ms"] = target_qos
        print(f"[xApp OK] Kebijakan diperbarui secara aman: {current_policy}")

        # Kirim Balasan ACK ke Mediator
        ack_body = json.dumps({"status": "SUCCESS", "policy_type_id": 20008}).encode("utf-8")
        self.rmr_rts(sbuf, new_mtype=20011, payload=ack_body)

    except json.JSONDecodeError:
        print("[ERROR] Payload A1 yang diterima bukan format JSON valid!")
    except Exception as err:
        print(f"[ERROR UNEXPECTED] Gagal memproses kebijakan A1: {err}")
```
