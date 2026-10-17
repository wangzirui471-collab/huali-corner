"""Server-operator-only role demotion; no HTTP endpoint and no schema migration."""
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Optional


def demote_account(database: Path, nickname: str, user_id: Optional[int] = None) -> dict:
    database = Path(database).resolve()
    if not database.is_file():
        raise FileNotFoundError('找不到已有数据库：' + str(database))
    if not isinstance(nickname, str) or not nickname.strip():
        raise ValueError('请指定要降权的昵称')
    if user_id is not None and (type(user_id) is not int or user_id <= 0):
        raise ValueError('账号ID必须是正整数')
    nickname = nickname.strip()
    with closing(sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE')
        try:
            required = {'users': {'id', 'nickname', 'role', 'status'},
                        'sessions': {'user_id'}, 'tickets': {'assignee', 'status'},
                        'audit': {'target', 'type', 'reason', 'created'}, 'settings': {'key', 'value'}}
            for table, columns in required.items():
                actual = {row[1] for row in connection.execute('PRAGMA table_info(' + table + ')')}
                if not columns.issubset(actual):
                    raise ValueError('这不是支持的试用账号库，请核对现用数据目录')
            mode = connection.execute("SELECT value FROM settings WHERE key='auth_mode'").fetchone()
            if not mode or mode['value'] != 'trial':
                raise ValueError('请选择可登录试用版的数据目录，不操作演示库')
            matches = connection.execute('SELECT id,nickname,role,status FROM users WHERE nickname=? COLLATE NOCASE', (nickname,)).fetchall()
            if user_id is not None:
                matches = [row for row in matches if row['id'] == user_id]
            if not matches:
                raise ValueError('该数据库中没有匹配的账号：' + nickname)
            if len(matches) != 1:
                raise ValueError('找到多个同名账号，请用 --user-id 指定ID：' + ', '.join(str(row['id']) for row in matches))
            target = matches[0]
            result = dict(id=target['id'], nickname=target['nickname'], previous_role=target['role'],
                          role='user', changed=False, revoked_sessions=0, released_tickets=0, backup_path=None)
            if target['role'] == 'user':
                connection.rollback()
                return result
            if target['role'] not in ['admin', 'support']:
                raise ValueError('未知的平台角色，请先人工核对：' + target['role'])
            if target['role'] == 'admin' and target['status'] == 'active':
                remaining = connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='active' AND id<>?", (target['id'],)).fetchone()[0]
                if not remaining:
                    raise ValueError('这是最后一个启用的管理员，请先配置另一个管理员再降权')
            backup_dir = database.parent / 'backups'
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / ('before-role-demotion-' + str(time.time_ns()) + '.sqlite3')
            # A separate read connection backs up committed data while this
            # IMMEDIATE transaction prevents another writer changing the target.
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(backup)) as destination:
                    source.backup(destination)
            connection.execute("UPDATE users SET role='user' WHERE id=?", (target['id'],))
            revoked = connection.execute('DELETE FROM sessions WHERE user_id=?', (target['id'],)).rowcount
            released = connection.execute("UPDATE tickets SET assignee=NULL,status=CASE WHEN status='processing' THEN 'open' ELSE status END WHERE assignee=? AND status NOT IN ('resolved','rejected')", (target['id'],)).rowcount
            reason = '服务器操作者将账号由' + target['role'] + '降为user；撤销' + str(revoked) + '个会话，退回' + str(released) + '个未结工单'
            connection.execute('INSERT INTO audit(target,type,reason,created) VALUES(?,?,?,?)',
                               (target['id'], 'operator_role_demotion', reason, time.time()))
            connection.commit()
            result.update(changed=True, revoked_sessions=revoked, released_tickets=released, backup_path=str(backup))
            return result
        except Exception:
            connection.rollback()
            raise
