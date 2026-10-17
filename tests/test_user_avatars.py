"""U02 contract source for A to run; do not execute on B's machine."""

from contextlib import closing, contextmanager
import gc
import hashlib
import io
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from PIL import Image
from app.account.avatars import UserAvatars, MAX_AVATAR_BYTES
from app.account.migrations import migrate_account
from app.account.profiles import UserProfiles
from app.core.errors import DomainError
from app.market import Market


class UserAvatarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='zj-avatar-contract-')
        self.addCleanup(self.clean_data)
        missing = tuple(mixin for mixin in (UserProfiles, UserAvatars)
                        if not issubclass(Market, mixin))
        avatar_market = type('AvatarContractMarket', (*missing, Market), {}) if missing else Market
        self.market = avatar_market(self.tmp.name, trial=True)
        with self.market.tx() as connection:
            migrate_account(connection)
            connection.executemany('''
                INSERT INTO users(id,phone,nickname,role) VALUES(?,?,?,?)
            ''', [(101,'13900000101','甲同学','user'), (102,'13900000102','乙同学','user'),
                  (103,'13900000103','客服','support')])

    def clean_data(self):
        gc.collect()
        self.tmp.cleanup()

    def image(self, format='PNG', **save_options):
        with Image.new('RGB', (120, 80), 'coral') as image:
            output = io.BytesIO()
            image.save(output, format, **save_options)
            return output.getvalue()

    def upload(self, actor=101, content=None):
        return self.market.user_upload_avatar(actor, content if content is not None else self.image())

    def select(self, upload_id, actor=101, version=None):
        version = self.market.user_profile(actor)['profile_version'] if version is None else version
        return self.market.user_set_avatar(actor, upload_id, version)

    def row(self, query, args=()):
        with closing(self.market.connect()) as connection:
            row = connection.execute(query, args).fetchone()
            return dict(row) if row else None

    def snapshot(self):
        with closing(self.market.connect()) as connection:
            return {table:[tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ['users','user_avatar_uploads','uploads','orders','sessions']}

    def disk_path(self, row):
        path = Path(row['path'])
        return path if path.is_absolute() else Path(self.tmp.name) / path

    def error(self, status, operation):
        before = self.snapshot()
        before_files = set((Path(self.tmp.name) / 'uploads').iterdir())
        with self.assertRaises(DomainError) as caught:
            operation()
        self.assertEqual(caught.exception.status, status)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(set((Path(self.tmp.name) / 'uploads').iterdir()), before_files)
        self.assertNotIn(self.tmp.name, str(caught.exception))

    def test_supported_real_formats_are_normalized_and_stored_privately(self):
        for format in ['JPEG','PNG','WEBP']:
            with self.subTest(format=format):
                uploaded = self.upload(content=self.image(format))
                self.assertEqual(set(uploaded), {'upload_id','preview_url'})
                self.assertRegex(uploaded['upload_id'], r'^ua_[0-9a-f]{32}$')
                self.assertEqual(uploaded['preview_url'], '/media/' + uploaded['upload_id'])
                self.assertEqual(self.market.user_profile(101)['profile_version'], 0)
                row = self.row('SELECT * FROM user_avatar_uploads WHERE upload_id=?',
                               (uploaded['upload_id'],))
                self.assertIsNone(self.row('SELECT id FROM uploads WHERE id=?', (uploaded['upload_id'],)))
                with Image.open(self.disk_path(row)) as image:
                    self.assertEqual(image.format, 'WEBP')
                    self.assertLessEqual(max(image.size), 512)
                    self.assertEqual(getattr(image, 'n_frames', 1), 1)
                self.assertFalse(self.market.user_is_public_avatar(uploaded['upload_id']))

    def test_raw_size_limit_is_exactly_two_mib(self):
        data = self.image().ljust(MAX_AVATAR_BYTES, b'\0')
        self.upload(content=data)
        self.error(400, lambda: self.upload(content=data+b'x'))

    def test_invalid_content_and_unsupported_formats_are_rejected(self):
        for content in [b'', b'not a PNG', b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                        self.image('BMP'), self.image('JPEG')[:50], None, 'encoded text']:
            with self.subTest(kind=type(content).__name__, length=len(content) if content else 0):
                self.error(400, lambda: self.market.user_upload_avatar(101, content))

    def test_animated_png_is_rejected(self):
        output = io.BytesIO()
        with Image.new('RGB', (12,12), 'red') as first, Image.new('RGB', (12,12), 'blue') as second:
            first.save(output, 'PNG', save_all=True, append_images=[second], duration=100, loop=0)
        self.error(400, lambda: self.upload(content=output.getvalue()))

    def test_huge_pixel_header_is_rejected_before_decoding(self):
        def chunk(name, data):
            return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)

        header = struct.pack('>IIBBBBB',5000,4000,8,2,0,0,0)
        content = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)
                   +chunk(b'IDAT',zlib.compress(b'\0'*16))+chunk(b'IEND',b''))
        self.error(400, lambda: self.upload(content=content))

    def test_orientation_corrected_metadata_removed_and_output_resized(self):
        output = io.BytesIO()
        with Image.new('RGB', (900,600), 'green') as source:
            exif = source.getexif()
            exif[274] = 6
            exif[270] = 'private location metadata'
            source.save(output, 'JPEG', exif=exif)
        uploaded = self.upload(content=output.getvalue())
        data = self.market.user_avatar_bytes(101, uploaded['upload_id'])
        with Image.open(io.BytesIO(data)) as normalized:
            self.assertEqual(normalized.size, (341,512))
            self.assertFalse(normalized.getexif())
            self.assertNotIn('exif',normalized.info)
            self.assertNotIn('icc_profile',normalized.info)

    def test_only_owner_can_read_unselected_upload_even_staff_cannot(self):
        upload_id = self.upload()['upload_id']
        self.assertIsInstance(self.market.user_avatar_bytes(101,upload_id), bytes)
        self.error(403, lambda:self.market.user_avatar_bytes(None,upload_id))
        self.error(403, lambda:self.market.user_avatar_bytes(102,upload_id))
        self.error(403, lambda:self.market.user_avatar_bytes(103,upload_id))

    def test_selection_publishes_only_current_avatar_and_increments_profile_version(self):
        first = self.upload()['upload_id']
        result = self.select(first)
        self.assertEqual(result['avatar_url'], '/media/'+first)
        self.assertEqual(result['profile_version'], 1)
        self.assertTrue(self.market.user_is_public_avatar(first))
        self.assertIsInstance(self.market.user_avatar_bytes(None,first), bytes)
        second = self.upload()['upload_id']
        self.select(second)
        self.assertFalse(self.market.user_is_public_avatar(first))
        self.assertTrue(self.market.user_is_public_avatar(second))
        self.error(403, lambda:self.market.user_avatar_bytes(None,first))
        self.assertIsInstance(self.market.user_avatar_bytes(101,first), bytes)

    def test_remove_revokes_public_access_without_deleting_history(self):
        upload_id = self.upload()['upload_id']
        self.select(upload_id)
        result = self.select(None)
        self.assertIsNone(result['avatar_upload_id'])
        self.assertIsNone(result['avatar_url'])
        self.assertFalse(self.market.user_is_public_avatar(upload_id))
        self.assertIsNotNone(self.row('SELECT * FROM user_avatar_uploads WHERE upload_id=?',(upload_id,)))
        self.assertTrue((Path(self.tmp.name)/'uploads'/(upload_id+'.webp')).exists())

    def test_cannot_select_other_users_avatar(self):
        upload_id = self.upload(actor=102)['upload_id']
        self.error(403, lambda:self.select(upload_id))

    def test_legacy_product_and_evidence_uploads_cannot_become_avatars(self):
        for upload_id, angle in [('f'*32,'front'),('e'*32,'proof')]:
            with self.market.tx() as connection:
                connection.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',
                                   (upload_id,101,'not-read',hashlib.sha256(b'').hexdigest(),angle,1))
            self.error(400, lambda:self.select(upload_id))

    def test_avatar_cannot_be_reused_as_product_or_private_evidence_upload(self):
        upload_id = self.upload()['upload_id']
        self.error(403, lambda:self.market.validate_evidence(101,[upload_id]))
        self.assertIsNone(self.row('SELECT id FROM uploads WHERE id=?',(upload_id,)))

    def test_external_urls_and_paths_are_not_accepted_as_upload_ids(self):
        for upload_id in ['https://example.com/a.png','../secret','/tmp/a.webp',True,7,[],{}]:
            self.error(400, lambda:self.select(upload_id))

    def test_version_conflict_and_invalid_version_leave_current_avatar_unchanged(self):
        upload_id = self.upload()['upload_id']
        self.select(upload_id)
        self.error(409, lambda:self.select(None,version=0))
        for version in [True,False,-1,'1',1.0,None]:
            self.error(400, lambda:self.market.user_set_avatar(101,None,version))

    def test_inactive_user_cannot_upload_or_select_or_publish_avatar(self):
        upload_id = self.upload()['upload_id']
        self.select(upload_id)
        with self.market.tx() as connection:
            connection.execute('UPDATE users SET is_active=0 WHERE id=101')
        self.error(403, lambda:self.upload())
        self.error(403, lambda:self.select(None))
        self.assertFalse(self.market.user_is_public_avatar(upload_id))
        self.error(403, lambda:self.market.user_avatar_bytes(None,upload_id))

    def test_missing_file_and_foreign_path_never_become_public(self):
        upload_id = self.upload()['upload_id']
        row = self.row('SELECT path FROM user_avatar_uploads WHERE upload_id=?',(upload_id,))
        self.disk_path(row).unlink()
        self.error(404, lambda:self.select(upload_id))
        with self.market.tx() as connection:
            connection.execute('UPDATE user_avatar_uploads SET path=? WHERE upload_id=?',
                               (str(Path(self.tmp.name)/'market.sqlite3'),upload_id))
        self.assertFalse(self.market.user_is_public_avatar(upload_id))
        self.error(404, lambda:self.market.user_avatar_bytes(101,upload_id))

    def test_upload_transaction_failure_removes_only_its_new_file(self):
        original = self.market.tx

        @contextmanager
        def failing_transaction():
            with original() as connection:
                yield connection
                raise RuntimeError('synthetic rollback')

        before = self.snapshot()
        before_files = set((Path(self.tmp.name)/'uploads').iterdir())
        with patch.object(self.market,'tx',failing_transaction), self.assertRaises(RuntimeError):
            self.upload()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(set((Path(self.tmp.name)/'uploads').iterdir()),before_files)

    def test_empty_file_is_invalid_for_selection_projection_and_media(self):
        upload_id = self.upload()['upload_id']
        self.select(upload_id)
        row = self.row('SELECT path FROM user_avatar_uploads WHERE upload_id=?',(upload_id,))
        self.disk_path(row).write_bytes(b'')
        self.assertFalse(self.market.user_is_public_avatar(upload_id))
        self.assertIsNone(self.market.user_profile(101)['avatar_url'])
        self.error(404, lambda:self.select(upload_id))
        self.error(404, lambda:self.market.user_avatar_bytes(101,upload_id))

    def test_profile_saves_preserve_selected_avatar_and_share_same_version(self):
        upload_id = self.upload()['upload_id']
        self.select(upload_id)
        result = self.market.user_update_profile(101,{'profile_version':1,'bio':'资料更新'})
        self.assertEqual((result['profile_version'],result['avatar_url']),(2,'/media/'+upload_id))
        self.error(409, lambda:self.select(None,version=1))
        result = self.market.user_update_legacy_profile(101,{'nickname':'旧客户端'})
        self.assertEqual((result['profile_version'],result['avatar_url']),(3,'/media/'+upload_id))

    def test_migration_preserves_legacy_upload_table_shape(self):
        with closing(self.market.connect()) as connection:
            self.assertEqual([row[1] for row in connection.execute('PRAGMA table_info(uploads)')],
                             ['id','user_id','path','digest','angle','private'])
            migrate_account(connection)
        self.upload()

    def test_snapshot_entries_include_private_history_and_restore_to_a_new_root(self):
        first = self.upload()['upload_id']
        current = self.upload()['upload_id']
        self.select(current)
        row = self.row('SELECT path FROM user_avatar_uploads WHERE upload_id=?',(first,))
        self.assertEqual(row['path'], 'uploads/'+first+'.webp')
        with tempfile.TemporaryDirectory(prefix='zj-avatar-restore-') as restored:
            destination = Path(restored)
            (destination/'uploads').mkdir()
            with closing(self.market.connect()) as source, closing(sqlite3.connect(destination/'market.sqlite3')) as target:
                source.backup(target)
            with closing(sqlite3.connect(destination/'market.sqlite3')) as snapshot:
                entries = self.market.user_avatar_backup_entries(snapshot)
            self.assertEqual({name for _,name in entries},
                             {'uploads/'+first+'.webp','uploads/'+current+'.webp'})
            for path, name in entries:
                (destination/name).write_bytes(path.read_bytes())
            relocated = type(self.market)(destination,trial=True)
            self.assertEqual(relocated.user_profile(101)['avatar_url'],'/media/'+current)
            self.assertIsInstance(relocated.user_avatar_bytes(None,current),bytes)
            gc.collect()


if __name__ == '__main__':
    unittest.main()
