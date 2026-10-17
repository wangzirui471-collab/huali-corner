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

__all__ = ['rules', 'configure', 'reload', 'overlay', 'scan_text', 'scan_product',
           'scan_private', 'report_of', 'flag_of', 'message_for', 'flagged',
           'ACTION_LABEL', 'LEVEL_NAME', 'RANK', 'describe', 'PRIVATE_ALLOWED',
           'FREE_TEXT_FIELDS', 'WORD_ONLY_FIELDS']

# 会参与扫描的自由文本字段。isbn 不在这里——它本身就是一长串数字，
# 会撞上「疑似QQ号」正则，所以单独放进 WORD_ONLY_FIELDS 只做词表检查。
FREE_TEXT_FIELDS = ('title', 'description', 'edition', 'publisher', 'author',
                    'notes', 'missing', 'accessories', 'condition', 'bought',
                    'course', 'major', 'college')
WORD_ONLY_FIELDS = ('isbn',)

_rules = None
_overlay = None


def configure(directory):
    """指定运行时词库覆盖目录（每个数据目录一份）。目录变了才重建自动机。"""
    global _overlay, _rules
    path = str(directory) if directory else None
    if path != _overlay:
        _overlay = path
        _rules = None


def overlay():
    return _overlay


def reload():
    """丢弃已建好的自动机，下次扫描时按最新词表重建。

    词库维护界面保存后必须调用它，否则改完词条要重启服务才生效。
    """
    global _rules
    _rules = None


def rules():
    """进程内只建一次自动机。词表几百条，构建成本可忽略，但没必要每次发布都重建。"""
    global _rules
    if _rules is None:
        _rules = RuleSet(overlay=_overlay)
    return _rules


def scan_text(text, with_patterns=True):
    return rules().scan(text, with_patterns)


# 私聊里放行的分类：两个人约在图书馆交货，互留微信/电话是正常沟通，
# 平台也没有权力管这个。真正要拦的是「把交易和钱搬出平台」——
# 站外平台、站外收款、以及违禁品本身，这些在私聊里同样拦截。
PRIVATE_ALLOWED = frozenset({'联系方式', '疑似联系方式'})


def scan_private(text):
    """私聊场景的扫描：联系方式类命中直接忽略，其余规则照常。

    与群聊/帖子的差别是有意的：
      群聊与帖子是**公开引流入口**，一句「加微信」能带走一整个群的人；
      私聊是已经建立的两人会话，拦「加微信」只会让正常交易没法约时间。
    所以私聊放行联系方式，但仍拦「走闲鱼」「微信转账」和违禁品。
    """
    report = rules().scan(text)
    if not report['hits']:
        return report
    hits = [h for h in report['hits'] if h['category'] not in PRIVATE_ALLOWED]
    return _rebuild(hits)


def _rebuild(hits):
    if not hits:
        return {'action': 'ok', 'hits': [], 'blocked': False, 'message': ''}
    worst = max(hits, key=lambda h: RANK[h['action']])
    return {'action': worst['action'], 'hits': hits,
            'blocked': worst['action'] == 'block', 'message': describe(worst)}


def flagged(report):
    """判定是否需要在工作台留一条待审记录。

    只有 block 以上的不算——block 是直接拦掉，内容根本没进库。
    剩下的 review / report 要进队列，report 记一笔、review 等人工判定。
    """
    return bool(report and report['action'] != 'ok')


def flag_of(report):
    """把扫描结果压成可存进 messages/posts.moderation 的小结构。

    与 report_of 的区别：那个带 reviewed 字段，是给商品用的（商品有「复核通过」
    这个状态）；聊天消息和帖子只有「删掉」这一个出口，没有复核概念，
    所以不存 reviewed，免得界面上出现永远为 false 的字段。
    """
    if not flagged(report):
        return None
    return {
        'action': report['action'],
        'level': LEVEL_NAME[report['action']],
        'hits': [{'hit': h['hit'], 'category': h['category'], 'action': h['action']}
                 for h in report['hits']],
    }


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
