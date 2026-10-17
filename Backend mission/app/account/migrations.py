"""Incremental user-profile schema; called by A inside the startup transaction."""

import sqlite3


def migrate_account(connection: sqlite3.Connection) -> None:
    """Add only missing columns and map history only into newly added columns.

    Do not commit here: the caller owns the transaction. In particular, reruns
    and partially migrated databases must not overwrite a user's newer choices.
    The original education value remains unchanged until an explicit edit.
    """
    existing = {column[1] for column in connection.execute('PRAGMA table_info(users)')}
    additions = {
        'degree_level': (
            "TEXT NOT NULL DEFAULT 'unspecified' "
            "CHECK(degree_level IN ('bachelor','junior_college','other','unspecified'))"
        ),
        'study_status': (
            "TEXT NOT NULL DEFAULT 'unspecified' "
            "CHECK(study_status IN ('studying','graduated','other','unspecified'))"
        ),
        'profile_version': (
            'INTEGER NOT NULL DEFAULT 0 '
            "CHECK(typeof(profile_version)='integer' AND profile_version>=0)"
        ),
        # Selection and public media authorization are implemented in U02.
        'avatar_upload_id': 'TEXT',
    }
    for name, definition in additions.items():
        if name not in existing:
            # Names/DDL are constants, never client input.
            connection.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')

    if 'degree_level' not in existing:
        connection.execute('''
            UPDATE users SET degree_level=CASE education
                WHEN '本科' THEN 'bachelor'
                WHEN '专科' THEN 'junior_college'
                ELSE 'unspecified' END
        ''')
    if 'study_status' not in existing:
        connection.execute('''
            UPDATE users SET study_status=CASE education
                WHEN '已毕业' THEN 'graduated' ELSE 'unspecified' END
        ''')
