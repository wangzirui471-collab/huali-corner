import sqlite3, json, time, threading
from contextlib import contextmanager
from pathlib import Path

# 写事务串行锁。
# SQLite 在 Windows 上让多个线程各自开写事务时，会随机抛
# sqlite3.OperationalError: attempt to write a readonly database —— 即使数据库
# 已经处于 WAL 模式也一样（实测 30 并发写约 7% 失败）。加锁后为 0 失败。
# 本站写入量很小（校园场景，主要是发布、下单、聊天），串行化的代价可以忽略；
# 读操作不经过这把锁，WAL 模式下读仍然并发。
_WRITE = threading.RLock()

SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,phone TEXT UNIQUE,nickname TEXT NOT NULL,college TEXT DEFAULT '计算机工程学院',major TEXT DEFAULT '',education TEXT DEFAULT '本科',bio TEXT DEFAULT '',role TEXT DEFAULT 'user',score INTEGER DEFAULT 100 CHECK(score BETWEEN 0 AND 100));
CREATE TABLE IF NOT EXISTS otp(phone TEXT PRIMARY KEY,digest TEXT,expires REAL,attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS password_credentials(user_id INTEGER PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,rounds INTEGER NOT NULL,recovery_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_attempts(phone TEXT PRIMARY KEY,attempts INTEGER NOT NULL,reset_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,user_id INTEGER,path TEXT,digest TEXT,angle TEXT,private INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,seller_id INTEGER,title TEXT,category TEXT,price INTEGER,delivery_fee INTEGER,delivery TEXT,region TEXT,status TEXT DEFAULT 'available',data TEXT,created REAL);
CREATE TABLE IF NOT EXISTS reactions(user_id INTEGER,product_id INTEGER,kind TEXT,PRIMARY KEY(user_id,product_id,kind));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,buyer_id INTEGER,seller_id INTEGER,items TEXT,subtotal INTEGER,delivery_fee INTEGER,total INTEGER,delivery TEXT,address TEXT,appointment REAL,status TEXT,created REAL,paid_at REAL,delivered_at REAL,handover_at REAL,completed_at REAL,request_key TEXT,schedule_confirmed INTEGER DEFAULT 0,UNIQUE(buyer_id,request_key));
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
