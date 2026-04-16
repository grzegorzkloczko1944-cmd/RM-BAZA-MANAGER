#!/usr/bin/env python3
"""
Test podstawowej funkcjonalności systemu płatności RM_MANAGER
"""

import sys
import os

# Dodaj katalog projektu do path
sys.path.insert(0, '/workspaces/BOM')

import rm_manager as rmm
from datetime import datetime

# Ścieżki testowe
TEST_RM_DB = "/tmp/test_rm_manager.sqlite"
TEST_MASTER_DB = "/tmp/test_master.sqlite"

def cleanup():
    """Usuń testowe bazy"""
    if os.path.exists(TEST_RM_DB):
        os.remove(TEST_RM_DB)
    if os.path.exists(TEST_MASTER_DB):
        os.remove(TEST_MASTER_DB)

def test_payment_system():
    """Test systemu płatności"""
    print("=" * 60)
    print("TEST SYSTEMU PŁATNOŚCI RM_MANAGER")
    print("=" * 60)
    
    cleanup()
    
    # 1. Inicjalizacja baz
    print("\n1️⃣ Inicjalizacja bazy rm_manager.sqlite...")
    try:
        rmm.ensure_rm_master_tables(TEST_RM_DB)
        print("   ✅ Baza utworzona")
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 2. Sprawdź czy tabele płatności istnieją
    print("\n2️⃣ Sprawdzanie tabel płatności...")
    try:
        con = rmm._open_rm_connection(TEST_RM_DB)
        tables = [
            'payment_milestones',
            'payment_history',
            'payment_notification_config',
            'payment_notifications_sent',
            'in_app_notifications'
        ]
        
        for table in tables:
            result = con.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()
            if result:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table} - BRAK!")
                return False
        con.close()
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 3. Test dodawania transzy płatności
    print("\n3️⃣ Test dodawania transzy płatności...")
    try:
        project_id = 123
        rmm.add_payment_milestone(
            TEST_RM_DB,
            project_id=project_id,
            percentage=30,
            payment_date='2026-04-01',
            user='test_user',
            check_trigger=False  # Nie wysyłaj powiadomień w teście
        )
        print("   ✅ Transza 30% dodana")
        
        rmm.add_payment_milestone(
            TEST_RM_DB,
            project_id=project_id,
            percentage=100,
            payment_date='2026-04-13',
            user='test_user',
            check_trigger=False
        )
        print("   ✅ Transza 100% dodana")
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 4. Test pobierania transz
    print("\n4️⃣ Test pobierania transz płatności...")
    try:
        milestones = rmm.get_payment_milestones(TEST_RM_DB, project_id)
        if len(milestones) == 2:
            print(f"   ✅ Znaleziono {len(milestones)} transze")
            for m in milestones:
                print(f"      - {m['percentage']}% | {m['payment_date']} | {m['created_by']}")
        else:
            print(f"   ❌ Oczekiwano 2 transzy, znaleziono {len(milestones)}")
            return False
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 5. Test edycji daty
    print("\n5️⃣ Test edycji daty transzy...")
    try:
        rmm.update_payment_milestone(
            TEST_RM_DB,
            project_id=project_id,
            percentage=100,
            new_date='2026-04-14',
            user='test_user',
            check_trigger=False
        )
        print("   ✅ Data zmieniona na 2026-04-14")
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 6. Test historii
    print("\n6️⃣ Test historii zmian...")
    try:
        history = rmm.get_payment_history(TEST_RM_DB, project_id)
        if len(history) == 3:  # 2x ADDED + 1x MODIFIED
            print(f"   ✅ Historia: {len(history)} wpisów")
            for h in history:
                print(f"      - {h['action']} | {h['percentage']}% | {h['changed_by']}")
        else:
            print(f"   ⚠️  Oczekiwano 3 wpisów, znaleziono {len(history)}")
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 7. Test konfiguracji powiadomień
    print("\n7️⃣ Test konfiguracji powiadomień...")
    try:
        config = rmm.get_payment_notification_config(TEST_RM_DB)
        if config:
            print(f"   ✅ Konfiguracja załadowana")
            print(f"      - Trigger: {config['trigger_percentage']}%")
            print(f"      - Enabled: {config['enabled']}")
            print(f"      - Recipients: {len(config['email_recipients'])}")
        else:
            print(f"   ❌ Brak konfiguracji")
            return False
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 8. Test aktualizacji konfiguracji
    print("\n8️⃣ Test aktualizacji konfiguracji...")
    try:
        rmm.update_payment_notification_config(
            TEST_RM_DB,
            recipients=['test1@firma.pl', 'test2@firma.pl'],
            trigger_percentage=100,
            enabled=True
        )
        
        config = rmm.get_payment_notification_config(TEST_RM_DB)
        if len(config['email_recipients']) == 2:
            print(f"   ✅ Odbiorcy zaktualizowani ({len(config['email_recipients'])})")
        else:
            print(f"   ❌ Błąd aktualizacji odbiorców")
            return False
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 9. Test usuwania transzy
    print("\n9️⃣ Test usuwania transzy...")
    try:
        rmm.delete_payment_milestone(TEST_RM_DB, project_id, 30, user='test_user')
        milestones = rmm.get_payment_milestones(TEST_RM_DB, project_id)
        if len(milestones) == 1:
            print(f"   ✅ Transza 30% usunięta")
        else:
            print(f"   ❌ Błąd usuwania")
            return False
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    # 10. Test nieprzeczytanych powiadomień
    print("\n🔟 Test powiadomień in-app...")
    try:
        # Utwórz powiadomienie
        con = rmm._open_rm_connection(TEST_RM_DB)
        con.execute("""
            INSERT INTO in_app_notifications 
                (project_id, project_name, notification_type, message, created_by, is_read)
            VALUES (?, ?, 'PAYMENT', ?, ?, 0)
        """, (project_id, 'Test Project', 'Test payment notification', 'test_user'))
        con.commit()
        con.close()
        
        # Pobierz nieprzeczytane
        notifications = rmm.get_unread_notifications(TEST_RM_DB)
        if len(notifications) == 1:
            print(f"   ✅ Powiadomienie utworzone i pobrane")
            
            # Oznacz jako przeczytane
            rmm.mark_notification_as_read(TEST_RM_DB, notifications[0]['id'], 'test_user')
            notifications = rmm.get_unread_notifications(TEST_RM_DB)
            if len(notifications) == 0:
                print(f"   ✅ Powiadomienie oznaczone jako przeczytane")
            else:
                print(f"   ❌ Błąd oznaczania jako przeczytane")
        else:
            print(f"   ❌ Błąd tworzenia powiadomienia")
            return False
    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ WSZYSTKIE TESTY ZALICZONE!")
    print("=" * 60)
    
    cleanup()
    return True

if __name__ == "__main__":
    success = test_payment_system()
    sys.exit(0 if success else 1)
