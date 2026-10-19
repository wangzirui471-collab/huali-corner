"""内容处置：客服/管理员/开发者可以下掉违法帖子与评论。

平台原来只有「自动审核打标 → 工作台送审」这一条路径，普通违法内容
（举报上来但没被规则命中）没有处置入口。这组用例锁住四条：
  1. 帖子/评论都能软删除，删完列表里看不到；
  2. 普通用户没有这个权限；
  3. 不能处置自己发的内容（避免当事管理员自己删证据）；
  4. 删除写审计、通知作者，而且能恢复。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_content_removal
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class ContentRemovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.dev = self.reg('13800000061', '开发者', 'developer')
        self.admin = self.reg('13800000062', '管理员', 'admin')
        self.sup = self.reg('13800000063', '客服', 'support')
        self.user = self.reg('13800000064', '普通用户', 'user')
        self.post = self.m.add_post(self.user, {'topic': '交流', 'body': '这是一条要被删的帖子'})['id']
        # comment() 只回 {'ok':True}，没有 id，这里回查一次。
        self.m.comment(self.user, self.post, '这是一条要被删的评论')
        self.comment = self.m.row('SELECT id FROM comments WHERE post_id=? ORDER BY id DESC LIMIT 1',
                                  (self.post,))['id']

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, phone, nickname, role):
        uid = self.m.register_password(phone, 'Passw0rd!123', nickname)['user']['id']
        if role != 'user':
            self.m.set_role_operator(phone, role)
        return uid

    def post_ids(self):
        return [p['id'] for p in self.m.posts()]

    def comment_ids(self):
        return [c['id'] for c in self.m.comments(self.post)]

    def test_remove_post_hides_it(self):
        self.m.content_action(self.sup, 'post', self.post, 'remove', '含违法交易信息')
        self.assertNotIn(self.post, self.post_ids())

    def test_remove_comment_hides_it(self):
        self.m.content_action(self.sup, 'comment', self.comment, 'remove', '人身攻击')
        self.assertNotIn(self.comment, self.comment_ids())

    def test_admin_and_developer_can_remove(self):
        p2 = self.m.add_post(self.user, {'topic': '互助', 'body': '第二条'})['id']
        self.m.content_action(self.admin, 'post', p2, 'remove', '管理员处置')
        self.assertNotIn(p2, self.post_ids())
        p3 = self.m.add_post(self.user, {'topic': '互助', 'body': '第三条'})['id']
        self.m.content_action(self.dev, 'post', p3, 'remove', '开发者处置')
        self.assertNotIn(p3, self.post_ids())

    def test_ordinary_user_cannot_remove(self):
        with self.assertRaises(DomainError):
            self.m.content_action(self.user, 'post', self.post, 'remove', '我想删别人的')
        self.assertIn(self.post, self.post_ids())

    def test_cannot_remove_own_content(self):
        """自己发的帖子不能自己删——防止处置人顺手删掉对自己不利的记录。"""
        own = self.m.add_post(self.admin, {'topic': '交流', 'body': '管理员自己的帖子'})['id']
        with self.assertRaises(DomainError):
            self.m.content_action(self.admin, 'post', own, 'remove', '自己删自己')

    def test_removed_post_blocks_comment_api(self):
        """帖子被删后，评论接口不该再吐出它的评论区。"""
        self.m.content_action(self.sup, 'post', self.post, 'remove', '违法内容')
        with self.assertRaises(DomainError):
            self.m.comments(self.post)

    def test_remove_notifies_author_and_writes_audit(self):
        self.m.content_action(self.sup, 'comment', self.comment, 'remove', '泄露他人隐私')
        notes = self.m.notifications(self.user)['items']
        self.assertTrue(any(n['kind'] == 'content_removed' for n in notes), notes[:2])
        logs = [a for a in self.m.audit_log(self.sup, limit=50) if a['type'] == 'content_remove']
        self.assertTrue(logs)

    def test_restore_puts_it_back(self):
        self.m.content_action(self.sup, 'comment', self.comment, 'remove', '误判')
        self.m.content_action(self.sup, 'comment', self.comment, 'restore', '申诉成立，恢复')
        self.assertIn(self.comment, self.comment_ids())


if __name__ == '__main__':
    unittest.main()
