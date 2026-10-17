"""Staff removal is separate from a seller's reversible delisting."""
import time

from ..core.errors import ValidationMixin


class CatalogModeration(ValidationMixin):
    def can_read_catalog_media(self, user_id, upload_id):
        if not user_id or self.profile(user_id)['role'] not in ['admin', 'support']:
            return False
        return bool(self.row("SELECT p.id FROM products p,json_each(p.data,'$.photos') photo WHERE json_extract(photo.value,'$.id')=?", (upload_id,)))

    def moderate_product(self, user_id, product_id, reason):
        reason = self.text(reason, 500, '下架原因')
        with self.tx() as connection:
            actor = connection.execute('SELECT role,is_active FROM users WHERE id=?', (user_id,)).fetchone()
            self.require(actor and actor['is_active'] and actor['role'] in ['admin', 'support'],
                         '仅启用的管理员或客服可下架商品', 403)
            product = connection.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            self.require(product, '商品不存在', 404)
            self.require(product['status'] == 'available', '仅在售商品可直接下架；交易中请先处理关联订单', 409)
            connection.execute("UPDATE products SET status='removed',removal_reason='staff_delist',version=version+1 WHERE id=?", (product_id,))
            connection.execute("UPDATE offers SET status='expired' WHERE product_id=? AND status IN ('pending','accepted')", (product_id,))
            audit_id = connection.execute(
                'INSERT INTO audit(actor,target,type,reason,product_id,created) VALUES(?,?,?,?,?,?)',
                (user_id, product['seller_id'], 'product_delist', reason, product_id, time.time()),
            ).lastrowid
            self.notify(connection, [product['seller_id']], 'product:delist:'+str(audit_id),
                        '商品《'+product['title']+'》已下架：'+reason, 'product', product_id)
        return {'ok': True, 'id': product_id, 'status': 'removed'}
