"""Asynchronous community contracts backed by atomic D1 batches."""
import json
import re
import time
from ..core.errors import ValidationMixin, DomainError
from ..moderation import flag_of, message_for, PRIVATE_ALLOWED, _rebuild
from .http import json_response, json_body, query_of, int_param, require
from . import sessions

STAFF=('admin','support','developer')

class CommunityApi:
    async def cf_community_scan(self,body,private=False):
        report=(await self.cf_rules()).scan(body)
        if private: report=_rebuild([h for h in report['hits'] if h['category'] not in PRIVATE_ALLOWED])
        require(not report['blocked'],'内容不能发布：'+message_for(report),422)
        mark=flag_of(report)
        return mark,json.dumps(mark,ensure_ascii=False) if mark else None

    async def cf_community_member(self,uid,rid):
        member=await self.db.first('SELECT * FROM members WHERE user_id=? AND room_id=?',(uid,rid))
        require(member,'请先加入该群或会话',403)
        room=await self.db.first('SELECT * FROM rooms WHERE id=?',(rid,));require(room,'会话不存在',404)
        if room['support'] and await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,)) in STAFF:
            require(room['assignee']==uid,'请先认领该客服会话',403)
        return member,room

    async def cf_community_mentions(self,uid,body,pid,skip=()):
        nickname=await self.db.scalar('SELECT nickname FROM users WHERE id=?',(uid,))
        statements=[];notified=set(skip)|{uid};count=0
        for name in dict.fromkeys(re.findall(r'@([^\s@，。！？!?,.：:；;~]{1,24})',body)):
            for target in await self.db.all('SELECT id FROM users WHERE nickname=?',(name,)):
                if target['id'] not in notified:
                    notified.add(target['id']);count+=1
                    statements.append(('INSERT INTO notifications(user_id,kind,post_id,body,created) VALUES(?,?,?,?,?)',(target['id'],'mention',pid,f'{nickname} 在帖子中提到了你',time.time())))
                    if count>=10:return statements
        return statements

    async def cf_community_posts(self,r):
        if r.method=='GET':
            from ..community.forum_read import posts_query
            q=query_of(r)
            for key in ('id','author','limit','offset'):
                if key in q:int_param(q,key)
            sql,args=posts_query(q.get('topic',''),q.get('limit',20),q.get('offset',0),q)
            return json_response(await self.db.all(sql,args))
        uid=await self.page_user(r);await self.require_capacity();d=await json_body(r)
        body=ValidationMixin.text(d.get('body'),2000,'帖子内容');topic=d.get('topic','交流');require(topic in ('交流','求购','毕业季','互助','交换人生','代拿快递'),'分区不正确')
        mark,stored=await self.cf_community_scan(body)
        for attempt in range(4):
            pid=await self.db.scalar('SELECT COALESCE(MAX(id),0)+1 FROM posts')
            statements=[('INSERT INTO posts(id,user_id,topic,body,created,moderation) VALUES(?,?,?,?,?,?)',(pid,uid,topic,body,time.time(),stored))]+await self.cf_community_mentions(uid,body,pid)
            try:
                await self.db.guarded_batch('SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM posts WHERE id=?)',(pid,),statements);break
            except DomainError:
                if attempt==3:raise
        return json_response({'id':pid,'moderation':mark})

    async def cf_community_comments(self,r):
        if r.method=='GET':
            q=query_of(r);pid=int_param(q,'id');before=int_param(q,'before',False)
            require(await self.db.first('SELECT 1 FROM posts WHERE id=? AND removed=0',(pid,)),'帖子不存在或已被删除',404)
            limit=max(1,min(int_param(q,'limit',False) or 100,100))
            sql='SELECT c.*,u.nickname,pc.user_id parent_user_id,pu.nickname parent_nickname FROM comments c JOIN users u ON u.id=c.user_id LEFT JOIN comments pc ON pc.id=c.parent_id LEFT JOIN users pu ON pu.id=pc.user_id WHERE c.post_id=?';args=(pid,)
            if q.get('order')=='asc':
                after=int_param(q,'after',False) or 0
                return json_response(await self.db.all(sql+' AND c.id>? ORDER BY c.id ASC LIMIT ?',args+(after,limit)))
            if before:sql+=' AND c.id<?';args+=(before,)
            rows=await self.db.all(sql+' ORDER BY c.id DESC LIMIT ?',args+(limit,));rows.reverse();return json_response(rows)
        uid=await self.page_user(r);d=await json_body(r);pid=int_param(d,'post_id');parent_id=int_param(d,'parent_id',False) or 0
        post=await self.db.first('SELECT * FROM posts WHERE id=? AND removed=0',(pid,));require(post,'帖子不存在',404)
        parent=await self.db.first('SELECT * FROM comments WHERE id=? AND post_id=?',(parent_id,pid)) if parent_id else None
        require(not parent_id or parent,'要回复的评论不存在',404)
        body=ValidationMixin.text(d.get('body'),1000,'回复');await self.cf_community_scan(body);await self.require_capacity()
        name=await self.db.scalar('SELECT nickname FROM users WHERE id=?',(uid,));excerpt=post['body'][:24]+('…' if len(post['body'])>24 else '')
        statements=[('INSERT INTO comments(post_id,user_id,body,created,parent_id) VALUES(?,?,?,?,?)',(pid,uid,body,time.time(),parent_id))];notified={uid}
        notifications=[(post['user_id'],f'{name} 回复了你的帖子「{excerpt}」')]
        if parent:notifications.append((parent['user_id'],f'{name} 回复了你在帖子「{excerpt}」中的评论'))
        for target,text in notifications:
            if target not in notified:
                notified.add(target);statements.append(('INSERT INTO notifications(user_id,kind,post_id,body,created) VALUES(?,?,?,?,?)',(target,'post_reply',pid,text,time.time())))
        statements+=await self.cf_community_mentions(uid,body,pid,notified)
        await self.db.guarded_batch('SELECT 1 FROM posts WHERE id=? AND removed=0 AND (?=0 OR EXISTS(SELECT 1 FROM comments WHERE id=? AND post_id=?))',(pid,parent_id,parent_id,pid),statements)
        return json_response({'ok':True})

    async def _decorate_room(self,row,uid):
        """补 unread / pinned / peer_id / blocked，私聊和客服房都要算。"""
        row['unread']=min(99,await self.db.scalar('SELECT COUNT(*) FROM messages m WHERE room_id=? AND id>? AND user_id<>? AND removed=0 AND NOT EXISTS(SELECT 1 FROM message_hides WHERE message_id=m.id AND user_id=?)',(row['id'],row['last_read_id'] or 0,uid,uid)))
        row['pinned']=bool(row.get('pinned_at'))
        if row['kind']=='private':
            name=await self.db.scalar('SELECT u.nickname FROM members m JOIN users u ON u.id=m.user_id WHERE room_id=? AND user_id<>? LIMIT 1',(row['id'],uid))
            if name:row['name']=name
            # 私聊才计算 peer_id / blocked；群聊固定 false。
            pair=row.get('pair') or ''
            a,b=pair.split(':') if ':' in pair else ('','')
            try:peer=int(a) if int(a)!=uid else int(b)
            except ValueError:peer=0
            row['peer_id']=peer
            row['blocked']=bool(peer and await self.db.first('SELECT 1 FROM blocks WHERE user_id=? AND target=?',(uid,peer)))
        else:
            row['peer_id']=0
            row['blocked']=False

    async def cf_community_rooms(self,r):
        uid=await self.page_user(r)
        role=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,))
        is_staff=role in STAFF
        columns='''r.*,(SELECT COUNT(*) FROM members WHERE room_id=r.id) count,
        (SELECT body FROM messages x WHERE room_id=r.id AND removed=0 AND NOT EXISTS(SELECT 1 FROM message_hides WHERE user_id=? AND message_id=x.id) ORDER BY id DESC LIMIT 1) last_body,
        (SELECT created FROM messages WHERE room_id=r.id ORDER BY id DESC LIMIT 1) last_at,
        (SELECT u.nickname FROM messages x JOIN users u ON u.id=x.user_id WHERE room_id=r.id ORDER BY x.id DESC LIMIT 1) last_nick,
        (SELECT nickname FROM users WHERE id=r.assignee) assignee_name,
        (SELECT pinned_at FROM room_pins WHERE user_id=? AND room_id=r.id) pinned_at'''
        # 普通用户：客服会话不进聊天列表（避免「发完问题还在聊天框」），
        # 改走「在线客服 / 我的客服」入口；客服/管理员仍需在接待台看，保留。
        support_clause="AND r.support=0" if not is_staff else "AND NOT (r.support=1 AND COALESCE(r.support_status,'open')='closed')"
        rows=await self.db.all("SELECT "+columns+",m.role,m.muted,m.last_read_id FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=? "+support_clause,(uid,uid,uid))
        for row in rows:
            await self._decorate_room(row,uid)
        if is_staff:
            have={row['id'] for row in rows}
            for row in await self.db.all('SELECT '+columns+" FROM rooms r WHERE support=1 AND COALESCE(support_status,'open')='open' ORDER BY id",(uid,uid)):
                if row['id'] not in have:row.update(role='member',muted=0,last_read_id=0,unread=0,via_pool=True,pinned=False,pinned_at=0,blocked=False,peer_id=0);rows.append(row)
        # 用户的在聊客服会话：列表里不显示，但聊天窗/入口要靠它恢复与提示未读。
        my_support=None
        if not is_staff:
            ms=await self.db.first("SELECT "+columns+",m.role,m.muted,m.last_read_id FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=? AND r.support=1 AND COALESCE(r.support_status,'open')='open' ORDER BY r.id DESC LIMIT 1",(uid,uid,uid))
            if ms:await self._decorate_room(ms,uid);my_support=ms
        return json_response({'joined':rows,'my_support':my_support,'general':await self.db.first('SELECT r.*,(SELECT COUNT(*) FROM members WHERE room_id=r.id) count FROM rooms r WHERE id=1'),'college':await self.db.scalar('SELECT college FROM users WHERE id=?',(uid,))})

    async def cf_pin_room(self,r):
        """置顶 / 取消置顶：只动当前用户这一行 room_pins。"""
        uid=await self.page_user(r);d=await json_body(r);rid=int_param(d,'room_id');pinned=bool(d.get('pinned',True))
        _,room=await self.cf_community_member(uid,rid)
        if pinned:await self.db.run('INSERT OR REPLACE INTO room_pins(user_id,room_id,pinned_at) VALUES(?,?,?)',(uid,rid,time.time()))
        else:await self.db.run('DELETE FROM room_pins WHERE user_id=? AND room_id=?',(uid,rid))
        return json_response({'ok':True,'pinned':pinned})

    async def cf_clear_room(self,r):
        """删除当前用户在该房间的所有可见消息：往 message_hides 写入，库里正文不动。"""
        uid=await self.page_user(r);d=await json_body(r);rid=int_param(d,'room_id')
        _,room=await self.cf_community_member(uid,rid)
        now=time.time()
        # D1 同样支持带 SELECT 子查询的 INSERT，与 SQLite 行为一致。
        await self.db.run('INSERT OR IGNORE INTO message_hides(user_id,message_id,created) '+
                          "SELECT ?,m.id,? FROM messages m WHERE m.room_id=? AND m.removed<>3 AND NOT EXISTS(SELECT 1 FROM message_hides h WHERE h.user_id=? AND h.message_id=m.id)",
                          (uid,now,rid,uid))
        await self.db.run('UPDATE members SET last_read_id=COALESCE((SELECT MAX(id) FROM messages WHERE room_id=?),0) WHERE room_id=? AND user_id=?',(rid,rid,uid))
        return json_response({'ok':True})

    async def cf_community_join(self,r):
        uid=await self.page_user(r);d=await json_body(r);kind=d.get('kind');require(kind in ('general','college'),'群类型不正确');await self.require_capacity()
        college=await self.db.scalar('SELECT college FROM users WHERE id=?',(uid,)) or '计算机工程学院'
        for attempt in range(5):
            existing=await self.db.first("SELECT r.* FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=? AND r.kind=? AND (?='general' OR college=?)",(uid,kind,kind,college))
            if existing:return json_response(existing)
            room=await self.db.first('SELECT * FROM rooms WHERE id=1') if kind=='general' else await self.db.first("SELECT r.* FROM rooms r WHERE kind='college' AND college=? AND (SELECT COUNT(*) FROM members WHERE room_id=r.id)<500 ORDER BY sequence,id LIMIT 1",(college,))
            statements=[]
            # Include the absence of another joined college room inside the transaction.
            absent=" AND NOT EXISTS(SELECT 1 FROM rooms r JOIN members m ON r.id=m.room_id WHERE r.kind='college' AND r.college=? AND m.user_id=?)" if kind=='college' else ''
            if room:
                rid=room['id'];guard='SELECT 1 FROM rooms WHERE id=? AND (SELECT COUNT(*) FROM members WHERE room_id=?)<500'+absent;params=(rid,rid)+((college,uid) if absent else ());role='member'
            else:
                require(kind!='general','总聊不存在',404)
                rid=await self.db.scalar('SELECT COALESCE(MAX(id),0)+1 FROM rooms');seq=await self.db.scalar("SELECT COALESCE(MAX(sequence),0)+1 FROM rooms WHERE kind='college' AND college=?",(college,))
                guard="SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM rooms WHERE id=?) AND NOT EXISTS(SELECT 1 FROM rooms WHERE kind='college' AND college=? AND sequence=?)"+absent;params=(rid,college,seq,college,uid);role='owner'
                statements.append(("INSERT INTO rooms(id,kind,name,college,sequence) VALUES(?,'college',?,?,?)",(rid,f'{college}交流{seq}群',college,seq)))
            statements.append(('INSERT OR IGNORE INTO members(room_id,user_id,role,last_read_id) VALUES(?,?,?,COALESCE((SELECT MAX(id) FROM messages WHERE room_id=?),0))',(rid,uid,role,rid)))
            try:
                await self.db.guarded_batch(guard,params,statements);return json_response(await self.db.first('SELECT * FROM rooms WHERE id=?',(rid,)))
            except DomainError:
                if kind=='general':require(False,'总聊已满，请加入学院群',409)
                if attempt==4:raise

    async def cf_community_private_for(self,uid,peer):
        require(peer!=uid,'不能给自己发私信');other=await self.db.first("SELECT * FROM users WHERE id=? AND status='active'",(peer,));require(other,'用户不存在',404)
        pair=':'.join(map(str,sorted((uid,peer))))
        guard='SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM blocks WHERE (user_id=? AND target=?) OR (user_id=? AND target=?))'
        await self.db.guarded_batch(guard,(uid,peer,peer,uid),[("INSERT OR IGNORE INTO rooms(kind,name,pair) VALUES('private',?,?)",(other['nickname'],pair)),('INSERT OR IGNORE INTO members(room_id,user_id,last_read_id) SELECT id,?,COALESCE((SELECT MAX(id) FROM messages WHERE room_id=rooms.id),0) FROM rooms WHERE pair=?',(uid,pair)),('INSERT OR IGNORE INTO members(room_id,user_id,last_read_id) SELECT id,?,COALESCE((SELECT MAX(id) FROM messages WHERE room_id=rooms.id),0) FROM rooms WHERE pair=?',(peer,pair))],message='对方暂不接受消息')
        return await self.db.first('SELECT * FROM rooms WHERE pair=?',(pair,))

    async def cf_community_private(self,r):
        uid=await self.page_user(r);d=await json_body(r);await self.require_capacity();return json_response(await self.cf_community_private_for(uid,int_param(d,'peer')))

    async def cf_community_support_room(self,r):
        uid=await self.page_user(r);d=await json_body(r);tid=int_param(d,'ticket_id',False)
        if tid:require(await self.db.first('SELECT id FROM tickets WHERE id=? AND user_id=?',(tid,uid)),'工单不存在或不属于你',404)
        pending=await self.db.scalar("SELECT id FROM tickets WHERE user_id=? AND status NOT IN ('resolved','rejected') ORDER BY id DESC LIMIT 1",(uid,));require(pending,'请先提交问题，提交后即可联系在线客服')
        peer=await self.db.scalar("SELECT id FROM users WHERE status='active' AND role IN ('admin','support','developer') ORDER BY (nickname='转角客服') DESC,(role='support') DESC,id LIMIT 1")
        require(peer and peer!=uid,'当前没有可用的在线客服，请改用「提交工单」留言');await self.require_capacity()
        room=await self.cf_community_private_for(uid,peer)
        guard="SELECT 1 FROM tickets WHERE user_id=? AND status NOT IN ('resolved','rejected')"
        stmts=[]
        if room['support'] and (room.get('support_status') or 'open')=='closed':
            stmts += [('UPDATE messages SET removed=3 WHERE room_id=? AND removed IN (0,1)',(room['id'],)),
                      ("UPDATE rooms SET support=1,ticket_id=?,support_status='open',support_closed_at=0,support_closed_by='',assignee=0 WHERE id=?",(tid or pending,room['id'])),
                      ('UPDATE members SET last_read_id=0 WHERE room_id=?',(room['id'],))]
        else:
            stmts.append(('UPDATE rooms SET support=1,ticket_id=? WHERE id=?',(tid or pending,room['id'])))
        await self.db.guarded_batch(guard,(uid,),stmts)
        return json_response(await self.db.first('SELECT * FROM rooms WHERE id=?',(room['id'],)))

    async def cf_support_close(self,r):
        """用户或客服结束当前咨询：归档消息并关闭会话，双方列表都不再显示。"""
        uid=await self.page_user(r);d=await json_body(r);rid=int_param(d,'room_id')
        room=await self.db.first('SELECT * FROM rooms WHERE id=? AND support=1',(rid,));require(room,'这不是客服会话',404)
        role=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,))
        party=await self.db.first('SELECT 1 FROM members WHERE room_id=? AND user_id=?',(rid,uid))
        require(party or role in STAFF,'无权结束该会话',403)
        by='agent' if role in STAFF else 'customer'
        try:
            await self.db.guarded_batch("SELECT 1 FROM rooms WHERE id=? AND support=1 AND COALESCE(support_status,'open')='open'",(rid,),
                [("UPDATE rooms SET support_status='closed',support_closed_at=?,support_closed_by=?,assignee=0 WHERE id=?",(time.time(),by,rid)),
                 ('UPDATE messages SET removed=3 WHERE room_id=? AND removed IN (0,1)',(rid,))])
        except DomainError:
            pass
        return json_response({'ok':True})

    async def cf_support_sessions(self,r):
        """客服接待台：进行中的客服会话，待接入优先、等待久的排前。"""
        await self.page_user(r,staff=True);now=time.time()
        rows=await self.db.all('''SELECT r.id,r.ticket_id,r.assignee,t.subject,t.type,t.status ticket_status,a.nickname assignee_name,
            (SELECT cu.id FROM members rm JOIN users cu ON cu.id=rm.user_id WHERE rm.room_id=r.id AND cu.role='user' LIMIT 1) customer_id,
            (SELECT cu.nickname FROM members rm JOIN users cu ON cu.id=rm.user_id WHERE rm.room_id=r.id AND cu.role='user' LIMIT 1) customer_name,
            (SELECT COUNT(*) FROM messages m WHERE m.room_id=r.id AND m.removed=0) total_messages,
            (SELECT CASE WHEN x.removed=2 THEN '' ELSE x.body END FROM messages x WHERE x.room_id=r.id AND x.removed=0 ORDER BY x.id DESC LIMIT 1) last_body,
            (SELECT x.created FROM messages x WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_at,
            (SELECT MAX(x.created) FROM messages x JOIN users xu ON xu.id=x.user_id WHERE x.room_id=r.id AND x.removed=0 AND xu.role='user') last_customer_at,
            (SELECT xu.nickname FROM messages x JOIN users xu ON xu.id=x.user_id WHERE x.room_id=r.id ORDER BY x.id DESC LIMIT 1) last_nick
            FROM rooms r LEFT JOIN tickets t ON t.id=r.ticket_id LEFT JOIN users a ON a.id=r.assignee
            WHERE r.support=1 AND COALESCE(r.support_status,'open')='open'
            ORDER BY (r.assignee=0) DESC, COALESCE((SELECT MAX(x.created) FROM messages x WHERE x.room_id=r.id),0) ASC''')
        for row in rows:
            lc=row['last_customer_at'] or 0;la=row['last_at'] or 0
            row['waiting']=max(0,int(now-lc)) if lc and lc>=la else 0
            row['online_hint']='等待接入' if not row['assignee'] else '由 '+(row['assignee_name'] or '客服')+' 接待'
        return json_response(rows)

    async def cf_community_claim(self,r):
        uid=await self.page_user(r,staff=True);d=await json_body(r);rid=int_param(d,'room_id');action=d.get('action','claim');require(action in ('claim','release'),'操作无效')
        room=await self.db.first('SELECT * FROM rooms WHERE id=? AND support=1',(rid,));require(room,'这不是客服会话',404)
        if action=='release':
            await self.db.run('UPDATE rooms SET assignee=0 WHERE id=? AND assignee=?',(rid,uid));assigned=await self.db.scalar('SELECT assignee FROM rooms WHERE id=?',(rid,));return json_response({'ok':True,'assignee':assigned,'assignee_name':await self.db.scalar('SELECT nickname FROM users WHERE id=?',(assigned,)) or ''})
        try:
            await self.db.guarded_batch('SELECT 1 FROM rooms WHERE id=? AND support=1 AND (assignee=0 OR assignee=?)',(rid,uid),[('UPDATE rooms SET assignee=? WHERE id=?',(uid,rid)),('INSERT OR IGNORE INTO members(room_id,user_id) VALUES(?,?)',(rid,uid))])
        except DomainError:
            assigned=await self.db.scalar('SELECT assignee FROM rooms WHERE id=?',(rid,));return json_response({'ok':False,'assignee':assigned,'assignee_name':await self.db.scalar('SELECT nickname FROM users WHERE id=?',(assigned,)) or ''})
        return json_response({'ok':True,'assignee':uid,'assignee_name':await self.db.scalar('SELECT nickname FROM users WHERE id=?',(uid,))})

    async def cf_community_messages(self,r):
        uid=await self.page_user(r)
        if r.method=='GET':
            q=query_of(r);rid=int_param(q,'room_id');after=int_param(q,'after',False) or 0;await self.cf_community_member(uid,rid)
            base="SELECT m.id,m.room_id,m.user_id,m.removed,CASE WHEN m.removed=1 THEN '消息已被移除' WHEN m.removed=2 THEN '' ELSE m.body END body,m.created,u.nickname FROM messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND m.removed<>3 AND NOT EXISTS(SELECT 1 FROM message_hides WHERE message_id=m.id AND user_id=?)"
            rows=await self.db.all(base+' AND m.id>? ORDER BY m.id ASC LIMIT 200',(rid,uid,after)) if after>0 else await self.db.all('SELECT * FROM ('+base+' ORDER BY m.id DESC LIMIT 200) ORDER BY id ASC',(rid,uid))
            if rows:await self.db.run('UPDATE members SET last_read_id=MAX(last_read_id,?) WHERE room_id=? AND user_id=?',(rows[-1]['id'],rid,uid))
            return json_response(rows)
        d=await json_body(r);rid=int_param(d,'room_id');member,room=await self.cf_community_member(uid,rid);require(not member['muted'],'你在该群已被禁言',403)
        body=ValidationMixin.text(d.get('body'),2000,'消息');key=d.get('key');require(isinstance(key,str) and 1<=len(key)<=100,'缺少消息标识')
        private=room['kind']=='private'
        if private and not room['support']:
            # 好友门禁：同意好友申请之前，私聊发不出去（对方仍可读历史）。
            # 客服会话（转角客服）不在此列——顾客/客服无需互为好友即可沟通，
            # 否则双方都发不出消息，客服功能直接不可用。
            peer=await self.db.first('SELECT user_id FROM members WHERE room_id=? AND user_id<>? LIMIT 1',(rid,uid))
            require(peer and await self.cf_is_friend(uid,peer['user_id']),'先加对方为好友才能聊天',403)
        if private and not room['support']:require(not await self.db.first('SELECT 1 FROM blocks b JOIN members p ON p.room_id=? AND p.user_id<>? WHERE (b.user_id=? AND b.target=p.user_id) OR (b.user_id=p.user_id AND b.target=?)',(rid,uid,uid,uid)),'该会话已被屏蔽',403)
        mark,stored=await self.cf_community_scan(body,private);await self.require_capacity()
        guard="""SELECT 1 FROM members m JOIN rooms r ON r.id=m.room_id JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND m.user_id=? AND m.muted=0 AND u.status='active' AND (r.support=0 OR u.role NOT IN ('admin','support','developer') OR r.assignee=u.id) AND (r.kind<>'private' OR NOT EXISTS(SELECT 1 FROM blocks b JOIN members p ON p.room_id=r.id AND p.user_id<>u.id WHERE (b.user_id=u.id AND b.target=p.user_id) OR (b.user_id=p.user_id AND b.target=u.id)))"""
        stmts=[]
        if room['support'] and (room.get('support_status') or 'open')=='closed':
            stmts += [('UPDATE messages SET removed=3 WHERE room_id=? AND removed IN (0,1)',(rid,)),
                      ("UPDATE rooms SET support_status='open',support_closed_at=0,support_closed_by='',assignee=0 WHERE id=?",(rid,)),
                      ('UPDATE members SET last_read_id=0 WHERE room_id=?',(rid,))]
        stmts.append(('INSERT OR IGNORE INTO messages(room_id,user_id,body,created,request_key,moderation) VALUES(?,?,?,?,?,?)',(rid,uid,body,time.time(),key,stored)))
        # 客服会话给对方发通知：客服回复→通知客户；客户发消息→通知受理客服。
        # 因为客服房不再进聊天列表，只能靠通知把对方拉回来。
        if room['support']:
            srole=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,))
            if srole in STAFF:
                cust=await self.db.scalar("SELECT m.user_id FROM members m JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND u.role NOT IN ('admin','support','developer') LIMIT 1",(rid,))
                if cust:stmts.append(('INSERT INTO notifications(user_id,kind,body,ticket_id,created) VALUES(?,?,?,?,?)',(cust,'support_reply',f'客服回复了你的咨询：{body[:50]}',room['ticket_id'],time.time())))
            elif room['assignee']:
                stmts.append(('INSERT INTO notifications(user_id,kind,body,ticket_id,created) VALUES(?,?,?,?,?)',(room['assignee'],'support_reply',f'咨询有新消息：{body[:50]}',room['ticket_id'],time.time())))
        await self.db.guarded_batch(guard,(rid,uid),stmts,message='会话权限已变化，请重试')
        return json_response({'ok':True,'moderation':mark})

    async def cf_community_recall(self,r):
        uid=await self.page_user(r);d=await json_body(r);mid=int_param(d,'message_id');m=await self.db.first('SELECT * FROM messages WHERE id=?',(mid,));require(m,'消息不存在',404);require(m['user_id']==uid,'只能撤回自己发送的消息',403);require(m['removed']==0,'该消息已不可撤回');require(time.time()-m['created']<=120,'超过两分钟的消息不能撤回了')
        await self.db.guarded_batch('SELECT 1 FROM messages WHERE id=? AND user_id=? AND removed=0 AND created>=?',(mid,uid,time.time()-120),[("UPDATE messages SET removed=2,body='' WHERE id=?",(mid,))]);return json_response({'ok':True})

    async def cf_message_receipts(self,r):
        """已读回执：本会话其他成员的已读位点（只读，不推进自己的已读位）。"""
        uid=await self.page_user(r);rid=int_param(query_of(r),'room_id');await self.cf_community_member(uid,rid)
        rows=await self.db.all('SELECT m.user_id,m.last_read_id,u.nickname FROM members m JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND m.user_id<>? ORDER BY m.user_id',(rid,uid))
        return json_response({'total':len(rows),'readers':[{'user_id':x['user_id'],'last_read_id':x['last_read_id'] or 0,'nickname':x['nickname']} for x in rows]})

    async def cf_community_hide(self,r):
        uid=await self.page_user(r);d=await json_body(r);mid=int_param(d,'message_id');m=await self.db.first('SELECT * FROM messages WHERE id=?',(mid,));require(m,'消息不存在',404);await self.cf_community_member(uid,m['room_id'])
        await self.db.run('INSERT OR IGNORE INTO message_hides(user_id,message_id,created) VALUES(?,?,?)',(uid,mid,time.time()));return json_response({'ok':True})

    async def cf_community_members(self,r):
        uid=await self.page_user(r);rid=int_param(query_of(r),'room_id');_,room=await self.cf_community_member(uid,rid)
        return json_response({'room':{k:room[k] for k in ('id','name','kind','pair')},'members':await self.db.all("SELECT m.user_id,m.role,m.muted,u.nickname,u.college FROM members m JOIN users u ON u.id=m.user_id WHERE room_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'moderator' THEN 1 ELSE 2 END,m.user_id",(rid,))})

    async def cf_community_block(self,r):
        uid=await self.page_user(r);d=await json_body(r);target=int_param(d,'target');require(target!=uid,'不能屏蔽自己');require(await self.db.first('SELECT 1 FROM users WHERE id=?',(target,)),'用户不存在',404)
        if d.get('enabled',True):await self.db.run('INSERT OR IGNORE INTO blocks VALUES(?,?)',(uid,target))
        else:await self.db.run('DELETE FROM blocks WHERE user_id=? AND target=?',(uid,target))
        return json_response({'ok':True})

    async def cf_community_moderate(self,r):
        uid=await self.page_user(r);d=await json_body(r);rid=int_param(d,'room_id');member,room=await self.cf_community_member(uid,rid);role=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,));require(member['role'] in ('owner','moderator') or role in ('admin','developer'),'没有群管理权限',403);require(room['kind']!='private','不能管理他人私聊')
        reason=ValidationMixin.text(d.get('reason'),500,'理由');action=d.get('action');require(action in ('mute','remove_message'),'不支持此管理操作')
        if action=='mute':statement=('UPDATE members SET muted=? WHERE room_id=? AND user_id=?',(int(bool(d.get('muted',True))),rid,int_param(d,'target')))
        else:statement=('UPDATE messages SET removed=1 WHERE id=? AND room_id=?',(int_param(d,'message_id'),rid))
        await self.db.guarded_batch("SELECT 1 FROM members m JOIN rooms r ON r.id=m.room_id JOIN users u ON u.id=m.user_id WHERE room_id=? AND user_id=? AND r.kind<>'private' AND (m.role IN ('owner','moderator') OR u.role IN ('admin','developer'))",(rid,uid),[statement,('INSERT INTO audit(actor,type,reason,created) VALUES(?,?,?,?)',(uid,'moderation',reason,time.time()))]);return json_response({'ok':True})

    async def cf_community_nominate(self,r):
        uid=await self.page_user(r);d=await json_body(r);rid=int_param(d,'room_id');await self.cf_community_member(uid,rid);reason=ValidationMixin.text(d.get('reason'),500,'申请理由')
        await self.db.guarded_batch('SELECT 1 FROM members WHERE room_id=? AND user_id=?',(rid,uid),[('INSERT INTO nominations(user_id,room_id,reason,created) VALUES(?,?,?,?)',(uid,rid,reason,time.time()))]);return json_response({'ok':True})

    async def cf_community_want_dto(self,uid,wid):
        want=await self.db.first('SELECT w.*,u.nickname FROM wants w JOIN users u ON u.id=w.user_id WHERE w.id=?',(wid,));require(want,'求购不存在',404)
        rows=await self.db.all("SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p JOIN users u ON u.id=p.seller_id WHERE p.status='available' ORDER BY p.id DESC")
        matches=[];kw=want['keyword'].lower()
        for row in rows:
            p=await self.listing_dto(row)
            if kw in ' '.join(str(p.get(k,'')) for k in ('title','description','category')).lower():matches.append(p)
        matches.sort(key=lambda p:(p['price']>want['budget'],p['price']));matches=matches[:20]
        trusted=await self.trusted_map([p['seller_id'] for p in matches])
        for p in matches:
            p['seller_trusted']=trusted.get(p['seller_id'],False);p['likes']=await self.db.scalar("SELECT COUNT(*) FROM reactions WHERE product_id=? AND kind='like'",(p['id'],)) or 0
            for name,kind in [('liked','like'),('favorited','favorite')]:p[name]=bool(uid and await self.db.first('SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind=?',(p['id'],uid,kind)))
        want['matches']=matches;return want

    async def cf_community_wants(self,r):
        if r.method=='POST':
            uid=await self.page_user(r);d=await json_body(r);keyword=ValidationMixin.text(d.get('keyword'),40,'求购物品');budget=ValidationMixin.cents(d.get('budget'),'预算');require(budget>0,'预算需大于0');await self.require_capacity()
            for attempt in range(4):
                wid=await self.db.scalar('SELECT COALESCE(MAX(id),0)+1 FROM wants')
                try:
                    await self.db.guarded_batch('SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM wants WHERE id=?)',(wid,),[('INSERT INTO wants(id,user_id,keyword,budget,description,status,created) VALUES(?,?,?,?,?,?,?)',(wid,uid,keyword,budget,str(d.get('description') or '').strip()[:1000],'open',time.time()))]);break
                except DomainError:
                    if attempt==3:raise
            return json_response(await self.cf_community_want_dto(uid,wid))
        uid,_=await sessions.current_user_id(self.db,r);q=query_of(r)
        search=str(q.get('q') or '').strip()
        limit=max(1,min(int_param(q,'limit',False) or 50,200));offset=max(0,int_param(q,'offset',False) or 0)
        sql='SELECT id FROM wants';args=[]
        if search:
            sql+=' WHERE keyword LIKE ? OR description LIKE ?'
            args+=['%'+search+'%','%'+search+'%']
        sql+=' ORDER BY id DESC LIMIT ? OFFSET ?';args+=[limit,offset]
        return json_response([await self.cf_community_want_dto(uid,w['id']) for w in await self.db.all(sql,tuple(args))])

    async def cf_community_want(self,r):
        uid,_=await sessions.current_user_id(self.db,r);return json_response(await self.cf_community_want_dto(uid,int_param(query_of(r),'id')))

