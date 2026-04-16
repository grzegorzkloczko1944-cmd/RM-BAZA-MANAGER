#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prosty skrypt do wysyłania wiadomości na WhatsApp
Użycie: python whatsapp_test.py
"""

import webbrowser
import urllib.parse
import sys

def send_whatsapp_url(phone_number, message):
    """
    Otwiera WhatsApp w przeglądarce z przygotowaną wiadomością.
    
    Args:
        phone_number: numer w formacie międzynarodowym bez '+' (np. '48123456789')
        message: treść wiadomości
    """
    encoded_message = urllib.parse.quote(message)
    url = f"https://wa.me/{phone_number}?text={encoded_message}"
    print(f"\n🔗 Otwieranie WhatsApp...")
    print(f"📱 Numer: +{phone_number}")
    print(f"💬 Wiadomość: {message}")
    print(f"\nURL: {url}\n")
    webbrowser.open(url)
    print("✅ Przeglądarka została otwarta. Kliknij 'Wyślij' w WhatsApp.")

def main():
    print("=" * 60)
    print("  WhatsApp Sender - Prosty skrypt konsolowy")
    print("=" * 60)
    
    # Pobierz numer telefonu
    print("\nPodaj numer telefonu w formacie międzynarodowym")
    print("Przykład: 48123456789 (dla Polski), 1234567890 (dla USA)")
    phone = input("📱 Numer telefonu (bez '+'): ").strip()
    
    if not phone:
        print("❌ Błąd: Numer telefonu nie może być pusty!")
        sys.exit(1)
    
    # Pobierz wiadomość
    print("\nPodaj treść wiadomości:")
    message = input("💬 Wiadomość: ").strip()
    
    if not message:
        print("❌ Błąd: Wiadomość nie może być pusta!")
        sys.exit(1)
    
    # Wyślij
    send_whatsapp_url(phone, message)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Anulowano przez użytkownika.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Błąd: {e}")
        sys.exit(1)
