"""信誉分制度（方案 A 定稿）的纯函数层。

只放「算分」的规则与常量，不做任何数据库/副作用——这样能单测，
也避免和 service 层的写库逻辑耦合。副作用（写 audit、改 score、发通知）
由 service 层负责。

方案要点见 docs/信誉分制度方案.md：
    扣分 = 违规基础分 + 金额阶梯
    加分 = 好评成交 / 申诉冲回 / 连续无违规（及时履约可后续加）
    诚信客户 = 发布≥10 件 + 至少1笔交付 + 全部按时交付 + 无退款

金额单位：订单金额传「分」（与全站一致），这里换算成元取阶梯。
"""
import datetime
import time

# --- 扣分 ---------------------------------------------------------------

# 违规三档的基础分
VIOLATION_BASE = {'minor': 3, 'moderate': 8, 'severe': 15}
VIOLATION_LABEL = {'minor': '轻微违规', 'moderate': '中度违规', 'severe': '严重违规'}

# 金额阶梯（单位：元，含下不含上）。二手书多在 20–80 元、电子产品才上几百，
# 所以档位刻意压在低位：30/100/300。第 0 档 <30 元不加额外分。
PRICE_STEPS = ((30, 0), (100, 1), (300, 3), (float('inf'), 6))


def suggest_penalty(violation, amount_cents):
    """按方案 A 计算建议扣分。

    violation 取 minor / moderate / severe；amount_cents 是订单金额（分）。
    返回正整数。未知违规类型抛 ValueError，由调用方先校验。
    """
    if violation not in VIOLATION_BASE:
        raise ValueError(f'未知违规类型：{violation}')
    yuan = amount_cents / 100
    extra = next(step for limit, step in PRICE_STEPS if yuan < limit)
    return VIOLATION_BASE[violation] + extra


# --- 加分 ---------------------------------------------------------------

# 好评成交：4–5 星记好评。每天 / 每月给同一个人加分的上限，防「互刷订单刷分」。
GOOD_REVIEW = 4
AWARD_PER_REVIEW = 1
AWARD_DAILY_CAP = 3
AWARD_MONTHLY_CAP = 10
AWARD_REASON_PREFIX = '获得好评'


def day_start(now=None):
    """本地日历日 0 点的时间戳（用于「每天」上限）。"""
    dt = datetime.datetime.fromtimestamp(now or time.time())
    return datetime.datetime(dt.year, dt.month, dt.day).timestamp()


def month_start(now=None):
    dt = datetime.datetime.fromtimestamp(now or time.time())
    return datetime.datetime(dt.year, dt.month, 1).timestamp()


# --- 诚信客户 -----------------------------------------------------------
#
# 2026-10 修订：信誉分不再是唯一标准。
# 旧规则「score ≥ 90」的问题是：刚注册的账号初始就是 100 分，一件东西没卖过、
# 一次货没交过，商品卡上就挂着「诚信客户」——这个标签于是没有任何信息量。
#
# 现在看真实经营记录，四条同时满足才亮标：
#   1. 发布商品 ≥ 10 件（按发布过算，含已售出；被平台下架的也计入发布历史）
#   2. 至少 1 笔已交付订单（没有交易记录的新账号不能凭空获得标签）
#   3. 所有已交付订单都按时（卖家标记交付的时间 ≤ 约定的交付时间）
#   4. 没有退款订单（退款说明交易出了问题，与「诚信」语义矛盾）
#
# 账号被封禁/注销时一律不亮标，由调用方在批量判定时排除。
TRUSTED_MIN_LISTINGS = 10
TRUSTED_MIN_DELIVERED = 1


def is_trusted(listings=0, delivered=0, late=0, refunded=0):
    """按经营记录判定诚信客户。

    参数都是该卖家在平台上的累计计数：
      listings  —— 发布过的商品数
      delivered —— 已交付订单数
      late      —— 交付时间晚于约定时间的订单数
      refunded  —— 发生退款（全额或部分）的订单数
    """
    return (listings >= TRUSTED_MIN_LISTINGS
            and delivered >= TRUSTED_MIN_DELIVERED
            and late == 0
            and refunded == 0)


# --- 信誉星级 -------------------------------------------------------------
#
# 分数（0-100）是即时健康度：违规扣、好评成交加，低于 60 暂停发布。
# 星级（1-7）是长期口碑：4 星起步，靠持续好评升级，6 星「诚信卖家」、7 星「优品卖家」。
#
# 星级不落库，由「有效好评数 + 严重违规次数 + 分数红线」实时派生：
#   · 不新增字段 → 老库无需迁移，也不会出现「字段与规则不同步」的数据漂移；
#   · 有效好评 = 买家给卖家打的 4-5 星（reviews 里去重到订单）；
#   · 阈值 3 / 8 / 20 递增，前期快、后期慢，防止刷单速升；
#   · 严重违规（单次扣 ≥15 分）每次掉 1 星、最多扣 2 星；
#   · 分数跌破 60/40/20 时星级依次封顶 3/2/1，和「暂停发布」的红线对齐。
STAR_TITLES = {1: '风险账号', 2: '受限卖家', 3: '待改进', 4: '新手卖家',
               5: '靠谱卖家', 6: '诚信卖家', 7: '优品卖家'}
STAR_REVIEW_NEED = {5: 3, 6: 8, 7: 20}
STAR_SCORE_CAPS = ((20, 1), (40, 2), (60, 3))
STAR_BASE = 4
STAR_MAX = 7
SEVERE_DELTA = -15


def star_badge(good_reviews=0, severe_violations=0, score=100, stars_adjust=0):
    """把「有效好评 / 严重违规次数 / 信誉分 / 管理员调整」换算成星级、称号与升星进度。

    stars_adjust 是管理员通过审计累积的调整量（每次 ±1/±2）。它最后应用、不受红线限制：
    管理员有裁量权纠正误判或追加惩罚；而「能否发布」仍由分数红线独立决定。
    """
    stars = STAR_BASE
    for star in sorted(STAR_REVIEW_NEED):
        if good_reviews >= STAR_REVIEW_NEED[star]:
            stars = star
    stars -= min(max(0, severe_violations), 2)
    for floor, cap in STAR_SCORE_CAPS:
        if score < floor:
            stars = min(stars, cap)
    stars = max(1, min(STAR_MAX, stars + int(stars_adjust or 0)))
    nxt = stars + 1 if stars < STAR_MAX else None
    need = STAR_REVIEW_NEED.get(nxt, 0) if nxt else 0
    return {
        'stars': stars,
        'star_title': STAR_TITLES[stars],
        'good_reviews': good_reviews,
        'severe_violations': severe_violations,
        'stars_adjust': int(stars_adjust or 0),
        'next_star': nxt,
        'next_star_need': max(0, need - good_reviews) if nxt else 0,
        'star_tiers': [{'star': s, 'title': STAR_TITLES[s], 'need': STAR_REVIEW_NEED[s]} for s in (5, 6, 7)],
        'star_pause_score': 60
    }
