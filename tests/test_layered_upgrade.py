"""Upgrade synthetic data created by both previously shipped database formats."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from app.market import Market

class LayeredUpgradeTests(unittest.TestCase):
    def test_main_and_feature_data_keep_accounts_media_orders_and_notes(self):
        # Old source snapshots are optional local fixtures: materialize exact Git revisions.
        repo=Path(__file__).resolve().parents[1]
        for revision,layered in [('ad39da0',True),('6286861',False)]:
            with self.subTest(revision=revision),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);code=root/'source';code.mkdir()
                result=subprocess.run(['git','archive',revision],cwd=repo,capture_output=True)
                if result.returncode:self.skipTest('旧版迁移对照需要包含 ad39da0 与 6286861 的 Git 历史')
                archive=result.stdout
                import io,tarfile
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(code,filter='data')
                backend=code/'Backend mission' if layered else code
                program='''import io,json,sys,time
from pathlib import Path
from PIL import Image
sys.path.insert(0,sys.argv[1])
IMPORT
m=Market(sys.argv[2]);users=[]
for phone in ['13800000121','13800000122']:
 code=m.request_code(phone)['demo_code'];users.append(m.login(phone,code)['user']['id'])
photos=[]
for angle,color in [('front','red'),('side','green'),('top','blue')]:
 image=io.BytesIO();Image.new('RGB',(80,80),color).save(image,'PNG');photos.append(m.add_upload(users[0],image.getvalue(),angle)['id'])
p=m.publish(users[0],dict(title='升级时保留的书',category='books',price=1234,delivery_fee=200,delivery='both',region='A1入口',description='原始介绍',photos=photos,edition='第二版',publisher='出版社',notes='无笔记',missing='无缺页',accessories='无附件'))
o=m.checkout(users[1],dict(product_ids=[p['id']],delivery='pickup',appointment=time.time()+7200,key='upgrade'))
m.order_action(users[1],o['id'],'pay',{})
if hasattr(m,'save_draft'):m.save_draft(users[0],{'version':0,'fields':{'title':'未发布草稿'}})
if LAYERED:
 with m.tx() as c:c.execute('INSERT INTO order_notes(order_id,user_id,body,created) VALUES(?,?,?,?)',(o['id'],users[0],'升级前的订单记录',time.time()))
print(json.dumps({'users':users,'product':p['id'],'order':o['id'],'photos':photos,'items':o['items']}))
'''.replace('IMPORT','from app.market import Market' if layered else 'from market import Market').replace('LAYERED',str(layered))
                old=root/'old-data'
                result=subprocess.run([sys.executable,'-c',program,str(backend),str(old)],capture_output=True,text=True,check=True)
                data=json.loads(result.stdout)
                restored=root/'restored';shutil.copytree(old,restored)
                m=Market(restored)
                order=m.order(data['users'][1],data['order'])
                self.assertEqual(order['items'],data['items'])
                self.assertEqual(order['total'],1234)
                self.assertEqual(order['ledger'][0]['kind'],'payment')
                self.assertEqual(m.profile(data['users'][0])['score'],100)
                for upload in data['photos']:
                    row=m.row('SELECT path FROM uploads WHERE id=?',(upload,))
                    self.assertTrue(Path(row['path']).is_relative_to(restored))
                    self.assertTrue(Path(row['path']).read_bytes())
                if layered:self.assertEqual(order['notes'][0]['body'],'升级前的订单记录')
                else:
                    self.assertEqual(m.list_drafts(data['users'][0])[0]['fields']['title'],'未发布草稿')
                    self.assertGreater(m.notifications(data['users'][0])['unread_count'],0)
                self.assertEqual(m.row('PRAGMA journal_mode')['journal_mode'],'delete')
