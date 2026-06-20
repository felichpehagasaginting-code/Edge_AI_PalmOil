# Edge AI Palm Oil FFB (TBS) Grading System

## Complete Production-Ready Codebase

**Target Platform:** Analog Devices MAX78000FTHR + ESP-12E Edge Gateway + Factory Server Stack  
**Classification System:** 4-class FFB/TBS grading (Mentah, Matang, Overripe, Janjang Kosong)

---

## Repository Structure

```text
IoT_Grad_Scanner/
│
├── 0_shared/                         # Common Utilities & Shared Libraries
│   ├── config_loader.py              # Configuration manager
│   ├── database_schema.sql           # Shared SQL Database definition
│   ├── db_logging.py                 # SQLite/PostgreSQL logger
│   ├── demo_system.py                # Full integration test demo
│   ├── error_tracker.py              # Robust diagnostic & error handler
│   ├── logger_config.py              # Python logging utility
│   ├── logging_config.yaml           # YAML configuration for logger
│   ├── performance_monitor.py        # System performance profiling tool
│   ├── requirements.txt              # Shared requirements
│   ├── QUICK_REFERENCE.md            # Quick reference guide
│   └── README_LOGGING_SYSTEM.md      # Detailed system integration guide
│
├── 1_ai_training/                    # Python AI Training Pipeline
│   ├── models/
│   │   └── tbs_classifier.py         # ai8x CNN model (< 442 KB weights)
│   ├── policies/
│   │   └── qat_policy_8b.yaml        # 8-bit QAT Distiller schedule
│   ├── dataset/
│   │   └── tbs_dataset.py            # Custom PyTorch dataset loader
│   ├── train_pipeline.sh             # 2-phase training script
│   └── README_synthesis.md           # ai8xize.py conversion guide
│
├── 2_max78000_firmware/              # MAX78000FTHR C Firmware (MSDK)
│   ├── include/
│   │   ├── camera.h                  # OV7692 camera driver API
│   │   ├── preprocess.h              # Image preprocessing API
│   │   ├── cnn_inference.h           # CNN accelerator API
│   │   └── uart_comm.h               # UART + buzzer API
│   ├── src/
│   │   ├── main.c                    # Central control loop
│   │   ├── cam_ov7692.c              # OV7692 camera driver implementation
│   │   ├── preprocess.c              # RGB565→INT8 normalization
│   │   ├── cnn_inference.c           # CNN HW inference + softmax
│   │   └── uart_comm.c               # JSON TX + buzzer GPIO
│   ├── cnn_generated/
│   │   ├── tbs_cnn.h                 # ⚠ STUB — replace with ai8xize output
│   │   ├── tbs_cnn.c                 # ⚠ STUB — replace with ai8xize output
│   │   └── weights.h                 # ⚠ STUB — replace with ai8xize output
│   └── Makefile                      # ARM GCC + MSDK build system
│
├── 3_esp12e_gateway/                 # ESP-12E Arduino C++ Gateway
│   └── gateway_main/
│       └── gateway_main.ino          # MQTT + LoRa failover gateway
│
├── 4_server_backend/                 # Docker Factory Server Stack
│   ├── docker-compose.yml            # 6-service stack
│   ├── mosquitto/
│   │   ├── mosquitto.conf            # Mosquitto 2.x config
│   │   └── passwd                    # ⚠ STUB — generate with mosquitto_passwd
│   ├── timescaledb/
│   │   └── init.sql                  # Schema + hypertables + views
│   ├── grafana/
│   │   └── provisioning/datasources/
│   │       └── timescale.yaml        # Auto-provisioned datasource
│   └── mqtt_to_db/
│       ├── mqtt_to_db.py             # Python MQTT→DB bridge daemon
│       ├── requirements.txt          # Python dependencies
│       └── Dockerfile                # Daemon container build
│
└── 5_web_dashboard/                  # Custom Real-Time Web Dashboard
    ├── backend/
    │   ├── api_server.py             # FastAPI REST API → TimescaleDB
    │   ├── api_server_monitoring_integration.py # API monitoring setup
    │   ├── monitoring_api.py         # Monitoring endpoints
    │   ├── requirements.txt
    │   └── Dockerfile
    ├── frontend/
    │   ├── index.html                # Dashboard SPA
    │   ├── monitoring.html           # Diagnostics Dashboard Page
    │   ├── monitoring.js             # Diagnostics Dashboard Frontend Logic
    │   ├── css/dashboard.css         # Dark industrial theme
    │   └── js/
    │       ├── config.js             # Dashboard configuration
    │       ├── mqtt_client.js        # Paho MQTT WebSocket client
    │       ├── charts.js             # Chart.js visualizations
    │       ├── indicators.js         # LED & card indicators
    │       └── dashboard.js          # Main orchestrator
    ├── nginx.conf                    # Frontend + API reverse proxy
    ├── IMPLEMENTATION_UI_COMPLETE.txt
    ├── MONITORING_DASHBOARD_GUIDE.md
    └── MONITORING_UI_SUMMARY.md
```

