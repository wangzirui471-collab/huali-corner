"""HTTP authorization and media access for direct product removal."""
import io
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
import test_trial_http as fixtures
from PIL import Image


class StaffWorkspaceHttpTests(unittest.TestCase):
    setUp=fixtures.TrialHttpTests.setUp
    tearDown=fixtures.TrialHttpTests.tearDown
    req=fixtures.TrialHttpTests.req

    def sessions(self):
        m=self.server.market
        m.bootstrap_admin('13900009400','OperatorPassword2026!')
        admin=m.login_password('13900009400','OperatorPassword2026!')
        worker=m.create_support(admin['user']['id'],dict(phone='13900009401',password='WorkerPassword2026!',nickname='客服甲'))
        support=m.login_password('13900009401','WorkerPassword2026!')
        seller=m.register_password('13900009402','SellerPassword2026!','卖家')
        return admin,support,seller

    def listing(self,seller):
        m=self.server.market;photos=[]
        for angle,color in [('front','red'),('side','green'),('top','blue')]:
            image=io.BytesIO();Image.new('RGB',(60,60),color).save(image,'PNG')
            photos.append(m.add_upload(seller['user']['id'],image.getvalue(),angle)['id'])
        draft=m.save_draft(seller['user']['id'],dict(version=0,fields=dict(title='审核教材',category='books',price='12',delivery='pickup',region='C1',photos=photos)))
        return m.publish_draft(seller['user']['id'],draft['id'],draft['version'])['id']

    def test_only_staff_can_remove_and_listing_is_not_publicly_buyable(self):
        admin,support,seller=self.sessions()
        for session in [admin,support]:
            pid=self.listing(seller);payload={'id':pid,'reason':'实拍与描述不符'}
            self.assertEqual(self.req('/api/product/moderation',payload)[0],401)
            self.assertEqual(self.req('/api/product/moderation',payload,seller['token'])[0],403)
            self.assertEqual(self.req('/api/product/moderation',{'id':pid,'reason':' '},session['token'])[0],400)
            status,result=self.req('/api/product/moderation',payload,session['token'])
            self.assertEqual(status,200,result)
            self.assertEqual(self.req('/api/product/moderation',payload,session['token'])[0],409)
            self.assertNotIn(pid,[p['id'] for p in self.req('/api/products')[1]])
            notice=self.req('/api/notifications',token=seller['token'])[1]['items'][0]
            self.assertEqual((notice['entity_type'],notice['entity_id']),('product',pid))
        self.server.market.set_support_active(admin['user']['id'],support['user']['id'],False)
        self.assertEqual(self.req('/api/product/moderation',payload,support['token'])[0],401)

    def test_workbench_apis_keep_admin_and_support_permissions_separate(self):
        admin,support,seller=self.sessions()
        for endpoint in ['/api/staff/queue','/api/admin/audit','/api/admin/operations','/api/credit/options?target_user_id='+str(seller['user']['id'])]:
            self.assertEqual(self.req(endpoint,token=seller['token'])[0],403)
            self.assertEqual(self.req(endpoint,token=admin['token'])[0],200)
            expected=200 if endpoint=='/api/staff/queue' else 403
            self.assertEqual(self.req(endpoint,token=support['token'])[0],expected)
        self.assertEqual(self.req('/api/staff/queue?page=invalid',token=support['token'])[0],400)
