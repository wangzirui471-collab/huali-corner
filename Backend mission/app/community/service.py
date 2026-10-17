"""社区模块：帖子、评论、总聊与学院群、私聊、举报与屏蔽。"""
import json, re, time
from ..core.errors import ValidationMixin, DomainError
from ..moderation import scan_text, scan_private, flag_of, message_for


class CommunityService(ValidationMixin):

    # @提及的解析口径：@ 后面跟 1–24 个非空白/非标点字符。
    # 昵称在库里不唯一，多个同名的都会收到通知——宁可多发一条，
    # 也不能让被 @ 的人错过。单条内容最多通知 10 个人，防刷。
    MENTION_RE = re.compile(r'@([^\s@，。！？!?,.：:；;~]{1,24})')

    def rooms(self,u):
        # 会话列表要像微信一样显示「最后一条消息」：摘要、时间、发言人。
        # 三个独立子查询比 join 一条消息再聚合快不了多少，但可读性好得多；
        # 摘要取 removed=0 的最新一条（被移除的消息不当作预览），时间取最新一条
        # （包括被移除的，否则撤回后时间会倒退）。
        joined=self.rows('''SELECT r.*,m.role,m.muted,m.last_read_id,
            (SELECT COUNT(*) FROM members z WHERE z.room_id=r.id) count,
            (SELECT CASE WHEN x.removed=2 THEN '' ELSE x.body END FROM messages x WHERE x.room_id=r.id AND x.removed=0 ORDER BY x.id DESC LIMIT 1) last_body,
            (SELECT x.created FROM messages x WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_at,
            (SELECT un.nickname FROM messages x JOIN users un ON un.id=x.user_id WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_nick,
            (SELECT un.nickname FROM users un WHERE un.id=r.assignee) assignee_name
            FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=?''',(u,))
        for r in joined:r['unread']=self._room_unread(u,r['id'],r['last_read_id'])
        # 客服额外看到所有客服会话（待接入池），即使自己还不是成员。
        # 这样新会话一进来所有客服都看得到，谁先认领归谁，不会没人接，
        # 也不会两个客服同时回同一个用户。via_pool 标记「你尚未加入」，
        # 前端点开时触发认领、认领成功才真正成为成员能读消息。
        if self.is_staff(u):
            have={r['id'] for r in joined}
            pool=self.rows('''SELECT r.*,
                (SELECT COUNT(*) FROM members z WHERE z.room_id=r.id) count,
                (SELECT CASE WHEN x.removed=2 THEN '' ELSE x.body END FROM messages x WHERE x.room_id=r.id AND x.removed=0 ORDER BY x.id DESC LIMIT 1) last_body,
                (SELECT x.created FROM messages x WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_at,
                (SELECT un.nickname FROM messages x JOIN users un ON un.id=x.user_id WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_nick,
                (SELECT un.nickname FROM users un WHERE un.id=r.assignee) assignee_name
                FROM rooms r WHERE r.support=1 ORDER BY r.id''')
            for r in pool:
                if r['id'] not in have:
                    r.update(role='member',muted=0,last_read_id=0,unread=0,via_pool=True)
                    joined.append(r)
        return {'joined':joined,'general':self.row('SELECT *, (SELECT COUNT(*) FROM members WHERE room_id=1) count FROM rooms WHERE id=1'),'college':self.profile(u)['college']}

    # --- 聊天未读 ----------------------------------------------------------
    # 每个成员记一个 last_read_id（读过的最大消息 id），未读 = 比它新的、
    # 别人发的、没被移除的消息。加入会话时把位点拨到当下，避免「入群即 99+」。
    def _room_unread(self,u,rid,last_read):
        n=self.row('SELECT COUNT(*) n FROM messages WHERE room_id=? AND id>? AND user_id<>? AND removed=0',
                   (rid,int(last_read or 0),u))['n']
        return min(n,99)

    def chat_unread(self,u):
        rows=self.rows('SELECT room_id,last_read_id FROM members WHERE user_id=?',(u,))
        return min(sum(self._room_unread(u,r['room_id'],r['last_read_id']) for r in rows),99)

    def _mark_room_read(self,c,rid,u,upto):
        c.execute('UPDATE members SET last_read_id=MAX(last_read_id,?) WHERE room_id=? AND user_id=?',
                  (int(upto),int(rid),u))

    # --- @提及通知 ----------------------------------------------------------
    def _notify_mentions(self,c,author_id,author,body,post_id,skip=()):
        seen=set()
        for raw in self.MENTION_RE.findall(body or ''):
            name=raw.strip()
            if not name or name in seen:continue
            seen.add(name)
            target=self.row('SELECT id FROM users WHERE nickname=?',(name,))
            if not target or target['id']==author_id or target['id'] in skip:continue
            self.notify(c,target['id'],'mention',f'{author} 在帖子中提到了你',post_id=post_id)
            if len(seen)>=10:break

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
            # 新加入的成员只算「加入之后」的未读：把已读位点拨到当前最新消息。
            c.execute('UPDATE members SET last_read_id=COALESCE((SELECT MAX(id) FROM messages WHERE room_id=?),0) WHERE room_id=? AND user_id=? AND last_read_id=0',(rid,rid,u))
            return dict(c.execute('SELECT * FROM rooms WHERE id=?',(rid,)).fetchone())
    def private_room(self,u,peer):
        peer=int(peer);self.profile(peer);self.require(peer!=u,'不能给自己发私信')
        self.require(not self.row('SELECT 1 FROM blocks WHERE (user_id=? AND target=?) OR (user_id=? AND target=?)',(u,peer,peer,u)),'对方暂不接受消息')
        pair=':'.join(map(str,sorted([u,peer])))
        with self.tx() as c:
            c.execute("INSERT OR IGNORE INTO rooms(kind,name,pair) VALUES('private',?,?)",(self.profile(peer)['nickname'],pair))
            rid=c.execute('SELECT id FROM rooms WHERE pair=?',(pair,)).fetchone()[0]
            for uid in [u,peer]:c.execute('INSERT OR IGNORE INTO members(room_id,user_id) VALUES(?,?)',(rid,uid))
            c.execute('UPDATE members SET last_read_id=COALESCE((SELECT MAX(id) FROM messages WHERE room_id=?),0) WHERE room_id=? AND last_read_id=0',(rid,rid))
        return self.row('SELECT * FROM rooms WHERE id=?',(rid,))

    def support_room(self,u,ticket_id=None):
        """普通用户与平台客服的直达私聊。

        客服身份取「转角客服」昵称的平台账号（bootstrap_admin 与演示 seed
        都用这个昵称），不存在则退回任一客服/管理员。复用 private_room——
        聊天室已有的未读、禁言、审核、撤回全部免费继承，不必再造一套客服 IM。

        房间额外打 support=1 标记：客服工作台据此区分「客服会话」和普通私聊，
        认领机制（assignee）也只看这类房间，避免污染用户之间的私聊。

        **门槛（2026-10 修订）**：必须先提交过工单。原来是谁点「在线客服」
        谁就能进，结果它变成绕过工单的免费咨询窗口——小事闲聊把客服池占满，
        真正要售后的用户反而排不上。现在只放行「自己名下有未结案工单」的
        用户，并把会话关联到那张工单（rooms.ticket_id），客服点开就知道
        在聊哪件事，不用再问一遍。
        """
        tid=None
        if ticket_id:
            t=self.row('SELECT id FROM tickets WHERE id=? AND user_id=?',(int(ticket_id),u))
            self.require(t,'工单不存在或不属于你',404)
            tid=t['id']
        pending=self.row("SELECT id FROM tickets WHERE user_id=? AND status NOT IN ('resolved','rejected') ORDER BY id DESC LIMIT 1",(u,))
        self.require(pending,'请先提交问题，提交后即可联系在线客服')
        if not tid:tid=pending['id']
        staff=self.row("SELECT id FROM users WHERE nickname='转角客服' AND role IN ('admin','support','developer') LIMIT 1")
        if not staff:
            staff=self.row("SELECT id FROM users WHERE role IN ('support','admin','developer') ORDER BY (role='support') DESC, id LIMIT 1")
        self.require(staff and staff['id']!=u,'当前没有可用的在线客服，请改用「提交工单」留言')
        room=self.private_room(u,staff['id'])
        with self.tx() as c:c.execute('UPDATE rooms SET support=1,ticket_id=? WHERE id=?',(tid,room['id']))
        return self.row('SELECT * FROM rooms WHERE id=?',(room['id'],))

    def claim_support_room(self,u,rid,action='claim'):
        """客服认领 / 释放一个客服会话（防止多客服撞车）。

        assignee 同时只属于一个客服：未认领时谁先点就是谁的；已被别人
        认领时不再改派，把持有人返回给前端提示「已由 XX 认领」。认领即
        加入该会话（成为成员）——没有认领的客服在「客服池」里能看见
        这个会话，但要回复必须先认领，天然形成「谁认领谁处理」。"""
        self.staff(u)
        room=self.row('SELECT * FROM rooms WHERE id=?',(int(rid),))
        self.require(room and room['support'],'这不是客服会话',404)
        if action=='release':
            with self.tx() as c:c.execute('UPDATE rooms SET assignee=0 WHERE id=? AND assignee=?',(room['id'],u))
            return {'ok':True,'assignee':0,'assignee_name':''}
        if room['assignee'] and room['assignee']!=u:
            name=self.row('SELECT nickname FROM users WHERE id=?',(room['assignee'],))
            return {'ok':False,'assignee':room['assignee'],'assignee_name':name['nickname'] if name else ''}
        with self.tx() as c:
            if not room['assignee']:
                c.execute('UPDATE rooms SET assignee=? WHERE id=?',(u,room['id']))
            c.execute('INSERT OR IGNORE INTO members(room_id,user_id,role) VALUES(?,?,?)',(room['id'],u,'member'))
        return {'ok':True,'assignee':u,'assignee_name':self.profile(u)['nickname']}
    def member(self,u,r):
        m=self.row('SELECT * FROM members WHERE room_id=? AND user_id=?',(r,u))
        self.require(m is not None,'请先加入该群或会话',403);return m
    def messages(self,u,r,after=0):
        self.member(u,r)
        # removed 取值：0=正常 1=被管理员移除 2=发送者撤回。
        # 移除的消息正文就地替换成提示语；撤回的正文清空（原文不能留在接口里），
        # 前端按 removed 和 user_id 渲染「你/xxx 撤回了一条消息」。
        # 首次拉取（after=0）返回最近 200 条——聊天窗打开时应该看到最新消息，
        # 而不是从建群第一条开始翻；增量拉取保持 id>after 升序。
        sql='''SELECT m.id,m.room_id,m.user_id,m.removed,
                      CASE WHEN m.removed=1 THEN '消息已被移除' WHEN m.removed=2 THEN '' ELSE m.body END body,
                      m.created,u.nickname
               FROM messages m JOIN users u ON u.id=m.user_id WHERE {{cond}}
               ORDER BY m.id {{order}} LIMIT {{limit}}'''
        # 「仅自己删除」不进 removed：removed 是「对所有人撤回/移除」，
        # 删除只影响本人，用 message_hides 过滤即可。两个分支都要带这个条件，
        # 否则删掉的消息会在下一次轮询或刷新时又冒出来。
        hidden='AND NOT EXISTS(SELECT 1 FROM message_hides h WHERE h.message_id=m.id AND h.user_id=?)'
        if after>0:
            rows=self.rows(sql.replace('{{cond}}','m.room_id=? AND m.id>? '+hidden).replace('{{order}}','ASC').replace('{{limit}}','200'),(r,int(after),u))
        else:
            rows=self.rows('''SELECT * FROM (SELECT m.id,m.room_id,m.user_id,m.removed,
                CASE WHEN m.removed=1 THEN '消息已被移除' WHEN m.removed=2 THEN '' ELSE m.body END body,
                m.created,u.nickname FROM messages m JOIN users u ON u.id=m.user_id
                WHERE m.room_id=? '''+hidden+''' ORDER BY m.id DESC LIMIT 200) ORDER BY id ASC''',(r,u))
        # 拉取即视为读到：把已读位点拨到这批消息的最大 id。轮询每 3 秒一次，
        # 但只有真的拉到新消息才会产生一次写事务，量可以忽略。
        if rows:
            with self.tx() as c:self._mark_room_read(c,r,u,rows[-1]['id'])
        return rows

    # --- 消息撤回 ----------------------------------------------------------
    # 只允许撤回自己 2 分钟内的消息，且没被移除过。撤回是软删（removed=2）：
    # 正文清掉，但记录保留——审核和工作台还需要知道「这里曾经有一条消息」。
    def recall_message(self,u,mid):
        m=self.row('SELECT * FROM messages WHERE id=?',(int(mid),))
        self.require(m,'消息不存在',404)
        self.require(m['user_id']==u,'只能撤回自己发送的消息',403)
        self.require(m['removed']==0,'该消息已不可撤回')
        self.require(time.time()-m['created']<=120,'超过两分钟的消息不能撤回了')
        with self.tx() as c:c.execute('UPDATE messages SET removed=2 WHERE id=?',(m['id'],))
        return {'ok':True}

    # --- 仅自己删除 --------------------------------------------------------
    # 聊天里的「删除」和「撤回」是两件事：撤回让所有人都看不到（限 2 分钟），
    # 删除只把自己聊天记录里的这条抹掉，对方不受影响。因此这里写
    # message_hides 而不是改 messages.removed——后者会把消息变成
    # 「已撤回」展示给所有人看。
    def hide_message(self,u,mid):
        m=self.row('SELECT id,room_id FROM messages WHERE id=?',(int(mid),))
        self.require(m,'消息不存在',404)
        self.member(u,m['room_id'])
        with self.tx() as c:
            c.execute('INSERT OR IGNORE INTO message_hides(user_id,message_id,created) VALUES(?,?,?)',(u,m['id'],time.time()))
        return {'ok':True}

    # --- 会话成员 ----------------------------------------------------------
    # 群聊右侧成员抽屉的数据源：昵称、角色（群主/管理员/成员）、禁言状态。
    # 私聊也走这个接口，前端按 kind 决定渲染成员列表还是对方资料。
    def room_members(self,u,r):
        self.member(u,r)
        room=self.row('SELECT * FROM rooms WHERE id=?',(r,))
        members=self.rows('''SELECT m.user_id,m.role,m.muted,u.nickname,u.college
            FROM members m JOIN users u ON u.id=m.user_id WHERE m.room_id=?
            ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'moderator' THEN 1 ELSE 2 END,m.user_id''',(r,))
        return {'room':{'id':room['id'],'name':room['name'],'kind':room['kind'],'pair':room['pair']},
                'members':members}
    def send_message(self,u,r,body,key):
        member=self.member(u,r);self.require(not member['muted'],'你在该群已被禁言',403)
        body=self.text(body,2000,'消息');self.require(1<=len(str(key))<=100,'缺少消息标识')
        room=self.row('SELECT * FROM rooms WHERE id=?',(r,))
        private=room['kind']=='private'
        if private:
            peer=self.row('SELECT user_id FROM members WHERE room_id=? AND user_id<>?',(r,u))['user_id']
            self.require(not self.row('SELECT 1 FROM blocks WHERE (user_id=? AND target=?) OR (user_id=? AND target=?)',(u,peer,peer,u)),'该会话已被屏蔽',403)
        # 聊天是反引流的主战场之一：群里一句「加微信」能带走一整群的人。
        # 私聊用另一套尺度——联系方式放行，站外平台/站外收款/违禁品照拦，
        # 理由见 moderation.scan_private() 的注释。
        report=(scan_private if private else scan_text)(body)
        self.require(not report['blocked'],'消息不能发送：'+message_for(report),422)
        mark=flag_of(report)
        with self.tx() as c:
            c.execute('INSERT OR IGNORE INTO messages(room_id,user_id,body,created,request_key,moderation) VALUES(?,?,?,?,?,?)',
                      (r,u,body,time.time(),key,json.dumps(mark,ensure_ascii=False) if mark else None))
        return {'ok':True,'moderation':mark}
    def block(self,u,target,enabled):
        self.require(u!=int(target),'不能屏蔽自己')
        with self.tx() as c:
            if enabled:c.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(u,int(target)))
            else:c.execute('DELETE FROM blocks WHERE user_id=? AND target=?',(u,int(target)))
        return {'ok':True}
    def posts(self,topic='',limit=20,offset=0):
        # 分页：前端「加载更多」按 limit 递增 offset 取更早的帖子。
        # 老实现 LIMIT 100 无分页，第 101 条帖子起永远翻不到。
        limit=max(1,min(int(limit or 20),50));offset=max(0,int(offset or 0))
        return self.rows('SELECT p.*,u.nickname,u.college,(SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) replies FROM posts p JOIN users u ON u.id=p.user_id WHERE p.removed=0 AND (?=\'\' OR topic=?) ORDER BY p.id DESC LIMIT ? OFFSET ?',(topic,topic,limit,offset))
    def add_post(self,u,d):
        body=self.text(d.get('body'),2000,'帖子内容');topic=d.get('topic','交流')
        self.require(topic in ['交流','求购','毕业季','互助'],'分区不正确')
        # 帖子是公开的引流入口，尺度按最严的来：联系方式也算高危。
        report=scan_text(body)
        self.require(not report['blocked'],'帖子不能发布：'+message_for(report),422)
        mark=flag_of(report)
        with self.tx() as c:
            pid=c.execute('INSERT INTO posts(user_id,topic,body,created,moderation) VALUES(?,?,?,?,?)',
                                          (u,topic,body,time.time(),json.dumps(mark,ensure_ascii=False) if mark else None)).lastrowid
            self._notify_mentions(c,u,self.profile(u)['nickname'],body,pid)
        return {'id':pid,'moderation':mark}

    def comments(self,p,before=None):
        # 取「最新」评论：老实现 ORDER BY c.id LIMIT 100 是升序取最旧 100 条，
        # 一条超过 100 条评论的帖子，最新回复（含用户刚发的）反而看不到。
        # 这里 DESC 取最新 100 条再倒序返回，保证最新评论一定可见；
        # before 游标用于「加载更早评论」。
        # 每条评论带 parent 关系：parent_id=0 为直接评论帖子，>0 时把父评论作者
        # 一并带出（parent_user_id/parent_nickname），前端据此渲染「谁回复谁」。
        limit=100
        base='''SELECT c.*,u.nickname,
            pc.user_id AS parent_user_id, pu.nickname AS parent_nickname
            FROM comments c JOIN users u ON u.id=c.user_id
            LEFT JOIN comments pc ON pc.id=c.parent_id
            LEFT JOIN users pu ON pu.id=pc.user_id
            WHERE c.post_id=?'''
        if before:
            rows=self.rows(base+' AND c.id<? ORDER BY c.id DESC LIMIT ?',(p,int(before),limit))
        else:
            rows=self.rows(base+' ORDER BY c.id DESC LIMIT ?',(p,limit))
        rows.reverse()
        return rows

    def comment(self,u,p,body,parent_id=0):
        post=self.row('SELECT p.*,u.nickname author FROM posts p JOIN users u ON u.id=p.user_id WHERE p.id=? AND p.removed=0',(p,))
        self.require(post is not None,'帖子不存在',404)
        body=self.text(body,1000,'回复')
        parent_id=int(parent_id or 0)
        parent=None
        if parent_id:
            # 只允许回复同一帖子下的评论，防止把别帖的评论挂过来制造乱序。
            parent=self.row('SELECT * FROM comments WHERE id=? AND post_id=?',(parent_id,p))
            self.require(parent is not None,'要回复的评论不存在',404)
        # 评论不落审核标记（没有「待审」这个环节，只有删），但高危照样拦。
        report=scan_text(body)
        self.require(not report['blocked'],'回复不能发布：'+message_for(report),422)
        with self.tx() as c:
            c.execute('INSERT INTO comments(post_id,user_id,body,created,parent_id) VALUES(?,?,?,?,?)',(p,u,body,time.time(),parent_id))
            me=self.profile(u)['nickname']
            # 帖子作者的通知：正文摘要截到 24 字，通知列表一行能放下。
            excerpt=post['body'][:24]+('…' if len(post['body'])>24 else '')
            notified={post['user_id']}
            if post['user_id']!=u:
                self.notify(c,post['user_id'],'post_reply',f'{me} 回复了你的帖子「{excerpt}」',post_id=p)
            # 回复某条评论时，被回复的评论作者也要收到通知（除非他本人就是帖子作者/自己）。
            if parent and parent['user_id']!=u and parent['user_id'] not in notified:
                notified.add(parent['user_id'])
                self.notify(c,parent['user_id'],'post_reply',f'{me} 回复了你在帖子「{excerpt}」中的评论',post_id=p)
            # @到的其他人单独通知；已通知过的作者跳过，避免双份。
            self._notify_mentions(c,u,me,body,p,skip=notified)
        return {'ok':True}
    def moderate(self,u,d):
        r=int(d['room_id']);member=self.member(u,r)
        self.require(member['role'] in ['owner','moderator'] or self.is_admin(u),'没有群管理权限',403)
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

    # --- 内容治理（工作台） ----------------------------------------------
    def flagged_content(self,u,limit=200):
        """自动审核打标的聊天消息与帖子。

        只有 review / report 级别会出现在这里——block 级别的根本没能入库，
        没有可处置的对象。这就是「拦截」与「送审」的分界：
        拦截是当场拒绝，送审是先放出去、再让人来判断。
        """
        self.staff(u);limit=max(1,min(int(limit or 200),500))
        messages=self.rows(
            """SELECT m.id,m.room_id,m.user_id,m.body,m.created,m.moderation,m.removed,
                      u.nickname,r.name room_name,r.kind room_kind
               FROM messages m JOIN users u ON u.id=m.user_id JOIN rooms r ON r.id=m.room_id
               WHERE m.moderation IS NOT NULL ORDER BY m.id DESC LIMIT ?""",(limit,))
        posts=self.rows(
            """SELECT p.id,p.user_id,p.topic,p.body,p.created,p.moderation,p.removed,u.nickname
               FROM posts p JOIN users u ON u.id=p.user_id
               WHERE p.moderation IS NOT NULL ORDER BY p.id DESC LIMIT ?""",(limit,))
        for item in messages+posts:
            try:item['moderation']=json.loads(item['moderation']) if item['moderation'] else None
            except (TypeError,ValueError):item['moderation']=None
        return {'messages':messages,'posts':posts}

    def content_action(self,u,kind,cid,action,reason):
        """移除 / 恢复一条被打标的聊天消息或帖子。

        移除以「软删除」实现（removed=1）：正文留着，用户侧显示「已被移除」，
        这样当事人申诉、或后来发现判错时还能还原，而不是数据已经没了。
        """
        self.staff(u)
        self.require(kind in ('message','post'),'内容类型无效')
        self.require(action in ('remove','restore'),'操作无效')
        reason=self.text(reason,500,'处置理由')
        table='messages' if kind=='message' else 'posts'
        row=self.row(f'SELECT id,user_id FROM {table} WHERE id=?',(int(cid),))
        self.require(row,f'{"消息" if kind=="message" else "帖子"}不存在',404)
        self.require(row['user_id']!=u,'不能处置自己发布的内容')
        label='聊天消息' if kind=='message' else '社区帖子'
        with self.tx() as c:
            c.execute(f'UPDATE {table} SET removed=? WHERE id=?',(1 if action=='remove' else 0,int(cid)))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u,row['user_id'],'content_'+action,f'{label} #{cid}：{reason}',time.time()))
            if action=='remove':
                self.notify(c,row['user_id'],'content_removed',
                            f'你发布的一条{label}因「{reason}」已被移除。如有异议可在客服中心申诉。')
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
