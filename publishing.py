"""Account-owned drafts and transactional publication; no HTTP or UI state."""

import json
import re
import time
import uuid
from decimal import Decimal, InvalidOperation


DRAFT_RETENTION = 30 * 86400
UNKNOWN = '未核对，交付时检查'
DRAFT_FIELDS = frozenset({
    'title', 'category', 'price', 'delivery_fee', 'delivery', 'region', 'description',
    'edition', 'publisher', 'notes', 'missing', 'accessories', 'bought', 'condition',
    'author', 'isbn', 'course', 'major', 'college', 'original_price', 'building', 'point', 'photos',
})


class Publishing:
    def _draft_fields(self, user_id, fields):
        self.require(isinstance(fields, dict) and not (fields.keys() - DRAFT_FIELDS), '草稿含无效字段')
        for name, value in fields.items():
            if name == 'photos':
                self.require(isinstance(value, list) and len(value) <= 9, '草稿图片最多九张')
                self.require(all(isinstance(item, str) for item in value), '图片标识无效')
                self.require(len(set(value)) == len(value), '图片不能重复')
                for upload_id in value:
                    upload = self.row('SELECT user_id,private FROM uploads WHERE id=?', (upload_id,))
                    self.require(upload and upload['user_id'] == user_id and not upload['private'], '只能使用自己的商品图', 403)
            else:
                self.require(isinstance(value, str) and len(value) <= 3000, '草稿文字格式错误')
        self.require(len(json.dumps(fields, ensure_ascii=False).encode()) <= 64000, '草稿内容过大', 413)
        return fields

    def _draft_row(self, connection, user_id, draft_id, *, active=True):
        row = connection.execute('SELECT * FROM drafts WHERE id=? AND user_id=?', (draft_id, user_id)).fetchone()
        self.require(row, '草稿不存在', 404)
        if active:
            self.require(row['status'] == 'active' and row['updated_at'] > time.time() - DRAFT_RETENTION,
                         '草稿已删除、发布或到期', 409)
        return row

    def _draft_result(self, row):
        result = dict(row)
        result['fields'] = json.loads(result['fields'])
        result.pop('user_id', None)
        result['photos'] = []
        for upload_id in result['fields'].get('photos', []):
            upload = self.row('SELECT id,angle FROM uploads WHERE id=?', (upload_id,))
            if upload:
                result['photos'].append({**upload, 'url': '/media/' + upload_id})
        return result

    def save_draft(self, user_id, payload):
        fields = self._draft_fields(user_id, payload.get('fields'))
        draft_id = payload.get('id') or uuid.uuid4().hex
        version = payload.get('version', 0)
        self.require(isinstance(draft_id, str) and re.fullmatch(r'[a-fA-F0-9-]{32,36}', draft_id), '草稿标识无效')
        self.require(type(version) is int and version >= 0, '草稿版本无效')
        now = time.time()
        with self.tx() as connection:
            row = connection.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
            if row:
                self.require(row['user_id'] == user_id, '草稿不存在', 404)
                self._draft_row(connection, user_id, draft_id)
                self.require(row['version'] == version, '另一窗口已更新草稿，请读取新版或另存一份', 409)
                connection.execute('UPDATE drafts SET fields=?,version=version+1,updated_at=? WHERE id=?',
                                   (json.dumps(fields, ensure_ascii=False), now, draft_id))
            else:
                self.require(version == 0, '草稿不存在或版本不正确', 409)
                source_product_id = None
                if payload.get('copy_from_id'):
                    original = self._draft_row(connection, user_id, payload['copy_from_id'])
                    source_product_id = original['source_product_id']
                count = connection.execute("SELECT COUNT(*) FROM drafts WHERE user_id=? AND status='active'", (user_id,)).fetchone()[0]
                self.require(count < 100, '草稿箱已满，请先删除不需要的草稿')
                connection.execute('INSERT INTO drafts(id,user_id,fields,updated_at,source_product_id) VALUES(?,?,?,?,?)',
                                   (draft_id, user_id, json.dumps(fields, ensure_ascii=False), now, source_product_id))
        return self.get_draft(user_id, draft_id)

    def get_draft(self, user_id, draft_id):
        with self.tx() as connection:
            row = dict(self._draft_row(connection, user_id, draft_id))
        return self._draft_result(row)

    def list_drafts(self, user_id):
        rows = self.rows("SELECT * FROM drafts WHERE user_id=? AND status='active' AND updated_at>? ORDER BY updated_at DESC",
                         (user_id, time.time() - DRAFT_RETENTION))
        return [self._draft_result(row) for row in rows]

    def delete_draft(self, user_id, draft_id):
        with self.tx() as connection:
            self._draft_row(connection, user_id, draft_id)
            connection.execute("UPDATE drafts SET status='deleted',fields='{}',version=version+1 WHERE id=?", (draft_id,))
        return {'ok': True}

    def cleanup_drafts(self, now=None):
        now = time.time() if now is None else now
        with self.tx() as connection:
            connection.execute("UPDATE drafts SET status='expired',fields='{}' WHERE status='active' AND updated_at<?",
                               (now - DRAFT_RETENTION,))

    def _yuan_to_cents(self, value, *, optional=False):
        if optional and not value:
            return 0
        self.require(isinstance(value, str) and len(value) <= 30, '请输入以元为单位的价格')
        try:
            amount = Decimal(value)
        except InvalidOperation:
            self.require(False, '请输入正确价格')
        self.require(amount.is_finite() and 0 <= amount <= 10000, '价格须在0至10000元之间')
        cents = amount * 100
        self.require(cents == cents.to_integral_value(), '价格最多保留两位小数')
        return int(cents)

    def _listing_from_draft(self, fields):
        data = dict(fields)
        data['price'] = self._yuan_to_cents(fields.get('price'))
        data['delivery_fee'] = self._yuan_to_cents(fields.get('delivery_fee', ''), optional=True)
        data['original_price'] = self._yuan_to_cents(fields.get('original_price', ''), optional=True)
        for field in ['notes', 'missing', 'accessories']:
            data[field] = fields.get(field) or UNKNOWN
        data['edition'] = fields.get('edition') or '版本待确认'
        data['publisher'] = fields.get('publisher') or '出版社待确认'
        data['bought'] = fields.get('bought') or '未知'
        data['condition'] = fields.get('condition') or '成色待核对，见实拍'
        if not fields.get('region'):
            data['region'] = ' · '.join(value for value in [fields.get('building'), fields.get('point')] if value)
        description = fields.get('description', '').strip()
        defect = any(value in data.get(field, '') for field, value in [('missing', '有缺页'), ('accessories', '附件缺失')])
        self.require(not defect or description, '请说明缺页位置或缺失附件，再发布')
        data['description'] = description or '；'.join([data['condition']] + (
            [f"版次：{data['edition']}", f"笔记：{data['notes']}", f"缺页：{data['missing']}", f"附件：{data['accessories']}"]
            if data.get('category') == 'books' else []))
        return data

    def publish_draft(self, user_id, draft_id, version):
        self.require(type(version) is int, '草稿版本无效')
        with self.tx() as connection:
            draft = self._draft_row(connection, user_id, draft_id, active=False)
            if draft['status'] == 'published':
                return {'id': draft['published_product_id']}
            self._draft_row(connection, user_id, draft_id)
            self.require(draft['version'] == version, '草稿有新版，请先同步', 409)
            data = self._listing_from_draft(json.loads(draft['fields']))
            stock_key = None
            if draft['source_product_id']:
                source = self._relist_source(connection, user_id, draft['source_product_id'])
                stock_key = source['stock_key']
            product = self.publish(user_id, data, connection=connection, stock_key=stock_key, source_draft_id=draft_id)
            connection.execute("UPDATE drafts SET status='published',published_product_id=?,fields='{}' WHERE id=?",
                               (product['id'], draft_id))
        return product
