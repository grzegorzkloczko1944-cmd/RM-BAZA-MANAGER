#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMS Sender - Wysyłanie SMS przez różne bramki
Obsługiwane bramki:
1. SMSAPI.pl (polska, popularna) - pip install smsapi-client
2. Twilio (międzynarodowa) - pip install twilio
3. SerwerSMS.pl (polska, tania)
"""

import sys
import requests
from typing import Optional

# ============================================================================
# OPCJA 1: SMSAPI.pl (Rekomendowana dla Polski)
# ============================================================================
# Instalacja: pip install smsapi-client
# Konto: https://www.smsapi.pl/
# Cena: ~0.08-0.10 PLN/SMS

def send_sms_via_smsapi(phone: str, message: str, token: str) -> bool:
    """
    Wysyła SMS przez SMSAPI.pl
    
    Args:
        phone: numer telefonu (np. '48123456789' lub '123456789')
        message: treść SMS (max 160 znaków dla 1 SMS)
        token: token OAuth z panelu SMSAPI.pl
    
    Returns:
        True jeśli wysłano, False przy błędzie
    """
    try:
        from smsapi.client import Client
    except ImportError:
        print("❌ Brak biblioteki smsapi-client!")
        print("Zainstaluj: pip install smsapi-client")
        return False
    
    try:
        client = Client(token)
        
        # Normalizuj numer (dodaj 48 jeśli brak)
        if not phone.startswith('48') and not phone.startswith('+'):
            phone = '48' + phone
        phone = phone.replace('+', '')
        
        print(f"📱 Wysyłanie SMS do: +{phone}")
        print(f"💬 Treść ({len(message)} znaków): {message}")
        
        send_results = client.sms.send(to=phone, message=message)
        
        print(f"✅ SMS wysłany! ID: {send_results.id}")
        print(f"💰 Koszt: {send_results.points} punktów")
        return True
        
    except Exception as e:
        print(f"❌ Błąd SMSAPI: {e}")
        return False


# ============================================================================
# OPCJA 2: Twilio (Międzynarodowa, popularna)
# ============================================================================
# Instalacja: pip install twilio
# Konto: https://www.twilio.com/
# Cena: ~$0.0075/SMS (~0.03 PLN)

def send_sms_via_twilio(phone: str, message: str, account_sid: str, auth_token: str, from_number: str) -> bool:
    """
    Wysyła SMS przez Twilio
    
    Args:
        phone: numer telefonu (format: '+48123456789')
        message: treść SMS
        account_sid: Account SID z Twilio
        auth_token: Auth Token z Twilio
        from_number: Twój numer Twilio (format: '+12345678901')
    
    Returns:
        True jeśli wysłano, False przy błędzie
    """
    try:
        from twilio.rest import Client
    except ImportError:
        print("❌ Brak biblioteki twilio!")
        print("Zainstaluj: pip install twilio")
        return False
    
    try:
        client = Client(account_sid, auth_token)
        
        # Normalizuj numer (dodaj + jeśli brak)
        if not phone.startswith('+'):
            phone = '+' + phone
        
        print(f"📱 Wysyłanie SMS do: {phone}")
        print(f"💬 Treść: {message}")
        
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=phone
        )
        
        print(f"✅ SMS wysłany! SID: {message_obj.sid}")
        print(f"📊 Status: {message_obj.status}")
        return True
        
    except Exception as e:
        print(f"❌ Błąd Twilio: {e}")
        return False


# ============================================================================
# OPCJA 3: SerwerSMS.pl (Polska, tania) - REST API
# ============================================================================
# Konto: https://www.serwersms.pl/
# Cena: ~0.05-0.07 PLN/SMS

def send_sms_via_serwersms(phone: str, message: str, username: str, password: str) -> bool:
    """
    Wysyła SMS przez SerwerSMS.pl (REST API)
    
    Args:
        phone: numer telefonu (np. '48123456789')
        message: treść SMS
        username: login SerwerSMS
        password: hasło SerwerSMS
    
    Returns:
        True jeśli wysłano, False przy błędzie
    """
    try:
        # Normalizuj numer
        if not phone.startswith('48'):
            phone = '48' + phone
        
        print(f"📱 Wysyłanie SMS do: +{phone}")
        print(f"💬 Treść: {message}")
        
        url = "https://api2.serwersms.pl/messages/send_sms"
        
        payload = {
            "username": username,
            "password": password,
            "phone": phone,
            "text": message,
            "sender": "Info"  # lub własna nazwa nadawcy (wymaga rejestracji)
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ SMS wysłany! ID: {result.get('items', [{}])[0].get('id')}")
                return True
            else:
                print(f"❌ Błąd SerwerSMS: {result.get('error', {}).get('message')}")
                return False
        else:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Błąd SerwerSMS: {e}")
        return False


# ============================================================================
# INTERAKTYWNY INTERFEJS
# ============================================================================

def main():
    print("=" * 70)
    print("  SMS Sender - Wysyłanie SMS przez bramki")
    print("=" * 70)
    
    print("\nWybierz bramkę SMS:")
    print("1. SMSAPI.pl (polska, popularna, ~0.08 PLN/SMS)")
    print("2. Twilio (międzynarodowa, ~0.03 PLN/SMS)")
    print("3. SerwerSMS.pl (polska, tania, ~0.05 PLN/SMS)")
    
    gateway = input("\nBramka (1-3): ").strip()
    
    # Dane wspólne
    phone = input("📱 Numer telefonu (np. 48123456789): ").strip()
    message = input("💬 Treść SMS: ").strip()
    
    if not message:
        print("❌ Treść SMS nie może być pusta!")
        sys.exit(1)
    
    # Wybór bramki
    if gateway == '1':
        print("\n🔑 Potrzebujesz token OAuth z https://www.smsapi.pl/")
        print("   Panel → Ustawienia → Dostępy → OAuth → Wygeneruj token")
        token = input("Token OAuth: ").strip()
        
        if not token:
            print("❌ Token nie może być pusty!")
            sys.exit(1)
            
        send_sms_via_smsapi(phone, message, token)
        
    elif gateway == '2':
        print("\n🔑 Potrzebujesz danych z https://www.twilio.com/console")
        account_sid = input("Account SID: ").strip()
        auth_token = input("Auth Token: ").strip()
        from_number = input("Twój numer Twilio (format +12345678901): ").strip()
        
        if not all([account_sid, auth_token, from_number]):
            print("❌ Wszystkie dane są wymagane!")
            sys.exit(1)
            
        send_sms_via_twilio(phone, message, account_sid, auth_token, from_number)
        
    elif gateway == '3':
        print("\n🔑 Potrzebujesz danych logowania z https://www.serwersms.pl/")
        username = input("Login SerwerSMS: ").strip()
        password = input("Hasło SerwerSMS: ").strip()
        
        if not all([username, password]):
            print("❌ Login i hasło są wymagane!")
            sys.exit(1)
            
        send_sms_via_serwersms(phone, message, username, password)
        
    else:
        print("❌ Nieprawidłowy wybór!")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Anulowano.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Błąd: {e}")
        sys.exit(1)
