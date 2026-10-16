import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

# 后端入口在 "Backend mission" 下（目录名带空格），测试要自己把它加进搜索路径。
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from app.market import Market


class BackupResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.market=Market(self.tmp.name,trial=True)

    @contextmanager
    def windows_file_lock_check(self):
        """Use real SQLite handles; require close before temporary-file cleanup."""
        connections=[]
        real_connect=sqlite3.connect
        real_temporary_directory=tempfile.TemporaryDirectory

        class Connection(sqlite3.Connection):
            closed=False
            def close(self):
                super().close();self.closed=True

        def connect(*args,**kwargs):
            connection=real_connect(*args,factory=Connection,**kwargs)
            connections.append(connection)
            return connection

        @contextmanager
        def temporary_directory(*args,**kwargs):
            with real_temporary_directory(*args,**kwargs) as directory:
                try:yield directory
                finally:
                    unclosed=[connection for connection in connections if not connection.closed]
                    # Always release handles so this regression can also clean up on Windows.
                    for connection in unclosed:connection.close()
                    self.assertEqual(len(unclosed),0,'SQLite handles must close before temporary database cleanup on Windows')

        # 备份链路现在横跨两个模块：SQLite 连接来自 core/database.py，
        # 临时目录来自 ops/service.py。patch 的是它们各自 import 进来的模块对象。
        with patch('app.core.database.sqlite3.connect',connect),patch('app.ops.service.tempfile.TemporaryDirectory',temporary_directory):
            yield
        self.assertEqual(len(connections),3)

    def test_backup_closes_all_handles_before_temporary_database_cleanup(self):
        with self.windows_file_lock_check():backup=self.market._backup()
        with zipfile.ZipFile(backup) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('market.sqlite3',archive.namelist())
            self.assertIn('manifest.json',archive.namelist())

    def test_archive_failure_does_not_leave_open_sqlite_handles(self):
        missing=Path(self.tmp.name)/'uploads/missing.webp'
        with self.market.tx() as connection:
            connection.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',('missing',1,str(missing),'digest','front',0))
        with self.assertRaises(FileNotFoundError),self.windows_file_lock_check():self.market._backup()


if __name__=='__main__':unittest.main()
