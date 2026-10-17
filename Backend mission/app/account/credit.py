"""信誉分制度（方案 A 定稿）的纯函数层。

只放「算分」的规则与常量，不做任何数据库/副作用——这样能单测，
也避免和 service 层的写库逻辑耦合。副作用（写 audit、改 score、发通知）
由 service 层负责。

方案要点见 docs/信誉分制度方案.md：
    扣分 = 违规基础分 + 金额阶梯
    加分 = 好评成交 / 申诉冲回 / 连续无违规（及时履约可后续加）
    诚信客户 = 信誉分 ≥ 90

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

# 信誉分达到该值即「诚信客户」，商品卡与主页展示标签。直接读实时 score，
# 掉到门槛以下自动失去标签——不需要额外的状态字段。
TRUSTED_SCORE = 90


def is_trusted(score):
    return (score or 0) >= TRUSTED_SCORE
