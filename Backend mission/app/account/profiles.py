"""User-profile DTO, guarded updates and the existing client's compatibility path.

This mixin deliberately does not define profile/update_profile: A forwards those
existing methods explicitly, rather than changing authentication through MRO.
"""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import Any, TypedDict

from ..core.errors import ValidationMixin
from .avatars import user_public_avatar_url


DEGREE_LEVELS = frozenset({'bachelor', 'junior_college', 'other', 'unspecified'})
STUDY_STATUSES = frozenset({'studying', 'graduated', 'other', 'unspecified'})
PROFILE_WRITABLE = frozenset({
    'nickname', 'major', 'bio', 'degree_level', 'study_status', 'profile_version',
})
PROFILE_SELECT = '''
    SELECT id,nickname,college,major,education,bio,role,score,status,
           degree_level,study_status,profile_version,avatar_upload_id
    FROM users WHERE id=?
'''


class UserProfileDTO(TypedDict):
    id: int
    nickname: str
    college: str
    major: str
    education: str
    bio: str
    role: str
    score: int
    degree_level: str
    study_status: str
    profile_version: int
    avatar_upload_id: str | None
    avatar_url: str | None


def user_legacy_education(degree_level: str, study_status: str) -> str:
    """Lossy projection for old clients, never a source of verified identity."""
    if study_status == 'graduated':
        return '已毕业'
    return {'bachelor': '本科', 'junior_college': '专科'}.get(degree_level, '其他')


def user_legacy_options(education: str) -> tuple[str, str]:
    return {
        '本科': ('bachelor', 'unspecified'),
        '专科': ('junior_college', 'unspecified'),
        '已毕业': ('unspecified', 'graduated'),
    }.get(education, ('unspecified', 'unspecified'))


def user_profile_dto(row: sqlite3.Row) -> UserProfileDTO:
    """Explicit allowlist; never return credentials, address or account phone."""
    return {
        'id': row['id'],
        'nickname': row['nickname'],
        'college': row['college'],
        'major': row['major'],
        'education': row['education'],
        'bio': row['bio'],
        'role': row['role'],
        'score': row['score'],
        'degree_level': row['degree_level'],
        'study_status': row['study_status'],
        'profile_version': row['profile_version'],
        'avatar_upload_id': None,
        'avatar_url': None,
    }


