"""Real SQLite and image tests for recoverable, private publishing drafts."""

import io
import sys
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import DomainError, Market


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.market = Market(self.tmp.name)
        self.seller = self.login('13800000021')
        self.buyer = self.login('13800000022')
        self.admin = self.login('13800000003')

    def login(self, phone):
        code = self.market.request_code(phone)['demo_code']
        return self.market.login(phone, code)['user']['id']

    def api(self, name):
        self.assertTrue(callable(getattr(self.market, name, None)), f'Missing {name} behavior')
        return getattr(self.market, name)

    def photos(self, owner=None):
        result = []
        for angle, color in zip(['front', 'side', 'top'], ['red', 'green', 'blue']):
            image = io.BytesIO()
            Image.new('RGB', (80, 80), color).save(image, 'PNG')
            result.append(self.market.add_upload(owner or self.seller, image.getvalue(), angle)['id'])
        return result

    def fields(self, **changes):
        fields = dict(title='数据结构', category='books', price='12.50', delivery='pickup',
                      region='A1楼下公共入口', photos=self.photos(), missing='未核对，交付时检查')
        fields.update(changes)
        return fields

    def draft(self, fields=None):
        return self.api('save_draft')(self.seller, {'fields': fields or self.fields(), 'version': 0})

    def test_incomplete_draft_survives_restart_and_is_private(self):
        draft = self.draft({'title': '还没填写完', 'category': 'books', 'price': ''})
        self.assertEqual(draft['version'], 1)
        restarted = Market(self.tmp.name)
        self.assertEqual(restarted.get_draft(self.seller, draft['id'])['fields']['title'], '还没填写完')
        with self.assertRaises(DomainError):
            restarted.get_draft(self.buyer, draft['id'])
        self.assertEqual(restarted.list_drafts(self.buyer), [])

    def test_stale_save_cannot_overwrite_newer_fields(self):
        draft = self.draft({'title': '第一版'})
        saved = self.market.save_draft(self.seller, {'id': draft['id'], 'version': 1, 'fields': {'title': '新版'}})
        self.assertEqual(saved['version'], 2)
        with self.assertRaises(DomainError) as error:
            self.market.save_draft(self.seller, {'id': draft['id'], 'version': 1, 'fields': {'title': '过时窗口'}})
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.market.get_draft(self.seller, draft['id'])['fields']['title'], '新版')

    def test_publish_uses_exact_cents_unknown_defaults_and_is_idempotent(self):
        draft = self.draft()
        result = self.api('publish_draft')(self.seller, draft['id'], draft['version'])
        repeated = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        self.assertEqual(repeated['id'], result['id'])
        product = self.market.product(result['id'])
        self.assertEqual(product['price'], 1250)
        self.assertIn('未核对', product['notes'])
        self.assertIn('未核对', product['missing'])
        self.assertTrue(product['description'])
        self.assertEqual(self.market.list_drafts(self.seller), [])
        self.assertEqual(len(self.market.rows('SELECT id FROM products')), 1)

    def test_publish_failure_preserves_draft_and_photos(self):
        draft = self.draft(self.fields(price='0.001'))
        with self.assertRaises(DomainError):
            self.api('publish_draft')(self.seller, draft['id'], draft['version'])
        self.assertEqual(self.market.get_draft(self.seller, draft['id'])['fields']['photos'], draft['fields']['photos'])
        self.assertEqual(self.market.rows('SELECT id FROM products'), [])

    def test_low_credit_cannot_publish_saved_draft(self):
        draft = self.draft()
        with self.market.tx() as connection:
            connection.execute('UPDATE users SET score=59 WHERE id=?', (self.seller,))
        with self.assertRaises(DomainError):
            self.api('publish_draft')(self.seller, draft['id'], draft['version'])
        self.assertEqual(len(self.market.list_drafts(self.seller)), 1)

    def test_draft_rejects_foreign_images_and_private_proof(self):
        foreign = self.photos(self.buyer)
        with self.assertRaises(DomainError):
            self.draft({'title': '越权', 'photos': foreign})

    def test_deleted_or_expired_draft_cannot_be_resurrected(self):
        draft = self.draft({'title': '删除测试'})
        self.api('delete_draft')(self.seller, draft['id'])
        with self.assertRaises(DomainError):
            self.market.save_draft(self.seller, {'id': draft['id'], 'version': 1, 'fields': {'title': '旧请求'}})
        draft = self.draft({'title': '到期测试'})
        self.api('cleanup_drafts')(time.time() + 31 * 86400)
        self.assertEqual(self.market.list_drafts(self.seller), [])
        with self.assertRaises(DomainError):
            self.market.get_draft(self.seller, draft['id'])

    def test_draft_types_are_strict_and_do_not_accept_privileges(self):
        for fields in [{'role': 'admin'}, {'photos': 'not-a-list'}, {'price': True}]:
            with self.assertRaises(DomainError):
                self.draft(fields)


if __name__ == '__main__':
    unittest.main()
