import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
import test_trial_http as fixtures


class HelpHttpTests(unittest.TestCase):
    setUp=fixtures.TrialHttpTests.setUp
    tearDown=fixtures.TrialHttpTests.tearDown
    req=fixtures.TrialHttpTests.req
    register=fixtures.TrialHttpTests.register

    def test_public_bulletin_authenticated_publish_and_owned_status(self):
        self.assertEqual(self.req('/api/help/posts')[0],200)
        data=dict(kind='need',service_type='parcel',title='快递代取',body='公开说明，取件码私聊',
                  place='C1楼下',reward_yuan='2',deadline=time.time()+7200,key='same-publish')
        self.assertEqual(self.req('/api/help/posts',data)[0],401)
        first=self.register('13900000451');second=self.register('13900000452')
        status,post=self.req('/api/help/posts',data,first['token']);self.assertEqual(status,200,post)
        self.assertEqual(self.req('/api/help/posts',data,first['token'])[1]['id'],post['id'])
        self.assertEqual(self.req('/api/help/status',dict(post_id=post['id'],status='closed'),second['token'])[0],403)
        self.assertEqual(self.req('/api/help/posts?service_type=parcel')[1]['items'][0]['reward'],200)
        status,ticket=self.req('/api/tickets',dict(type='report',post_id=post['id'],subject='反馈',body='可核查材料'),second['token'])
        self.assertEqual(status,200,ticket);self.assertEqual(ticket['post_id'],post['id'])
        self.assertEqual(self.req('/api/help/status',dict(post_id=post['id'],status='closed'),first['token'])[0],200)
        self.assertEqual(self.req('/api/help/posts')[1]['items'],[])

    def test_chat_read_api_preserves_other_viewer_and_future_messages(self):
        a=self.register('13900000453');b=self.register('13900000454')
        room=self.req('/api/rooms/private',dict(peer=b['user']['id']),a['token'])[1]
        self.req('/api/messages',dict(room_id=room['id'],body='你好',key='chat-one'),a['token'])
        self.assertEqual(self.req('/api/notifications',token=b['token'])[1]['unread_count'],1)
        message=self.req('/api/messages?room_id='+str(room['id']),token=b['token'])[1][0]
        self.assertEqual(self.req('/api/messages/read',dict(room_id=room['id'],through_id=message['id']),b['token'])[0],200)
        self.assertEqual(self.req('/api/notifications',token=b['token'])[1]['unread_count'],0)

    def test_support_cannot_read_global_administrator_audit(self):
        session=self.register('13900000455')
        with self.server.market.tx() as connection:
            connection.execute("UPDATE users SET role='support' WHERE id=?",(session['user']['id'],))
        self.assertEqual(self.req('/api/admin',token=session['token'])[0],403)
