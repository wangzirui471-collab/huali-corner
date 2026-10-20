import tempfile
import unittest
from cloudflare_test_support import CloudCase
from app.market import Market

class LocalForumRead(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.m=Market(self.tmp.name,trial=True)
        with self.m.tx() as c:
            c.execute("INSERT INTO users(id,phone,nickname) VALUES(91,'13900000991','读帖同学')")
            for pid,topic,body in [(1,'交换人生','吉他教学\n换摄影入门'),(2,'代拿快递','帮取快递'),(3,'交流','校园生活'),(4,'交换人生','已删除')]:
                c.execute('INSERT INTO posts(id,user_id,topic,body,created,removed) VALUES(?,?,?,?,?,?)',(pid,91,topic,body,pid,int(pid==4)))
            for i in range(1,26): c.execute('INSERT INTO comments(id,post_id,user_id,body,created) VALUES(?,1,91,?,?)',(i,f'回复{i}',i))
    def test_single_post_search_and_hot_sort_are_global(self):
        self.assertEqual([p['id'] for p in self.m.posts(filters={'forum':'1','sort':'hot'})],[1,2])
        self.assertEqual([p['id'] for p in self.m.posts(filters={'q':'摄影'})],[1])
        self.assertEqual(self.m.posts(filters={'id':'4'}),[])
        self.assertEqual([p['id'] for p in self.m.posts(filters={'id':'1'})],[1])
    def test_replies_page_from_first_floor_without_duplication(self):
        a=self.m.comments(1,limit=20,after=0,order='asc')
        b=self.m.comments(1,limit=20,after=a[-1]['id'],order='asc')
        self.assertEqual([r['id'] for r in a+b],list(range(1,26)))
        self.assertEqual(len(self.m.comments(1)),25)
    def test_forum_topics_can_be_published(self):
        for topic in ['交换人生','代拿快递']:
            self.assertTrue(self.m.add_post(91,{'topic':topic,'body':'课程经验交流与同学互助'})['id'])

class CloudForumRead(CloudCase):
    def setUp(self):
        super().setUp()
        for pid,topic,body in [(1,'交换人生','吉他教学\n换摄影入门'),(2,'代拿快递','帮取快递'),(3,'交流','校园生活'),(4,'交换人生','已删除')]:
            self.db.execute('INSERT INTO posts(id,user_id,topic,body,created,removed) VALUES(?,?,?,?,?,?)',(pid,2,topic,body,pid,int(pid==4)))
        for i in range(1,26):self.db.execute('INSERT INTO comments(id,post_id,user_id,body,created) VALUES(?,1,2,?,?)',(i,f'回复{i}',i))
    async def test_search_hot_and_single_post_contract(self):
        r=await self.req('/api/posts?forum=1&sort=hot');self.assertEqual([p['id'] for p in r.body],[1,2])
        r=await self.req('/api/posts?q=摄影');self.assertEqual([p['id'] for p in r.body],[1])
        self.assertEqual((await self.req('/api/posts?id=4')).body,[])
        self.assertEqual([p['id'] for p in (await self.req('/api/posts?id=1')).body],[1])
    async def test_first_page_and_after_cursor_contract(self):
        a=await self.req('/api/comments?id=1&limit=20&order=asc&after=0')
        b=await self.req('/api/comments?id=1&limit=20&order=asc&after=20')
        self.assertEqual([r['id'] for r in a.body+b.body],list(range(1,26)))
