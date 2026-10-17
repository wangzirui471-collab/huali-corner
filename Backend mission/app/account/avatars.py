"""Avatar-only resources, explicit selection and scoped binary media access.

No rows are inserted into legacy uploads: that registry also accepts private
order evidence, whose permissions must never be widened by selecting an avatar.
"""

from contextlib import closing
from collections.abc import Mapping
import hashlib
import io
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import TYPE_CHECKING

from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.errors import DomainError, ValidationMixin

if TYPE_CHECKING:
    from .profiles import UserProfileDTO


MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
AVATAR_EDGE = 512
AVATAR_ID = re.compile(r'ua_[0-9a-f]{32}')


def user_avatar_file(root: Path, record: sqlite3.Row | Mapping[str, str]) -> Path | None:
    """Only return this registry's canonical, existing file inside uploads/."""
    upload_id = record['upload_id']
    if not isinstance(upload_id, str) or not AVATAR_ID.fullmatch(upload_id):
        return None
    try:
        directory = (Path(root) / 'uploads').resolve(strict=True)
        expected = directory / (upload_id + '.webp')
        actual = Path(record['path'])
        if not actual.is_absolute():
            if record['path'] != 'uploads/' + upload_id + '.webp':
                return None
            actual = Path(root) / actual
        if actual.is_symlink() or actual.resolve(strict=True) != expected:
            return None
        if not expected.is_file() or not 0 < expected.stat().st_size <= MAX_AVATAR_BYTES:
            return None
        return expected
    except (OSError, ValueError, TypeError):
        return None


def user_public_avatar_url(connection: sqlite3.Connection, root: Path,
                           owner_id: int, upload_id: str | None) -> str | None:
    if not isinstance(upload_id, str) or not AVATAR_ID.fullmatch(upload_id):
        return None
    record = connection.execute('''
        SELECT a.upload_id,a.path FROM user_avatar_uploads a
        JOIN users u ON u.id=a.user_id
        WHERE a.upload_id=? AND a.user_id=? AND u.avatar_upload_id=a.upload_id AND u.is_active=1
    ''', (upload_id, owner_id)).fetchone()
    if record is None or user_avatar_file(root, record) is None:
        return None
    return '/media/' + upload_id


def user_normalize_avatar(content: bytes) -> bytes:
    """Validate before full decode; create a fresh static image without metadata."""
    ValidationMixin.require(isinstance(content, bytes) and 0 < len(content) <= MAX_AVATAR_BYTES,
                            '头像需为不超过2 MiB的JPEG、PNG或WebP图片')
    try:
        with Image.open(io.BytesIO(content)) as image:
            ValidationMixin.require(image.format in {'JPEG', 'PNG', 'WEBP'}, '头像仅支持JPEG、PNG或WebP')
            ValidationMixin.require(0 < image.width * image.height <= MAX_AVATAR_PIXELS,
                                    '头像像素不能超过1600万')
            ValidationMixin.require(not getattr(image, 'is_animated', False)
                                    and getattr(image, 'n_frames', 1) == 1, '头像不能是动画或多帧图片')
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            with ImageOps.exif_transpose(image) as oriented:
                mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                with oriented.convert(mode) as converted:
                    converted.thumbnail((AVATAR_EDGE, AVATAR_EDGE), Image.Resampling.LANCZOS)
                    # convert/copy may retain image.info; a fresh canvas does not.
                    with Image.new(mode, converted.size) as clean:
                        clean.paste(converted)
                        output = io.BytesIO()
                        clean.save(output, 'WEBP', quality=85)
                        return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DomainError('请上传完整、有效的静态JPEG、PNG或WebP头像') from None


