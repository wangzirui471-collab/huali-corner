import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloudflare_test_support import CloudCase, Binding
from app.cloudflare.api import Api
from app.cloudflare.catalog_api import CatalogApi, CATALOG_ROUTES
from app.cloudflare.http import path_of
class DomainApi(Api):
 async def dispatch(self,request):
  route=CATALOG_ROUTES.get(path_of(request))
  if route and request.method in route[0]:return await getattr(self,route[1])(request)
  return await super().dispatch(request)
class CatalogTests(CloudCase):
 def setUp(self):
  super().setUp();self.api=DomainApi(SimpleNamespace(DB=Binding(self.db),MEDIA=self.bucket))
  self.db.execute("INSERT INTO products(id,seller_id,title,category,price,status,data) VALUES(1,2,'测试书','living',100,'available','{}'),(2,3,'测试物品','living',100,'available','{}')")
  for i,angle in enumerate(('front','side','top')):
   self.db.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',(str(i),2,'media/upload/2/'+str(i),'digest'+str(i),angle,0))
  self.db.commit()
 async def post(self,path,body,uid=2):return await self.req(path,uid,method='POST',body=body)
 def payload(self):return dict(title='教材',description='学校使用的二手教材',category='living',price=100,region='A1',photos=['0','1','2'])
 async def test_publish_and_three_photo_and_integer_money_rules(self):
  r=await self.post('/api/publish',self.payload());self.assertEqual(r.status,200,r.body)
  self.assertEqual(self.db.execute('SELECT price FROM products WHERE id=?',(r.body['id'],)).fetchone()[0],100)
  for edits in ({'photos':['0','1']},{'price':1.2},{'price':True},{'photos':['0','1','1']},{'category':'bad'}):
   r=await self.post('/api/publish',{**self.payload(),**edits});self.assertEqual(r.status,400,r.body)
 async def test_publish_ownership_duplicate_digest_score_and_block(self):
  self.assertEqual((await self.post('/api/publish',self.payload(),3)).status,400)
  self.db.execute("UPDATE uploads SET digest='same'")
  self.assertEqual((await self.post('/api/publish',self.payload())).status,400)
  self.db.execute('UPDATE users SET score=59 WHERE id=2')
  self.assertEqual((await self.post('/api/publish',self.payload())).status,403)
 async def test_status_ownership_platform_lock_and_refund_lock(self):
  self.assertEqual((await self.post('/api/product/status',dict(id=2,action='delist'))).status,403)
  self.assertEqual((await self.post('/api/product/status',dict(id=1,action='delist'))).status,200)
  self.db.execute("INSERT INTO orders(id,items,status) VALUES(1,'[{\"id\":1}]','refunded')")
  self.assertEqual((await self.post('/api/product/status',dict(id=1,action='relist'))).status,403)
  self.db.execute('DELETE FROM orders');self.db.execute('UPDATE products SET delisted_by=1 WHERE id=1')
  self.assertEqual((await self.post('/api/product/status',dict(id=1,action='relist'))).status,403)
 async def test_promote_accumulates_and_writes_audit(self):
  a=await self.post('/api/product/promote',dict(id=1,tier='1d'));self.assertEqual(a.status,200,a.body)
  b=await self.post('/api/product/promote',dict(id=1,tier='3d'));self.assertEqual(b.body['promoted_until']-a.body['promoted_until'],3*86400)
  self.assertEqual(self.db.execute("SELECT count(*) FROM audit WHERE type='promote'").fetchone()[0],2)
 async def test_offer_exclusive_accept_and_ownership(self):
  a=await self.post('/api/offer',dict(product_id=1,amount=50),3);self.assertEqual(a.status,200,a.body)
  b=await self.post('/api/offer',dict(product_id=1,amount=60),4)
  self.assertEqual((await self.post('/api/offer/accept',dict(id=a.body['id'],accept=True),3)).status,403)
  self.assertEqual((await self.post('/api/offer/accept',dict(id=a.body['id'],accept=True))).status,200)
  self.assertEqual(self.db.execute('SELECT status FROM offers WHERE id=?',(b.body['id'],)).fetchone()[0],'rejected')
  self.assertEqual((await self.post('/api/offer',dict(product_id=1,amount=70),3)).status,400)
 async def test_moderation_role_audit_notification_and_second_reviewer(self):
  self.assertEqual((await self.post('/api/product/moderate',dict(id=1,action='delist',reason='违规'))).status,403)
  r=await self.post('/api/product/moderate',dict(id=1,action='delist',reason='违规'),4);self.assertEqual(r.status,200,r.body)
  self.assertEqual(self.db.execute('SELECT delisted_by FROM products WHERE id=1').fetchone()[0],4)
  self.assertEqual((await self.post('/api/product/moderate',dict(id=1,action='restore',reason='复核'),4)).status,403)
  self.assertEqual((await self.post('/api/product/moderate',dict(id=1,action='restore',reason='复核'),1)).status,200)
  self.assertEqual(self.db.execute('SELECT count(*) FROM notifications').fetchone()[0],2)
 async def test_review_approval_clears_pending_and_audits(self):
  self.db.execute('UPDATE products SET data=? WHERE id=1',(json.dumps({'moderation':{'action':'review','reviewed':False}}),))
  r=await self.post('/api/product/review',dict(id=1,decision='approve'),4);self.assertEqual(r.status,200,r.body);self.assertFalse(r.body['under_review'])
  self.assertEqual(self.db.execute("SELECT count(*) FROM audit WHERE type='product_review'").fetchone()[0],1)
 async def test_reaction_idempotence_and_removed_rejection(self):
  for _ in range(2):self.assertEqual((await self.post('/api/react',dict(product_id=1,kind='like',on=True))).status,200)
  self.assertEqual(self.db.execute('SELECT count(*) FROM reactions').fetchone()[0],1)
  self.db.execute("UPDATE products SET status='removed' WHERE id=1")
  self.assertEqual((await self.post('/api/react',dict(product_id=1,kind='like',on=True))).status,400)
 async def test_versioned_profile_unknown_fields_stale_and_legacy(self):
  r=await self.post('/api/user/profile',dict(profile_version=0,nickname='新昵称',degree_level='junior_college'));self.assertEqual(r.status,200,r.body);self.assertEqual(r.body['education'],'专科')
  self.assertEqual((await self.post('/api/user/profile',dict(profile_version=0,nickname='覆盖'))).status,409)
  self.assertEqual((await self.post('/api/user/profile',dict(profile_version=1,role='admin'))).status,400)
  r=await self.post('/api/me',dict(nickname='旧客户端'));self.assertEqual(r.status,200,r.body);self.assertEqual(r.body['degree_level'],'junior_college');self.assertEqual(r.body['profile_version'],2)
 def image(self):
  stream=io.BytesIO();Image.new('RGB',(8,8),'red').save(stream,'PNG');return base64.b64encode(stream.getvalue()).decode()
 async def test_avatar_upload_private_selection_ownership_and_clear(self):
  r=await self.post('/api/user/avatar/upload',dict(content=self.image()));self.assertEqual(r.status,200,r.body);fid=r.body['upload_id']
  self.assertEqual(self.db.execute('SELECT count(*) FROM uploads').fetchone()[0],3)
  self.assertEqual((await self.post('/api/user/avatar',dict(upload_id=fid,profile_version=0),3)).status,403)
  r=await self.post('/api/user/avatar',dict(upload_id=fid,profile_version=0));self.assertEqual(r.status,200,r.body);self.assertEqual(r.body['avatar_url'],'/media/'+fid)
  self.assertEqual((await self.post('/api/user/avatar',dict(upload_id=None,profile_version=0))).status,409)
  self.assertEqual((await self.post('/api/user/avatar',dict(upload_id=None,profile_version=1))).status,200)
 async def test_upload_database_failure_removes_only_new_object(self):
  await self.post('/api/user/avatar/upload',dict(content=self.image()));before=set(self.bucket.objects)
  async def fail(*a,**k):raise RuntimeError('DB failure')
  with patch.object(self.api.db,'guarded_batch',fail):r=await self.post('/api/user/avatar/upload',dict(content=self.image()))
  self.assertEqual(r.status,500);self.assertEqual(set(self.bucket.objects),before)
 async def test_guard_race_rolls_back_promotion_audit(self):
  original=self.api.db.guarded_batch
  async def race(*args,**kwargs):
   self.db.execute("UPDATE products SET status='sold' WHERE id=1")
   return await original(*args,**kwargs)
  with patch.object(self.api.db,'guarded_batch',race):r=await self.post('/api/product/promote',dict(id=1,tier='1d'))
  self.assertEqual(r.status,409,r.body);self.assertEqual(self.db.execute('SELECT count(*) FROM audit').fetchone()[0],0)
 async def test_anonymous_mutations_require_login(self):
  for path in CATALOG_ROUTES:
   self.assertEqual((await self.post(path,{},0)).status,401,path)

 async def test_product_upload_angle_and_private_registry(self):
  r=await self.post('/api/upload',dict(content=self.image(),angle='front'));self.assertEqual(r.status,200,r.body)
  stored=self.db.execute('SELECT * FROM uploads WHERE id=?',(r.body['id'],)).fetchone();self.assertEqual(stored['private'],0)
  self.assertIn(stored['path'],self.bucket.objects)
  self.assertEqual((await self.post('/api/upload',dict(content=self.image(),angle='bad'))).status,400)
  self.assertEqual((await self.post('/api/upload',dict(content='invalid',angle='front'))).status,400)
 async def test_profile_race_returns_conflict_without_overwriting(self):
  original=self.api.db.guarded_batch
  async def race(*args,**kwargs):
   self.db.execute("UPDATE users SET nickname='并发保存',profile_version=1 WHERE id=2")
   return await original(*args,**kwargs)
  with patch.object(self.api.db,'guarded_batch',race):r=await self.post('/api/user/profile',dict(profile_version=0,nickname='覆盖'))
  self.assertEqual(r.status,409,r.body);self.assertEqual(r.body['error'],'资料已更新，请重新载入并核对')
  self.assertEqual(self.db.execute('SELECT nickname FROM users WHERE id=2').fetchone()[0],'并发保存')
 async def test_accept_race_cannot_accept_two_offers(self):
  a=await self.post('/api/offer',dict(product_id=1,amount=50),3)
  b=await self.post('/api/offer',dict(product_id=1,amount=60),4)
  original=self.api.db.guarded_batch
  async def race(*args,**kwargs):
   self.db.execute("UPDATE offers SET status='accepted',accepted_at=9999999999 WHERE id=?",(a.body['id'],))
   return await original(*args,**kwargs)
  with patch.object(self.api.db,'guarded_batch',race):r=await self.post('/api/offer/accept',dict(id=b.body['id'],accept=True))
  self.assertEqual(r.status,409,r.body)
  self.assertEqual(self.db.execute('SELECT status FROM offers WHERE id=?',(b.body['id'],)).fetchone()[0],'pending')
 async def test_moderation_audit_failure_rolls_back_product_and_notification(self):
  self.db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'failed audit'); END")
  r=await self.post('/api/product/moderate',dict(id=1,action='delist',reason='违规'),4)
  self.assertEqual(r.status,500,r.body)
  self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=1').fetchone()[0],'available')
  self.assertEqual(self.db.execute('SELECT count(*) FROM notifications').fetchone()[0],0)
 async def test_blocked_product_content_rejected_before_insert(self):
  r=await self.post('/api/publish',{**self.payload(),'description':'加微信联系我'})
  self.assertEqual(r.status,422,r.body)
  self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0],2)
 async def test_disabled_account_cannot_mutate(self):
  self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
  self.assertEqual((await self.post('/api/user/profile',dict(profile_version=0,nickname='修改'))).status,403)
 async def test_review_cannot_review_own_product(self):
  self.db.execute("UPDATE products SET seller_id=4,data=? WHERE id=1",(json.dumps({'moderation':{'reviewed':False}}),))
  self.assertEqual((await self.post('/api/product/review',dict(id=1,decision='approve'),4)).status,403)
 async def test_r2_failed_put_cleans_unregistered_object(self):
  original=self.bucket.put
  async def fail(*args,**kwargs):await original(*args,**kwargs);return None
  with patch.object(self.bucket,'put',fail):r=await self.post('/api/user/avatar/upload',dict(content=self.image()))
  self.assertEqual(r.status,503,r.body);self.assertEqual(self.bucket.objects,{})
  self.assertEqual(self.db.execute('SELECT count(*) FROM user_avatar_uploads').fetchone()[0],0)
 async def test_malformed_tier_and_proof_are_validation_errors(self):
  self.assertEqual((await self.post('/api/product/promote',dict(id=1,tier=[]))).status,400)
  self.assertEqual((await self.post('/api/publish',{**self.payload(),'proof':{'bad':1}})).status,400)
 async def test_avatar_media_public_only_while_selected_and_active(self):
  uploaded=await self.post('/api/user/avatar/upload',dict(content=self.image()));fid=uploaded.body['upload_id']
  self.assertEqual((await self.req('/media/'+fid,uid=0)).status,403)
  self.assertEqual((await self.req('/media/'+fid,uid=3)).status,403)
  self.assertEqual((await self.req('/media/'+fid,uid=1)).status,403)
  own=await self.req('/media/'+fid);self.assertEqual(own.status,200);self.assertEqual(own.headers['Cache-Control'],'private, no-store')
  await self.post('/api/user/avatar',dict(upload_id=fid,profile_version=0))
  public=await self.req('/media/'+fid,uid=0);self.assertEqual(public.status,200)
  self.assertEqual(public.headers['Content-Type'],'image/webp');self.assertEqual(public.headers['X-Content-Type-Options'],'nosniff')
  await self.post('/api/user/avatar',dict(upload_id=None,profile_version=1))
  self.assertEqual((await self.req('/media/'+fid,uid=0)).status,403)
  self.db.execute("UPDATE users SET status='disabled',avatar_upload_id=? WHERE id=2",(fid,))
  self.assertEqual((await self.req('/media/'+fid)).status,403)
  self.assertEqual((await self.req('/media/'+fid,uid=0)).status,403)
 async def test_private_media_requires_active_owner_or_staff_and_private_cache(self):
  uploaded=await self.post('/api/upload',dict(content=self.image(),angle='proof',private=True));fid=uploaded.body['id']
  for uid in (2,1,4,5):
   r=await self.req('/media/'+fid,uid=uid);self.assertEqual(r.status,200,r.body);self.assertEqual(r.headers['Cache-Control'],'private, no-store')
  for uid in (0,3):self.assertEqual((await self.req('/media/'+fid,uid=uid)).status,403)
  for uid in (2,1,4,5):
   self.db.execute("UPDATE users SET status='disabled' WHERE id=?",(uid,))
   self.assertEqual((await self.req('/media/'+fid,uid=uid)).status,403)
 async def test_unpublished_public_upload_not_available_to_disabled_owner(self):
  uploaded=await self.post('/api/upload',dict(content=self.image(),angle='front'));fid=uploaded.body['id']
  own=await self.req('/media/'+fid);self.assertEqual(own.status,200);self.assertEqual(own.headers['Cache-Control'],'private, no-store')
  self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
  self.assertEqual((await self.req('/media/'+fid)).status,403)
 async def test_new_credentials_require_exact_600000_rounds(self):
  from app.core.errors import DomainError
  self.assertEqual(self.api.check_rounds(600000),600000)
  for rounds in (10000,599999,600001,True,'600000',600000.0,None):
   with self.subTest(rounds=rounds), self.assertRaises(DomainError):self.api.check_rounds(rounds)

