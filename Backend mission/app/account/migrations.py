"""用户资料与专用头像的增量迁移。

只做两件事：给 users 补四个列、建一张 user_avatar_uploads 表。
不删列、不改旧列类型、不清数据，可以反复执行。

为什么单独一个文件、而不是继续堆进 core/database.py：
那边已经有十来个「老库自动补列」的 ALTER，再加四列一张表会把原有注释淹没；
而这些列只属于账号领域，将来接口下线时能整块删掉。

历史 education（本科/专科/已毕业）只在**本次新建 degree_level/study_status**
时映射一次。映射只写进新列，不回写 education——旧接口仍在读它，
两边各说各的会让老客户端看到自己没改过的值突然变了。
"""

# 学历层次 / 在读状态的机器值。与前端 components/user-profile.js 的选项一一对应，
# 改这里必须同步改那边，否则用户会选到一个后端不认的值。
DEGREE_LEVELS = ('bachelor', 'junior_college', 'other', 'unspecified')
STUDY_STATUSES = ('studying', 'graduated', 'other', 'unspecified')

_NEW_COLUMNS = (
    ('degree_level', "TEXT NOT NULL DEFAULT 'unspecified'"),
    ('study_status', "TEXT NOT NULL DEFAULT 'unspecified'"),
    # 乐观并发用的版本号：客户端读到几，保存时就得带几。两个人同时改同一份资料时，
    # 后到的那次会因为版本对不上被拒成 409，而不是悄悄覆盖前一个人的改动。
    ('profile_version', 'INTEGER NOT NULL DEFAULT 0'),
    # 当前选中的头像 upload_id（ua_<32位hex>）。为空表示用默认头像。
    ('avatar_upload_id', 'TEXT'),
    # 年级（如「2023级」）。注册时选择，空串表示未填——老账号不回填猜测值。
    ('grade', "TEXT NOT NULL DEFAULT ''"),
)

# 旧 education 到新列的投影。「已毕业」只表示状态，不猜学历；
# 「其他」与空值都留 unspecified——不能把用户没填过的东西当成他选过。
_EDUCATION_TO_DEGREE = (
    ('本科', 'bachelor'),
    ('专科', 'junior_college'),
)


def migrate_account(connection):
    """在 Store 初始化的同一个连接上补齐账号领域的列与表。

    不提交事务：调用方（_init_schema）本来就在自己的事务里。
    """
    columns = [row[1] for row in connection.execute('PRAGMA table_info(users)')]
    first_time = 'degree_level' not in columns

    for name, definition in _NEW_COLUMNS:
        if name not in columns:
            connection.execute('ALTER TABLE users ADD COLUMN %s %s' % (name, definition))

    if first_time:
        for legacy, machine in _EDUCATION_TO_DEGREE:
            connection.execute('UPDATE users SET degree_level=? WHERE education=?', (machine, legacy))
        connection.execute("UPDATE users SET study_status='graduated' WHERE education='已毕业'")

    connection.execute('''
        CREATE TABLE IF NOT EXISTS user_avatar_uploads(
            upload_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            digest TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    ''')
    connection.execute('CREATE INDEX IF NOT EXISTS user_avatar_uploads_owner ON user_avatar_uploads(user_id)')
