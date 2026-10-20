"""Shared, parameter-bound read queries for the local and cloud forum."""

def posts_query(topic='', limit=20, offset=0, filters=None, hide_removed_comments=False):
    q=filters or {}; clauses=['p.removed=0']; args=[]
    if topic: clauses.append('p.topic=?');args.append(topic)
    if q.get('forum')=='1': clauses.append("p.topic IN ('交换人生','代拿快递')")
    if q.get('id'): clauses.append('p.id=?');args.append(int(q['id']))
    if q.get('author'): clauses.append('p.user_id=?');args.append(int(q['author']))
    if str(q.get('q') or '').strip():
        clauses.append('instr(lower(p.body),lower(?))>0');args.append(str(q['q']).strip()[:100])
    visible=' AND c.removed=0' if hide_removed_comments else ''
    count=f'(SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id{visible}) replies'
    order='replies DESC,p.id DESC' if q.get('sort')=='hot' else 'p.id DESC'
    sql=f"SELECT p.*,u.nickname,u.college,{count} FROM posts p JOIN users u ON u.id=p.user_id WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT ? OFFSET ?"
    return sql,tuple(args+[max(1,min(int(limit or 20),50)),max(0,int(offset or 0))])
