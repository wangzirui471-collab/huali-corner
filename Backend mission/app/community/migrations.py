"""Additive community migrations, including durable per-member read cursors."""


def migrate_community(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(members)')}
    if 'last_read_message_id' not in columns:
        connection.execute('ALTER TABLE members ADD COLUMN last_read_message_id INTEGER NOT NULL DEFAULT 0')
    connection.execute('CREATE INDEX IF NOT EXISTS messages_room_cursor ON messages(room_id,id)')
