import sqlite3, json, time
from contextlib import contextmanager
from pathlib import Path

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
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,fields TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,status TEXT NOT NULL DEFAULT 'active',updated_at REAL NOT NULL,published_product_id INTEGER,source_product_id INTEGER);
'''

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'uploads').mkdir(exist_ok=True)
        self.path=self.root/'market.sqlite3'
        with self.connect() as c:
            c.executescript(SCHEMA)
            if 'schedule_confirmed' not in [x[1] for x in c.execute('PRAGMA table_info(orders)')]:c.execute('ALTER TABLE orders ADD COLUMN schedule_confirmed INTEGER DEFAULT 0')
            for name, definition in [('stock_key', 'TEXT'), ('source_draft_id', 'TEXT')]:
                if name not in [column[1] for column in c.execute('PRAGMA table_info(products)')]:
                    c.execute('ALTER TABLE products ADD COLUMN '+name+' '+definition)
            c.execute("UPDATE products SET stock_key='legacy:'||id WHERE stock_key IS NULL")
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS products_source_draft ON products(source_draft_id) WHERE source_draft_id IS NOT NULL')
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS products_live_stock ON products(stock_key) WHERE status IN ('available','reserved','sold')")
            c.execute('CREATE INDEX IF NOT EXISTS drafts_user_status ON drafts(user_id,status,updated_at)')
            additions = {
                'users': [('is_active', 'INTEGER NOT NULL DEFAULT 1'), ('trading_blocked', 'INTEGER NOT NULL DEFAULT 0')],
                'tickets': [('refund_mode', "TEXT NOT NULL DEFAULT 'refund_only'"), ('return_sent_at', 'REAL'),
                            ('return_received_at', 'REAL'), ('requested_amount', 'INTEGER')],
                'audit': [('rule_key', "TEXT NOT NULL DEFAULT ''"), ('reversal_of', 'INTEGER'),
                          ('score_before', 'INTEGER'), ('score_after', 'INTEGER')],
            }
            for table, columns in additions.items():
                existing = {column[1] for column in c.execute('PRAGMA table_info('+table+')')}
                for name, definition in columns:
                    if name not in existing:
                        c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS audit_reversal_once ON audit(reversal_of) WHERE reversal_of IS NOT NULL')
            c.execute("INSERT OR IGNORE INTO rooms(id,kind,name) VALUES(1,'general','广州校区总聊')")
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
        return c
    @contextmanager
    def tx(self):
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE');yield c;c.commit()
        except Exception:c.rollback();raise
        finally:c.close()
    def rows(self,q,args=()):
        with self.connect() as c:return [dict(x) for x in c.execute(q,args).fetchall()]
    def row(self,q,args=()):
        r=self.rows(q,args);return r[0] if r else None
