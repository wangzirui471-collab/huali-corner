"""Resource authorization regressions using synthetic D1/R2 fixtures."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloudflare_test_support import CloudCase


class MediaAuthorizationTests(CloudCase):
    def setUp(self):
        """为每个用例创建独立内存库、合成图片和默认下架商品。"""
        super().setUp()
        self.key = "synthetic-photo"
        self.path = "media/upload/2/synthetic.webp"
        self.bucket.objects[self.path] = b"synthetic image"
        self.db.execute(
            "INSERT INTO uploads(id,user_id,path,private) VALUES(?,?,?,0)",
            (self.key, 2, self.path),
        )
        self.product()

    def product(self, status="removed", *, photos=None, proof=None, seller=2):
        """建立指定状态的合成商品，可替换照片、凭证及卖家关系。"""
        detail = {"photos": photos if photos is not None else [
            {"id": self.key, "url": "/media/" + self.key}
        ]}
        if proof is not None:
            detail["proof"] = proof
        self.db.execute(
            "INSERT OR REPLACE INTO products(id,seller_id,status,data) VALUES(1,?,?,?)",
            (seller, status, json.dumps(detail)),
        )

    def order(self, *, buyer=3, seller=2, items=None):
        """建立已完成订单，用于验证历史图片与交易参与方的权限。"""
        self.db.execute(
            "INSERT OR REPLACE INTO orders(id,buyer_id,seller_id,items,status) "
            "VALUES(10,?,?,?,'completed')",
            (buyer, seller, json.dumps(items if items is not None else [
                {"id": 1, "photo": "/media/" + self.key}
            ])),
        )

    def ticket(self, *, product=1, order=None, owner=3, assignee=4):
        """建立关联商品或订单的工单，并指定提交人和处理人。"""
        self.db.execute(
            "INSERT OR REPLACE INTO tickets"
            "(id,user_id,product_id,order_id,status,assignee) VALUES(20,?,?,?,'open',?)",
            (owner, product, order, assignee),
        )

    async def media(self, uid=0, ticket=None):
        """以指定合成用户请求图片；ticket 为显式案件上下文。"""
        suffix = "" if ticket is None else "?ticket_id=" + str(ticket)
        return await self.req("/media/" + self.key + suffix, uid=uid)

    async def test_order_history_is_private_to_parties(self):
        """历史订单图片仅交易双方可读，匿名和无关员工均拒绝。"""
        self.order()
        for uid in (0, 1, 4, 5):
            with self.subTest(uid=uid):
                self.assertEqual((await self.media(uid)).status, 403)
        for uid in (2, 3):
            response = await self.media(uid)
            self.assertEqual(response.status, 200, response.body)
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    async def test_public_photo_requires_available_product_and_active_seller(self):
        """在售且卖家有效时允许公开读，售出或停用后立即收回权限。"""
        self.product("available")
        response = await self.media()
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.product("sold")
        self.assertEqual((await self.media()).status, 403)
        self.product("available")
        self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
        self.assertEqual((await self.media()).status, 403)

    async def test_text_and_prefix_references_do_not_publish_upload(self):
        """排除前缀、任意正文及其他卖家引用，防止模糊匹配误授权。"""
        self.product("available", photos=[{"url": "/media/" + self.key + "-other"}])
        self.order(items=[{"id": 99, "photo": "/media/" + self.key + "-other",
                           "notes": "/media/" + self.key}])
        self.assertEqual((await self.media()).status, 403)
        self.assertEqual((await self.media(3)).status, 403)
        self.product("available", seller=3)
        self.assertEqual((await self.media()).status, 403)

    async def test_unpublished_owner_and_denied_requests_do_not_read_r2(self):
        """未发布图片仅有效上传者可预览；拒绝请求不得触及 R2。"""
        self.db.execute("DELETE FROM products")
        with patch.object(self.api.media_store, "read", side_effect=AssertionError("R2 read")):
            self.assertEqual((await self.media(3)).status, 403)
        self.assertEqual((await self.media(2)).status, 200)
        self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
        self.assertEqual((await self.media(2)).status, 403)

    async def test_private_proof_needs_owner_or_assigned_related_case(self):
        """凭证不对买家或员工角色自动开放，只授予本人及相关处理人。"""
        self.db.execute("UPDATE uploads SET private=1")
        self.product(proof=self.key)
        self.order()
        for uid in (0, 1, 3, 4, 5):
            self.assertEqual((await self.media(uid)).status, 403)
        self.assertEqual((await self.media(2)).status, 200)
        self.ticket()
        self.assertEqual((await self.media(4, ticket=20)).status, 200)
        for uid in (1, 3, 5):
            self.assertEqual((await self.media(uid, ticket=20)).status, 403)
        self.db.execute("UPDATE users SET status='disabled' WHERE id=4")
        self.assertEqual((await self.media(4, ticket=20)).status, 403)

    async def test_case_must_relate_to_resource_not_just_owner(self):
        """验证工单必须精确关联图片所在商品或订单，不能按用户泛授权。"""
        self.db.execute("UPDATE uploads SET private=1")
        self.product(proof=self.key)
        self.ticket(product=99)
        self.assertEqual((await self.media(4, ticket=20)).status, 403)
        self.ticket(product=None, order=10)
        self.order(items=[{"id": 99, "photo": "/media/unrelated"}])
        self.assertEqual((await self.media(4, ticket=20)).status, 403)
        self.order()
        self.assertEqual((await self.media(4, ticket=20)).status, 200)

    async def test_claimed_support_room_grants_and_release_revokes_case_access(self):
        """认领关联客服会话授予案件访问；释放认领后立即撤销。"""
        self.ticket(assignee=None)
        self.db.execute(
            "INSERT INTO rooms(id,kind,support,ticket_id,assignee,support_status) "
            "VALUES(30,'private',1,20,4,'open')"
        )
        self.db.execute("INSERT INTO members(room_id,user_id) VALUES(30,4)")
        self.assertEqual((await self.media(4, ticket=20)).status, 200)
        self.db.execute("UPDATE rooms SET assignee=0 WHERE id=30")
        self.assertEqual((await self.media(4, ticket=20)).status, 403)

    async def test_staff_case_conflicts_deny_proof_access(self):
        """工单提交人或涉事交易参与者不能利用员工身份读取凭证。"""
        self.db.execute("UPDATE uploads SET private=1")
        self.product(proof=self.key)
        self.ticket(owner=4)
        self.assertEqual((await self.media(4, ticket=20)).status, 403)
        self.ticket()
        self.order(buyer=4)
        self.assertEqual((await self.media(4, ticket=20)).status, 403)

    async def test_snapshot_photo_survives_product_removal(self):
        """商品记录消失时，订单中的精确图片快照仍对合法参与方可读。"""
        self.order()
        self.db.execute("DELETE FROM products")
        self.assertEqual((await self.media(3)).status, 200)
        self.ticket(product=None, order=10)
        self.assertEqual((await self.media(4, ticket=20)).status, 200)

    async def test_invalid_case_id_is_validation_error(self):
        """非法案件编号返回参数错误，不进入图片授权查询。"""
        self.assertEqual((await self.media(4, ticket="bad")).status, 400)
