"""Additive community migrations, including durable per-member read cursors."""


def migrate_community(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(members)')}
    if 'last_read_message_id' not in columns:
        connection.execute('ALTER TABLE members ADD COLUMN last_read_message_id INTEGER NOT NULL DEFAULT 0')
    connection.execute('CREATE INDEX IF NOT EXISTS messages_room_cursor ON messages(room_id,id)')
    connection.execute("""CREATE TABLE IF NOT EXISTS service_posts(
        post_id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL,service_type TEXT NOT NULL,
        title TEXT NOT NULL,reward INTEGER,place TEXT NOT NULL,deadline REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',request_key TEXT NOT NULL,UNIQUE(user_id,request_key))""")
    connection.execute('CREATE INDEX IF NOT EXISTS service_posts_listing ON service_posts(status,post_id)')
