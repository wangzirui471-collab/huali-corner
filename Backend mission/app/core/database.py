"""数据库层：同时支持 SQLite（默认）与 MySQL（设置 HC_DB 后启用）。

双引擎策略
----------
  - 默认使用 SQLite 文件（market.sqlite3），保证现有测试与演示/试用实例零改动、可随时回退。
  - 设置环境变量 HC_DB=mysql://user:pass@host:port/dbname 后，Store 自动切换到 MySQL。
  - 两条硬约束与 SQLite 时代一致：
      1. 不使用 WAL，写事务串行化（_WRITE 锁）。
      2. 所有对外查询仍通过 tx()/rows()/row()，service 层不感知后端差异。

dialect 适配
------------
  sqlite3 的 connection.execute() 返回 cursor，且可链式 .fetchone()/.fetchall()/.lastrowid；
  pymysql 的 connection 没有 .execute()，且 .execute() 返回的是受影响的行数而非 cursor。
  为了不改变 10 个 service 文件里成千上万处 `c.execute(...).fetchone()` 的写法，这里用
  _Conn 包装器抹平差异：两种后端下 self.connect() 都返回一个 _Conn，它的 .execute()
  始终返回 cursor（MySQL 模式下还会做 SQL 方言改写）。

  方言改写只发生在 MySQL 模式，覆盖本项目用到的全部 SQLite 专有写法：
      ?                        -> %s            （占位符）
      INSERT OR IGNORE         -> INSERT IGNORE
      INSERT OR REPLACE        -> REPLACE INTO
      BEGIN IMMEDIATE          -> BEGIN
      ON CONFLICT(...) DO UPDATE SET a=excluded.x
                               -> ON DUPLICATE KEY UPDATE a=VALUES(x)
  其余 SQL（JOIN / COALESCE / LIMIT / 子查询等）两种库通用，无需改写。
"""
import os, re, sqlite3, json, time, threading, queue
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

# 写事务串行锁：让并发写入在 Python 层排队，而不是各自去撞底层写锁。
# 关于它【不】负责什么，写清楚以免后人误会：
#   · 它不负责防止超卖 —— 那是 tx() 里 BEGIN IMMEDIATE 的职责：事务一开始就申请
#     底层写锁，后到的事务必须等待，读到的是已提交的新状态。实测用不同请求键
#     三线程抢购，有锁无锁都是 0 次超卖。
#   · 它也不是「attempt to write a readonly database」的修复 —— 那个问题的根因是
#     WAL 模式下最后一个连接关闭时 checkpoint 并删除 -wal/-shm，已由改用删除日志模式解决。
#     关掉 WAL 之后实测 30 并发写 × 5 轮，有锁无锁都是 0 失败。
# 留着它的理由只有一个：写入在 Python 层确定性排队，不必依赖 busy_timeout
# 的重试行为，也不会有 database is locked 在极端争用时冒出来。本站写入量很小。
# 读操作不经过这把锁，不受影响。
_WRITE = threading.RLock()

