"""B-side U01 contract tests; no production wiring or real user data."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import gc
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.core.database import SCHEMA
from app.core.errors import DomainError
from app.market import Market

try:
    from app.account.migrations import migrate_account
    from app.account.profiles import UserProfiles
except ModuleNotFoundError:
    migrate_account = None
    UserProfiles = None


class AccountMigrationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(migrate_account, 'U01 migrate_account is not implemented')
        self.connection = sqlite3.connect(':memory:')
        self.addCleanup(self.connection.close)
        self.connection.executescript('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, phone TEXT, nickname TEXT, education TEXT,
                role TEXT, score INTEGER
            );
            CREATE TABLE orders (id INTEGER PRIMARY KEY, buyer_id INTEGER, items TEXT);
            INSERT INTO orders VALUES (51, 1, 'immutable order snapshot');
        ''')
        for uid, education in enumerate(['本科', '专科', '已毕业', '其他', '', '未知旧值', None], 1):
            self.connection.execute(
                'INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)',
                (uid, f'139000000{uid:02}', '旧同学', education, 'support', 73),
            )

    def test_legacy_values_map_without_guessing_or_changing_old_fields(self):
        before = self.connection.execute('SELECT * FROM users').fetchall()
        migrate_account(self.connection)
        expected = [
            ('bachelor', 'unspecified'), ('junior_college', 'unspecified'),
            ('unspecified', 'graduated'), *[('unspecified', 'unspecified')] * 4,
        ]
        self.assertEqual(
            self.connection.execute('SELECT degree_level, study_status FROM users ORDER BY id').fetchall(),
            expected,
        )
        self.assertEqual(
            self.connection.execute('SELECT id,phone,nickname,education,role,score FROM users').fetchall(),
            before,
        )
        self.assertEqual(self.connection.execute('SELECT * FROM orders').fetchall(),
                         [(51, 1, 'immutable order snapshot')])

    def test_repeat_migration_preserves_choices_versions_and_avatar(self):
        migrate_account(self.connection)
        self.connection.execute('''
            UPDATE users SET degree_level='other',study_status='studying',
                profile_version=9,avatar_upload_id='already-selected' WHERE id=3
        ''')
        before = self.connection.execute('SELECT * FROM users').fetchall()
        migrate_account(self.connection)
        self.assertEqual(self.connection.execute('SELECT * FROM users').fetchall(), before)

    def test_partial_migration_preserves_existing_degree_column(self):
        self.connection.execute("ALTER TABLE users ADD COLUMN degree_level TEXT DEFAULT 'other'")
        migrate_account(self.connection)
        self.assertEqual(self.connection.execute(
            'SELECT degree_level,study_status FROM users WHERE id=3').fetchone(),
            ('other', 'graduated'))

    def test_partial_migration_preserves_existing_status_column(self):
        self.connection.execute("ALTER TABLE users ADD COLUMN study_status TEXT DEFAULT 'other'")
        migrate_account(self.connection)
        self.assertEqual(self.connection.execute(
            'SELECT degree_level,study_status FROM users WHERE id=1').fetchone(),
            ('bachelor', 'other'))

    def test_new_columns_have_safe_defaults_for_future_accounts(self):
        migrate_account(self.connection)
        self.connection.execute("INSERT INTO users(id,nickname,education) VALUES(20,'新同学','本科')")
        self.assertEqual(self.connection.execute('''
            SELECT degree_level,study_status,profile_version,avatar_upload_id FROM users WHERE id=20
        ''').fetchone(), ('unspecified', 'unspecified', 0, None))

    def test_new_constraints_reject_invalid_values(self):
        migrate_account(self.connection)
        for column, value in [('degree_level', '本科'), ('study_status', 'student'),
                              ('profile_version', -1), ('profile_version', 1.5)]:
            with self.subTest(column=column, value=value), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(f'UPDATE users SET {column}=? WHERE id=1', (value,))

    def test_migration_works_with_row_factory_and_respects_caller_rollback(self):
        self.connection.commit()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('BEGIN')
        migrate_account(self.connection)
        self.connection.rollback()
        self.assertNotIn('degree_level', [r[1] for r in self.connection.execute('PRAGMA table_info(users)')])


class UserProfileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(UserProfiles, 'U01 UserProfiles is not implemented')
        self.tmp = tempfile.TemporaryDirectory(prefix='zj-user-profile-')
        self.addCleanup(self.clean_data)

        # Existing accounts must precede the first startup migration. Once A
        # wires migrate_account into Store, inserting these rows afterwards
        # would create new accounts with unspecified defaults, not legacy data.
        with closing(sqlite3.connect(Path(self.tmp.name) / 'market.sqlite3')) as connection:
            connection.executescript(SCHEMA)
            connection.execute('''
                INSERT INTO users(id,phone,nickname,education,role,score,major,bio)
                VALUES(101,'13900000101','甲同学','已毕业','user',89,'原专业','原简介')
            ''')
            connection.execute('''
                INSERT INTO users(id,phone,nickname,education,role,score)
                VALUES(102,'13900000102','乙同学','专科','support',77)
            ''')
            connection.execute("INSERT INTO settings VALUES('auth_mode','trial')")
            connection.commit()

        # Run the same tests before and after A adds UserProfiles to Market;
        # adding an already inherited base before Market would conflict in MRO.
        profile_market = Market
        if not issubclass(Market, UserProfiles):
            class ProfileMarket(UserProfiles, Market):
                pass

            profile_market = ProfileMarket
        self.market = profile_market(self.tmp.name, trial=True)
        with self.market.tx() as connection:
            migrate_account(connection)
            connection.execute("INSERT INTO sessions VALUES('synthetic-hash',101,9999999999)")
            connection.execute("INSERT INTO password_credentials VALUES(101,'salt','digest',1,'recovery-hash')")
            connection.execute('''
                INSERT INTO orders(id,buyer_id,seller_id,items,status,total)
                VALUES(201,101,102,'original snapshot','paid',1500)
            ''')

    def clean_data(self):
        # Baseline Store uses SQLite context managers without close(); release
        # its already-unreachable startup handles before Windows temp cleanup.
        gc.collect()
        self.tmp.cleanup()

    def row(self, query, args=()):
        with closing(self.market.connect()) as connection:
            row = connection.execute(query, args).fetchone()
            return dict(row) if row else None

    def snapshot(self):
        with closing(self.market.connect()) as connection:
            return {table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ['users', 'orders', 'sessions', 'password_credentials']}

    def save(self, **updates):
        payload = {'profile_version': self.market.user_profile(101)['profile_version'], **updates}
        return self.market.user_update_profile(101, payload)

    def expect_error(self, status, operation):
        before = self.snapshot()
        with self.assertRaises(DomainError) as error:
            operation()
        self.assertEqual(error.exception.status, status)
        self.assertEqual(self.snapshot(), before, 'rejected write changed persistent data')

    def test_dto_has_only_contract_fields_and_no_private_account_data(self):
        profile = self.market.user_profile(101)
        self.assertEqual(set(profile), {
            'id','nickname','college','major','education','bio','role','score',
            'degree_level','study_status','profile_version','avatar_upload_id','avatar_url',
        })
        self.assertEqual((profile['degree_level'], profile['study_status']), ('unspecified', 'graduated'))
        self.assertIsNone(profile['avatar_url'])
        self.assertIsNone(profile['avatar_upload_id'])
        self.assertEqual(profile['education'], '已毕业')

    def test_new_save_persists_both_options_and_returns_incremented_version(self):
        result = self.save(nickname='新昵称', major='软件工程', bio='继续分享',
                           degree_level='bachelor', study_status='studying')
        self.assertEqual(result['profile_version'], 1)
        self.assertEqual(result['education'], '本科')
        self.assertEqual(self.market.user_profile(101), result)
        self.assertEqual(self.row('SELECT nickname FROM users WHERE id=102')['nickname'], '乙同学')

    def test_degree_and_status_enum_combinations_project_legacy_education(self):
        for degree in ['bachelor','junior_college','other','unspecified']:
            for status in ['studying','graduated','other','unspecified']:
                with self.subTest(degree=degree, status=status):
                    result = self.save(degree_level=degree, study_status=status)
                    expected = '已毕业' if status == 'graduated' else {
                        'bachelor':'本科', 'junior_college':'专科',
                    }.get(degree, '其他')
                    self.assertEqual(result['education'], expected)

    def test_partial_new_save_preserves_omitted_fields(self):
        result = self.save(bio='只改简介')
        self.assertEqual((result['nickname'],result['major'],result['study_status']),
                         ('甲同学','原专业','graduated'))

    def test_maximum_lengths_accepted_and_blank_optional_fields_can_clear(self):
        result = self.save(nickname='名'*24, major='专'*80, bio='简'*300)
        self.assertEqual(len(result['bio']), 300)
        result = self.save(major='', bio='', degree_level='unspecified', study_status='unspecified')
        self.assertEqual((result['major'], result['bio'], result['education']), ('', '', '其他'))

    def test_invalid_text_is_rejected_instead_of_truncated_or_coerced(self):
        for key, values in {
            'nickname':['', '   ', '名'*25, 12, None, ['甲']],
            'major':['专'*81, 12, None], 'bio':['简'*301, {}, None],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.expect_error(400, lambda: self.save(**{key:value}))

    def test_invalid_enums_are_rejected(self):
        for key in ['degree_level', 'study_status']:
            for value in ['', '本科', 'student', None, True, 0, [], {}]:
                with self.subTest(key=key,value=value):
                    self.expect_error(400, lambda: self.save(**{key:value}))

    def test_version_is_required_and_must_be_nonnegative_integer(self):
        for value in [-1, True, False, 0.0, '0', None, [], {}]:
            with self.subTest(version=value):
                self.expect_error(400, lambda: self.market.user_update_profile(101, {'profile_version':value}))
        self.expect_error(400, lambda: self.market.user_update_profile(101, {'nickname':'甲'}))

    def test_unknown_or_protected_new_fields_rejected(self):
        for key in ['id','user_id','actor_id','phone','password','role','score','college',
                    'education','avatar_upload_id','avatar_url','is_active','trading_blocked','typo']:
            with self.subTest(field=key):
                self.expect_error(400, lambda: self.save(**{key:'forged'}))

    def test_nonobject_payload_rejected(self):
        for value in [None, [], 'bad', 0, True]:
            with self.subTest(payload=value):
                self.expect_error(400, lambda: self.market.user_update_profile(101, value))

    def test_missing_invalid_or_unknown_actor_rejected(self):
        for actor in [None, False, True, '101', 0, -1]:
            with self.subTest(actor=actor):
                self.expect_error(401, lambda: self.market.user_update_profile(actor, {'profile_version':0}))
        self.expect_error(404, lambda: self.market.user_update_profile(999, {'profile_version':0}))
        with self.assertRaises(DomainError):
            self.market.user_profile(None)

    def test_disabled_actor_cannot_save_even_with_valid_version(self):
        with self.market.tx() as connection:
            connection.execute('UPDATE users SET is_active=0 WHERE id=101')
        self.expect_error(403, lambda: self.save(nickname='不应保存'))
        self.expect_error(403, lambda: self.market.user_update_legacy_profile(101, {'nickname':'不应保存'}))

    def test_stale_version_returns_409_without_overwriting_newer_data(self):
        first = self.save(bio='先保存')
        self.expect_error(409, lambda: self.market.user_update_profile(
            101, {'profile_version':0, 'bio':'旧页面'}))
        self.assertEqual(self.market.user_profile(101), first)

    def test_competing_connections_allow_exactly_one_writer(self):
        barrier = threading.Barrier(2)

        def write(bio):
            barrier.wait()
            try:
                return self.market.user_update_profile(101, {'profile_version':0, 'bio':bio})
            except DomainError as error:
                return error.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['页面一', '页面二']))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count(409), 1)
        self.assertEqual(self.market.user_profile(101)['profile_version'], 1)

    def test_profile_save_cannot_change_auth_orders_or_privileges(self):
        before = self.snapshot()
        self.save(nickname='资料变更', degree_level='other', study_status='other')
        after = self.snapshot()
        for table in ['orders','sessions','password_credentials']:
            self.assertEqual(before[table], after[table])
        user = self.row('SELECT phone,role,score,is_active,trading_blocked FROM users WHERE id=101')
        self.assertEqual(user, {'phone':'13900000101','role':'user','score':89,
                                'is_active':1,'trading_blocked':0})

    def test_trial_college_fixed_and_nontrial_college_preserved(self):
        self.assertEqual(self.save()['college'], '计算机工程学院')
        self.market.trial = False
        with self.market.tx() as connection:
            connection.execute("UPDATE users SET college='历史学院' WHERE id=101")
        self.assertEqual(self.save(bio='变更简介')['college'], '历史学院')

    def test_legacy_same_education_does_not_erase_modern_choices(self):
        self.save(degree_level='junior_college', study_status='graduated')
        result = self.market.user_update_legacy_profile(
            101, {'nickname':'旧客户端', 'education':'已毕业'})
        self.assertEqual((result['degree_level'],result['study_status']), ('junior_college','graduated'))
        self.assertEqual(result['profile_version'], 2)

    def test_legacy_omitted_education_preserves_both_choices(self):
        self.save(degree_level='other', study_status='studying')
        result = self.market.user_update_legacy_profile(101, {'nickname':'旧客户端'})
        self.assertEqual((result['degree_level'],result['study_status']), ('other','studying'))

    def test_legacy_changed_education_maps_only_explicit_change(self):
        for legacy, expected in [('本科',('bachelor','unspecified')),('专科',('junior_college','unspecified')),
                                 ('已毕业',('unspecified','graduated')),('其他',('unspecified','unspecified'))]:
            self.save(degree_level='other', study_status='other')
            # '其他' equals the exposed legacy value: preserve the explicit
            # modern 'other' choices; a legacy same-value save is not a change.
            if legacy == '其他':
                self.save(degree_level='bachelor')
            result = self.market.user_update_legacy_profile(101, {'nickname':'旧客户端','education':legacy})
            self.assertEqual((result['degree_level'],result['study_status']), expected)

    def test_legacy_unknown_old_value_is_not_reinterpreted_on_omission(self):
        with self.market.tx() as connection:
            connection.execute("UPDATE users SET education='未知旧值' WHERE id=101")
        result = self.market.user_update_legacy_profile(101, {'nickname':'旧客户端'})
        self.assertEqual(result['education'], '未知旧值')
        self.assertEqual(result['study_status'], 'graduated')

    def test_legacy_preserves_existing_text_and_permission_policy(self):
        result = self.market.user_update_legacy_profile(101, {
            'nickname':'旧客户端', 'major':'专'*81, 'bio':'简'*301, 'college':'其他学院',
            'role':'admin', 'score':100, 'phone':'forged', 'user_id':102,
        })
        self.assertEqual((len(result['major']),len(result['bio'])), (80,300))
        self.assertEqual((result['college'],result['role'],result['score']), ('计算机工程学院','user',89))
        self.assertEqual(self.row('SELECT nickname FROM users WHERE id=102')['nickname'], '乙同学')

    def test_legacy_optional_version_prevents_stale_save_when_supplied(self):
        self.save(bio='新资料')
        self.expect_error(409, lambda: self.market.user_update_legacy_profile(
            101, {'nickname':'旧客户端', 'profile_version':0}))

    def test_legacy_bad_education_or_nickname_has_no_side_effect(self):
        for payload in [{'nickname':'甲','education':'不合法'}, {'nickname':' '},
                        {'nickname':'甲','profile_version':True}]:
            self.expect_error(400, lambda: self.market.user_update_legacy_profile(101,payload))

    def test_read_uses_explicit_dto_and_never_recurses_into_old_profile(self):
        self.market.profile = lambda actor: self.fail('new read called old profile')
        self.assertEqual(self.market.user_profile(101)['id'], 101)
        self.assertEqual(self.save(bio='<script>alert(1)</script>')['bio'], '<script>alert(1)</script>')

    def test_new_class_does_not_override_existing_authentication_methods(self):
        self.assertFalse({'profile','update_profile','user','login_password','register_password'}
                         & set(vars(UserProfiles)))

    def test_domain_connections_close_without_relying_on_gc(self):
        class TrackedConnection(sqlite3.Connection):
            closed = False

            def close(self):
                self.closed = True
                super().close()

        opened = []

        def connect():
            connection = sqlite3.connect(self.market.path, factory=TrackedConnection)
            connection.row_factory = sqlite3.Row
            opened.append(connection)
            return connection

        self.market.connect = connect
        self.market.user_profile(101)
        self.save(bio='资源关闭检查')
        self.assertTrue(opened)
        self.assertTrue(all(connection.closed for connection in opened))


if __name__ == '__main__':
    unittest.main()