class UserProfiles(ValidationMixin):
    """Uses Store.connect/tx and Market.trial without owning authentication."""

    def user_profile_projection(self, connection: sqlite3.Connection,
                                row: sqlite3.Row) -> UserProfileDTO:
        result = user_profile_dto(row)
        url = user_public_avatar_url(connection, self.root, row['id'], row['avatar_upload_id'])
        if url is not None:
            result['avatar_upload_id'] = row['avatar_upload_id']
            result['avatar_url'] = url
        return result

    def user_profile(self, actor_id: int) -> UserProfileDTO:
        """Read a profile by a server-resolved ID; HTTP authentication stays in A.

        Reading itself permits historical/inactive profiles for existing callers.
        Mutations independently recheck is_active inside their write transaction.
        Public endpoints must retain their separate public-field allowlist.
        """
        self.require(type(actor_id) is int and actor_id > 0, '请先登录', 401)
        with closing(self.connect()) as connection:
            row = connection.execute(PROFILE_SELECT, (actor_id,)).fetchone()
            self.require(row is not None, '用户不存在', 404)
            return self.user_profile_projection(connection, row)

    def user_update_profile(self, actor_id: int, payload: dict[str, Any]) -> UserProfileDTO:
        """Save only editable fields using the version read by this client."""
        self.require(type(actor_id) is int and actor_id > 0, '请先登录', 401)
        self.require(isinstance(payload, dict), '资料必须是对象')
        self.require(not (set(payload) - PROFILE_WRITABLE), '包含不可修改的资料字段')
        version = payload.get('profile_version')
        self.require(type(version) is int and version >= 0, '资料版本须为非负整数')

        edits = {}
        for name, maximum, label in [('nickname', 24, '昵称'), ('major', 80, '专业'), ('bio', 300, '简介')]:
            if name not in payload:
                continue
            value = payload[name]
            if name == 'nickname':
                edits[name] = self.text(value, maximum, label)
            else:
                self.require(isinstance(value, str) and len(value) <= maximum,
                             f'{label}须为不超过{maximum}字的文字')
                edits[name] = value
        for name, allowed in [('degree_level', DEGREE_LEVELS), ('study_status', STUDY_STATUSES)]:
            if name in payload:
                self.require(isinstance(payload[name], str) and payload[name] in allowed,
                             '学历层次或在读状态选项不合法')
                edits[name] = payload[name]

        with self.tx() as connection:
            current = connection.execute(PROFILE_SELECT, (actor_id,)).fetchone()
            self.require(current is not None, '用户不存在', 404)
            self.require(current['status'] == 'active', '账号已停用，请联系运营者', 403)
            self.require(current['profile_version'] == version, '资料已更新，请重新载入并核对', 409)
            values = {name: edits.get(name, current[name]) for name in
                      ['nickname', 'major', 'bio', 'degree_level', 'study_status']}
            college = '计算机工程学院' if self.trial else current['college']
            # 只有学历/在读状态真的变了，才回写旧 education。老客户端与小程序还在读它：
            # 用户只是改个昵称，却把原本的「本科」改写成「其他」，属于读一次改一次。
            picked = (values['degree_level'] != current['degree_level']
                      or values['study_status'] != current['study_status'])
            education = (user_legacy_education(values['degree_level'], values['study_status'])
                         if picked else current['education'])
            cursor = connection.execute('''
                UPDATE users SET nickname=?,major=?,bio=?,degree_level=?,study_status=?,
                    college=?,education=?,profile_version=profile_version+1
                WHERE id=? AND profile_version=?
            ''', (values['nickname'], values['major'], values['bio'], values['degree_level'],
                  values['study_status'], college, education, actor_id, version))
            self.require(cursor.rowcount == 1, '资料已更新，请重新载入并核对', 409)
            return self.user_profile_projection(connection,
                                                connection.execute(PROFILE_SELECT, (actor_id,)).fetchone())

    def user_update_legacy_profile(self, actor_id: int, payload: dict[str, Any]) -> UserProfileDTO:
        """Adapt /api/me without erasing new choices on an old-client round trip.

        Legacy optional strings retain the old conversion/truncation policy;
        unknown fields never become assignments. Old clients without a version
        cannot detect concurrent legacy saves, but every save invalidates the
        versions already held by modern clients. A supplied version is checked.
        """
        self.require(type(actor_id) is int and actor_id > 0, '请先登录', 401)
        self.require(isinstance(payload, dict), '资料必须是对象')
        nickname = self.text(payload.get('nickname'), 24, '昵称')
        if 'profile_version' in payload:
            version = payload['profile_version']
            self.require(type(version) is int and version >= 0, '资料版本须为非负整数')

        with self.tx() as connection:
            current = connection.execute(PROFILE_SELECT, (actor_id,)).fetchone()
            self.require(current is not None, '用户不存在', 404)
            self.require(current['status'] == 'active', '账号已停用，请联系运营者', 403)
            if 'profile_version' in payload:
                self.require(current['profile_version'] == payload['profile_version'],
                             '资料已更新，请重新载入并核对', 409)

            degree_level, study_status = current['degree_level'], current['study_status']
            education = current['education']
            if 'education' in payload and payload['education'] != education:
                education = payload['education']
                self.require(isinstance(education, str) and education in ['本科', '专科', '已毕业', '其他'],
                             '暂不开放该层次')
                degree_level, study_status = user_legacy_options(education)
            college = '计算机工程学院' if self.trial else str(payload.get('college', ''))[:80]
            connection.execute('''
                UPDATE users SET nickname=?,college=?,major=?,bio=?,education=?,
                    degree_level=?,study_status=?,profile_version=profile_version+1 WHERE id=?
            ''', (nickname, college, str(payload.get('major', ''))[:80], str(payload.get('bio', ''))[:300],
                  education, degree_level, study_status, actor_id))
            return self.user_profile_projection(connection,
                                                connection.execute(PROFILE_SELECT, (actor_id,)).fetchone())
