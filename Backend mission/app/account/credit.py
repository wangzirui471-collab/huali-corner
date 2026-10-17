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
