"""Local account demotion changes only its target and preserves business records."""
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.staff.roles import demote_account


class OperatorDemotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'market.sqlite3'
        with sqlite3.connect(self.db) as connection:
            connection.executescript('''
                CREATE TABLE users(id INTEGER PRIMARY KEY,nickname TEXT,role TEXT,status TEXT);
                CREATE TABLE sessions(token TEXT,user_id INTEGER,expires REAL);
                CREATE TABLE tickets(id INTEGER PRIMARY KEY,user_id INTEGER,assignee INTEGER,status TEXT);
                CREATE TABLE audit(id INTEGER PRIMARY KEY,actor INTEGER,target INTEGER,type TEXT,reason TEXT,created REAL);
                CREATE TABLE orders(id INTEGER PRIMARY KEY,buyer_id INTEGER,seller_id INTEGER,status TEXT);
                CREATE TABLE products(id INTEGER PRIMARY KEY,seller_id INTEGER,status TEXT);
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO settings VALUES('auth_mode','trial');
                INSERT INTO users VALUES(1,'day','admin','active'),(2,'godfly','admin','active'),(3,'同学','user','active');
                INSERT INTO sessions VALUES('target-session',2,9999999999),('other-session',1,9999999999);
                INSERT INTO tickets VALUES(1,3,2,'processing'),(2,3,2,'review'),(3,3,2,'resolved');
                INSERT INTO orders VALUES(1,3,2,'paid');
                INSERT INTO products VALUES(1,2,'available');
            ''')

    def query(self, sql, parameters=()):
        with sqlite3.connect(self.db) as connection:
            return connection.execute(sql, parameters).fetchall()

    def test_demote_backup_sessions_handoff_audit_and_idempotency(self):
        result = demote_account(self.db, 'godfly')
        self.assertTrue(result['changed'])
        self.assertEqual(result['role'], 'user')
        self.assertEqual(result['revoked_sessions'], 1)
        self.assertEqual(result['released_tickets'], 2)
        self.assertEqual(self.query('SELECT nickname,role,status FROM users WHERE id=2'), [('godfly','user','active')])
        self.assertEqual(self.query('SELECT user_id FROM sessions'), [(1,)])
        self.assertEqual(self.query('SELECT assignee,status FROM tickets ORDER BY id'), [(None,'open'),(None,'review'),(2,'resolved')])
        self.assertEqual(self.query('SELECT * FROM orders'), [(1,3,2,'paid')])
        self.assertEqual(self.query('SELECT * FROM products'), [(1,2,'available')])
        self.assertEqual(self.query('SELECT target,type FROM audit'), [(2,'operator_role_demotion')])
        with sqlite3.connect(result['backup_path']) as backup:
            self.assertEqual(backup.execute('SELECT role FROM users WHERE id=2').fetchone()[0], 'admin')
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 2)
        again = demote_account(self.db, 'godfly')
        self.assertFalse(again['changed'])
        self.assertEqual(len(self.query('SELECT * FROM audit')), 1)

    def test_missing_duplicate_and_wrong_id_do_not_mutate(self):
        with self.assertRaises(ValueError):
            demote_account(self.db, 'not-found')
        with sqlite3.connect(self.db) as connection:
            connection.execute("INSERT INTO users VALUES(4,'GodFly','support','active')")
        with self.assertRaisesRegex(ValueError, '多个'):
            demote_account(self.db, 'godfly')
        with self.assertRaises(ValueError):
            demote_account(self.db, 'godfly', user_id=1)
        self.assertEqual(self.query('SELECT role FROM users WHERE id=2'), [('admin',)])
        self.assertEqual(self.query('SELECT * FROM audit'), [])
        demote_account(self.db, 'godfly', user_id=4)
        self.assertEqual(self.query('SELECT role FROM users WHERE id=2'), [('admin',)])
        self.assertEqual(self.query('SELECT role FROM users WHERE id=4'), [('user',)])

    def test_last_active_admin_and_incorrect_data_path_are_rejected(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE users SET role='user' WHERE id=1")
        with self.assertRaisesRegex(ValueError, '最后'):
            demote_account(self.db, 'godfly')
        missing = self.db.parent / 'missing' / 'market.sqlite3'
        with self.assertRaises(FileNotFoundError):
            demote_account(missing, 'godfly')
        self.assertFalse(missing.exists())

    def test_failure_rolls_back_every_change(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TRIGGER audit_failure BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            demote_account(self.db, 'godfly')
        self.assertEqual(self.query('SELECT role FROM users WHERE id=2'), [('admin',)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM sessions WHERE user_id=2'), [(1,)])
        self.assertEqual(self.query('SELECT assignee,status FROM tickets WHERE id=1'), [(2,'processing')])

    def test_portable_command_runs_without_installed_project(self):
        root = Path(__file__).resolve().parents[1]
        tool = Path(self.tmp.name) / '本机降权工具'
        tool.mkdir()
        shutil.copyfile(root / 'scripts/demote_staff.py', tool / 'demote_staff.py')
        shutil.copyfile(root / 'Backend mission/app/staff/roles.py', tool / 'roles.py')
        result = subprocess.run([sys.executable, str(tool / 'demote_staff.py'), '--data', str(self.db.parent)],
                                cwd=tool, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('已降为普通用户', result.stdout)
        self.assertEqual(self.query('SELECT role FROM users WHERE id=2'), [('user',)])

    def test_wal_database_backup_and_demotion(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        result = demote_account(self.db, 'godfly')
        self.assertTrue(result['changed'])
        with sqlite3.connect(result['backup_path']) as backup:
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(backup.execute('SELECT role FROM users WHERE id=2').fetchone()[0], 'admin')


if __name__ == '__main__':
    unittest.main()
