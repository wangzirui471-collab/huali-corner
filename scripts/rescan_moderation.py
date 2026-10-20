"""一次性回扫：给词表上线前发布的历史帖子/聊天消息补审核标记。

背景：审核词表（含代考/代课/代签到/代写论文等学术不端词条）只在发布那一刻生效；
之前发布的内容 moderation 字段为 NULL，永远进不了客服工作台的 flagged_content
队列，于是存量违规内容对用户一直可见——这不是词表缺口，是「老内容没机会再扫」。

本脚本只补「标记」，不删除、不修改正文。是否移除由客服在工作台按既有
content_action 流程决定（软删除 removed=1，可恢复）。默认只报告不写库，
加 --apply 才落盘；写库前请自行确认已有数据库备份。

用法（在项目根目录）：
    python scripts/rescan_moderation.py                 # 只报告
    python scripts/rescan_moderation.py --apply         # 写入标记
    python scripts/rescan_moderation.py --db "其他数据目录/market.sqlite3" --apply
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend mission'))

from app.moderation import configure, scan_text, flag_of  # noqa: E402


def rescan(db_path, apply):
    configure(db_path.parent / 'moderation')  # 与 market.py 的词库覆盖目录保持一致
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    stats = {'posts_scanned': 0, 'posts_flagged': 0,
             'messages_scanned': 0, 'messages_flagged': 0}
    flagged = []
    try:
        posts = conn.execute(
            'SELECT id,topic,body FROM posts WHERE moderation IS NULL AND removed=0').fetchall()
        for r in posts:
            stats['posts_scanned'] += 1
            mark = flag_of(scan_text(r['body'] or ''))
            if not mark:
                continue
            stats['posts_flagged'] += 1
            flagged.append(('post', r['id'], r['topic'], (r['body'] or '')[:40], mark['action']))
            if apply:
                conn.execute('UPDATE posts SET moderation=? WHERE id=? AND moderation IS NULL',
                             (json.dumps(mark, ensure_ascii=False), r['id']))
        messages = conn.execute(
            'SELECT id,room_id,body FROM messages WHERE moderation IS NULL AND removed=0').fetchall()
        for r in messages:
            stats['messages_scanned'] += 1
            mark = flag_of(scan_text(r['body'] or ''))
            if not mark:
                continue
            stats['messages_flagged'] += 1
            flagged.append(('message', r['id'], 'room#%s' % r['room_id'], (r['body'] or '')[:40], mark['action']))
            if apply:
                conn.execute('UPDATE messages SET moderation=? WHERE id=? AND moderation IS NULL',
                             (json.dumps(mark, ensure_ascii=False), r['id']))
        if apply:
            conn.commit()
    finally:
        conn.close()
    return stats, flagged


def main():
    parser = argparse.ArgumentParser(description='回扫历史帖子/消息的审核标记（默认只报告）')
    default_db = ROOT / 'var-trial' / 'market.sqlite3'
    parser.add_argument('--db', default=str(default_db), help='SQLite 数据文件路径')
    parser.add_argument('--apply', action='store_true', help='实际写入标记（默认只报告）')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print('找不到数据库文件：%s' % db_path)
        return 2
    stats, flagged = rescan(db_path, args.apply)
    print('模式：', '写入' if args.apply else '仅报告（加 --apply 才落盘）')
    print('帖子：扫描 %d，命中 %d' % (stats['posts_scanned'], stats['posts_flagged']))
    print('消息：扫描 %d，命中 %d' % (stats['messages_scanned'], stats['messages_flagged']))
    for kind, cid, ctx, body, action in flagged:
        print('  [%s#%s|%s|%s] %s…' % (kind, cid, ctx, action, body))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
