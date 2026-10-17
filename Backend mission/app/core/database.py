"""SQLite 连接、事务与表结构。

注意两处不能动的设计（详见文件内注释）：
  1. 不使用 WAL，用默认的删除日志模式
  2. 写事务必须串行化（_WRITE 锁）
改动前请先读下方注释，那里记录了不这么做会出什么故障。
"""
import sqlite3, json, time, threading
from contextlib import contextmanager
from pathlib import Path

# 写事务串行锁：让并发写入在 Python 层排队，而不是各自去撞 SQLite 的写锁。
#
# 关于它【不】负责什么，写清楚以免后人误会：
#   · 它不负责防止超卖 —— 那是 tx() 里 BEGIN IMMEDIATE 的职责：事务一开始就申请
#     SQLite 的写锁，后到的事务必须等待，读到的是已提交的新状态。实测用不同请求键
#     三线程抢购，有锁无锁都是 0 次超卖。
#   · 它也不是「attempt to write a readonly database」的修复 —— 那个问题的根因是
#     WAL 模式下最后一个连接关闭时 checkpoint 并删除 -wal/-shm，已由改用删除日志模式解决。
#     关掉 WAL 之后实测 30 并发写 × 5 轮，有锁无锁都是 0 失败。
#
# 留着它的理由只有一个：写入在 Python 层确定性排队，不必依赖 SQLite busy_timeout
# 的重试行为，也不会有 database is locked 在极端争用时冒出来。本站写入量很小。
# 读操作不经过这把锁，不受影响。
_WRITE = threading.RLock()

SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,phone TEXT UNIQUE,nickname TEXT NOT NULL,college TEXT DEFAULT '计算机工程学院',major TEXT DEFAULT '',education TEXT DEFAULT '本科',bio TEXT DEFAULT '',role TEXT DEFAULT 'user',score INTEGER DEFAULT 100 CHECK(score BETWEEN 0 AND 100),status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS otp(phone TEXT PRIMARY KEY,digest TEXT,expires REAL,attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS password_credentials(user_id INTEGER PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,rounds INTEGER NOT NULL,recovery_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts(phone TEXT PRIMARY KEY,attempts INTEGER NOT NULL,reset_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,user_id INTEGER,path TEXT,digest TEXT,angle TEXT,private INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,seller_id INTEGER,title TEXT,category TEXT,price INTEGER,delivery_fee INTEGER,delivery TEXT,region TEXT,status TEXT DEFAULT 'available',data TEXT,created REAL,promoted_until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS reactions(user_id INTEGER,product_id INTEGER,kind TEXT,PRIMARY KEY(user_id,product_id,kind));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,buyer_id INTEGER,seller_id INTEGER,items TEXT,subtotal INTEGER,delivery_fee INTEGER,total INTEGER,delivery TEXT,address TEXT,appointment REAL,status TEXT,created REAL,paid_at REAL,delivered_at REAL,handover_at REAL,completed_at REAL,request_key TEXT,schedule_confirmed INTEGER DEFAULT 0,want_id INTEGER,UNIQUE(buyer_id,request_key));
CREATE TABLE IF NOT EXISTS order_changes(id INTEGER PRIMARY KEY,order_id INTEGER,proposer INTEGER,appointment REAL,address TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS order_notes(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,body TEXT,created REAL);
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,order_id INTEGER,kind TEXT,amount INTEGER,created REAL,UNIQUE(order_id,kind));
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER,order_id INTEGER,product_id INTEGER,type TEXT,subject TEXT,body TEXT,status TEXT DEFAULT 'open',assignee INTEGER,outcome TEXT,reason TEXT,created REAL);
CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY,ticket_id INTEGER,user_id INTEGER,body TEXT,internal INTEGER DEFAULT 0,created REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER,target INTEGER,type TEXT,delta INTEGER,reason TEXT,ticket_id INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,rating INTEGER,body TEXT,created REAL,UNIQUE(order_id,user_id));
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,kind TEXT,name TEXT,college TEXT DEFAULT '',sequence INTEGER DEFAULT 1,pair TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS members(room_id INTEGER,user_id INTEGER,muted INTEGER DEFAULT 0,role TEXT DEFAULT 'member',PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,room_id INTEGER,user_id INTEGER,body TEXT,created REAL,request_key TEXT,removed INTEGER DEFAULT 0,UNIQUE(user_id,room_id,request_key));
CREATE TABLE IF NOT EXISTS blocks(user_id INTEGER,target INTEGER,PRIMARY KEY(user_id,target));
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,user_id INTEGER,topic TEXT,body TEXT,created REAL);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,post_id INTEGER,user_id INTEGER,body TEXT,created REAL);
CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY,product_id INTEGER,buyer_id INTEGER,amount INTEGER,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS nominations(id INTEGER PRIMARY KEY,user_id INTEGER,room_id INTEGER,reason TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS wants(id INTEGER PRIMARY KEY,user_id INTEGER,keyword TEXT,budget INTEGER,description TEXT,status TEXT DEFAULT 'open',created REAL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,order_id INTEGER,ticket_id INTEGER,body TEXT,read_at REAL,created REAL);
'''

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'uploads').mkdir(exist_ok=True)
        self.path=self.root/'market.sqlite3'
        with self.connect() as c:
            # 这里刻意使用默认的删除日志模式，而不是 WAL。
            # 原因：本项目的写法是「每次事务新开连接、用完即关」，而 WAL 模式下
            # 最后一个连接关闭时会自动 checkpoint 并删除 -wal / -shm 文件。
            # 如果此刻另一个线程刚开好连接准备写入，它找不到 wal 文件，就会抛
            # sqlite3.OperationalError: attempt to write a readonly database。
            # 实测并发写约 7% 失败。改用删除日志模式后为 0 失败（并发读的损失可以忽略，
            # 校园场景读多写少且写入已由 _WRITE 串行化）。
            # 这一句同时把已经处于 WAL 的旧数据库迁移回删除日志模式。
            c.execute('PRAGMA journal_mode=DELETE')
            c.executescript(SCHEMA)
            if 'schedule_confirmed' not in [x[1] for x in c.execute('PRAGMA table_info(orders)')]:c.execute('ALTER TABLE orders ADD COLUMN schedule_confirmed INTEGER DEFAULT 0')
            # 账号状态：active / banned(封禁) / deactivated(注销)。老库自动补列。
            if 'status' not in [x[1] for x in c.execute('PRAGMA table_info(users)')]:c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
            # 付费置顶到期时间戳（0=未置顶）。老库自动补列。
            if 'promoted_until' not in [x[1] for x in c.execute('PRAGMA table_info(products)')]:c.execute('ALTER TABLE products ADD COLUMN promoted_until REAL DEFAULT 0')
            # 订单关联的求购编号（NULL=普通下单）。没有它就无法在取消/退款时回滚求购状态，
            # 求购会永久停在 matched。老库自动补列。
            if 'want_id' not in [x[1] for x in c.execute('PRAGMA table_info(orders)')]:c.execute('ALTER TABLE orders ADD COLUMN want_id INTEGER')
            c.execute("INSERT OR IGNORE INTO rooms(id,kind,name) VALUES(1,'general','广州校区总聊')")
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c
    @contextmanager
    def tx(self):
        with _WRITE:
            c=self.connect()
            try:
                c.execute('BEGIN IMMEDIATE');yield c;c.commit()
            except Exception:c.rollback();raise
            finally:c.close()
    def rows(self,q,args=()):
        with self.connect() as c:return [dict(x) for x in c.execute(q,args).fetchall()]
    def row(self,q,args=()):
        r=self.rows(q,args);return r[0] if r else None
