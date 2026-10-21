"""Synthetic SQLite check for the additive checkout replay migration."""

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "infra/d1/migrations/0001_add_checkout_request_hash.sql"
SCHEMA = ROOT / "Backend mission/app/cloudflare/schema.sql"


class CheckoutMigrationTests(unittest.TestCase):
    def test_existing_order_survives_additive_migration(self):
        """验证加法迁移保留旧订单，且不会凭空生成历史请求摘要。"""
        with sqlite3.connect(":memory:") as db:
            db.execute(
                "CREATE TABLE orders(id INTEGER PRIMARY KEY, buyer_id INTEGER, "
                "request_key TEXT, items TEXT, delivery TEXT, address TEXT, "
                "appointment REAL, want_id INTEGER)"
            )
            db.execute(
                "INSERT INTO orders VALUES(1, 2, 'old-key', '[]', 'pickup', '', 123, NULL)"
            )
            db.executescript(MIGRATION.read_text(encoding="utf-8"))
            row = db.execute(
                "SELECT id, request_hash FROM orders WHERE request_key='old-key'"
            ).fetchone()
            self.assertEqual(row, (1, None))

    def test_fresh_schema_contains_request_hash(self):
        """验证全新合成库具有请求摘要列，避免初始化与升级结构不一致。"""
        with sqlite3.connect(":memory:") as db:
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
            columns = {row[1] for row in db.execute("PRAGMA table_info(orders)")}
            self.assertIn("request_hash", columns)


if __name__ == "__main__":
    unittest.main()
