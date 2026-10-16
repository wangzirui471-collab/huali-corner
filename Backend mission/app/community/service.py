"""社区模块：帖子、评论、总聊与学院群、私聊、举报与屏蔽。"""
import time
from ..core.errors import ValidationMixin, DomainError


class CommunityService(ValidationMixin):

    def rooms(self,u):
        joined=self.rows('SELECT r.*,m.role,m.muted,(SELECT COUNT(*) FROM members z WHERE z.room_id=r.id) count FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=?',(u,))
        return {'joined':joined,'general':self.row('SELECT *, (SELECT COUNT(*) FROM members WHERE room_id=1) count FROM rooms WHERE id=1'),'college':self.profile(u)['college']}
    def join_room(self,u,kind):
        self.require(kind in ['general','college'],'群类型不正确')
        college=self.profile(u)['college'] or '计算机工程学院'
        created=False
        with self.tx() as c:
            if kind=='general': rid=1
            else:
                existing=c.execute("SELECT r.* FROM rooms r JOIN members m ON m.room_id=r.id WHERE r.kind='college' AND r.college=? AND m.user_id=?",(college,u)).fetchone()
                if existing:return dict(existing)
                r=c.execute("SELECT r.* FROM rooms r WHERE kind='college' AND college=? AND (SELECT COUNT(*) FROM members m WHERE m.room_id=r.id)<500 ORDER BY sequence LIMIT 1",(college,)).fetchone()
                if r:rid=r['id']
                else:
                    n=c.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM rooms WHERE kind='college' AND college=?",(college,)).fetchone()[0]
                    rid=c.execute("INSERT INTO rooms(kind,name,college,sequence) VALUES('college',?,?,?)",(f'{college}交流{n}群',college,n)).lastrowid
                    created=True
            # 新建群的创建者自动成为群主，这样学院群里有人能禁言、删消息；
            # 加入已有群或总聊则保持普通成员。
            c.execute('INSERT OR IGNORE INTO members(room_id,user_id,role) VALUES(?,?,?)',(rid,u,'owner' if created else 'member'))
            return dict(c.execute('SELECT * FROM rooms WHERE id=?',(rid,)).fetchone())
    def private_room(self,u,peer):
        peer=int(peer);self.profile(peer);self.require(peer!=u,'不能给自己发私信')
        self.require(not self.row('SELECT 1 FROM blocks WHERE (user_id=? AND target=?) OR (user_id=? AND target=?)',(u,peer,peer,u)),'对方暂不接受消息')
        pair=':'.join(map(str,sorted([u,peer])))
        with self.tx() as c:
            c.execute("INSERT OR IGNORE INTO rooms(kind,name,pair) VALUES('private',?,?)",(self.profile(peer)['nickname'],pair))
            rid=c.execute('SELECT id FROM rooms WHERE pair=?',(pair,)).fetchone()[0]
            for uid in [u,peer]:c.execute('INSERT OR IGNORE INTO members(room_id,user_id) VALUES(?,?)',(rid,uid))
        return self.row('SELECT * FROM rooms WHERE id=?',(rid,))
    def member(self,u,r):
        m=self.row('SELECT * FROM members WHERE room_id=? AND user_id=?',(r,u))
        self.require(m is not None,'请先加入该群或会话',403);return m
    def messages(self,u,r,after=0):
        self.member(u,r)
        return self.rows('SELECT m.id,m.room_id,m.user_id,CASE WHEN m.removed=1 THEN \'消息已被移除\' ELSE m.body END body,m.created,u.nickname FROM messages m JOIN users u ON u.id=m.user_id WHERE room_id=? AND m.id>? ORDER BY m.id LIMIT 100',(r,int(after)))
    def send_message(self,u,r,body,key):
        member=self.member(u,r);self.require(not member['muted'],'你在该群已被禁言',403)
        body=self.text(body,2000,'消息');self.require(1<=len(str(key))<=100,'缺少消息标识')
        room=self.row('SELECT * FROM rooms WHERE id=?',(r,))
        if room['kind']=='private':
            peer=self.row('SELECT user_id FROM members WHERE room_id=? AND user_id<>?',(r,u))['user_id']
            self.require(not self.row('SELECT 1 FROM blocks WHERE (user_id=? AND target=?) OR (user_id=? AND target=?)',(u,peer,peer,u)),'该会话已被屏蔽',403)
        with self.tx() as c:
            c.execute('INSERT OR IGNORE INTO messages(room_id,user_id,body,created,request_key) VALUES(?,?,?,?,?)',(r,u,body,time.time(),key))
        return {'ok':True}
    def block(self,u,target,enabled):
        self.require(u!=int(target),'不能屏蔽自己')
        with self.tx() as c:
            if enabled:c.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(u,int(target)))
            else:c.execute('DELETE FROM blocks WHERE user_id=? AND target=?',(u,int(target)))
        return {'ok':True}
    def posts(self,topic=''):
        return self.rows('SELECT p.*,u.nickname,u.college,(SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) replies FROM posts p JOIN users u ON u.id=p.user_id WHERE (?=\'\' OR topic=?) ORDER BY p.id DESC LIMIT 100',(topic,topic))
    def add_post(self,u,d):
        body=self.text(d.get('body'),2000,'帖子内容');topic=d.get('topic','交流')
        self.require(topic in ['交流','求购','毕业季','互助'],'分区不正确')
        with self.tx() as c:pid=c.execute('INSERT INTO posts(user_id,topic,body,created) VALUES(?,?,?,?)',(u,topic,body,time.time())).lastrowid
        return {'id':pid}
    def comments(self,p):return self.rows('SELECT c.*,u.nickname FROM comments c JOIN users u ON u.id=c.user_id WHERE post_id=? ORDER BY c.id LIMIT 100',(p,))
    def comment(self,u,p,body):
        self.require(self.row('SELECT 1 FROM posts WHERE id=?',(p,)) is not None,'帖子不存在',404)
        with self.tx() as c:c.execute('INSERT INTO comments(post_id,user_id,body,created) VALUES(?,?,?,?)',(p,u,self.text(body,1000,'回复'),time.time()))
        return {'ok':True}
    def moderate(self,u,d):
        r=int(d['room_id']);member=self.member(u,r)
        self.require(member['role'] in ['owner','moderator'] or self.profile(u)['role']=='admin','没有群管理权限',403)
        self.require(self.row('SELECT kind FROM rooms WHERE id=?',(r,))['kind']!='private','不能管理他人私聊')
        with self.tx() as c:
            if d['action']=='mute':c.execute('UPDATE members SET muted=? WHERE room_id=? AND user_id=?',(int(bool(d.get('muted',True))),r,int(d['target'])))
            elif d['action']=='remove_message':c.execute('UPDATE messages SET removed=1 WHERE id=? AND room_id=?',(int(d['message_id']),r))
            else:self.require(False,'不支持此管理操作')
            c.execute('INSERT INTO audit(actor,type,reason,created) VALUES(?,?,?,?)',(u,'moderation',self.text(d.get('reason'),500,'理由'),time.time()))
        return {'ok':True}
    def nominate(self,u,d):
        self.member(u,int(d['room_id']))
        with self.tx() as c:c.execute('INSERT INTO nominations(user_id,room_id,reason,created) VALUES(?,?,?,?)',(u,int(d['room_id']),self.text(d.get('reason'),500,'申请理由'),time.time()))
        return {'ok':True}

    # --- 校园求购撮合 ---------------------------------------------------
    def create_want(self,u,d):
        keyword=self.text(d.get('keyword'),40,'求购物品')
        budget=self.cents(d.get('budget'),'预算');self.require(budget>0,'预算需大于0')
        desc=str(d.get('description') or '').strip()[:1000]
        with self.tx() as c:
            wid=c.execute('INSERT INTO wants(user_id,keyword,budget,description,status,created) VALUES(?,?,?,?,?,?)',(u,keyword,budget,desc,'open',time.time())).lastrowid
        return self.want(u,wid)

    def wants(self,u=None):
        return [self.want(u,r['id']) for r in self.rows('SELECT id FROM wants ORDER BY id DESC LIMIT 50')]

    def want(self,u,wid):
        w=self.row('SELECT w.*,u.nickname FROM wants w JOIN users u ON u.id=w.user_id WHERE w.id=?',(wid,))
        self.require(w,'求购不存在',404)
        w['matches']=self.match_wants(w['keyword'],w['budget'],u)
        return w

    def match_wants(self,keyword,budget,u=None):
        """按关键词匹配在售商品：标题/描述/分类包含关键词即命中，预算内优先、价低优先。"""
        kw=str(keyword).lower()
        result=[]
        for p in self.products(u):
            hay=' '.join(str(p.get(k,'')) for k in ['title','description','category']).lower()
            if kw in hay:result.append(p)
        result.sort(key=lambda p:(p['price']>budget,p['price']))
        return result[:20]
