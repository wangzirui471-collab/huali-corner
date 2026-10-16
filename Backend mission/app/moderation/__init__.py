"""内容审核模块：违禁品自动审核 + 交易外流（反引流）检测。

对外只暴露三件事：

    scan_text(text)        扫一段自由文本，返回三级判定
    scan_product(payload)  扫一条商品发布/编辑请求
    message_for(report)    把判定结果转成给用户看的一句话

判定分为三级（与 docs/管理端权限清单-v2.md 一致）：

    block   高  法定禁止流通 / 明确的交易外流指令  -> 拦截发布
    review  中  平台限制类目 / 疑似联系方式        -> 允许发布，打标进人工待审队列
    report  低  规避平台的意图表达                 -> 仅记录，不打扰用户

词表来源是「自建为主」：开源社区只提供暴恐·色情·非法网址类词库，
没有现成的电商禁售品目录，而反引流需要的是闲鱼/微信这类站内目标，
开源黑名单里几乎没有。所以两个核心词表都是自建的，
开源词表作为可选补充由 scripts/fetch_wordlists.py 拉取。
"""
from .rules import RuleSet, ACTION_LABEL, LEVEL_NAME, RANK, describe

__all__ = ['rules', 'scan_text', 'scan_product', 'report_of', 'message_for',
           'ACTION_LABEL', 'LEVEL_NAME', 'RANK', 'describe',
           'FREE_TEXT_FIELDS', 'WORD_ONLY_FIELDS']

# 会参与扫描的自由文本字段。isbn 不在这里——它本身就是一长串数字，
# 会撞上「疑似QQ号」正则，所以单独放进 WORD_ONLY_FIELDS 只做词表检查。
FREE_TEXT_FIELDS = ('title', 'description', 'edition', 'publisher', 'author',
                    'notes', 'missing', 'accessories', 'condition', 'bought',
                    'course', 'major', 'college')
WORD_ONLY_FIELDS = ('isbn',)

_rules = None


def rules():
    """进程内只建一次自动机。词表几百条，构建成本可忽略，但没必要每次发布都重建。"""
    global _rules
    if _rules is None:
        _rules = RuleSet()
    return _rules


def scan_text(text, with_patterns=True):
    return rules().scan(text, with_patterns)


def scan_product(payload):
    """扫描一条商品请求，合并所有字段的命中，返回单个判定报告。"""
    payload = payload or {}
    free = ' \n '.join(str(payload.get(k) or '') for k in FREE_TEXT_FIELDS)
    report = rules().scan(free)
    hits = list(report['hits'])
    for key in WORD_ONLY_FIELDS:
        value = str(payload.get(key) or '')
        if value:
            hits.extend(rules().hits(value, with_patterns=False))
    if not hits:
        return {'action': 'ok', 'hits': [], 'blocked': False, 'message': ''}
    worst = max(hits, key=lambda h: RANK[h['action']])
    return {'action': worst['action'], 'hits': hits,
            'blocked': worst['action'] == 'block', 'message': describe(worst)}


def report_of(report):
    """把扫描结果压成可存进商品 data 字段的小结构（不存原始长文本）。"""
    if not report or report['action'] == 'ok':
        return None
    return {
        'action': report['action'],
        'level': LEVEL_NAME[report['action']],
        'hits': [{'hit': h['hit'], 'category': h['category'], 'action': h['action']} for h in report['hits']],
        'reviewed': False,
    }


def message_for(report):
    """给用户看的提示。说清命中了什么、属于哪一类，但不吐出整份词表。"""
    if not report or report['action'] == 'ok':
        return ''
    if report['action'] == 'block':
        detail = '、'.join(f'「{h["hit"]}」({h["category"]})' for h in report['hits'] if h['action'] == 'block')
        return f'{detail} 属于本站禁止发布的内容，已拦截。如有异议可在客服中心申诉。'
    detail = '、'.join(f'「{h["hit"]}」({h["category"]})' for h in report['hits'])
    return f'{detail} 需要人工复核，已转客服审核，通过后会正常展示。'
