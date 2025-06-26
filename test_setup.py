#!/usr/bin/env python3
"""
Test script untuk memverifikasi setup subdomain monitor (Multi Domain)
"""

import requests
import json
import os
from subdomain_monitor import load_config

def test_crtsh_api(domain):
    """Test API crt.sh"""
    print(f"Testing crt.sh API for domain: {domain}")
    url = f"https://crt.sh/?q=%.{domain}&output=json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        subdomains = set()
        for entry in data:
            name_value = entry.get('name_value', '')
            if name_value:
                for subdomain in name_value.split('\n'):
                    subdomain = subdomain.strip().lower()
                    if subdomain and domain in subdomain:
                        # Clean up the subdomain (remove wildcards, etc.)
                        subdomain = subdomain.replace('*.', '')
                        if subdomain.endswith('.' + domain):
                            subdomains.add(subdomain)
        
        print(f"✅ crt.sh API working - Found {len(subdomains)} subdomains")
        if subdomains:
            print("Sample subdomains:")
            for i, subdomain in enumerate(list(subdomains)[:5], 1):
                print(f"  {i}. {subdomain}")
        return True
        
    except Exception as e:
        print(f"❌ crt.sh API error: {e}")
        return False

def test_telegram_bot(bot_token, chat_id):
    """Test Telegram bot"""
    print(f"Testing Telegram bot...")
    
    try:
        # Test bot info
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        bot_info = response.json()
        
        if bot_info.get('ok'):
            print(f"✅ Bot connected: @{bot_info['result']['username']}")
        else:
            print(f"❌ Bot error: {bot_info}")
            return False
        
        # Test sending message
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': '🧪 Test message from Subdomain Monitor (Multi Domain)\n\nBot setup successful!',
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get('ok'):
            print("✅ Test message sent successfully")
            return True
        else:
            print(f"❌ Failed to send message: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Telegram bot error: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Subdomain Monitor Setup Test (Multi Domain)")
    print("=" * 50)
    
    # Load configuration
    config = load_config()
    
    DOMAINS_STR = config.get('DOMAINS') or os.getenv('DOMAINS', 'example.com')
    TELEGRAM_BOT_TOKEN = config.get('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = config.get('TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Parse domains
    domains = [domain.strip() for domain in DOMAINS_STR.split(',') if domain.strip()]
    
    print(f"Domains: {', '.join(domains)}")
    print(f"Bot Token: {'✅ Set' if TELEGRAM_BOT_TOKEN else '❌ Not set'}")
    print(f"Chat ID: {'✅ Set' if TELEGRAM_CHAT_ID else '❌ Not set'}")
    print()
    
    # Test crt.sh API for each domain
    crt_tests = []
    for domain in domains:
        print(f"Testing domain: {domain}")
        crt_test = test_crtsh_api(domain)
        crt_tests.append(crt_test)
        print()
    
    # Test Telegram bot
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        telegram_test = test_telegram_bot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    else:
        print("⚠️  Skipping Telegram test - missing credentials")
        telegram_test = False
    print()
    
    # Summary
    print("📊 Test Summary:")
    for i, domain in enumerate(domains):
        print(f"crt.sh API ({domain}): {'✅ PASS' if crt_tests[i] else '❌ FAIL'}")
    print(f"Telegram Bot: {'✅ PASS' if telegram_test else '❌ FAIL'}")
    
    if all(crt_tests) and telegram_test:
        print("\n🎉 All tests passed! Your multi-domain setup is ready.")
        print("You can now run: python subdomain_monitor.py")
    else:
        print("\n⚠️  Some tests failed. Please check your configuration.")
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("Make sure to set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

if __name__ == "__main__":
    main() 