"""Isolated D1 community contracts; never opens application data."""
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))
class Response:
    def __init__(self,value,status=200,**kw): self.body=value;self.status=status
    @classmethod
    def from_json(cls,value,**kw): return cls(value,**kw)
sys.modules.setdefault('workers',SimpleNamespace(Response=Response))
from app.cloudflare.community_api import CommunityApi, COMMUNITY_ROUTES
from app.cloudflare.http import guard, require
from app.cloudflare.d1 import Database
from cloudflare_test_support import Binding

from app.cloudflare.api import Api as BaseApi
from app.cloudflare.crypto import session_digest

if issubclass(BaseApi, CommunityApi):
    Api=BaseApi
else:
    class Api(CommunityApi,BaseApi):
        pass

class CommunityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;self.addCleanup(self.c.close)
        self.c.executescript((ROOT/'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
        for u,role in [(1,'admin'),(2,'user'),(3,'user'),(4,'support')]:self.c.execute('INSERT INTO users(id,phone,nickname,role,college) VALUES(?,?,?,?,?)',(u,str(u),f'同学{u}',role,'测试学院'))
        self.c.execute("INSERT INTO rooms(id,kind,name) VALUES(1,'general','总聊')")
        self.c.executemany('INSERT INTO sessions VALUES(?,?,?)',[(session_digest(f'test-{u}'),u,9999999999) for u in range(1,5)])
        self.api=Api(SimpleNamespace(DB=Binding(self.c),MEDIA=object()))
    async def req(self,path,body=None,uid=2):
        method='POST' if body is not None else 'GET'
        async def text():return json.dumps(body)
        r=SimpleNamespace(url='https://test.invalid'+path,method=method,text=text,uid=uid,headers={'Authorization':f'Bearer test-{uid}'} if uid else {})
        return await guard(lambda:getattr(self.api,COMMUNITY_ROUTES[path.split('?')[0]][1])(r))
    async def test_posts_comments_pagination_mentions_and_parent_scope(self):
        p=await self.req('/api/posts',{'body':'测试 @同学3','topic':'交流'});self.assertEqual(p.status,200)
        pid=p.body['id'];self.assertEqual((await self.req('/api/posts?limit=1')).body[0]['id'],pid)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM notifications WHERE user_id=3').fetchone()[0],1)
        r=await self.req('/api/comments',{'post_id':pid,'body':'回复'},uid=3);self.assertEqual(r.status,200)
        self.assertEqual((await self.req(f'/api/comments?id={pid}')).body[0]['nickname'],'同学3')
        self.assertEqual((await self.req('/api/comments',{'post_id':pid,'body':'回复','parent_id':999})).status,404)
        self.assertEqual((await self.req('/api/posts',{'body':'去 https://example.com','topic':'交流'})).status,422)
    async def test_private_idempotency_hide_recall_and_block(self):
        a=await self.req('/api/rooms/private',{'peer':3});self.assertEqual(a.status,200);rid=a.body['id']
        self.assertEqual((await self.req('/api/rooms/private',{'peer':2},uid=3)).body['id'],rid)
        for _ in range(2):self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'你好','key':'one'})).status,200)
        rows=(await self.req(f'/api/messages?room_id={rid}',uid=3)).body;self.assertEqual(len(rows),1);mid=rows[0]['id']
        self.assertEqual((await self.req('/api/messages/hide',{'message_id':mid},uid=3)).status,200)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}',uid=3)).body,[])
        self.assertEqual((await self.req('/api/messages/recall',{'message_id':mid})).status,200)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}')).body[0]['body'],'')
        await self.req('/api/block',{'target':3})
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'你好','key':'two'})).status,403)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}',uid=4)).status,403)
    async def test_college_full_split_and_member_roles(self):
        self.c.execute("INSERT INTO rooms(id,kind,name,college) VALUES(10,'college','满群','测试学院')")
        self.c.executemany('INSERT INTO members(room_id,user_id) VALUES(10,?)',[(u,) for u in range(100,600)])
        r=await self.req('/api/rooms/join',{'kind':'college'});self.assertEqual(r.status,200);self.assertNotEqual(r.body['id'],10)
        rid=r.body['id'];self.assertEqual((await self.req(f'/api/room/members?room_id={rid}')).body['members'][0]['role'],'owner')
        self.assertEqual((await self.req('/api/rooms/join',{'kind':'college'})).body['id'],rid)
    async def test_support_requires_ticket_and_claim_controls_read_send(self):
        self.assertEqual((await self.req('/api/support/room',{})).status,400)
        self.c.execute("INSERT INTO tickets(id,user_id,status) VALUES(1,2,'open')")
        room=await self.req('/api/support/room',{});self.assertEqual(room.status,200);rid=room.body['id']
        self.assertEqual((await self.req('/api/support/claim',{'room_id':rid},uid=4)).body['ok'],True)
        self.assertEqual((await self.req('/api/support/claim',{'room_id':rid},uid=1)).body['ok'],False)
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'客服答复','key':'a'},uid=1)).status,403)
    async def test_moderation_nomination_and_wants(self):
        room=await self.req('/api/rooms/join',{'kind':'college'});rid=room.body['id']
        await self.req('/api/rooms/join',{'kind':'college'},uid=3)
        self.assertEqual((await self.req('/api/moderate',{'room_id':rid,'action':'mute','target':3,'reason':'测试'})).status,200)
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'你好','key':'a'},uid=3)).status,403)
        self.assertEqual((await self.req('/api/nominate',{'room_id':rid,'reason':'申请'})).status,200)
        self.assertEqual((await self.req('/api/wants',{'keyword':'书','budget':100})).status,200)
        self.assertEqual(len((await self.req('/api/wants')).body),1)

    async def test_messages_latest_200_cursor_and_unread_hide(self):
        rid=(await self.req('/api/rooms/private',{'peer':3})).body['id']
        self.c.executemany('INSERT INTO messages(room_id,user_id,body,created,request_key) VALUES(?,?,?,?,?)',[(rid,2,str(i),time.time(),str(i)) for i in range(250)])
        rooms=(await self.req('/api/rooms',uid=3)).body
        room=next(x for x in rooms['joined'] if x['id']==rid)
        self.assertEqual(room['name'],'同学2');self.assertEqual(room['unread'],99)
        messages=(await self.req(f'/api/messages?room_id={rid}',uid=3)).body
        self.assertEqual(len(messages),200);self.assertEqual(messages[0]['body'],'50');self.assertEqual(messages[-1]['body'],'249')
        after=messages[-1]['id'];await self.req('/api/messages',{'room_id':rid,'body':'新消息','key':'new'})
        delta=(await self.req(f'/api/messages?room_id={rid}&after={after}',uid=3)).body
        self.assertEqual([m['body'] for m in delta],['新消息'])
        await self.req('/api/messages/hide',{'message_id':delta[0]['id']},uid=3)
        self.assertEqual((await self.req('/api/rooms',uid=3)).body['joined'][0]['last_body'],'249')

    async def test_comments_latest_100_cursor_and_cross_post_parent(self):
        pid=(await self.req('/api/posts',{'body':'帖子','topic':'互助'})).body['id']
        self.c.executemany('INSERT INTO comments(post_id,user_id,body,created) VALUES(?,?,?,?)',[(pid,3,str(i),time.time()) for i in range(130)])
        comments=(await self.req(f'/api/comments?id={pid}')).body
        self.assertEqual(len(comments),100);self.assertEqual(comments[0]['body'],'30');self.assertEqual(comments[-1]['body'],'129')
        older=(await self.req(f"/api/comments?id={pid}&before={comments[0]['id']}")).body
        self.assertEqual(len(older),30)
        other=(await self.req('/api/posts',{'body':'另一帖','topic':'互助'})).body['id']
        self.assertEqual((await self.req('/api/comments',{'post_id':other,'parent_id':comments[0]['id'],'body':'错误回复'})).status,404)

    async def test_expired_recall_and_nonowner_moderation_forbidden(self):
        rid=(await self.req('/api/rooms/join',{'kind':'college'})).body['id']
        await self.req('/api/rooms/join',{'kind':'college'},uid=3)
        await self.req('/api/messages',{'room_id':rid,'body':'旧消息','key':'old'})
        mid=self.c.execute('SELECT MAX(id) FROM messages').fetchone()[0]
        self.c.execute('UPDATE messages SET created=? WHERE id=?',(time.time()-121,mid))
        self.assertEqual((await self.req('/api/messages/recall',{'message_id':mid})).status,400)
        self.assertEqual((await self.req('/api/messages/recall',{'message_id':mid},uid=3)).status,403)
        self.assertEqual((await self.req('/api/moderate',{'room_id':rid,'action':'mute','target':2,'reason':'越权'},uid=3)).status,403)
        self.assertEqual((await self.req('/api/moderate',{'room_id':rid,'action':'remove_message','message_id':mid,'reason':'违规'})).status,200)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}')).body[0]['body'],'消息已被移除')

    async def test_private_contact_allowed_public_contact_flagged(self):
        rid=(await self.req('/api/rooms/private',{'peer':3})).body['id']
        private=await self.req('/api/messages',{'room_id':rid,'body':'电话13800138000','key':'contact'})
        self.assertEqual(private.status,200);self.assertIsNone(private.body['moderation'])
        post=await self.req('/api/posts',{'body':'电话13800138000','topic':'交流'})
        self.assertEqual(post.status,200);self.assertEqual(post.body['moderation']['action'],'review')
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'走闲鱼','key':'offsite'})).status,422)

    async def test_claim_race_loser_never_joins(self):
        self.c.execute("INSERT INTO tickets(id,user_id,status) VALUES(1,2,'open')")
        rid=(await self.req('/api/support/room',{})).body['id']
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.c.execute('UPDATE rooms SET assignee=1 WHERE id=?',(rid,))
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        claim=await self.req('/api/support/claim',{'room_id':rid},uid=4)
        self.assertEqual(claim.body['ok'],False)
        # Initially selected support account 4 may already be a member, but never gains the claim.
        self.assertEqual(self.c.execute('SELECT assignee FROM rooms WHERE id=?',(rid,)).fetchone()[0],1)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}',uid=4)).status,403)

    async def test_full_room_race_diverts_without_501st_member(self):
        self.c.execute("INSERT INTO rooms(id,kind,name,college) VALUES(10,'college','临界群','测试学院')")
        self.c.executemany('INSERT INTO members(room_id,user_id) VALUES(10,?)',[(u,) for u in range(100,599)])
        original=self.api.db.guarded_batch;fired=False
        async def race(sql,params,statements,**kw):
            nonlocal fired
            if not fired:
                fired=True;self.c.execute('INSERT INTO members(room_id,user_id) VALUES(10,999)')
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        joined=await self.req('/api/rooms/join',{'kind':'college'})
        self.assertEqual(joined.status,200);self.assertNotEqual(joined.body['id'],10)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM members WHERE room_id=10').fetchone()[0],500)

    async def test_permission_change_between_check_and_send_rolls_back(self):
        rid=(await self.req('/api/rooms/private',{'peer':3})).body['id']
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.c.execute('INSERT OR IGNORE INTO blocks VALUES(3,2)')
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        sent=await self.req('/api/messages',{'room_id':rid,'body':'竞态消息','key':'race'})
        self.assertEqual(sent.status,409);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)

    async def test_want_matches_budget_order_and_complete_product_fields(self):
        self.c.executemany("INSERT INTO products(id,seller_id,title,category,price,delivery,status,data) VALUES(?,3,'测试书籍','book',?,'pickup','available','{}')",[(1,1000),(2,200),(3,500)])
        want=await self.req('/api/wants',{'keyword':'书籍','budget':600})
        self.assertEqual(want.status,200);self.assertEqual([p['id'] for p in want.body['matches']],[2,3,1])
        self.assertTrue({'liked','favorited','seller_trusted','likes','nickname'}.issubset(want.body['matches'][0]))
        wid=want.body['id'];self.assertEqual((await self.req(f'/api/want?id={wid}',uid=0)).body['id'],wid)


    async def test_support_release_revokes_old_staff_and_reassignment(self):
        self.c.execute("INSERT INTO tickets(id,user_id,status) VALUES(1,2,'open')")
        rid=(await self.req('/api/support/room',{})).body['id']
        self.assertEqual((await self.req('/api/support/claim',{'room_id':rid},uid=4)).body['assignee'],4)
        release=await self.req('/api/support/claim',{'room_id':rid,'action':'release'},uid=4)
        self.assertEqual(release.body['assignee'],0)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}',uid=4)).status,403)
        self.assertEqual((await self.req('/api/support/claim',{'room_id':rid},uid=1)).body['assignee'],1)
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'已接入','key':'reply'},uid=1)).status,200)
        self.assertEqual((await self.req(f'/api/messages?room_id={rid}',uid=2)).body[0]['body'],'已接入')
        pool=(await self.req('/api/rooms',uid=3)).body['joined']
        self.assertFalse(any(room['id']==rid for room in pool))
        self.assertEqual((await self.req('/api/support/claim',{'room_id':rid},uid=3)).status,403)

    async def test_general_capacity_and_existing_member_at_capacity(self):
        await self.req('/api/rooms/join',{'kind':'general'})
        self.c.executemany('INSERT INTO members(room_id,user_id) VALUES(1,?)',[(u,) for u in range(100,599)])
        self.assertEqual((await self.req('/api/rooms/join',{'kind':'general'})).status,200)
        self.assertEqual((await self.req('/api/rooms/join',{'kind':'general'},uid=3)).status,409)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM members WHERE room_id=1').fetchone()[0],500)

    async def test_comment_reply_and_mentions_notify_once(self):
        pid=(await self.req('/api/posts',{'body':'测试','topic':'交流'})).body['id']
        await self.req('/api/comments',{'post_id':pid,'body':'评论'},uid=3)
        parent=(await self.req(f'/api/comments?id={pid}')).body[0]['id']
        self.c.execute('DELETE FROM notifications')
        await self.req('/api/comments',{'post_id':pid,'parent_id':parent,'body':'@同学2 @同学3 @同学3'},uid=4)
        rows=self.c.execute('SELECT user_id,COUNT(*) n FROM notifications GROUP BY user_id').fetchall()
        self.assertEqual({x['user_id']:x['n'] for x in rows},{2:1,3:1})

    async def test_unblock_restores_send_and_guest_writes_require_login(self):
        rid=(await self.req('/api/rooms/private',{'peer':3})).body['id']
        await self.req('/api/block',{'target':3});await self.req('/api/block',{'target':3,'enabled':False})
        self.assertEqual((await self.req('/api/messages',{'room_id':rid,'body':'恢复','key':'ok'})).status,200)
        self.assertEqual((await self.req('/api/posts',{'body':'无登录','topic':'交流'},uid=0)).status,401)
        self.c.execute("UPDATE users SET status='banned' WHERE id=2")
        self.assertEqual((await self.req('/api/rooms')).status,403)
        self.assertEqual((await self.req('/api/nominate',{'room_id':rid,'reason':'申请'})).status,403)

if __name__=='__main__':unittest.main()




