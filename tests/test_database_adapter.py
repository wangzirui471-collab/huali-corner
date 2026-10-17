"""Connection adapter keeps SQLite persistence and failure semantics intact."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.core.database import Store, _Conn


class DatabaseAdapterTests(unittest.TestCase):
    def test_fresh_general_room_survives_closed_initialization_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            self.assertEqual(store.row('SELECT name FROM rooms WHERE id=1')['name'], '广州校区总聊')

    def test_connection_context_commits_success_and_rolls_back_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with store.connect() as connection:
                connection.execute("INSERT INTO settings VALUES('committed','yes')")
            with self.assertRaisesRegex(ValueError, 'abort'):
                with store.connect() as connection:
                    connection.execute("INSERT INTO settings VALUES('rolled-back','no')")
                    raise ValueError('abort')
            self.assertEqual(store.row("SELECT value FROM settings WHERE key='committed'")['value'], 'yes')
            self.assertIsNone(store.row("SELECT value FROM settings WHERE key='rolled-back'"))

    def test_commit_failure_is_propagated(self):
        raw = Mock()
        raw.commit.side_effect = sqlite3.OperationalError('disk full')
        connection = _Conn(raw, 'sqlite')
        with self.assertRaisesRegex(sqlite3.OperationalError, 'disk full'):
            connection.commit()

    def test_sqlite_backup_accepts_raw_snapshot_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            snapshot = sqlite3.connect(':memory:')
            try:
                with store.connect() as source:
                    source.backup(snapshot)
                self.assertEqual(snapshot.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(snapshot.execute('SELECT name FROM rooms WHERE id=1').fetchone()[0], '广州校区总聊')
            finally:
                snapshot.close()


if __name__ == '__main__':
    unittest.main()
