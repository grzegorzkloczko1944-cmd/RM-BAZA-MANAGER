#!/usr/bin/env python3
"""
Test jednostkowy systemu kodów PLC (PLC Unlock Codes)

Testy dla funkcji w rm_manager.py:
- add_plc_code()
- update_plc_code()
- delete_plc_code()
- get_plc_codes()
- mark_plc_code_as_used()
- get_plc_codes_summary()

Uruchom: python3 test_plc_codes.py
"""

import os
import sqlite3
import tempfile
import unittest

import rm_manager as rmm


class TestPLCCodes(unittest.TestCase):
    """Testy systemu kodów PLC."""
    
    def setUp(self):
        """Przygotuj tymczasową bazę danych przed każdym testem."""
        # Utwórz tymczasowy plik
        self.temp_fd, self.temp_db = tempfile.mkstemp(suffix='.sqlite')
        
        # Inicjalizuj tabele
        con = sqlite3.connect(self.temp_db)
        con.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        con.execute("INSERT INTO projects (id, name) VALUES (1, 'Test Project')")
        con.commit()
        con.close()
        
        rmm.ensure_rm_master_tables(self.temp_db)
        
        self.project_id = 1
        self.test_user = 'test.user'
    
    def tearDown(self):
        """Usuń tymczasową bazę po każdym teście."""
        os.close(self.temp_fd)
        os.remove(self.temp_db)
    
    def test_01_add_plc_code_temporary(self):
        """Test dodawania kodu TEMPORARY."""
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='TEMPORARY',
            unlock_code='TEST-TEMP-12345',
            description='Kod testowy tymczasowy',
            user=self.test_user
        )
        
        self.assertIsInstance(code_id, int)
        self.assertGreater(code_id, 0)
        
        # Sprawdź czy kod został dodany
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]['code_type'], 'TEMPORARY')
        self.assertEqual(codes[0]['unlock_code'], 'TEST-TEMP-12345')
        self.assertEqual(codes[0]['is_used'], 0)
    
    def test_02_add_plc_code_extended(self):
        """Test dodawania kodu EXTENDED."""
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='EXTENDED',
            unlock_code='TEST-EXT-67890',
            description='Kod rozszerzony',
            user=self.test_user
        )
        
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]['code_type'], 'EXTENDED')
    
    def test_03_add_plc_code_permanent(self):
        """Test dodawania kodu PERMANENT."""
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='PERMANENT',
            unlock_code='TEST-PERM-ABCDE',
            description='Kod stały',
            user=self.test_user
        )
        
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]['code_type'], 'PERMANENT')
    
    def test_04_add_plc_code_invalid_type(self):
        """Test dodawania kodu z nieprawidłowym typem - powinien rzucić ValueError."""
        with self.assertRaises(ValueError):
            rmm.add_plc_code(
                self.temp_db,
                self.project_id,
                code_type='INVALID_TYPE',
                unlock_code='TEST-INVALID',
                user=self.test_user
            )
    
    def test_05_update_plc_code(self):
        """Test aktualizacji kodu PLC."""
        # Dodaj kod
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='TEMPORARY',
            unlock_code='OLD-CODE-123',
            description='Stary opis',
            user=self.test_user
        )
        
        # Zaktualizuj
        rmm.update_plc_code(
            self.temp_db,
            code_id=code_id,
            unlock_code='NEW-CODE-456',
            description='Nowy opis',
            user=self.test_user
        )
        
        # Sprawdź
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]['unlock_code'], 'NEW-CODE-456')
        self.assertEqual(codes[0]['description'], 'Nowy opis')
        self.assertEqual(codes[0]['modified_by'], self.test_user)
    
    def test_06_delete_plc_code(self):
        """Test usuwania kodu PLC."""
        # Dodaj kod
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='TEMPORARY',
            unlock_code='DELETE-ME',
            user=self.test_user
        )
        
        # Sprawdź że istnieje
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        
        # Usuń
        rmm.delete_plc_code(self.temp_db, code_id)
        
        # Sprawdź że zniknął
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 0)
    
    def test_07_mark_plc_code_as_used(self):
        """Test oznaczania kodu jako użyty."""
        # Dodaj kod
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='PERMANENT',
            unlock_code='USE-ME-001',
            user=self.test_user
        )
        
        # Sprawdź że jest nieużyty
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(codes[0]['is_used'], 0)
        self.assertIsNone(codes[0]['used_at'])
        self.assertIsNone(codes[0]['used_by'])
        
        # Oznacz jako użyty
        rmm.mark_plc_code_as_used(
            self.temp_db,
            code_id=code_id,
            user=self.test_user,
            notes='Przesłano klientowi email'
        )
        
        # Sprawdź
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(codes[0]['is_used'], 1)
        self.assertIsNotNone(codes[0]['used_at'])
        self.assertEqual(codes[0]['used_by'], self.test_user)
        self.assertEqual(codes[0]['notes'], 'Przesłano klientowi email')
    
    def test_08_get_plc_codes_multiple(self):
        """Test pobierania wielu kodów z sortowaniem."""
        # Dodaj 3 kody różnych typów
        rmm.add_plc_code(self.temp_db, self.project_id, 'PERMANENT', 'PERM-001', user=self.test_user)
        rmm.add_plc_code(self.temp_db, self.project_id, 'TEMPORARY', 'TEMP-001', user=self.test_user)
        rmm.add_plc_code(self.temp_db, self.project_id, 'EXTENDED', 'EXT-001', user=self.test_user)
        
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 3)
        
        # Sprawdź sortowanie (TEMPORARY → EXTENDED → PERMANENT)
        self.assertEqual(codes[0]['code_type'], 'TEMPORARY')
        self.assertEqual(codes[1]['code_type'], 'EXTENDED')
        self.assertEqual(codes[2]['code_type'], 'PERMANENT')
    
    def test_09_get_plc_codes_summary_empty(self):
        """Test podsumowania gdy brak kodów."""
        summary = rmm.get_plc_codes_summary(self.temp_db, self.project_id)
        
        self.assertEqual(summary['TEMPORARY']['total'], 0)
        self.assertEqual(summary['EXTENDED']['total'], 0)
        self.assertEqual(summary['PERMANENT']['total'], 0)
    
    def test_10_get_plc_codes_summary_with_data(self):
        """Test podsumowania z wieloma kodami."""
        # Dodaj kody
        temp_id1 = rmm.add_plc_code(self.temp_db, self.project_id, 'TEMPORARY', 'T1', user=self.test_user)
        temp_id2 = rmm.add_plc_code(self.temp_db, self.project_id, 'TEMPORARY', 'T2', user=self.test_user)
        ext_id = rmm.add_plc_code(self.temp_db, self.project_id, 'EXTENDED', 'E1', user=self.test_user)
        perm_id = rmm.add_plc_code(self.temp_db, self.project_id, 'PERMANENT', 'P1', user=self.test_user)
        
        # Oznacz jeden jako użyty
        rmm.mark_plc_code_as_used(self.temp_db, temp_id1, user=self.test_user)
        
        # Pobierz podsumowanie
        summary = rmm.get_plc_codes_summary(self.temp_db, self.project_id)
        
        # Sprawdź TEMPORARY (2 total, 1 used, 1 unused)
        self.assertEqual(summary['TEMPORARY']['total'], 2)
        self.assertEqual(summary['TEMPORARY']['used'], 1)
        self.assertEqual(summary['TEMPORARY']['unused'], 1)
        
        # Sprawdź EXTENDED (1 total, 0 used, 1 unused)
        self.assertEqual(summary['EXTENDED']['total'], 1)
        self.assertEqual(summary['EXTENDED']['used'], 0)
        self.assertEqual(summary['EXTENDED']['unused'], 1)
        
        # Sprawdź PERMANENT (1 total, 0 used, 1 unused)
        self.assertEqual(summary['PERMANENT']['total'], 1)
        self.assertEqual(summary['PERMANENT']['used'], 0)
        self.assertEqual(summary['PERMANENT']['unused'], 1)
    
    def test_11_plc_code_without_description(self):
        """Test dodawania kodu bez opisu (description = None)."""
        code_id = rmm.add_plc_code(
            self.temp_db,
            self.project_id,
            code_type='TEMPORARY',
            unlock_code='NO-DESC',
            description=None,
            user=self.test_user
        )
        
        codes = rmm.get_plc_codes(self.temp_db, self.project_id)
        self.assertEqual(len(codes), 1)
        self.assertIsNone(codes[0]['description'])


def run_tests():
    """Uruchom wszystkie testy."""
    print("=" * 70)
    print("Test systemu kodów PLC")
    print("=" * 70)
    print()
    
    # Uruchom testy
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPLCCodes)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ WSZYSTKIE TESTY PRZESZŁY POMYŚLNIE")
    else:
        print("❌ NIEKTÓRE TESTY NIE POWIODŁY SIĘ")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
