import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloudflare_test_support import CloudCase
from app.core.errors import DomainError

class AtomicTests(CloudCase):
    async def test_guard_failure_leaves_no_partial_rows(self):
        with self.assertRaises(DomainError):
            await self.api.db.guarded_batch('SELECT 1 WHERE 0',(),[
                ("UPDATE users SET score=1 WHERE id=2",())], '状态冲突')
        self.assertEqual(self.db.execute('SELECT score FROM users WHERE id=2').fetchone()[0],100)
    async def test_statement_failure_rolls_back_previous_writes(self):
        with self.assertRaises(Exception):
            await self.api.db.guarded_batch('SELECT 1',(),[
                ("UPDATE users SET score=1 WHERE id=2",()),
                ("INSERT INTO settings(key,value) VALUES('test',NULL)",())])
        self.assertEqual(self.db.execute('SELECT score FROM users WHERE id=2').fetchone()[0],100)
    async def test_guard_success_applies_without_creating_a_guard_record(self):
        await self.api.db.guarded_batch('SELECT 1 FROM users WHERE id=? AND score=?',(2,100),[
            ('UPDATE users SET score=99 WHERE id=2',())])
        self.assertEqual(self.db.execute('SELECT score FROM users WHERE id=2').fetchone()[0],99)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM settings').fetchone()[0],0)