COMMUNITY_ROUTES={
 '/api/posts':(('GET','POST'),'cf_community_posts'),'/api/comments':(('GET','POST'),'cf_community_comments'),
 '/api/wants':(('GET','POST'),'cf_community_wants'),'/api/want':(('GET',),'cf_community_want'),
 '/api/rooms':(('GET',),'cf_community_rooms'),'/api/rooms/join':(('POST',),'cf_community_join'),
 '/api/rooms/private':(('POST',),'cf_community_private'),'/api/support/room':(('POST',),'cf_community_support_room'),
 '/api/support/claim':(('POST',),'cf_community_claim'),'/api/support/close':(('POST',),'cf_support_close'),'/api/support/sessions':(('GET',),'cf_support_sessions'),'/api/messages':(('GET','POST'),'cf_community_messages'),
 '/api/messages/recall':(('POST',),'cf_community_recall'),'/api/messages/hide':(('POST',),'cf_community_hide'),
 '/api/messages/receipts':(('GET',),'cf_message_receipts'),
 '/api/room/members':(('GET',),'cf_community_members'),'/api/block':(('POST',),'cf_community_block'),
 '/api/rooms/pin':(('POST',),'cf_pin_room'),'/api/rooms/clear':(('POST',),'cf_clear_room'),
 '/api/moderate':(('POST',),'cf_community_moderate'),'/api/nominate':(('POST',),'cf_community_nominate')}
