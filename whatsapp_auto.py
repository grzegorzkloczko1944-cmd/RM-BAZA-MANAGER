#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatyczne wysyłanie wiadomości na WhatsApp (przez WhatsApp Web)
Wymaga: pip install pywhatkit
Ważne: Musisz być zalogowany w WhatsApp Web w przeglądarce!
"""

import sys

try:
    import pywhatkit
except ImportError:
    print("❌ Brak biblioteki pywhatkit!")
    print("Zainstaluj przez: pip install pywhatkit")
    sys.exit(1)

def send_whatsapp_now(phone_number, message):
    """
    Wysyła wiadomość natychmiast (otwiera przeglądarkę i automatycznie wysyła)
    
    Args:
        phone_number: numer z '+' (np. '+48123456789')
        message: treść wiadomości
    """
    print(f"\n📱 Wysyłanie do: {phone_number}")
    print(f"💬 Treść: {message}")
    print("\n⏳ Otwieranie WhatsApp Web i wysyłanie...")
    print("(Musisz być zalogowany w WhatsApp Web!)\n")
    
    try:
        # wait_time: ile sekund czeka zanim wyśle (domyślnie 15)
        # tab_close: czy zamknąć kartę po wysłaniu
        pywhatkit.sendwhatmsg_instantly(
            phone_number, 
            message,
            wait_time=15,
            tab_close=True
        )
        print("\n✅ Wiadomość została wysłana!")
    except Exception as e:
        print(f"\n❌ Błąd wysyłania: {e}")
        print("\nSprawdź czy:")
        print("1. Jesteś zalogowany w WhatsApp Web")
        print("2. Numer telefonu jest prawidłowy (z '+')")
        print("3. Masz połączenie z internetem")

def send_whatsapp_scheduled(phone_number, message, hour, minute):
    """
    Wysyła wiadomość o określonej godzinie
    
    Args:
        phone_number: numer z '+' (np. '+48123456789')
        message: treść wiadomości
        hour: godzina 0-23
        minute: minuta 0-59
    """
    print(f"\n📱 Zaplanowano wysyłkę do: {phone_number}")
    print(f"💬 Treść: {message}")
    print(f"⏰ Godzina: {hour:02d}:{minute:02d}")
    print("\n⏳ Czekam na zaplanowaną godzinę...")
    
    try:
        pywhatkit.sendwhatmsg(phone_number, message, hour, minute)
        print("\n✅ Wiadomość została wysłana!")
    except Exception as e:
        print(f"\n❌ Błąd: {e}")

def main():
    print("=" * 70)
    print("  WhatsApp Auto Sender - Automatyczne wysyłanie przez WhatsApp Web")
    print("=" * 70)
    print("\n⚠️  WYMAGANIA:")
    print("   1. Musisz być zalogowany w WhatsApp Web w przeglądarce")
    print("   2. pip install pywhatkit")
    print()
    
    # Tryb wysyłki
    print("Wybierz tryb:")
    print("1. Wyślij teraz")
    print("2. Zaplanuj wysyłkę")
    mode = input("\nTryb (1 lub 2): ").strip()
    
    # Pobierz numer
    print("\nPodaj numer telefonu z kodem kraju")
    print("Przykład: +48123456789")
    phone = input("📱 Numer (z '+'): ").strip()
    
    if not phone.startswith('+'):
        print("⚠️  Dodaję '+' na początku...")
        phone = '+' + phone
    
    # Pobierz wiadomość
    message = input("💬 Wiadomość: ").strip()
    
    if not message:
        print("❌ Wiadomość nie może być pusta!")
        sys.exit(1)
    
    # Wyślij
    if mode == '1':
        send_whatsapp_now(phone, message)
    elif mode == '2':
        hour = int(input("⏰ Godzina (0-23): "))
        minute = int(input("⏰ Minuta (0-59): "))
        send_whatsapp_scheduled(phone, message, hour, minute)
    else:
        print("❌ Nieprawidłowy tryb!")
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
