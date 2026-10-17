"""Staff queue and source context; private detail still uses case_access."""
import json
import time

from ..core.errors import DomainError


class StaffWorkbench:
    def staff_queue(self, user_id, filters):
        self.staff(user_id)
        try:
            page, size = int(filters.get('page', 1)), int(filters.get('page_size', 20))
        except (TypeError, ValueError):
            raise DomainError('分页参数无效')
        self.require(page > 0 and 1 <= size <= 50, '分页参数无效')
        scope = filters.get('scope', 'all')
        self.require(scope in ['all', 'mine', 'unassigned', 'review', 'overdue', 'new'], '待办范围无效')
        rows = self.rows('SELECT t.id,t.user_id,t.order_id,t.product_id,t.post_id,t.subject,t.type,t.status,t.assignee,t.created, '
                         'u.nickname,a.nickname assignee_name, '
                         'MAX(t.created,COALESCE((SELECT MAX(created) FROM ticket_messages WHERE ticket_id=t.id),0), '
                         'COALESCE((SELECT MAX(created) FROM audit WHERE ticket_id=t.id),0)) updated_at, '
                         'EXISTS(SELECT 1 FROM notifications n WHERE n.user_id=? AND n.entity_type=\'ticket\' '
                         'AND n.entity_id=t.id AND n.read_at IS NULL) has_unread '
                         'FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN users a ON a.id=t.assignee', (user_id,))
        now = time.time()
        for row in rows:
            row['overdue'] = row['status'] != 'resolved' and now-row['updated_at'] >= 86400
        summary = {'open': 0, 'processing': 0, 'review': 0, 'resolved': 0, 'mine': 0, 'unassigned': 0, 'overdue': 0, 'new': 0}
        for row in rows:
            summary[row['status']] += 1
            live = row['status'] != 'resolved'
            summary['mine'] += int(live and row['assignee'] == user_id)
            summary['unassigned'] += int(live and not row['assignee'])
            summary['overdue'] += int(row['overdue'])
            summary['new'] += int(bool(row['has_unread']))
        matches = {
            'all': lambda t: True,
            'mine': lambda t: t['assignee'] == user_id and t['status'] != 'resolved',
            'unassigned': lambda t: not t['assignee'] and t['status'] != 'resolved',
            'review': lambda t: t['status'] == 'review',
            'overdue': lambda t: t['overdue'],
            'new': lambda t: t['has_unread'],
        }
        query = str(filters.get('q', '')).strip().lower()
        rows = [t for t in rows if matches[scope](t) and
                (not filters.get('type') or t['type'] == filters['type']) and
                (not filters.get('status') or t['status'] == filters['status']) and
                (not query or query in (str(t['id'])+' '+t['subject']+' '+t['nickname']+' '+str(t['assignee_name'] or '')).lower())]
        rows.sort(key=lambda t: (t['status'] == 'resolved', not t['overdue'], t['updated_at'], t['id']))
        total = len(rows)
        items = rows[(page-1)*size:page*size]
        for item in items:
            item['restricted'] = self.ticket(user_id, item['id'])['restricted']
        return {'items': items, 'total': total, 'page': page, 'page_size': size, 'summary': summary}

    def case_sources(self, ticket):
        stored = json.loads(ticket.get('source_snapshot') or '{}')
        if stored:
            return {**stored, 'captured': True}
        result = {}
        if ticket.get('product_id'):
            product = self.product(ticket['product_id'])
            result['product'] = {key: product.get(key) for key in
                                 ['id', 'seller_id', 'nickname', 'title', 'description', 'price', 'edition', 'notes', 'missing', 'photos']}
        if ticket.get('post_id'):
            post = self.row('SELECT p.id,p.user_id,p.topic,p.body,u.nickname FROM posts p JOIN users u ON u.id=p.user_id WHERE p.id=?', (ticket['post_id'],))
            if post:
                help_post = self.row('SELECT title,service_type,place,reward FROM service_posts WHERE post_id=?', (post['id'],))
                result['post'] = {**post, **(help_post or {})}
        return {**result, 'captured': False}

    def admin_audit(self, user_id, filters=None):
        self._administrator(user_id)
        filters = filters or {}
        try:
            page = int(filters.get('page', 1))
        except (ValueError, TypeError):
            raise DomainError('分页参数无效')
        self.require(page > 0, '分页参数无效')
        query = str(filters.get('q', '')).strip()
        where = 'WHERE (?=\'\' OR INSTR(COALESCE(a.reason,\'\')||COALESCE(a.type,\'\')||COALESCE(u.nickname,\'\')||COALESCE(t.nickname,\'\'),?)>0)'
        args = (query, query)
        joins = 'FROM audit a LEFT JOIN users u ON u.id=a.actor LEFT JOIN users t ON t.id=a.target '
        total = self.row('SELECT COUNT(*) n '+joins+where, args)['n']
        items = self.rows('SELECT a.*,u.nickname actor_name,t.nickname target_name '+joins+where+' ORDER BY a.id DESC LIMIT 30 OFFSET ?', (*args, (page-1)*30))
        return {'items': items, 'total': total, 'page': page, 'page_size': 30}

    def credit_options(self, user_id, target):
        self._administrator(user_id)
        result = {'user': self.profile(target), 'penalty_cases': [], 'appeal_cases': [], 'penalties': []}
        for row in self.rows("SELECT id,type,subject FROM tickets WHERE status='resolved' AND outcome IN ('resolved','refund') ORDER BY id DESC"):
            try:
                self._verified_credit_target(user_id, target, row['id'], appeal=row['type']=='appeal')
            except DomainError:
                continue
            result['appeal_cases' if row['type']=='appeal' else 'penalty_cases'].append(row)
        result['penalties'] = self.rows("SELECT a.id,a.delta,a.reason,a.ticket_id,a.rule_key FROM audit a WHERE a.target=? AND a.type IN ('credit','credit_warning') AND NOT EXISTS(SELECT 1 FROM audit b WHERE b.reversal_of=a.id) ORDER BY a.id DESC", (target,))
        result['recent_no_show'] = bool(self.row("SELECT id FROM audit WHERE target=? AND rule_key='no_show' AND created>? AND type IN ('credit','credit_warning') AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.reversal_of=audit.id)", (target, time.time()-30*86400)))
        return result
