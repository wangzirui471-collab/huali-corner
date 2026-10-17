"""把 var-trial（学院试用）的 SQLite 数据迁移到 MySQL。

用法：
    set HC_DB=mysql://root@127.0.0.1:3306/huali_corner
    python migrate_to_mysql.py

说明：
  - 目标库结构由 app/core/database.py 的 MYSQL_SCHEMA 决定（先正常启动一次 Store 建表）。
  - 逐表 SELECT * 读出，按 MySQL 实际列过滤后批量 INSERT（保留原 id）。
  - 迁移后修正每张表的 AUTO_INCREMENT，使后续自增 id 不冲突。
  - 仅迁移试用库；演示库（var/）与试用库互斥，请另建库另跑一次。
"""
import os, sys, sqlite3, pymysql
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import data_dir

SQLITE_PATH = os.path.join(data_dir(trial=True), 'market.sqlite3')
HC_DB = os.environ.get('HC_DB') or 'mysql://root@127.0.0.1:3306/huali_corner'

# 仅迁移列名与 MySQL 一致的表；顺序无所谓（无外键约束）。
TABLES = ['users', 'otp', 'sessions', 'settings', 'password_credentials',
          'auth_attempts', 'uploads', 'products', 'reactions', 'orders',
          'order_changes', 'order_notes', 'ledger', 'tickets', 'ticket_messages',
          'audit', 'reviews', 'rooms', 'members', 'messages', 'message_hides',
          'blocks', 'posts', 'comments', 'offers', 'nominations', 'wants',
          'notifications']


def dsn():
    from urllib.parse import urlparse
    p = urlparse(HC_DB)
    return dict(host=p.hostname or '127.0.0.1', port=p.port or 3306,
               user=p.username or 'root', password=p.password or '',
               database=(p.path or '').lstrip('/') or 'huali_corner')


def main():
    assert os.path.exists(SQLITE_PATH), f'找不到源库: {SQLITE_PATH}'
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = pymysql.connect(charset='utf8mb4', autocommit=True, **dsn())
    cur = dst.cursor(pymysql.cursors.DictCursor)

    # 清空目标库（避免重复迁移时主键冲突）
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in TABLES:
        cur.execute(f'DELETE FROM `{t}`')
    cur.execute("SET FOREIGN_KEY_CHECKS=1")

    total = 0
    for t in TABLES:
        rows = src.execute(f'SELECT * FROM `{t}`').fetchall()
        if not rows:
            print(f'{t:18s} 空')
            continue
        cols = [r[1] for r in src.execute(f'PRAGMA table_info(`{t}`)').fetchall()]
        cur.execute(
            "SELECT COLUMN_NAME c FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s", (dsn()['database'], t))
        mysql_cols = {r['c'] for r in cur.fetchall()}
        use = [c for c in cols if c in mysql_cols]
        assert use, f'{t} 在 MySQL 中无可用列'
        ph = ','.join(['%s'] * len(use))
        col_sql = ','.join(f'`{c}`' for c in use)
        sql = f'INSERT INTO `{t}` ({col_sql}) VALUES ({ph})'
        vals = [tuple(r[c] for c in use) for r in rows]
        cur.executemany(sql, vals)
        # 仅对「id 为 AUTO_INCREMENT」的表修正自增计数器。
        # 注意 uploads.id 是 TEXT（文件 id 令牌），不是自增整数，必须排除。
        cur.execute(
            "SELECT EXTRA FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name='id'",
            (dsn()['database'], t))
        erow = cur.fetchone()
        if erow and 'auto_increment' in (erow['EXTRA'] or ''):
            cur.execute(f'SELECT MAX(id) m FROM `{t}`')
            mx = cur.fetchone()['m']
            mx = int(mx) if mx is not None else None
            if mx:
                cur.execute(f'ALTER TABLE `{t}` AUTO_INCREMENT = {mx + 1}')
        else:
            mx = None
        total += len(rows)
        print(f'{t:18s} {len(rows):>5d} 行  max_id={mx}')
    print(f'\n迁移完成，共 {total} 行。')
    src.close(); dst.close()


if __name__ == '__main__':
    main()
