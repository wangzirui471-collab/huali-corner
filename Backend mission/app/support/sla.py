"""工单 SLA：首响与停滞的超时判定。

规则只有一份，本地 SQLite 与 Cloudflare/D1 都从这里取，避免两端各算一套。
阈值按试用期人力取值——待处理 2 小时没人认领、处理中 12 小时没有新的客服
动作，就值得提醒；比这更短会在 08:00—20:00 之外整批误报（夜间不排班）。
"""
import time

STAFF_ROLES = ('support', 'admin', 'developer', 'owner')
ACTIVE_STATUSES = ('open', 'processing', 'review')
FIRST_REPLY_SECONDS = 2 * 3600
STALL_SECONDS = 12 * 3600
# 超过这个时间的工单不再补发提醒：试用期里堆积的测试单（十几天前的）会一次性
# 给全部客服刷出上百条，真正需要处理的近期工单反而被淹。工作台仍照常标超时。
NOTICE_WINDOW_SECONDS = 7 * 86400
NOTICE_KIND = {'first_reply': 'ticket_overdue', 'progress': 'ticket_stalled'}


def ticket_sla(status, created, last_staff_at=None, now=None):
    """返回工单的超时信息；已结案的工单没有 SLA。

    created/last_staff_at 都是秒级时间戳，与现有字段保持一致。
    处理中/待复核从「最近一次客服回复或内部备注」起算：用户补一句话不应该
    把客服的停滞计时清零，所以 last_staff_at 只统计客服侧的 ticket_messages。
    """
    now = now or time.time()
    if status not in ACTIVE_STATUSES:
        return None
    if status == 'open':
        stage, limit, since = 'first_reply', FIRST_REPLY_SECONDS, created
    else:
        stage, limit, since = 'progress', STALL_SECONDS, (last_staff_at or created)
    since = since or now
    due = since + limit
    return {
        'stage': stage,
        'limit': limit,
        'since': since,
        'due': due,
        'waited': max(0, int(now - since)),
        'overdue': now > due,
        'overdue_seconds': max(0, int(now - due)),
    }
