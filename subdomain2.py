#!/usr/bin/env python3
"""
Subdomain Monitor Script
Monitors new subdomains from crt.sh and sends alerts to Telegram and/or Discord
Supports multiple domains monitoring
"""

import requests
import json
import time
import sqlite3
import os
from datetime import datetime
import logging
from typing import List, Dict, Set, Optional
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('subdomain_monitor.log'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)

CONFIG_FILE = 'config.json'

def load_config():
    """Load configuration from config.env file"""
    config = {}
    
    # Try to load from config.env file
    if os.path.exists('config.env'):
        with open('config.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        config[key] = value
    
    return config

def load_live_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_live_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

class SubdomainMonitor:
    def __init__(self, domains: List[str], telegram_bot_token: Optional[str], telegram_chat_id: Optional[str], discord_webhook_url: Optional[str], interval: int):
        self.domains = domains
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url
        self.interval = interval
        self.db_path = 'subdomains.db'
        self.lock = threading.Lock()
        self.running = True
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database to store known subdomains"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Check if release_date column exists
        cursor.execute("PRAGMA table_info(subdomains)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'release_date' not in columns:
            # If table exists, add release_date column
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subdomains'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE subdomains ADD COLUMN release_date TEXT")
        # Create table if not exists (with release_date)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subdomains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                subdomain TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                release_date TEXT,
                UNIQUE(domain, subdomain)
            )
        ''')
        conn.commit()
        conn.close()
        logging.info(f"Database initialized: {self.db_path}")
    
    def get_subdomains_from_crtsh(self, domain: str):
        """Fetch subdomains and their release date from crt.sh API for specific domain"""
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            subdomains = {}
            for entry in data:
                name_value = entry.get('name_value', '')
                entry_time = entry.get('entry_timestamp') or entry.get('not_before') or ''
                if name_value:
                    for subdomain in name_value.split('\n'):
                        subdomain = subdomain.strip().lower()
                        if subdomain and domain in subdomain:
                            subdomain = subdomain.replace('*.', '')
                            if subdomain.endswith('.' + domain):
                                # Only keep the earliest release date for each subdomain
                                if subdomain not in subdomains or (entry_time and entry_time < subdomains[subdomain]):
                                    subdomains[subdomain] = entry_time
            logging.info(f"Found {len(subdomains)} subdomains for {domain} from crt.sh")
            return subdomains  # dict: subdomain -> release_date
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data from crt.sh for {domain}: {e}")
            return {}
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing JSON response for {domain}: {e}")
            return {}
    
    def get_known_subdomains(self, domain: str) -> Set[str]:
        """Get known subdomains from database for specific domain"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT subdomain FROM subdomains WHERE domain = ?', (domain,))
        known_subdomains = {row[0] for row in cursor.fetchall()}
        conn.close()
        return known_subdomains
    
    def save_new_subdomains(self, domain: str, new_subdomains: Set[str], crtsh_subdomains: dict = None):
        """Save new subdomains to database for specific domain, with release_date if available"""
        if not new_subdomains:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for subdomain in new_subdomains:
            release_date = None
            if crtsh_subdomains and subdomain in crtsh_subdomains:
                release_date = crtsh_subdomains[subdomain]
            try:
                cursor.execute(
                    'INSERT INTO subdomains (domain, subdomain, release_date) VALUES (?, ?, ?)',
                    (domain, subdomain, release_date)
                )
            except sqlite3.IntegrityError:
                # Subdomain already exists, update last_seen
                cursor.execute(
                    'UPDATE subdomains SET last_seen = CURRENT_TIMESTAMP WHERE domain = ? AND subdomain = ?',
                    (domain, subdomain)
                )
        conn.commit()
        conn.close()
        logging.info(f"Saved {len(new_subdomains)} new subdomains for {domain} to database")
    
    def send_telegram_alert(self, domain: str, new_subdomains: Set[str], crtsh_subdomains=None):
        if not self.telegram_bot_token or not self.telegram_chat_id or not new_subdomains:
            return
        # Use release date from crtsh_subdomains if available
        if crtsh_subdomains:
            sorted_subdomains = sorted(new_subdomains, key=lambda s: crtsh_subdomains.get(s, '9999-99-99 99:99:99'))
        else:
            subdomain_dates = self.get_subdomain_dates(domain, new_subdomains)
            sorted_subdomains = sorted(new_subdomains, key=lambda s: subdomain_dates.get(s, '9999-99-99 99:99:99'))
        message = f"🚨 **New Subdomains Detected for {domain}**\n\n"
        message += f"Found {len(new_subdomains)} new subdomain(s):\n\n"
        for i, subdomain in enumerate(sorted_subdomains, 1):
            message += f"{i}. `{subdomain}`\n"
        message += f"\n⏰ Detected at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        data = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            logging.info(f"Telegram alert sent successfully for {domain}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending Telegram alert for {domain}: {e}")
    
    def send_discord_alert(self, domain: str, new_subdomains: Set[str], crtsh_subdomains=None):
        if not self.discord_webhook_url or not new_subdomains:
            return
        if crtsh_subdomains:
            sorted_subdomains = sorted(new_subdomains, key=lambda s: crtsh_subdomains.get(s, '9999-99-99 99:99:99'))
        else:
            subdomain_dates = self.get_subdomain_dates(domain, new_subdomains)
            sorted_subdomains = sorted(new_subdomains, key=lambda s: subdomain_dates.get(s, '9999-99-99 99:99:99'))
        message = f"🚨 **New Subdomains Detected for {domain}**\n\n"
        message += f"Found {len(new_subdomains)} new subdomain(s):\n\n"
        for i, subdomain in enumerate(sorted_subdomains, 1):
            message += f"{i}. `{subdomain}`\n"
        message += f"\n⏰ Detected at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        data = {
            "content": message
        }
        try:
            response = requests.post(self.discord_webhook_url, json=data, timeout=30)
            response.raise_for_status()
            logging.info(f"Discord alert sent successfully for {domain}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending Discord alert for {domain}: {e}")
    
    def get_subdomain_dates(self, domain: str, subdomains: Set[str]):
        """Get first_seen date for each subdomain from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        q = f"SELECT subdomain, first_seen FROM subdomains WHERE domain = ? AND subdomain IN ({','.join(['?']*len(subdomains))})"
        params = [domain] + list(subdomains)
        cursor.execute(q, params)
        result = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return result
    
    def monitor_domain(self, domain: str):
        """Monitor single domain"""
        try:
            logging.info(f"Checking subdomains for {domain}...")
            crtsh_subdomains = self.get_subdomains_from_crtsh(domain)  # dict: subdomain -> release_date
            current_subdomains = set(crtsh_subdomains.keys())
            known_subdomains = self.get_known_subdomains(domain)
            new_subdomains = current_subdomains - known_subdomains
            if new_subdomains:
                logging.info(f"Found {len(new_subdomains)} new subdomain(s) for {domain}: {new_subdomains}")
                self.save_new_subdomains(domain, new_subdomains, crtsh_subdomains)
                self.send_telegram_alert(domain, new_subdomains, crtsh_subdomains)
                self.send_discord_alert(domain, new_subdomains, crtsh_subdomains)
            else:
                logging.info(f"No new subdomains found for {domain}")
        except Exception as e:
            logging.error(f"Error monitoring {domain}: {e}")
    
    def set_domains(self, domains: List[str]):
        with self.lock:
            self.domains = domains
    def set_interval(self, interval: int):
        with self.lock:
            self.interval = interval
    def get_domains(self):
        with self.lock:
            return list(self.domains)
    def get_interval(self):
        with self.lock:
            return self.interval
    def stop(self):
        self.running = False
    def monitor(self):
        logging.info(f"Starting subdomain monitoring for {len(self.domains)} domains: {', '.join(self.domains)}")
        while self.running:
            try:
                domains = self.get_domains()
                interval = self.get_interval()
                logging.info(f"Starting monitoring cycle (parallel)...")
                threads = []
                for domain in domains:
                    t = threading.Thread(target=self.monitor_domain, args=(domain,))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
                logging.info(f"Monitoring cycle completed. Next check in {interval} seconds...")
                for _ in range(interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(5)

def is_domain_active(domain):
    # Try DNS resolve
    try:
        socket.gethostbyname(domain)
    except Exception:
        return False
    # Try HTTP/HTTPS
    for proto in ("https://", "http://"):
        try:
            resp = requests.get(proto + domain, timeout=5)
            if resp.status_code < 500:
                return True
        except Exception:
            continue
    return False

# --- Telegram Bot Command Handlers ---
async def add_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /add domain.com")
        return
    domain = context.args[0].strip().lower()
    monitor: SubdomainMonitor = context.bot_data['monitor']
    domains = monitor.get_domains()
    if domain in domains:
        await update.message.reply_text(f"Domain {domain} already monitored.")
        return
    # Check if domain is active
    active = is_domain_active(domain)
    if not active:
        await update.message.reply_text(f"Domain {domain} TIDAK AKTIF (tidak bisa diakses). Tidak akan dimonitor.")
        return
    domains.append(domain)
    monitor.set_domains(domains)
    # Save config
    config = load_live_config()
    config['domains'] = domains
    save_live_config(config)
    await update.message.reply_text(f"Domain {domain} added to monitoring list.")

async def del_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /del domain.com")
        return
    domain = context.args[0].strip().lower()
    monitor: SubdomainMonitor = context.bot_data['monitor']
    domains = monitor.get_domains()
    if domain not in domains:
        await update.message.reply_text(f"Domain {domain} not in monitoring list.")
        return
    domains.remove(domain)
    monitor.set_domains(domains)
    # Save config
    config = load_live_config()
    config['domains'] = domains
    save_live_config(config)
    await update.message.reply_text(f"Domain {domain} removed from monitoring list.")

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /interval detik")
        return
    try:
        interval = int(context.args[0])
        if interval < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Interval harus angka >= 1 detik.")
        return
    monitor: SubdomainMonitor = context.bot_data['monitor']
    monitor.set_interval(interval)
    # Save config
    config = load_live_config()
    config['interval'] = interval
    save_live_config(config)
    await update.message.reply_text(f"Interval monitoring diubah ke {interval} detik.")

async def list_domains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    monitor: SubdomainMonitor = context.bot_data['monitor']
    domains = monitor.get_domains()
    if not domains:
        await update.message.reply_text("Tidak ada domain yang dimonitor.")
        return
    msg = "Domain yang dimonitor:\n"
    for d in domains:
        if is_domain_active(d):
            msg += f"- {d}\n"
        else:
            msg += f"- {d} ❌ Not active\n"
    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    monitor: SubdomainMonitor = context.bot_data['monitor']
    domains = monitor.get_domains()
    interval = monitor.get_interval()
    await update.message.reply_text(f"Monitoring {len(domains)} domain(s):\n" + '\n'.join(domains) + f"\nInterval: {interval} detik")

async def database_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('monitor'):
        await update.message.reply_text("Monitor not initialized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /database domain.com")
        return
    domain = context.args[0].strip().lower()
    monitor: SubdomainMonitor = context.bot_data['monitor']
    # Fetch all subdomains for this domain from database, order by release_date
    conn = sqlite3.connect(monitor.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT subdomain, release_date FROM subdomains WHERE domain = ? ORDER BY release_date ASC, subdomain ASC", (domain,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"Tidak ada data subdomain untuk {domain} di database.")
        return
    msg = f"📦 Database subdomain untuk {domain} (urut create date, dari certificate transparency log):\n\n"
    for i, (sub, tgl) in enumerate(rows, 1):
        msg += f"{i}. {sub}\n   Create date: {tgl or '-'}\n"
    for part in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        await update.message.reply_text(part)

# --- Main ---
def main():
    config = load_config()
    live_config = load_live_config()
    raw_domains = live_config.get('domains') or config.get('DOMAINS') or os.getenv('DOMAINS', 'example.com')
    if isinstance(raw_domains, list):
        domains = [d.strip() for d in raw_domains if d.strip()]
    else:
        domains = [d.strip() for d in str(raw_domains).split(',') if d.strip()]
    TELEGRAM_BOT_TOKEN = config.get('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = config.get('TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID', '')
    DISCORD_WEBHOOK_URL = config.get('DISCORD_WEBHOOK_URL') or os.getenv('DISCORD_WEBHOOK_URL', '')
    MONITORING_INTERVAL = int(live_config.get('interval') or config.get('MONITORING_INTERVAL') or os.getenv('MONITORING_INTERVAL', '3600'))
    if not TELEGRAM_BOT_TOKEN and not DISCORD_WEBHOOK_URL:
        print("Error: Please set at least one alert method: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL")
        return
    if not domains:
        print("Error: Please set at least one domain in DOMAINS")
        return
    monitor = SubdomainMonitor(domains, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL, MONITORING_INTERVAL)
    monitor_thread = threading.Thread(target=monitor.monitor, daemon=True)
    monitor_thread.start()
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.bot_data['monitor'] = monitor
        app.add_handler(CommandHandler("add", add_domain))
        app.add_handler(CommandHandler("del", del_domain))
        app.add_handler(CommandHandler("interval", set_interval))
        app.add_handler(CommandHandler("list", list_domains))
        app.add_handler(CommandHandler("status", status))
        app.add_handler(CommandHandler("database", database_cmd))
        print("Telegram bot is running. Send commands to your bot chat.")
        app.run_polling()
    else:
        print("Telegram bot not enabled. Monitoring only.")
        monitor_thread.join()

if __name__ == "__main__":
    main() 