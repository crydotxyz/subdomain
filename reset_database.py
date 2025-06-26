#!/usr/bin/env python3
"""
Script untuk reset database subdomain monitor
"""

import os
import sqlite3
import logging

def reset_database():
    """Reset the subdomain database"""
    db_path = 'subdomains.db'
    
    if os.path.exists(db_path):
        # Backup old database
        backup_path = f"{db_path}.backup"
        os.rename(db_path, backup_path)
        print(f"✅ Database lama di-backup ke: {backup_path}")
    
    # Create new database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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
    
    conn.commit()
    conn.close()
    
    print("✅ Database baru berhasil dibuat!")
    print("📊 Struktur database:")
    print("   - domain: Domain yang dimonitor")
    print("   - subdomain: Subdomain yang ditemukan")
    print("   - first_seen: Waktu pertama kali ditemukan")
    print("   - last_seen: Waktu terakhir kali ditemukan")

if __name__ == "__main__":
    print("🗑️  Reset Subdomain Monitor Database")
    print("=" * 40)
    
    confirm = input("Yakin mau reset database? (y/N): ")
    if confirm.lower() == 'y':
        reset_database()
    else:
        print("❌ Reset dibatalkan") 