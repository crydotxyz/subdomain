# Subdomain Monitor (Multi Domain)

Script untuk monitoring subdomain baru dari crt.sh dan mengirim alert ke Telegram **dan/atau** Discord.
**Mendukung monitoring multiple domains secara bersamaan!**

## Fitur

- 🔍 Monitoring subdomain baru dari crt.sh untuk multiple domains
- 💾 Penyimpanan data subdomain di SQLite database (terpisah per domain)
- 📱 Alert otomatis ke Telegram **dan/atau** Discord (bisa pilih salah satu atau keduanya)
- ⏰ Monitoring berkelanjutan dengan interval yang dapat dikonfigurasi
- 📝 Logging lengkap untuk setiap domain
- 🚀 Support monitoring puluhan domain sekaligus
- ⚡ **Cek seluruh domain secara paralel (threading), bukan berurutan!**

## Instalasi

1. **Clone atau download script ini**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup Telegram Bot (Opsional):**
   - Chat dengan [@BotFather](https://t.me/BotFather) di Telegram
   - Buat bot baru dengan command `/newbot`
   - Dapatkan Bot Token
   - Chat dengan bot yang baru dibuat
   - Dapatkan Chat ID dengan mengirim pesan ke bot dan cek di: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`

4. **Setup Discord Webhook (Opsional):**
   - Buka Discord, klik channel yang ingin dipakai
   - Klik Edit Channel → Integrations → Webhooks → New Webhook
   - Copy Webhook URL

5. **Konfigurasi Multi Domain & Alert:**
   - Copy `config.env.example` ke `config.env`
   - Edit `config.env` dengan informasi yang sesuai:
     ```bash
     # Single domain
     DOMAINS=example.com
     
     # Multiple domains (comma-separated)
     DOMAINS=example.com,google.com,github.com,microsoft.com
     
     # Telegram (opsional)
     TELEGRAM_BOT_TOKEN=your_bot_token_here
     TELEGRAM_CHAT_ID=your_chat_id_here
     
     # Discord (opsional)
     DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url_here
     
     MONITORING_INTERVAL=3600
     ```
   - **Kamu bisa mengisi hanya Telegram, hanya Discord, atau keduanya!**

## Penggunaan

### Cara 1: Menggunakan file config
```bash
python subdomain_monitor.py
```

### Cara 2: Menggunakan environment variables
```bash
# Single domain
export DOMAINS=example.com

# Multiple domains
export DOMAINS=example.com,google.com,github.com

# Telegram (opsional)
export TELEGRAM_BOT_TOKEN=your_bot_token
export TELEGRAM_CHAT_ID=your_chat_id

# Discord (opsional)
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url_here

export MONITORING_INTERVAL=3600
python subdomain_monitor.py
```

### Cara 3: Run sebagai service (Linux)
```bash
# Buat service file
sudo nano /etc/systemd/system/subdomain-monitor.service
```

Isi dengan:
```ini
[Unit]
Description=Subdomain Monitor (Multi Domain)
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/script
Environment=DOMAINS=example.com,google.com,github.com
Environment=TELEGRAM_BOT_TOKEN=your_bot_token
Environment=TELEGRAM_CHAT_ID=your_chat_id
Environment=DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url_here
Environment=MONITORING_INTERVAL=3600
ExecStart=/usr/bin/python3 subdomain_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Kemudian:
```bash
sudo systemctl daemon-reload
sudo systemctl enable subdomain-monitor
sudo systemctl start subdomain-monitor
```

## File Output

- `subdomains.db` - Database SQLite yang menyimpan semua subdomain yang ditemukan (terpisah per domain)
- `subdomain_monitor.log` - File log dengan informasi monitoring untuk semua domain

## Monitoring Database

Untuk melihat subdomain yang sudah ditemukan:
```bash
# Semua subdomain
sqlite3 subdomains.db "SELECT * FROM subdomains ORDER BY first_seen DESC;"

# Subdomain untuk domain tertentu
sqlite3 subdomains.db "SELECT * FROM subdomains WHERE domain='example.com' ORDER BY first_seen DESC;"

# Statistik per domain
sqlite3 subdomains.db "SELECT domain, COUNT(*) as count FROM subdomains GROUP BY domain;"
```

## Cara Kerja Multi Domain & Multi Alert

1. **Script akan monitor setiap domain secara paralel (threading, BERSAMAAN, BUKAN berurutan!)**
2. **Setiap domain memiliki data terpisah di database**
3. **Alert Telegram dan/atau Discord akan dikirim terpisah untuk setiap domain**
4. **Interval monitoring berlaku untuk semua domain**

### Contoh Output Log:
```
2024-01-15 14:30:25 - INFO - Starting monitoring cycle (parallel)...
2024-01-15 14:30:25 - INFO - Checking subdomains for example.com...
2024-01-15 14:30:25 - INFO - Found 15 subdomains for example.com from crt.sh
2024-01-15 14:30:25 - INFO - No new subdomains found for example.com
2024-01-15 14:30:25 - INFO - Checking subdomains for google.com...
2024-01-15 14:30:25 - INFO - Found 25 subdomains for google.com from crt.sh
2024-01-15 14:30:25 - INFO - Found 2 new subdomain(s) for google.com: {'api.google.com', 'dev.google.com'}
2024-01-15 14:30:25 - INFO - Saved 2 new subdomains for google.com to database
2024-01-15 14:30:25 - INFO - Telegram alert sent successfully for google.com
2024-01-15 14:30:25 - INFO - Discord alert sent successfully for google.com
2024-01-15 14:30:25 - INFO - Checking subdomains for github.com...
2024-01-15 14:30:25 - INFO - Found 8 subdomains for github.com from crt.sh
2024-01-15 14:30:25 - INFO - No new subdomains found for github.com
2024-01-15 14:30:25 - INFO - Monitoring cycle completed. Next check in 3600 seconds...
```

## Troubleshooting

1. **Error Telegram Bot Token:**
   - Pastikan bot token benar
   - Pastikan bot sudah di-start (kirim `/start` ke bot)

2. **Error Chat ID:**
   - Pastikan sudah chat dengan bot
   - Cek Chat ID di: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`

3. **Error Discord Webhook:**
   - Pastikan URL webhook benar
   - Pastikan bot Discord punya akses ke channel

4. **Error crt.sh:**
   - Cek koneksi internet
   - Pastikan domain yang dimonitor valid
   - Jika terlalu banyak domain, coba kurangi atau tingkatkan interval

5. **Rate Limiting:**
   - Script sudah ada delay 5 detik antar domain untuk menghindari rate limiting
   - Jika masih error, coba tingkatkan interval monitoring

## Contoh Alert Telegram/Discord (Multi Domain)

```
🚨 New Subdomains Detected for google.com

Found 2 new subdomain(s):

1. `api.google.com`
2. `dev.google.com`

⏰ Detected at: 2024-01-15 14:30:30
```

## Test Setup

Untuk test konfigurasi multi domain:
```bash
python test_setup.py
```

## Lisensi

Script ini dibuat untuk tujuan monitoring dan security research. Gunakan dengan bertanggung jawab. 