SQLITE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,phone TEXT UNIQUE,nickname TEXT NOT NULL,college TEXT DEFAULT '计算机工程学院',major TEXT DEFAULT '',education TEXT DEFAULT '本科',bio TEXT DEFAULT '',role TEXT DEFAULT 'user',score INTEGER DEFAULT 100 CHECK(score BETWEEN 0 AND 100),status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS otp(phone TEXT PRIMARY KEY,digest TEXT,expires REAL,attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS password_credentials(user_id INTEGER PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,rounds INTEGER NOT NULL,recovery_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts(phone TEXT PRIMARY KEY,attempts INTEGER NOT NULL,reset_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,user_id INTEGER,path TEXT,digest TEXT,angle TEXT,private INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,seller_id INTEGER,title TEXT,category TEXT,price INTEGER,delivery_fee INTEGER,delivery TEXT,region TEXT,status TEXT DEFAULT 'available',data TEXT,created REAL,promoted_until REAL DEFAULT 0,delisted_by INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reactions(user_id INTEGER,product_id INTEGER,kind TEXT,PRIMARY KEY(user_id,product_id,kind));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,buyer_id INTEGER,seller_id INTEGER,items TEXT,subtotal INTEGER,delivery_fee INTEGER,total INTEGER,delivery TEXT,address TEXT,appointment REAL,status TEXT,created REAL,paid_at REAL,delivered_at REAL,handover_at REAL,completed_at REAL,request_key TEXT,schedule_confirmed INTEGER DEFAULT 0,want_id INTEGER,UNIQUE(buyer_id,request_key));
CREATE TABLE IF NOT EXISTS order_changes(id INTEGER PRIMARY KEY,order_id INTEGER,proposer INTEGER,appointment REAL,address TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS order_notes(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,body TEXT,created REAL);
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,order_id INTEGER,kind TEXT,amount INTEGER,created REAL,UNIQUE(order_id,kind));
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER,order_id INTEGER,product_id INTEGER,type TEXT,subject TEXT,body TEXT,status TEXT DEFAULT 'open',assignee INTEGER,outcome TEXT,reason TEXT,created REAL);
CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY,ticket_id INTEGER,user_id INTEGER,body TEXT,internal INTEGER DEFAULT 0,created REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER,target INTEGER,type TEXT,delta INTEGER,reason TEXT,ticket_id INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,rating INTEGER,body TEXT,created REAL,UNIQUE(order_id,user_id));
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,kind TEXT,name TEXT,college TEXT DEFAULT '',sequence INTEGER DEFAULT 1,pair TEXT UNIQUE,support INTEGER DEFAULT 0,assignee INTEGER DEFAULT 0,ticket_id INTEGER DEFAULT 0,support_status TEXT DEFAULT 'open',support_closed_at REAL DEFAULT 0,support_closed_by TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS members(room_id INTEGER,user_id INTEGER,muted INTEGER DEFAULT 0,role TEXT DEFAULT 'member',last_read_id INTEGER DEFAULT 0,PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,room_id INTEGER,user_id INTEGER,body TEXT,created REAL,request_key TEXT,removed INTEGER DEFAULT 0,moderation TEXT,UNIQUE(user_id,room_id,request_key));
CREATE TABLE IF NOT EXISTS message_hides(user_id INTEGER,message_id INTEGER,created REAL,PRIMARY KEY(user_id,message_id));
CREATE TABLE IF NOT EXISTS blocks(user_id INTEGER,target INTEGER,PRIMARY KEY(user_id,target));
CREATE TABLE IF NOT EXISTS room_pins(user_id INTEGER,room_id INTEGER,pinned_at REAL,PRIMARY KEY(user_id,room_id));
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,user_id INTEGER,topic TEXT,body TEXT,created REAL,moderation TEXT,removed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,post_id INTEGER,user_id INTEGER,body TEXT,created REAL,parent_id INTEGER DEFAULT 0,removed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY,product_id INTEGER,buyer_id INTEGER,amount INTEGER,status TEXT DEFAULT 'pending',created REAL,accepted_at REAL);
CREATE TABLE IF NOT EXISTS nominations(id INTEGER PRIMARY KEY,user_id INTEGER,room_id INTEGER,reason TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS wants(id INTEGER PRIMARY KEY,user_id INTEGER,keyword TEXT,budget INTEGER,description TEXT,status TEXT DEFAULT 'open',created REAL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,order_id INTEGER,ticket_id INTEGER,body TEXT,read_at REAL,created REAL,post_id INTEGER,product_id INTEGER);
'''

# MySQL 等价表结构。与 SQLITE_SCHEMA 字段一一对应，差异点：
#   · id INTEGER PRIMARY KEY  ->  id INT PRIMARY KEY AUTO_INCREMENT
#   · REAL                    ->  DOUBLE
#   · 保留字 key / type 用反引号引用
#   · 带 UNIQUE/PRIMARY KEY 的文本列用 VARCHAR（MySQL 对 TEXT 建唯一索引在严格模式下受限）
MYSQL_SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INT PRIMARY KEY AUTO_INCREMENT,phone VARCHAR(32) NOT NULL UNIQUE,nickname VARCHAR(64) NOT NULL,college VARCHAR(64) DEFAULT '计算机工程学院',major VARCHAR(64) DEFAULT '',education VARCHAR(32) DEFAULT '本科',bio TEXT,role VARCHAR(32) DEFAULT 'user',score INT DEFAULT 100 CHECK (score BETWEEN 0 AND 100),status VARCHAR(32) DEFAULT 'active',last_login DOUBLE DEFAULT 0,degree_level VARCHAR(16) NOT NULL DEFAULT 'unspecified',study_status VARCHAR(16) NOT NULL DEFAULT 'unspecified',profile_version INT NOT NULL DEFAULT 0,avatar_upload_id VARCHAR(64) NULL);
CREATE TABLE IF NOT EXISTS otp(phone VARCHAR(32) NOT NULL PRIMARY KEY,digest TEXT,expires DOUBLE,attempts INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token VARCHAR(128) NOT NULL PRIMARY KEY,user_id INT,expires DOUBLE);
CREATE TABLE IF NOT EXISTS settings(`key` VARCHAR(64) NOT NULL PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS password_credentials(user_id INT NOT NULL PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,rounds INT NOT NULL,recovery_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts(phone VARCHAR(32) NOT NULL PRIMARY KEY,attempts INT NOT NULL,reset_at DOUBLE NOT NULL);
CREATE TABLE IF NOT EXISTS uploads(id VARCHAR(64) NOT NULL PRIMARY KEY,user_id INT,path TEXT,digest TEXT,angle VARCHAR(16),private INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS user_avatar_uploads(upload_id VARCHAR(64) NOT NULL PRIMARY KEY,user_id INT NOT NULL,path TEXT NOT NULL,digest TEXT NOT NULL,created_at DOUBLE NOT NULL,INDEX user_avatar_uploads_owner(user_id));
CREATE TABLE IF NOT EXISTS products(id INT PRIMARY KEY AUTO_INCREMENT,seller_id INT,title VARCHAR(255),category VARCHAR(32),price INT,delivery_fee INT,delivery VARCHAR(32),region VARCHAR(32),status VARCHAR(32) DEFAULT 'available',data TEXT,created DOUBLE,promoted_until DOUBLE DEFAULT 0,delisted_by INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS reactions(user_id INT,product_id INT,kind VARCHAR(16),PRIMARY KEY(user_id,product_id,kind));
CREATE TABLE IF NOT EXISTS orders(id INT PRIMARY KEY AUTO_INCREMENT,buyer_id INT,seller_id INT,items TEXT,subtotal INT,delivery_fee INT,total INT,delivery VARCHAR(32),address TEXT,appointment DOUBLE,status VARCHAR(48),created DOUBLE,paid_at DOUBLE,delivered_at DOUBLE,handover_at DOUBLE,completed_at DOUBLE,request_key VARCHAR(64),schedule_confirmed INT DEFAULT 0,want_id INT,UNIQUE(buyer_id,request_key));
CREATE TABLE IF NOT EXISTS order_changes(id INT PRIMARY KEY AUTO_INCREMENT,order_id INT,proposer INT,appointment DOUBLE,address TEXT,status VARCHAR(32) DEFAULT 'pending',created DOUBLE);
CREATE TABLE IF NOT EXISTS order_notes(id INT PRIMARY KEY AUTO_INCREMENT,order_id INT,user_id INT,body TEXT,created DOUBLE);
CREATE TABLE IF NOT EXISTS ledger(id INT PRIMARY KEY AUTO_INCREMENT,order_id INT,kind VARCHAR(48),amount INT,created DOUBLE,UNIQUE(order_id,kind));
CREATE TABLE IF NOT EXISTS tickets(id INT PRIMARY KEY AUTO_INCREMENT,user_id INT,order_id INT,product_id INT,`type` VARCHAR(48),subject VARCHAR(255),body TEXT,status VARCHAR(32) DEFAULT 'open',assignee INT,outcome VARCHAR(48),reason TEXT,created DOUBLE);
CREATE TABLE IF NOT EXISTS ticket_messages(id INT PRIMARY KEY AUTO_INCREMENT,ticket_id INT,user_id INT,body TEXT,internal INT DEFAULT 0,created DOUBLE);
CREATE TABLE IF NOT EXISTS audit(id INT PRIMARY KEY AUTO_INCREMENT,actor INT,target INT,`type` VARCHAR(48),delta INT,reason TEXT,ticket_id INT,created DOUBLE);
CREATE TABLE IF NOT EXISTS reviews(id INT PRIMARY KEY AUTO_INCREMENT,order_id INT,user_id INT,rating INT,body TEXT,created DOUBLE,UNIQUE(order_id,user_id));
CREATE TABLE IF NOT EXISTS rooms(id INT PRIMARY KEY AUTO_INCREMENT,kind VARCHAR(32),name VARCHAR(128),college VARCHAR(64) DEFAULT '',sequence INT DEFAULT 1,pair VARCHAR(128) UNIQUE,support INT DEFAULT 0,assignee INT DEFAULT 0,ticket_id INT DEFAULT 0,support_status VARCHAR(16) DEFAULT 'open',support_closed_at DOUBLE DEFAULT 0,support_closed_by VARCHAR(16) DEFAULT '');
CREATE TABLE IF NOT EXISTS members(room_id INT,user_id INT,muted INT DEFAULT 0,role VARCHAR(32) DEFAULT 'member',last_read_id INT DEFAULT 0,PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS messages(id INT PRIMARY KEY AUTO_INCREMENT,room_id INT,user_id INT,body TEXT,created DOUBLE,request_key VARCHAR(64),removed INT DEFAULT 0,moderation TEXT,UNIQUE(user_id,room_id,request_key));
CREATE TABLE IF NOT EXISTS message_hides(user_id INT,message_id INT,created DOUBLE,PRIMARY KEY(user_id,message_id));
CREATE TABLE IF NOT EXISTS blocks(user_id INT,target INT,PRIMARY KEY(user_id,target));
CREATE TABLE IF NOT EXISTS room_pins(user_id INT,room_id INT,pinned_at DOUBLE,PRIMARY KEY(user_id,room_id));
CREATE TABLE IF NOT EXISTS posts(id INT PRIMARY KEY AUTO_INCREMENT,user_id INT,topic VARCHAR(128),body TEXT,created DOUBLE,moderation TEXT,removed INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS comments(id INT PRIMARY KEY AUTO_INCREMENT,post_id INT,user_id INT,body TEXT,created DOUBLE,parent_id INT DEFAULT 0,removed INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS offers(id INT PRIMARY KEY AUTO_INCREMENT,product_id INT,buyer_id INT,amount INT,status VARCHAR(48) DEFAULT 'pending',created DOUBLE,accepted_at DOUBLE);
CREATE TABLE IF NOT EXISTS nominations(id INT PRIMARY KEY AUTO_INCREMENT,user_id INT,room_id INT,reason TEXT,status VARCHAR(32) DEFAULT 'pending',created DOUBLE);
CREATE TABLE IF NOT EXISTS wants(id INT PRIMARY KEY AUTO_INCREMENT,user_id INT,keyword VARCHAR(128),budget INT,description TEXT,status VARCHAR(32) DEFAULT 'open',created DOUBLE);
CREATE TABLE IF NOT EXISTS notifications(id INT PRIMARY KEY AUTO_INCREMENT,user_id INT,kind VARCHAR(48),order_id INT,ticket_id INT,body TEXT,read_at DOUBLE,created DOUBLE,post_id INT,product_id INT);
'''

# MySQL 模式下的 SQL 方言改写（仅作用于进来的 SQL 文本）。
_RE_IGNORE = re.compile(r'\bINSERT\s+OR\s+IGNORE\b', re.I)
_RE_REPLACE = re.compile(r'\bINSERT\s+OR\s+REPLACE\b', re.I)  # 替换为 REPLACE（原句自带 INTO，不要写成 REPLACE INTO）
_RE_BEGIN = re.compile(r'\bBEGIN\s+IMMEDIATE\b', re.I)
_RE_CONFLICT = re.compile(r'ON\s+CONFLICT\s*\([^)]*\)\s*DO\s+UPDATE\s+SET', re.I)
_RE_EXCLUDED = re.compile(r'excluded\.(\w+)', re.I)
# key / type 是 MySQL 保留字，但本项目只把它们当列名用（从不在字符串字面量里出现），
# 因此用「前后必须是标识符边界、且不在引号内」的限定把它们反引号化。
# 前瞻只接受空白/逗号/等号/行尾，避免命中 'auth_mode' 这类字符串里恰好含该单词的情况。
_RE_KEY = re.compile(r"(?<![\w'\"`])key\b(?=[\s,)=]|$)", re.I)
_RE_TYPE = re.compile(r"(?<![\w'\"`])type\b(?=[\s,)=]|$)", re.I)


def _rewrite_mysql(sql):
    # 注意顺序：先处理列名保留字 key/type，再改写 ON CONFLICT -> ON DUPLICATE KEY，
    # 否则后一步引入的 "DUPLICATE KEY" 里的 KEY 会被误加反引号。
    s = _RE_IGNORE.sub('INSERT IGNORE', sql)
    s = _RE_REPLACE.sub('REPLACE', s)
    s = _RE_BEGIN.sub('BEGIN', s)
    s = _RE_KEY.sub('`key`', s)
    s = _RE_TYPE.sub('`type`', s)
    s = _RE_CONFLICT.sub('ON DUPLICATE KEY UPDATE', s)
    s = _RE_EXCLUDED.sub(r'VALUES(\1)', s)
    s = s.replace('?', '%s')
    return s


def _split_statements(sql):
    out = []
    buf = ''
    for ch in sql:
        buf += ch
        if ch == ';':
            out.append(buf.strip())
            buf = ''
    if buf.strip():
        out.append(buf.strip())
    return out


class _Conn:
    """统一 sqlite3 / pymysql 的游标语义。

    sqlite3：connection.execute() 返回 cursor，可链式 .fetchone()/.lastrowid。
    pymysql：connection 没有 .execute()；必须 cursor.execute()，且返回的是 rowcount。
    这里两种后端都返回 _Conn，其 .execute() 始终返回 cursor，并代理 commit/rollback/close。
    MySQL 模式下 .execute() 会先过方言改写器。
    """

    def __init__(self, raw, dialect, rewriter=None, pool=None):
        self._raw = raw
        self._dialect = dialect
        self._rew = rewriter
        self._pool = pool

    def _sql(self, sql):
        if self._dialect == 'mysql' and self._rew:
            return self._rew(sql)
        return sql

    def execute(self, sql, args=()):
        sql2 = self._sql(sql)
        cur = self._raw.cursor()
        cur.execute(sql2, args)
        return cur

    def executemany(self, sql, args):
        sql2 = self._sql(sql)
        cur = self._raw.cursor()
        cur.executemany(sql2, args)
        return cur

    def executescript(self, sql):
        if self._dialect == 'sqlite':
            self._raw.executescript(sql)
            return
        # MySQL 没有 executescript：拆成单条依次执行。
        for stmt in _split_statements(sql):
            if stmt:
                self._raw.cursor().execute(stmt)

    def commit(self):
        # A failed commit must reach tx()/the caller. Reporting success here
        # can make an order look saved even though the database rejected it.
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._pool is not None:
            try:
                self._pool.put(self._raw)
            except Exception:
                try:
                    self._raw.close()
                except Exception:
                    pass
        else:
            try:
                self._raw.close()
            except Exception:
                pass

    def backup(self, target):
        """SQLite 在线备份 API 的代理（ops 备份与降权前快照依赖它）。

        语义与 sqlite3.Connection.backup 一致：把本连接已提交的内容拷到 target。
        MySQL 模式没有等价物，直接报错而不是静默产出空文件。
        """
        if self._dialect != 'sqlite':
            raise RuntimeError('当前为 MySQL 后端，sqlite3 backup 不可用；请改用 mysqldump 备份')
        destination = target._raw if isinstance(target, _Conn) else target
        return self._raw.backup(destination)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # 必须与 sqlite3.Connection 的上下文语义一致：成功则提交、异常则回滚，然后关闭。
        # 少了这一步，`with store.connect() as c:` 里插入的种子行（例如 rooms 里的
        # 「广州校区总聊」）会在连接关闭时被静默回滚，随后 join_room 找不到房间。
        try:
            if exc_type is None:
                try:
                    self.commit()
                except Exception:
                    self.rollback()
                    raise
            else:
                self.rollback()
        finally:
            self.close()


# MySQL 连接池：避免每次查询都做 TCP 握手。按 DSN 维度隔离。
_MYSQL_POOLS = {}
_MYSQL_POOLS_LOCK = threading.Lock()


def _pool_for(dsn_key, factory):
    with _MYSQL_POOLS_LOCK:
        if dsn_key not in _MYSQL_POOLS:
            _MYSQL_POOLS[dsn_key] = queue.Queue()
        q = _MYSQL_POOLS[dsn_key]
    return q, factory


class Store:
    def __init__(self, root):
        self.root = Path(root)
        dsn = (os.environ.get('HC_DB') or '').strip()
        if dsn.startswith('mysql://'):
            self.dialect = 'mysql'
            self.mysql = self._parse_mysql_dsn(dsn)
            self._init_mysql_db()
        else:
            self.dialect = 'sqlite'
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / 'uploads').mkdir(exist_ok=True)
            self.path = self.root / 'market.sqlite3'
        self._init_schema()

    # ---- MySQL 相关 ----
    @staticmethod
    def _parse_mysql_dsn(dsn):
        p = urlparse(dsn)
        return {
            'host': p.hostname or '127.0.0.1',
            'port': p.port or 3306,
            'user': p.username or 'root',
            'password': p.password or '',
            'db': (p.path or '').lstrip('/') or 'huali_corner',
        }

    def _mysql_connect(self, db=None, pool=None):
        import pymysql
        cfg = dict(self.mysql)
        if db is not None:
            cfg['db'] = db
        raw = pymysql.connect(
            host=cfg['host'], port=cfg['port'], user=cfg['user'],
            password=cfg['password'], database=cfg.get('db'),
            charset='utf8mb4', autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )
        return _Conn(raw, 'mysql', _rewrite_mysql, pool=pool)

    def _init_mysql_db(self):
        """确保目标库存在（不存在则建库），并预建连接池。"""
        import pymysql
        cfg = self.mysql
        # 先连到服务端（不带库名）建库。
        raw = pymysql.connect(
            host=cfg['host'], port=cfg['port'], user=cfg['user'],
            password=cfg['password'], charset='utf8mb4', autocommit=True,
            cursorclass=pymysql.cursors.DictCursor, connect_timeout=10,
        )
        try:
            with raw.cursor() as cur:
                cur.execute('CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4' % cfg['db'])
        finally:
            raw.close()
        # 建连接池（懒填充，connect() 时按需补到合适数量）。
        self._pool, self._pool_factory = _pool_for(
            (cfg['host'], cfg['port'], cfg['user'], cfg['db']),
            lambda: self._mysql_connect(pool=None),
        )

    def _mysql_get_conn(self):
        try:
            raw = self._pool.get_nowait()
            if raw.open:  # 连接还活着
                return _Conn(raw, 'mysql', _rewrite_mysql, pool=self._pool)
        except queue.Empty:
            pass
        # 新连接（带 pool 引用，close 时归还）。
        return self._mysql_connect(pool=self._pool)

    # ---- 统一接口 ----
    def connect(self):
        if self.dialect == 'sqlite':
            c = sqlite3.connect(self.path, timeout=20)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            return _Conn(c, 'sqlite', None)
        return self._mysql_get_conn()

    def _init_schema(self):
        if self.dialect == 'sqlite':
            with self.connect() as c:
                # 这里刻意使用默认的删除日志模式，而不是 WAL。
                # 原因：本项目的写法是「每次事务新开连接、用完即关」，而 WAL 模式下
                # 最后一个连接关闭时会自动 checkpoint 并删除 -wal / -shm 文件。
                # 如果此刻另一个线程刚开好连接准备写入，它找不到 wal 文件，就会抛
                # sqlite3.OperationalError: attempt to write a readonly database。
                # 实测并发写约 7% 失败。改用删除日志模式后为 0 失败。
                # 这一句同时把已经处于 WAL 的旧数据库迁移回删除日志模式。
                c.execute('PRAGMA journal_mode=DELETE')
                c.executescript(SQLITE_SCHEMA)
                if 'schedule_confirmed' not in [x[1] for x in c.execute('PRAGMA table_info(orders)')]:
                    c.execute('ALTER TABLE orders ADD COLUMN schedule_confirmed INTEGER DEFAULT 0')
                if 'status' not in [x[1] for x in c.execute('PRAGMA table_info(users)')]:
                    c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
                if 'promoted_until' not in [x[1] for x in c.execute('PRAGMA table_info(products)')]:
                    c.execute('ALTER TABLE products ADD COLUMN promoted_until REAL DEFAULT 0')
                if 'want_id' not in [x[1] for x in c.execute('PRAGMA table_info(orders)')]:
                    c.execute('ALTER TABLE orders ADD COLUMN want_id INTEGER')
                if 'delisted_by' not in [x[1] for x in c.execute('PRAGMA table_info(products)')]:
                    c.execute('ALTER TABLE products ADD COLUMN delisted_by INTEGER DEFAULT 0')
                if 'last_login' not in [x[1] for x in c.execute('PRAGMA table_info(users)')]:
                    c.execute('ALTER TABLE users ADD COLUMN last_login REAL DEFAULT 0')
                if 'moderation' not in [x[1] for x in c.execute('PRAGMA table_info(messages)')]:
                    c.execute('ALTER TABLE messages ADD COLUMN moderation TEXT')
                if 'moderation' not in [x[1] for x in c.execute('PRAGMA table_info(posts)')]:
                    c.execute('ALTER TABLE posts ADD COLUMN moderation TEXT')
                if 'removed' not in [x[1] for x in c.execute('PRAGMA table_info(posts)')]:
                    c.execute('ALTER TABLE posts ADD COLUMN removed INTEGER DEFAULT 0')
                if 'parent_id' not in [x[1] for x in c.execute('PRAGMA table_info(comments)')]:
                    c.execute('ALTER TABLE comments ADD COLUMN parent_id INTEGER DEFAULT 0')
                # 评论软删除：违法/辱骂评论要能下掉，但记录留着可回溯。
                if 'removed' not in [x[1] for x in c.execute('PRAGMA table_info(comments)')]:
                    c.execute('ALTER TABLE comments ADD COLUMN removed INTEGER DEFAULT 0')
                if 'last_read_id' not in [x[1] for x in c.execute('PRAGMA table_info(members)')]:
                    c.execute('ALTER TABLE members ADD COLUMN last_read_id INTEGER DEFAULT 0')
                if 'post_id' not in [x[1] for x in c.execute('PRAGMA table_info(notifications)')]:
                    c.execute('ALTER TABLE notifications ADD COLUMN post_id INTEGER')
                # 商品处置（下架/恢复/复核）通知要能点进商品详情，补 product_id 引用列。
                if 'product_id' not in [x[1] for x in c.execute('PRAGMA table_info(notifications)')]:
                    c.execute('ALTER TABLE notifications ADD COLUMN product_id INTEGER')
                if 'accepted_at' not in [x[1] for x in c.execute('PRAGMA table_info(offers)')]:
                    c.execute('ALTER TABLE offers ADD COLUMN accepted_at REAL')
                if 'support' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute('ALTER TABLE rooms ADD COLUMN support INTEGER DEFAULT 0')
                if 'assignee' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute('ALTER TABLE rooms ADD COLUMN assignee INTEGER DEFAULT 0')
                if 'ticket_id' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute('ALTER TABLE rooms ADD COLUMN ticket_id INTEGER DEFAULT 0')
                # 客服会话生命周期：open / closed。关闭时消息归档（removed=3），
                # 双方会话列表不再显示；重新咨询重新开启并清空上一轮。
                if 'support_status' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute("ALTER TABLE rooms ADD COLUMN support_status TEXT DEFAULT 'open'")
                if 'support_closed_at' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute('ALTER TABLE rooms ADD COLUMN support_closed_at REAL DEFAULT 0')
                if 'support_closed_by' not in [x[1] for x in c.execute('PRAGMA table_info(rooms)')]:
                    c.execute("ALTER TABLE rooms ADD COLUMN support_closed_by TEXT DEFAULT ''")
                c.execute("INSERT OR IGNORE INTO rooms(id,kind,name) VALUES(1,'general','广州校区总聊')")
                # 账号领域的增量迁移（degree_level / study_status / profile_version /
                # avatar_upload_id 四个列 + user_avatar_uploads 表）。放在这里而不是
                # 账号模块自己初始化，是因为它必须和其它补列跑在同一个启动事务里：
                # 任何一处失败都要整体回滚，不能留下「列建了、表没建」的半截库。
                # 延迟导入：core 不该在模块加载期依赖 account 领域。
                from ..account.migrations import migrate_account
                migrate_account(c)
        else:
            with self.connect() as c:
                c.executescript(MYSQL_SCHEMA)
                # CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，老 MySQL 库要单独 ALTER。
                # MySQL 没有 ADD COLUMN IF NOT EXISTS，重复执行靠异常兜住（列已存在即视为完成）。
                for ddl in ('ALTER TABLE comments ADD COLUMN removed INT DEFAULT 0',):
                    try:
                        c.execute(ddl)
                    except Exception:
                        pass
                c.execute("INSERT IGNORE INTO rooms(id,kind,name) VALUES(1,'general','广州校区总聊')")

    @contextmanager
    def tx(self):
        with _WRITE:
            c = self.connect()
            try:
                c.execute('BEGIN IMMEDIATE')
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    def rows(self, q, args=()):
        with self.connect() as c:
            return [dict(x) for x in c.execute(q, args).fetchall()]

    def row(self, q, args=()):
        r = self.rows(q, args)
        return r[0] if r else None
