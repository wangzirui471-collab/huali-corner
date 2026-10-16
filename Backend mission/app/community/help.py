"""Campus help bulletin: structured posts, private negotiation, no payment orders."""
import secrets
import time

HELP_TYPES = {'parcel': '快递代取', 'documents': '资料代交', 'moving': '搬运帮忙',
              'study': '学习辅导／笔记整理', 'other': '其他互助'}


class CommunityHelp:
    def _help_view(self, row, user_id=None):
        item = dict(row)
        item['status'] = 'expired' if item['status'] == 'open' and item['deadline'] <= time.time() else item['status']
        item['is_owner'] = item['user_id'] == user_id
        item['service_label'] = HELP_TYPES[item['service_type']]
        item['simulation'] = True
        item.pop('request_key', None)
        return item

    def help_post(self, post_id, user_id=None):
        row = self.row('SELECT h.*,p.id,p.body,p.created,u.nickname,u.college FROM service_posts h '
                      'JOIN posts p ON p.id=h.post_id JOIN users u ON u.id=p.user_id WHERE p.id=?', (post_id,))
        self.require(row, '互助信息不存在', 404)
        return self._help_view(row, user_id)

    def publish_help(self, user_id, data):
        kind = data.get('kind', 'need')
        service_type = data.get('service_type')
        self.require(kind in ['need', 'offer'] and service_type in HELP_TYPES, '请选择有效互助类型')
        title = self.text(data.get('title'), 80, '互助标题')
        body = self.text(data.get('body'), 2000, '互助说明')
        place = self.text(data.get('place'), 120, '公共地点')
        deadline = data.get('deadline')
        self.require(type(deadline) in [int, float] and time.time()+60 < deadline < time.time()+86400*30,
                     '请选择未来30天内的截止时间')
        reward = None if data.get('reward_yuan', '') == '' else self._yuan_to_cents(data['reward_yuan'])
        key = self.text(data.get('key') or secrets.token_hex(16), 100, '发布标识')
        with self.tx() as connection:
            self._listing_account(connection, user_id)
            old = connection.execute('SELECT post_id FROM service_posts WHERE user_id=? AND request_key=?', (user_id, key)).fetchone()
            if old:
                post_id = old['post_id']
            else:
                post_id = connection.execute("INSERT INTO posts(user_id,topic,body,created) VALUES(?,'互助',?,?)",
                                             (user_id, body, time.time())).lastrowid
                connection.execute('INSERT INTO service_posts(post_id,user_id,kind,service_type,title,reward,place,deadline,request_key) '
                                   'VALUES(?,?,?,?,?,?,?,?,?)', (post_id,user_id,kind,service_type,title,reward,place,deadline,key))
        return self.help_post(post_id, user_id)

    def help_posts(self, user_id=None, filters=None):
        filters = filters or {}
        status = filters.get('status', 'open')
        self.require(status in ['open', 'closed', 'expired', 'all'], '互助状态无效')
        page_size = int(filters.get('page_size', 20))
        before = int(filters.get('before_id', 0))
        self.require(1 <= page_size <= 50 and before >= 0, '分页参数无效')
        where = ['1=1']; args = []
        for field, choices in [('service_type', HELP_TYPES), ('kind', ['need', 'offer'])]:
            value = filters.get(field)
            if value:
                self.require(value in choices, '互助筛选无效')
                where.append('h.'+field+'=?'); args.append(value)
        if status != 'all':
            where.append("(CASE WHEN h.status='open' AND h.deadline<=? THEN 'expired' ELSE h.status END)=?")
            args.extend([time.time(), status])
        if filters.get('mine') == '1':
            self.require(user_id, '请先登录', 401)
            where.append('p.user_id=?'); args.append(user_id)
        if before:
            where.append('p.id<?'); args.append(before)
        if filters.get('post_id'):
            where.append('p.id=?'); args.append(int(filters['post_id']))
        if filters.get('q'):
            query = self.text(filters['q'], 80, '搜索内容')
            where.append('(h.title LIKE ? OR p.body LIKE ?)'); args.extend(['%'+query+'%']*2)
        rows = self.rows('SELECT h.*,p.id,p.body,p.created,u.nickname,u.college FROM service_posts h '
            'JOIN posts p ON p.id=h.post_id JOIN users u ON u.id=p.user_id WHERE '+ ' AND '.join(where) +
            ' ORDER BY p.id DESC LIMIT ?', (*args, page_size+1))
        items = [self._help_view(row, user_id) for row in rows[:page_size]]
        return {'items':items, 'has_more':len(rows)>page_size,
                'next_cursor':items[-1]['id'] if len(rows)>page_size else None}

    def set_help_status(self, user_id, post_id, status):
        self.require(status in ['open', 'closed'], '互助状态无效')
        with self.tx() as connection:
            post = connection.execute('SELECT * FROM service_posts WHERE post_id=?', (post_id,)).fetchone()
            self.require(post and post['user_id'] == user_id, '只能修改自己发布的互助信息', 403)
            if status == 'open':
                self._listing_account(connection, user_id)
                self.require(post['deadline'] > time.time(), '信息已过期，请重新发布', 409)
            connection.execute('UPDATE service_posts SET status=? WHERE post_id=?', (status, post_id))
        return self.help_post(post_id, user_id)
