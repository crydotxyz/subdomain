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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('subdomain_monitor.log'),
        logging.StreamHandler()
    ]
)

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

class SubdomainMonitor:
    def __init__(self, domains: List[str], telegram_bot_token: Optional[str], telegram_chat_id: Optional[str], discord_webhook_url: Optional[str]):
        self.domains = domains
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url
        self.db_path = 'subdomains.db'
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database to store known subdomains"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if old database structure exists (without domain column)
        cursor.execute("PRAGMA table_info(subdomains)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'domain' not in columns:
            # Migrate old database to new structure
            logging.info("Migrating old database structure to multi-domain format...")
            
            # Create backup of old data
            cursor.execute("SELECT subdomain, first_seen, last_seen FROM subdomains")
            old_data = cursor.fetchall()
            
            # Drop old table
            cursor.execute("DROP TABLE subdomains")
            
            # Create new table with domain column
            cursor.execute('''
                CREATE TABLE subdomains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    subdomain TEXT NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(domain, subdomain)
                )
            ''')
            
            # Migrate old data to new structure (assign to first domain)
            if old_data and self.domains:
                default_domain = self.domains[0]
                for subdomain, first_seen, last_seen in old_data:
                    cursor.execute('''
                        INSERT INTO subdomains (domain, subdomain, first_seen, last_seen) 
                        VALUES (?, ?, ?, ?)
                    ''', (default_domain, subdomain, first_seen, last_seen))
                logging.info(f"Migrated {len(old_data)} subdomains to domain: {default_domain}")
        else:
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subdomains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    subdomain TEXT NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(domain, subdomain)
                )
            ''')
        
        conn.commit()
        conn.close()
        logging.info(f"Database initialized: {self.db_path}")
    
    def get_subdomains_from_crtsh(self, domain: str) -> Set[str]:
        """Fetch subdomains from crt.sh API for specific domain"""
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            subdomains = set()
            
            for entry in data:
                # Extract subdomain from name_value field
                name_value = entry.get('name_value', '')
                if name_value:
                    # Split by newlines and process each subdomain
                    for subdomain in name_value.split('\n'):
                        subdomain = subdomain.strip().lower()
                        if subdomain and domain in subdomain:
                            # Clean up the subdomain (remove wildcards, etc.)
                            subdomain = subdomain.replace('*.', '')
                            if subdomain.endswith('.' + domain):
                                subdomains.add(subdomain)
            
            logging.info(f"Found {len(subdomains)} subdomains for {domain} from crt.sh")
            return subdomains
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data from crt.sh for {domain}: {e}")
            return set()
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing JSON response for {domain}: {e}")
            return set()
    
    def get_known_subdomains(self, domain: str) -> Set[str]:
        """Get known subdomains from database for specific domain"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT subdomain FROM subdomains WHERE domain = ?', (domain,))
        known_subdomains = {row[0] for row in cursor.fetchall()}
        conn.close()
        return known_subdomains
    
    def save_new_subdomains(self, domain: str, new_subdomains: Set[str]):
        """Save new subdomains to database for specific domain"""
        if not new_subdomains:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for subdomain in new_subdomains:
            try:
                cursor.execute(
                    'INSERT INTO subdomains (domain, subdomain) VALUES (?, ?)',
                    (domain, subdomain)
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
    
    def send_telegram_alert(self, domain: str, new_subdomains: Set[str]):
        """Send alert to Telegram about new subdomains for specific domain"""
        if not self.telegram_bot_token or not self.telegram_chat_id or not new_subdomains:
            return
        
        message = f"🚨 **New Subdomains Detected for {domain}**\n\n"
        message += f"Found {len(new_subdomains)} new subdomain(s):\n\n"
        
        for i, subdomain in enumerate(sorted(new_subdomains), 1):
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
    
    def send_discord_alert(self, domain: str, new_subdomains: Set[str]):
        """Send alert to Discord webhook about new subdomains for specific domain"""
        if not self.discord_webhook_url or not new_subdomains:
            return
        
        # Discord webhook expects JSON payload
        message = f"🚨 **New Subdomains Detected for {domain}**\n\n"
        message += f"Found {len(new_subdomains)} new subdomain(s):\n\n"
        for i, subdomain in enumerate(sorted(new_subdomains), 1):
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
    
    def monitor_domain(self, domain: str):
        """Monitor single domain"""
        try:
            logging.info(f"Checking subdomains for {domain}...")
            current_subdomains = self.get_subdomains_from_crtsh(domain)
            known_subdomains = self.get_known_subdomains(domain)
            
            # Find new subdomains
            new_subdomains = current_subdomains - known_subdomains
            
            if new_subdomains:
                logging.info(f"Found {len(new_subdomains)} new subdomain(s) for {domain}: {new_subdomains}")
                
                # Save to database
                self.save_new_subdomains(domain, new_subdomains)
                
                # Send Telegram alert (if enabled)
                self.send_telegram_alert(domain, new_subdomains)
                # Send Discord alert (if enabled)
                self.send_discord_alert(domain, new_subdomains)
            else:
                logging.info(f"No new subdomains found for {domain}")
                
        except Exception as e:
            logging.error(f"Error monitoring {domain}: {e}")
    
    def monitor(self, interval: int = 3600):
        """Main monitoring loop for all domains (parallel/threaded)"""
        logging.info(f"Starting subdomain monitoring for {len(self.domains)} domains: {', '.join(self.domains)}")
        logging.info(f"Monitoring interval: {interval} seconds")
        
        while True:
            try:
                logging.info("Starting monitoring cycle (parallel)...")
                threads = []
                for domain in self.domains:
                    t = threading.Thread(target=self.monitor_domain, args=(domain,))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
                logging.info(f"Monitoring cycle completed. Next check in {interval} seconds...")
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                logging.info(f"Retrying in {interval} seconds...")
                time.sleep(interval)

def main():
    """Main function"""
    # Load configuration
    config = load_config()
    
    # Configuration with fallback to environment variables
    DOMAINS_STR = config.get('DOMAINS') or os.getenv('DOMAINS', 'example.com')
    TELEGRAM_BOT_TOKEN = config.get('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = config.get('TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID', '')
    DISCORD_WEBHOOK_URL = config.get('DISCORD_WEBHOOK_URL') or os.getenv('DISCORD_WEBHOOK_URL', '')
    MONITORING_INTERVAL = int(config.get('MONITORING_INTERVAL') or os.getenv('MONITORING_INTERVAL', '3600'))
    
    # Parse domains (support comma-separated or single domain)
    domains = [domain.strip() for domain in DOMAINS_STR.split(',') if domain.strip()]
    
    if not TELEGRAM_BOT_TOKEN and not DISCORD_WEBHOOK_URL:
        print("Error: Please set at least one alert method: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL")
        print("You can set them in config.env file or as environment variables")
        print("See config.env.example for reference")
        return
    
    if not domains:
        print("Error: Please set at least one domain in DOMAINS")
        return
    
    print(f"Starting Subdomain Monitor for {len(domains)} domain(s):")
    for domain in domains:
        print(f"  - {domain}")
    print(f"Monitoring interval: {MONITORING_INTERVAL} seconds")
    print("Press Ctrl+C to stop")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Telegram alert: ENABLED")
    else:
        print("Telegram alert: DISABLED")
    if DISCORD_WEBHOOK_URL:
        print("Discord alert: ENABLED")
    else:
        print("Discord alert: DISABLED")
    
    # Create monitor instance
    monitor = SubdomainMonitor(domains, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL)
    
    # Start monitoring
    monitor.monitor(MONITORING_INTERVAL)

if __name__ == "__main__":
    main() 