CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER,target INTEGER,type TEXT,delta INTEGER,reason TEXT,ticket_id INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS auth_attempts(phone TEXT PRIMARY KEY,attempts INTEGER NOT NULL,reset_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS blocks(user_id INTEGER,target INTEGER,PRIMARY KEY(user_id,target));
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,post_id INTEGER,user_id INTEGER,body TEXT,created REAL, parent_id INTEGER DEFAULT 0, removed INTEGER DEFAULT 0);
-- 好友关系：friend_api.py 的好友门禁与 community/service.py 的 is_friend 都要查它。
-- 本地 schema（app/core/database.py）一直有这张表，云端漏了会导致私聊发消息 500。
-- 定义与本地 SQLite 版逐字一致（三处 schema 必须同步）。
CREATE TABLE IF NOT EXISTS friendships(id INTEGER PRIMARY KEY,requester INTEGER NOT NULL,target INTEGER NOT NULL,message TEXT DEFAULT '',want_id INTEGER DEFAULT 0,status TEXT DEFAULT 'pending',created REAL,decided REAL,UNIQUE(requester,target));
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,order_id INTEGER,kind TEXT,amount INTEGER,created REAL,UNIQUE(order_id,kind));
CREATE TABLE IF NOT EXISTS members(room_id INTEGER,user_id INTEGER,muted INTEGER DEFAULT 0,role TEXT DEFAULT 'member', last_read_id INTEGER DEFAULT 0,PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS message_hides(user_id INTEGER,message_id INTEGER,created REAL,PRIMARY KEY(user_id,message_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,room_id INTEGER,user_id INTEGER,body TEXT,created REAL,request_key TEXT,removed INTEGER DEFAULT 0, moderation TEXT,UNIQUE(user_id,room_id,request_key));
CREATE TABLE IF NOT EXISTS nominations(id INTEGER PRIMARY KEY,user_id INTEGER,room_id INTEGER,reason TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,order_id INTEGER,ticket_id INTEGER,body TEXT,read_at REAL,created REAL, post_id INTEGER, product_id INTEGER);
CREATE TABLE IF NOT EXISTS offers(id INTEGER PRIMARY KEY,product_id INTEGER,buyer_id INTEGER,amount INTEGER,status TEXT DEFAULT 'pending',created REAL, accepted_at REAL);
CREATE TABLE IF NOT EXISTS order_changes(id INTEGER PRIMARY KEY,order_id INTEGER,proposer INTEGER,appointment REAL,address TEXT,status TEXT DEFAULT 'pending',created REAL);
CREATE TABLE IF NOT EXISTS order_notes(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,body TEXT,created REAL);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,buyer_id INTEGER,seller_id INTEGER,items TEXT,subtotal INTEGER,delivery_fee INTEGER,total INTEGER,delivery TEXT,address TEXT,appointment REAL,status TEXT,created REAL,paid_at REAL,delivered_at REAL,handover_at REAL,completed_at REAL,request_key TEXT,schedule_confirmed INTEGER DEFAULT 0, want_id INTEGER,UNIQUE(buyer_id,request_key));
CREATE TABLE IF NOT EXISTS otp(phone TEXT PRIMARY KEY,digest TEXT,expires REAL,attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS password_credentials(user_id INTEGER PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,rounds INTEGER NOT NULL,recovery_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,user_id INTEGER,topic TEXT,body TEXT,created REAL, moderation TEXT, removed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,seller_id INTEGER,title TEXT,category TEXT,price INTEGER,delivery_fee INTEGER,delivery TEXT,region TEXT,status TEXT DEFAULT 'available',data TEXT,created REAL, promoted_until REAL DEFAULT 0, delisted_by INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reactions(user_id INTEGER,product_id INTEGER,kind TEXT,PRIMARY KEY(user_id,product_id,kind));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,order_id INTEGER,user_id INTEGER,rating INTEGER,body TEXT,created REAL,UNIQUE(order_id,user_id));
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,kind TEXT,name TEXT,college TEXT DEFAULT '',sequence INTEGER DEFAULT 1,pair TEXT UNIQUE, support INTEGER DEFAULT 0, assignee INTEGER DEFAULT 0, ticket_id INTEGER DEFAULT 0, support_status TEXT DEFAULT 'open', support_closed_at REAL DEFAULT 0, support_closed_by TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS room_pins(user_id INTEGER,room_id INTEGER,pinned_at REAL,PRIMARY KEY(user_id,room_id));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY,ticket_id INTEGER,user_id INTEGER,body TEXT,internal INTEGER DEFAULT 0,created REAL);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER,order_id INTEGER,product_id INTEGER,type TEXT,subject TEXT,body TEXT,status TEXT DEFAULT 'open',assignee INTEGER,outcome TEXT,reason TEXT,created REAL);
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,user_id INTEGER,path TEXT,digest TEXT,angle TEXT,private INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS user_avatar_uploads(
            upload_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            digest TEXT NOT NULL,
            created_at REAL NOT NULL
        );
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,phone TEXT UNIQUE,nickname TEXT NOT NULL,college TEXT DEFAULT '计算机工程学院',major TEXT DEFAULT '',education TEXT DEFAULT '本科',bio TEXT DEFAULT '',role TEXT DEFAULT 'user',score INTEGER DEFAULT 100 CHECK(score BETWEEN 0 AND 100), status TEXT DEFAULT 'active', last_login REAL DEFAULT 0, degree_level TEXT NOT NULL DEFAULT 'unspecified', study_status TEXT NOT NULL DEFAULT 'unspecified', profile_version INTEGER NOT NULL DEFAULT 0, avatar_upload_id TEXT, grade TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS wants(id INTEGER PRIMARY KEY,user_id INTEGER,keyword TEXT,budget INTEGER,description TEXT,status TEXT DEFAULT 'open',created REAL);
CREATE INDEX IF NOT EXISTS user_avatar_uploads_owner ON user_avatar_uploads(user_id);