class UserAvatars(ValidationMixin):
    """Requires Store's root/connect/tx and UserProfiles.user_profile_projection."""

    def user_upload_avatar(self, actor_id: int, content: bytes) -> dict[str, str]:
        self.require(type(actor_id) is int and actor_id > 0, '请先登录', 401)
        with closing(self.connect()) as connection:
            account = connection.execute('SELECT is_active FROM users WHERE id=?', (actor_id,)).fetchone()
            self.require(account is not None, '用户不存在', 404)
            self.require(account['is_active'] == 1, '账号已停用，请联系运营者', 403)
        normalized = user_normalize_avatar(content)
        upload_id = 'ua_' + secrets.token_hex(16)
        path = Path(self.root) / 'uploads' / (upload_id + '.webp')
        created = False
        try:
            # Exclusive create never replaces an existing resource on collision.
            with path.open('xb') as output:
                created = True
                output.write(normalized)
            with self.tx() as connection:
                account = connection.execute('SELECT is_active FROM users WHERE id=?', (actor_id,)).fetchone()
                self.require(account is not None and account['is_active'] == 1, '账号已停用，请联系运营者', 403)
                connection.execute('''
                    INSERT INTO user_avatar_uploads(upload_id,user_id,path,digest,created_at)
                    VALUES(?,?,?,?,?)
                ''', (upload_id, actor_id, 'uploads/'+upload_id+'.webp',
                      hashlib.sha256(normalized).hexdigest(), time.time()))
        except BaseException as error:
            if created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    raise DomainError('头像保存失败，临时文件需由维护者清理', 500) from None
            if isinstance(error, OSError):
                raise DomainError('头像保存失败，请稍后重试', 500) from None
            raise
        return {'upload_id': upload_id, 'preview_url': '/media/' + upload_id}

    def user_set_avatar(self, actor_id: int, upload_id: str | None,
                        profile_version: int) -> 'UserProfileDTO':
        self.require(type(actor_id) is int and actor_id > 0, '请先登录', 401)
        self.require(type(profile_version) is int and profile_version >= 0, '资料版本须为非负整数')
        self.require(upload_id is None or (isinstance(upload_id, str) and AVATAR_ID.fullmatch(upload_id)),
                     '头像标识不合法')
        with self.tx() as connection:
            account = connection.execute('SELECT * FROM users WHERE id=?', (actor_id,)).fetchone()
            self.require(account is not None, '用户不存在', 404)
            self.require(account['is_active'] == 1, '账号已停用，请联系运营者', 403)
            self.require(account['profile_version'] == profile_version, '资料已更新，请重新载入并核对', 409)
            if upload_id is not None:
                record = connection.execute('SELECT * FROM user_avatar_uploads WHERE upload_id=?',
                                            (upload_id,)).fetchone()
                self.require(record is not None, '头像不存在，请重新上传', 404)
                self.require(record['user_id'] == actor_id, '只能选择本人上传的头像', 403)
                self.require(user_avatar_file(self.root, record) is not None, '头像文件不可用，请重新上传', 404)
            changed = connection.execute('''
                UPDATE users SET avatar_upload_id=?,profile_version=profile_version+1
                WHERE id=? AND profile_version=?
            ''', (upload_id, actor_id, profile_version))
            self.require(changed.rowcount == 1, '资料已更新，请重新载入并核对', 409)
            account = connection.execute('SELECT * FROM users WHERE id=?', (actor_id,)).fetchone()
            return self.user_profile_projection(connection, account)

    def user_is_public_avatar(self, upload_id: str) -> bool:
        if not isinstance(upload_id, str) or not AVATAR_ID.fullmatch(upload_id):
            return False
        with closing(self.connect()) as connection:
            record = connection.execute('SELECT user_id FROM user_avatar_uploads WHERE upload_id=?',
                                        (upload_id,)).fetchone()
            return bool(record and user_public_avatar_url(connection, self.root,
                                                         record['user_id'], upload_id))

    def user_avatar_backup_entries(self, snapshot: sqlite3.Connection) -> list[tuple[Path, str]]:
        """A calls this on the same SQLite backup snapshot, before closing it.

        Include unselected private history too; never query a newer live DB for
        a snapshot's file manifest. Relative stored paths need no restore rewrite.
        """
        result = []
        for row in snapshot.execute('SELECT upload_id,path FROM user_avatar_uploads'):
            path = user_avatar_file(self.root, {'upload_id':row[0], 'path':row[1]})
            self.require(path is not None, '头像备份缺少有效文件，请联系维护者', 500)
            result.append((path,'uploads/'+row[0]+'.webp'))
        return result

    def user_avatar_bytes(self, actor_id: int | None, upload_id: str) -> bytes:
        """Public only while selected; otherwise owner only, with no staff bypass.

        A calls this before the generic /media uploads lookup for the ua_ prefix.
        Return binary data, never a local path in a JSON response.
        """
        self.require(isinstance(upload_id, str) and AVATAR_ID.fullmatch(upload_id), '头像不存在', 404)
        self.require(actor_id is None or (type(actor_id) is int and actor_id > 0), '请先登录', 401)
        with closing(self.connect()) as connection:
            record = connection.execute('''
                SELECT a.*,u.is_active,u.avatar_upload_id FROM user_avatar_uploads a
                JOIN users u ON u.id=a.user_id WHERE a.upload_id=?
            ''', (upload_id,)).fetchone()
            self.require(record is not None, '头像不存在', 404)
            selected = record['is_active'] == 1 and record['avatar_upload_id'] == upload_id
            owner = record['is_active'] == 1 and actor_id == record['user_id']
            self.require(selected or owner, '无权读取此头像', 403)
            path = user_avatar_file(self.root, record)
            self.require(path is not None, '头像文件不可用', 404)
            try:
                with path.open('rb') as source:
                    content = source.read(MAX_AVATAR_BYTES + 1)
            except OSError:
                raise DomainError('头像文件不可用', 404) from None
            self.require(0 < len(content) <= MAX_AVATAR_BYTES, '头像文件不可用', 404)
            return content