---

## ⚙️ Panduan Menjalankan Program (Step by Step)

> **Urutan eksekusi wajib diikuti.** Setiap tahap bergantung pada tahap sebelumnya.

---

### 📋 TAHAP 0 — Persiapan Awal (Satu Kali)

#### 0.1 Install Prerequisites

| Software | Versi | Link |
| --- | --- | --- |
| **Maxim MSDK** | Latest | [github.com/analogdevicesinc/msdk](https://github.com/analogdevicesinc/msdk) |
| **ai8x-training SDK** | Latest | [github.com/analogdevicesinc/ai8x-training](https://github.com/analogdevicesinc/ai8x-training) |
| **ai8x-synthesis SDK** | Latest | [github.com/analogdevicesinc/ai8x-synthesis](https://github.com/analogdevicesinc/ai8x-synthesis) |
| **Arduino IDE 2.x** | 2.x | [arduino.cc](https://www.arduino.cc) |
| **ESP8266 Board Package** | 3.x | Lewat Arduino Board Manager |
| **Docker + Docker Compose** | v2.x | [docker.com](https://docker.com) |
| **Python** | 3.9–3.11 | [python.org](https://python.org) |

#### 0.2 Clone Repository

```bash
git clone https://github.com/<your-username>/IoT_Grad_Scanner.git
cd IoT_Grad_Scanner
```

#### 0.3 Sambungkan Hardware (Wiring)

Pasang kabel sesuai tabel di bawah sebelum flashing firmware apapun:

**MAX78000FTHR → ESP-12E:**

```text
MAX78000 P0.1 (TX)  ──►  ESP-12E GPIO3 (RX)
MAX78000 P0.0 (RX)  ◄──  ESP-12E GPIO1 (TX)
MAX78000 GND        ──►  ESP-12E GND
```

**ESP-12E → LoRa-02 (SX1278):**

```text
ESP-12E GPIO15  ──►  LoRa NSS (CS)
ESP-12E GPIO14  ──►  LoRa SCK
ESP-12E GPIO13  ──►  LoRa MOSI
ESP-12E GPIO12  ──►  LoRa MISO
ESP-12E GPIO16  ──►  LoRa RST
ESP-12E GPIO4   ──►  LoRa DIO0
```

**Sensor ke MAX78000:**

```text
Photoelectric Sensor DO  ──►  MAX78000 P0.14  (+10kΩ pull-up ke 3.3V)
Buzzer (-)               ──►  MAX78000 P0.12
Buzzer (+)               ──►  3.3V
```

---

### 🧠 TAHAP 1 — Latih Model AI (Di PC/Server GPU)

> Lewati tahap ini jika sudah punya file checkpoint `.pth.tar`.

#### Step 1.1 — Setup ai8x-training

```bash
# Clone SDK
git clone https://github.com/analogdevicesinc/ai8x-training.git
cd ai8x-training

# Buat virtual environment (direkomendasikan)
python -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

#### Step 1.2 — Siapkan Dataset

```bash
# Buat struktur folder dataset
mkdir -p data/TBSDataset/train/{0_mentah,1_matang,2_overripe,3_janjang_kosong}
mkdir -p data/TBSDataset/val/{0_mentah,1_matang,2_overripe,3_janjang_kosong}

# Isi setiap folder dengan foto tandan (minimal 500 gambar per kelas)
# Format: JPG/PNG, resolusi bebas (akan di-resize otomatis ke 128×128)
#
# Contoh isi folder:
#   data/TBSDataset/train/1_matang/
#     ├── IMG_001.jpg
#     ├── IMG_002.jpg
#     └── ...
```

#### Step 1.3 — Copy File Proyek ke SDK

```bash
# Dari root IoT_Grad_Scanner/
cp 1_ai_training/models/tbs_classifier.py  ai8x-training/models/
cp 1_ai_training/dataset/tbs_dataset.py    ai8x-training/datasets/
cp 1_ai_training/policies/qat_policy_8b.yaml ai8x-training/policies/
```

#### Step 1.4 — Jalankan Training (2 Fase)

```bash
cd ai8x-training

# Fase 1: Float training (200 epoch, ~4-8 jam tergantung GPU)
python train.py \
    --model TBSClassifier \
    --dataset TBSDataset \
    --epochs 200 \
    --lr 0.001 \
    --optimizer Adam \
    --save-dir logs/TBSClassifier/phase1

# Fase 2: Quantization-Aware Training / QAT (100 epoch)
python train.py \
    --model TBSClassifier \
    --dataset TBSDataset \
    --epochs 100 \
    --lr 0.0001 \
    --optimizer Adam \
    --compress policies/qat_policy_8b.yaml \
    --resume-from logs/TBSClassifier/phase1/best.pth.tar \
    --save-dir logs/TBSClassifier/phase2

# Atau jalankan kedua fase sekaligus:
bash 1_ai_training/train_pipeline.sh
```

**✅ Cek hasil:** File `logs/TBSClassifier/phase2/best.pth.tar` harus terbentuk.

---

### ⚙️ TAHAP 2 — Sintesis Kode C dari Model (ai8xize)

> Tahap ini mengkonversi model PyTorch → kode C yang berjalan di CNN hardware MAX78000.

#### Step 2.1 — Setup ai8x-synthesis

```bash
git clone https://github.com/analogdevicesinc/ai8x-synthesis.git
cd ai8x-synthesis
pip install -r requirements.txt
```

#### Step 2.2 — Buat File Konfigurasi Jaringan

Buat file `ai8x-synthesis/networks/tbs_classifier-hwc.yaml` dengan isi:
```yaml
# Lihat 1_ai_training/README_synthesis.md untuk contoh lengkap
arch: tbs_classifier
dataset: TBSDataset
```
> Lihat [`1_ai_training/README_synthesis.md`](1_ai_training/README_synthesis.md) untuk konfigurasi YAML lengkap.

#### Step 2.3 — Jalankan ai8xize.py

```bash
cd ai8x-synthesis

python ai8xize.py \
    --prefix tbs_cnn \
    --checkpoint-file ../ai8x-training/logs/TBSClassifier/phase2/best.pth.tar \
    --config-file networks/tbs_classifier-hwc.yaml \
    --device MAX78000 \
    --compact-weights \
    --mexpress \
    --embedded-code \
    --overwrite \
    --verbose
```

#### Step 2.4 — Copy File yang Dihasilkan ke Firmware

```bash
# Copy 3 file yang di-generate ke folder cnn_generated/
cp tests/tbs_cnn/tbs_cnn.c  ../IoT_Grad_Scanner/2_max78000_firmware/cnn_generated/
cp tests/tbs_cnn/tbs_cnn.h  ../IoT_Grad_Scanner/2_max78000_firmware/cnn_generated/
cp tests/tbs_cnn/weights.h  ../IoT_Grad_Scanner/2_max78000_firmware/cnn_generated/
```

**✅ Cek:** Ketiga file di `cnn_generated/` sekarang berisi kode asli, bukan stub.

---

### 💾 TAHAP 3 — Build & Flash Firmware MAX78000FTHR

#### Step 3.1 — Install MSDK

```bash
# Download installer dari:
# https://github.com/analogdevicesinc/msdk/releases

# Default install path: ~/MaximSDK
# Verifikasi instalasi:
ls ~/MaximSDK/Tools/GNUTools/10.3/bin/arm-none-eabi-gcc
```

#### Step 3.2 — Build Firmware

```bash
cd IoT_Grad_Scanner/2_max78000_firmware

# Build debug (default)
make

# Atau build release (teroptimasi, tanpa debug symbols)
make release

# Cek ukuran binary vs memory limit
make size
# Flash: 512 KB limit | SRAM: 128 KB limit
```

**Output yang diharapkan:**

```text
[CC]  src/main.c
[CC]  src/camera.c
...
[LD]  build/tbs_grader.elf
[BIN] build/tbs_grader.bin
Build complete: build/tbs_grader.bin
```

#### Step 3.3 — Flash ke Board

```bash
# Sambungkan MAX78000FTHR ke PC via USB (MAX32625PICO debugger)
# LED debugger harus menyala

# Flash firmware
make flash

# Flash + buka serial monitor (115200 baud)
make flash-and-monitor
```

**✅ Output serial yang diharapkan:**

```text
=========================================
  Edge AI Palm Oil FFB Grading System
  Target: MAX78000FTHR
=========================================
[MAIN] System clock: 100000000 Hz
[MAIN] Initializing camera module...
[MAIN] Initializing CNN hardware accelerator...
[MAIN] Configuring proximity sensor GPIO interrupt...
{"status":"READY","dev":"MAX78000"}
[MAIN] System ready. Waiting for conveyor trigger...
```

---

### 📡 TAHAP 4 — Flash Gateway ESP-12E

#### Step 4.1 — Install Library Arduino

Buka Arduino IDE → **Tools → Manage Libraries**, install:

- `ArduinoJson` by Benoit Blanchon (v6.x)
- `PubSubClient` by Nick O'Leary (v2.8+)
- `LoRa` by Sandeep Mistry (v0.8+)

Install **ESP8266 Board Package:**

1. **File → Preferences → Additional Board Manager URLs:**

   ```text
   http://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
2. **Tools → Board Manager** → cari `esp8266` → Install

#### Step 4.2 — Edit Konfigurasi Gateway

Buka `3_esp12e_gateway/gateway_main/gateway_main.ino`, ubah baris berikut:

```cpp
// ═══ WAJIB DIUBAH SEBELUM FLASH ═══
const char *WIFI_SSID      = "NAMA_WIFI_FACTORY";     // ← Ganti ini
const char *WIFI_PASSWORD  = "PASSWORD_WIFI";          // ← Ganti ini
const char *MQTT_BROKER_IP = "192.168.1.100";          // ← IP server factory
```

> **Cek IP server:** Jalankan `hostname -I` di server factory.  
> **LoRa Indonesia:** Pastikan `LORA_FREQUENCY = 433E6` (sudah default).

#### Step 4.3 — Flash ke ESP-12E

1. **Tools → Board → ESP8266 Boards → Generic ESP8266 Module**
2. **Tools → Upload Speed → 115200**
3. **Tools → Flash Size → 4MB (FS:2MB OTA:~1019KB)**
4. Tahan tombol FLASH pada board, klik **Upload**, lepas tombol saat upload mulai
5. **Tools → Serial Monitor** (115200 baud) untuk melihat log

**✅ Output Serial yang diharapkan:**

```text
=========================================
  ESP-12E Edge Gateway — TBS Grader
=========================================
[GW] Initializing LoRa-02 (SX1278) at 433 MHz...
[GW] LoRa initialized successfully.
[GW] Connecting to Wi-Fi: NAMA_WIFI_FACTORY
[GW] Wi-Fi connected! IP: 192.168.1.101, RSSI: -65 dBm
[GW] Connecting to MQTT broker 192.168.1.100...
[GW] MQTT connected.
[GW] Setup complete. Listening for MAX78000 data...
```

---

### 🐳 TAHAP 5 — Jalankan Server Backend (Docker)

#### Step 5.1 — Generate Password Mosquitto

```bash
cd IoT_Grad_Scanner/4_server_backend

# Generate password file (ganti 'secure_mqtt_pass' dengan password pilihan Anda)
docker run --rm eclipse-mosquitto:2.0.18 \
    mosquitto_passwd -b /dev/stdout iot_gateway secure_mqtt_pass \
    > mosquitto/passwd

# Verifikasi isi file (harus ada hash, bukan plaintext)
cat mosquitto/passwd
# Output: iot_gateway:$7$101$xxxx...
```

#### Step 5.2 — Sesuaikan Password di docker-compose.yml

Buka `4_server_backend/docker-compose.yml` dan ganti semua password default:

```yaml
# Cari dan ganti baris-baris ini:
POSTGRES_PASSWORD: secure_db_pass_123   # ← Ganti
MQTT_PASSWORD:     secure_mqtt_pass     # ← Harus sama dengan Step 5.1
DB_PASSWORD:       secure_db_pass_123   # ← Sama dengan POSTGRES_PASSWORD
GF_SECURITY_ADMIN_PASSWORD: admin_grafana_pass  # ← Ganti
```

#### Step 5.3 — Jalankan Semua Services

```bash
cd IoT_Grad_Scanner/4_server_backend

# Start semua 6 services (background)
docker-compose up -d

# Pantau proses startup (tunggu sampai semua "healthy")
docker-compose ps

# Ikuti log MQTT daemon untuk verifikasi data masuk
docker-compose logs -f mqtt_to_db
```

**Output `docker-compose ps` yang diharapkan (setelah ~30 detik):**

```text
NAME                  IMAGE                      STATUS
tbs_mosquitto         eclipse-mosquitto:2.0.18   Up (healthy)
tbs_timescaledb       timescale/timescaledb:...  Up (healthy)
tbs_mqtt_to_db        iot_grad_scanner-mqtt...   Up
tbs_grafana           grafana/grafana:10.2.0     Up (healthy)
tbs_dashboard_api     iot_grad_scanner-dash...   Up (healthy)
tbs_dashboard_nginx   nginx:1.25-alpine          Up (healthy)
```

#### Step 5.4 — Verifikasi Database Berjalan

```bash
# Cek schema database berhasil dibuat
docker exec tbs_timescaledb \
    psql -U tbs_user -d grading_db \
    -c "SELECT * FROM v_recent_events LIMIT 5;"

# Harus ada 7 baris sample data dari init.sql
```

---

### 🖥️ TAHAP 6 — Akses Web Dashboard & Grafana

#### Web Dashboard (Custom UI)

```text
http://<IP-SERVER-FACTORY>/
```

Buka di browser dari komputer manapun di jaringan factory.

**Indikator di navbar yang harus hijau:**

- 🟢 **MQTT** — terkoneksi ke Mosquitto via WebSocket
- 🟢 **Server** — API backend online

Setelah hardware aktif (Tahap 3 & 4):

- 🟢 **MAX78000** — berkedip setiap kali ada scan
- 🟢 **ESP-12E** — update dari heartbeat 30 detik
- 🟢 **LoRa** — status dari ESP-12E

#### Grafana Dashboard (Advanced Analytics)

```text
http://<IP-SERVER-FACTORY>:3000/
Username: admin
Password: admin_grafana_pass  (atau yang sudah diubah)
```

---

### 🧪 TAHAP 7 — Uji Sistem End-to-End

#### Test 1 — Kirim Data Manual via MQTT (tanpa hardware)

```bash
# Dari komputer manapun di jaringan factory
# Install: pip install paho-mqtt

# Kirim scan result simulasi (Grade 1 = Matang, 94% confidence)
mosquitto_pub \
    -h <IP-SERVER-FACTORY> \
    -p 1883 \
    -t "pks/grading/tbs/result" \
    -m '{"g":1,"c":94,"ts":12345,"cnt":100}' \
    -u iot_gateway \
    -P secure_mqtt_pass

# Verifikasi: baris baru muncul di Live Feed Table dashboard
```

#### Test 2 — Simulasi Anomaly Alert

```bash
# Grade 3 = Janjang Kosong → trigger anomaly alert + screen flash
mosquitto_pub \
    -h <IP-SERVER-FACTORY> \
    -p 1883 \
    -t "pks/grading/tbs/result" \
    -m '{"g":3,"c":88,"ts":12346,"cnt":101}' \
    -u iot_gateway \
    -P secure_mqtt_pass

# Verifikasi: toast merah muncul di pojok kanan atas dashboard
#             Anomaly Counter bertambah 1
#             Layar berkedip merah sebentar
```

#### Test 3 — Trigger Proximity Sensor (hardware)

```bash
# Tutup/blokir beam photoelectric sensor → MAX78000 akan:
# 1. Wake dari WFI sleep
# 2. Capture frame kamera
# 3. Inferensi CNN
# 4. Kirim JSON ke ESP-12E
# 5. ESP-12E publish MQTT
# Monitor serial MAX78000 (115200):
make flash-and-monitor
# Akan muncul: === SCAN #X STARTED === ... === SCAN #X COMPLETE ===
```

#### Test 4 — Cek Data Tersimpan di Database

```bash
docker exec tbs_timescaledb \
    psql -U tbs_user -d grading_db \
    -c "SELECT event_time, grade_name, confidence_pct, is_anomaly
        FROM grading_events
        ORDER BY event_time DESC
        LIMIT 10;"
```

---

### 🛑 Menghentikan Sistem

```bash
# Hentikan semua Docker services
cd IoT_Grad_Scanner/4_server_backend
docker-compose down

# Hentikan + hapus semua data (HATI-HATI — data hilang permanen!)
docker-compose down -v
```

---

### 🔄 Restart & Update

```bash
# Restart service tertentu
docker-compose restart mqtt_to_db
docker-compose restart dashboard_api

# Rebuild setelah ada perubahan kode backend/dashboard
docker-compose up -d --build dashboard_api dashboard_nginx

# Lihat log real-time
docker-compose logs -f               # semua services
docker-compose logs -f mqtt_to_db    # hanya MQTT daemon
docker-compose logs -f dashboard_api # hanya API

# Status & health
docker-compose ps
docker stats                          # CPU & memory usage
```

---

## Hardware Connections Reference

### MAX78000FTHR Pin Assignments

| Function | GPIO Pin | Notes |
| --- | --- | --- |
| OV7692 Camera | Built-in DVP | On-board ribbon — no wiring needed |
| UART0 TX (→ ESP-12E) | P0.1 | 115200 baud, 3.3V logic |
| UART0 RX (← ESP-12E) | P0.0 | |
| Buzzer GPIO | P0.12 | LOW = ON (low-level trigger) |
| Proximity Sensor IRQ | P0.14 | NPN OC output + 10kΩ pull-up |

### ESP-12E Pin Assignments

| Function | GPIO | Notes |
| --- | --- | --- |
| UART RX (← MAX78000) | GPIO3 (U0RXD) | Hardware Serial |
| UART TX (→ MAX78000) | GPIO1 (U0TXD) | Hardware Serial |
| LoRa-02 NSS (CS) | GPIO15 | SPI Chip Select |
| LoRa-02 SCK | GPIO14 | SPI Clock |
| LoRa-02 MOSI | GPIO13 | SPI MOSI |
| LoRa-02 MISO | GPIO12 | SPI MISO |
| LoRa-02 RST | GPIO16 | LoRa Reset |
| LoRa-02 DIO0 | GPIO4 | LoRa IRQ |

---

## Data Flow

```text
[Conveyor Belt Object]
         ↓ (photoelectric sensor trigger)
[MAX78000: GPIO IRQ wakes from WFI sleep]
         ↓
[OV7692 Camera: DMA capture 128×128 RGB565]
         ↓
[Preprocess: RGB565 → INT8, contrast enhance]
         ↓
[CNN HW Accelerator: ~5ms inference]
         ↓ {"g":1,"c":94}\n  (UART 115200 baud)
[ESP-12E Gateway: parse JSON]
         ↓
[Wi-Fi available?]
   YES → [MQTT QoS 1 → pks/grading/tbs/result]
   NO  → [LoRa-02: TBS:G1:C94 packet]
         ↓
[Mosquitto MQTT Broker]
   ├──► [mqtt_to_db.py → TimescaleDB]
   └──► [Web Dashboard: MQTT WebSocket → Live Feed]
         ↓
[Grafana Dashboard: analytics & historical charts]
```

---

## MQTT Topic Reference

| Topic | QoS | Direction | Description |
| --- | --- | --- | --- |
| `pks/grading/tbs/result` | 1 | ESP→Broker | Scan results |
| `pks/grading/tbs/status` | 0 | ESP→Broker | 30s heartbeat |
| `pks/grading/tbs/cmd` | 1 | Broker→ESP | Commands (reboot, status) |

---

## 📊 Sistem Monitoring Diagnostik & Error Tracking (`0_shared`)

Sistem ini memiliki modul diagnostik, logging terstruktur, pelacakan performa (SLA), dan manajemen alert terintegrasi yang memantau kesehatan seluruh ekosistem IoT secara real-time.

### Fitur Utama

1. **Structured JSON Logging (`logger_config.py`)**: Format log terstruktur untuk mempermudah indexing dan monitoring.
2. **Error Tracker & Alerts (`error_tracker.py`)**: Deteksi otomatis lonjakan error (spikes), pengkategorian tingkat keberatan (severity), dan error berulang.
3. **Performance Profiling & SLA (`performance_monitor.py`)**: Pengukuran latensi kueri database dan respons API untuk mendeteksi degradasi performa.
4. **Database Persistence (`db_logging.py`)**: Log, error, performa, dan alert disimpan langsung ke TimescaleDB hypertable untuk analisis jangka panjang.
5. **Diagnostics Dashboard UI (`monitoring.html` & `monitoring.js`)**: Halaman khusus di dashboard web untuk memantau kesehatan tiap komponen sistem secara real-time dengan pembaruan otomatis setiap 10 detik.

### Cara Mengakses Diagnostics Dashboard

Setelah server backend Docker berjalan (Tahap 5):

```text
http://<IP-SERVER-FACTORY>/monitoring
```

Anda dapat memantau beberapa tab:

- **Overview**: Status kesehatan sistem, tren error 60 menit terakhir, status per komponen.
- **Errors**: Tabel detail error dengan pencarian dan filter komponen/severity.
- **Alerts**: Daftar peringatan aktif dengan tombol aksi Acknowledge.
- **Components**: Status detail error count & info error terakhir per komponen.
- **Performance**: Grafik visualisasi rata-rata latensi API/DB vs target SLA.

---

## ⚠ Key Notes Before Deployment

1. **Replace CNN stub files** in `cnn_generated/` dengan output nyata dari ai8xize sebelum flash.
2. **Generate real Mosquitto passwords** — file `passwd` saat ini hanya placeholder.
3. **Change all default passwords** di `docker-compose.yml` untuk production.
4. **LoRa frequency**: Default 433 MHz untuk Indonesia. Ubah `LORA_FREQUENCY` di `gateway_main.ino` jika deploy di negara lain.
5. **MQTT broker IP**: Update `MQTT_BROKER_IP` di `gateway_main.ino` sesuai IP server factory.
6. **Dataset collection**: Minimum 500 gambar per kelas untuk akurasi model yang baik.
7. **Port 9001 (MQTT WebSocket)** harus bisa diakses dari browser — jangan diblokir firewall factory.

---

## Urutan Pengerjaan (Ringkas)

```text
TAHAP 0  → Install tools + pasang kabel hardware
TAHAP 1  → Latih model AI (butuh GPU + dataset)
TAHAP 2  → Sintesis kode C dari model terlatih
TAHAP 3  → Build + flash firmware MAX78000FTHR
TAHAP 4  → Flash gateway ESP-12E
TAHAP 5  → Jalankan server Docker
TAHAP 6  → Buka dashboard di browser
TAHAP 7  → Uji sistem end-to-end
```
