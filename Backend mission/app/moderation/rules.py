"""内容审核规则引擎：词表加载 + Aho–Corasick 多模式匹配 + 三级判定。

依赖策略：**纯标准库**。不引入 jieba / ahocorasick / pyahocorasick 等第三方包，
与项目「标准库 + Pillow」的一贯做法保持一致（见 Backend mission/requirements.txt）。

匹配语义：**整串包含**（子串匹配），不做分词。
因此词表里不允许出现单字——`匕首` 可以收，`刀` 不行，否则「剪刀」「水果刀」
「《刀锋》」全部中招。这条由 load_words() 强制拦截并在 skipped 里报告。

为什么数据文件用 __file__ 而不是 core/config.py：
config.py 管的是**项目根路径**（ROOT / WEB / var / var-trial），因为那两个目录
和代码不在同一层。而本目录的 data/ 是**随包一起走的代码附属数据**，
它跟着 app/moderation/ 一起被拷贝、一起被部署，用 __file__ 才是正确的定位方式。
"""
import re
from pathlib import Path

# 由轻到重。数值越大越严重，判定时取最重的一条。
RANK = {'report': 0, 'review': 1, 'block': 2}
LEVEL_NAME = {'block': '高', 'review': '中', 'report': '低'}
ACTION_LABEL = {'block': '已拦截', 'review': '待人工审核', 'report': '仅记录'}

DATA_DIR = Path(__file__).resolve().parent / 'data'


class _Automaton:
    """Aho–Corasick 自动机。

    构造代价 O(词表总长度)，扫描代价 O(文本长度 + 命中数)，
    与词表规模无关——所以就算以后塞进几万条开源黑名单也不会拖慢发帖。
    朴素写法是「对每个词做一次 text 包含判断」，词表上万条时单次发布要几十毫秒。
    """

    __slots__ = ('goto', 'fail', 'out')

    def __init__(self):
        self.goto = [{}]
        self.fail = [0]
        self.out = [[]]

    def add(self, word, payload):
        node = 0
        for ch in word:
            nxt = self.goto[node].get(ch)
            if nxt is None:
                self.goto.append({})
                self.fail.append(0)
                self.out.append([])
                nxt = len(self.goto) - 1
                self.goto[node][ch] = nxt
            node = nxt
        self.out[node].append((word, payload))

    def build(self):
        from collections import deque
        queue = deque()
        for node in self.goto[0].values():
            self.fail[node] = 0
            queue.append(node)
        while queue:
            cur = queue.popleft()
            for ch, node in self.goto[cur].items():
                queue.append(node)
                f = self.fail[cur]
                while f and ch not in self.goto[f]:
                    f = self.fail[f]
                self.fail[node] = self.goto[f].get(ch, 0)
                if self.out[self.fail[node]]:
                    self.out[node] = self.out[node] + self.out[self.fail[node]]

    def find(self, text):
        """返回 [(起始下标, 命中词, payload), ...]，允许重叠命中。"""
        node = 0
        hits = []
        for i, ch in enumerate(text):
            while node and ch not in self.goto[node]:
                node = self.fail[node]
            node = self.goto[node].get(ch, 0)
            for word, payload in self.out[node]:
                hits.append((i - len(word) + 1, word, payload))
        return hits


# 正则类规则。词表管「词」，这里管「形状」。
# 注意 QQ 号取 6-11 位而不是 5 位：5 位纯数字在文本里太常见（价格、年份编号），
# 误伤成本高于漏掉几个老号。ISBN-13 因为前一位也是数字，被 (?<!\d) 挡掉。
PATTERNS = (
    ('外链', re.compile(r'(?:https?://|www\.)[\w\-.:/?=&%#]+', re.I), '站外链接', 'block'),
    ('手机号', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'), '疑似联系方式', 'review'),
    ('邮箱', re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,}'), '疑似联系方式', 'review'),
    ('疑似QQ号', re.compile(r'(?<![\d\-])\d{6,11}(?![\d\-])'), '疑似联系方式', 'review'),
)


def load_words(directory=None):
    """读取 data/*.txt 与 data/thirdparty/*.txt。格式：词条|分类|级别|处置

    thirdparty/ 放的是 scripts/fetch_wordlists.py 拉下来的开源词库，
    刻意不随仓库提交：一是体积（单份可达几百 KB），二是许可证各不相同，
    三是这些词表随时会被上游更新。自建词表在 data/ 下，随仓库走。

    单字词条会被拒收并计入 skipped——这是有意的，见模块顶部说明。
    """
    directory = Path(directory or DATA_DIR)
    words, skipped = [], []
    files = _word_files(directory)
    for path in files:
        for word, category, level, action, reason in _parse_file(path):
            if reason:
                skipped.append((path.name, word, reason))
                continue
            words.append({'word': word, 'category': category, 'level': level,
                          'action': action, 'source': path.name})
    return words, skipped


def _word_files(directory):
    files = []
    for folder in (directory, directory / 'thirdparty'):
        if folder.is_dir():
            files.extend(sorted(folder.glob('*.txt')))
    return files


def _parse_file(path):
    """逐行解析词表，产出 (词条, 分类, 级别, 处置, 拒收原因)。

    必须显式 utf-8：Windows 上 Python 3.8 的 open() 默认走 GBK，
    会让中文词表直接读成乱码（项目在院校目录 JSON 上踩过同一个坑）。
    """
    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) != 4:
            yield raw, '', '', '', '字段数不是 4'
            continue
        word, category, level, action = parts
        if len(word) < 2:
            yield word, category, level, action, '单字词条误伤面太大'
            continue
        if action not in RANK:
            yield word, category, level, action, f'未知处置 {action}'
            continue
        yield word, category, level, action, ''


# --- 运行时覆盖 -------------------------------------------------------------
#
# 词表维护界面改的是**数据目录**里的两个文件，不是仓库里的 data/*.txt：
#
#   <数据目录>/moderation/custom.txt     运营新增的词条，格式与内置词表一致
#   <数据目录>/moderation/disabled.txt   被停用的词条，一行一个
#
# 为什么分开两个文件而不是直接改内置词表：
#   1. 内置词表随 git 走，运行时改写会让每次升级都产生冲突；
#   2. 「停用一条内置词条」如果靠删除实现，下次拉取代码就复活了，
#      必须有一个独立的「黑名单的黑名单」才能稳定生效。

CUSTOM_FILE = 'custom.txt'
DISABLED_FILE = 'disabled.txt'


def load_overrides(overlay):
    """读取运行时覆盖。返回 (自定义词条, 停用词集合, 拒收的条目)。

    overlay 为空目录或不存在时返回空覆盖——调用方不必先建目录。
    """
    if not overlay:
        return [], set(), []
    folder = Path(overlay)
    custom, skipped = [], []
    path = folder / CUSTOM_FILE
    if path.is_file():
        for word, category, level, action, reason in _parse_file(path):
            if reason:
                skipped.append((CUSTOM_FILE, word, reason))
                continue
            custom.append({'word': word, 'category': category, 'level': level,
                           'action': action, 'source': 'custom.txt'})
    disabled = set()
    path = folder / DISABLED_FILE
    if path.is_file():
        for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = raw.strip()
            if line and not line.startswith('#'):
                disabled.add(line)
    return custom, disabled, skipped



class RuleSet:
    """一份可复用的规则集合。进程内建一次，之后只做扫描。

    overlay 是运行时覆盖目录（见 load_overrides）：运营在界面上新增或停用的词条
    存在那里。规则改动后调用方需要重建 RuleSet（moderation.reload() 已包好）。
    """

    def __init__(self, directory=None, overlay=None):
        self.words, self.skipped = load_words(directory)
        self.custom, self.disabled, skipped = load_overrides(overlay)
        self.skipped.extend(skipped)
        known = {w['word'] for w in self.words}
        # 停用优先于新增：一条词被停用后，即便内置词表里也有，也不再生效。
        if self.disabled:
            self.words = [w for w in self.words if w['word'] not in self.disabled]
            known = {w['word'] for w in self.words}
        for item in self.custom:
            if item['word'] in known or item['word'] in self.disabled:
                continue
            self.words.append(item)
            known.add(item['word'])
        self.automaton = _Automaton()
        for item in self.words:
            self.automaton.add(item['word'], item)
        self.automaton.build()
        self.patterns = PATTERNS

    def __len__(self):
        return len(self.words)

    def hits(self, text, with_patterns=True):
        """返回去重后的命中列表（同一词只报一次，保留第一次出现的位置）。

        with_patterns=False 时只走词表，跳过正则。
        用途：ISBN 这类「本身就是一长串数字」的结构化字段，
        走正则必然被「疑似QQ号」误伤，所以只做词表检查。
        """
        text = text or ''
        found, seen = [], set()
        for start, word, payload in self.automaton.find(text):
            key = (word, payload['action'])
            if key in seen:
                continue
            seen.add(key)
            found.append({**payload, 'hit': word, 'start': start, 'end': start + len(word), 'kind': 'word'})
        if with_patterns:
            for name, rx, category, action in self.patterns:
                for m in rx.finditer(text):
                    key = (name, m.group(0))
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append({'word': name, 'hit': m.group(0), 'category': category,
                                  'level': LEVEL_NAME[action], 'action': action, 'source': 'pattern',
                                  'start': m.start(), 'end': m.end(), 'kind': 'pattern'})
        return _drop_covered(found)

    def scan(self, text, with_patterns=True):
        """扫描一段文本，返回 {action, hits, blocked, message}。

        action 取所有命中里最重的一级；无命中为 'ok'。
        """
        found = self.hits(text, with_patterns)
        if not found:
            return {'action': 'ok', 'hits': [], 'blocked': False, 'message': ''}
        worst = max(found, key=lambda h: RANK[h['action']])
        return {
            'action': worst['action'],
            'hits': found,
            'blocked': worst['action'] == 'block',
            'message': describe(worst),
        }


def _drop_covered(found):
    """去掉被更长命中完全覆盖、且不更严重的短命中。

    两个作用：
      1. 「13800138000」会被手机号和疑似QQ号两条正则同时抓到 -> 只报一次；
      2. 「走闲鱼」是 block，其中包着的「闲鱼」只是 review -> 只留「走闲鱼」，
         否则拦截理由里会混进一堆噪声词，用户看不懂自己到底错在哪。
    只在**外层命中不更轻**时才丢弃，避免把 block 藏进 review 里。
    """
    accepted = []
    for hit in sorted(found, key=lambda h: (h['start'], -(h['end'] - h['start']))):
        covered = any(a['start'] <= hit['start'] and hit['end'] <= a['end']
                      and RANK[a['action']] >= RANK[hit['action']] for a in accepted)
        if not covered:
            accepted.append(hit)
    accepted.sort(key=lambda h: (h['start'], -RANK[h['action']]))
    return accepted


def describe(hit):
    """把一条命中翻译成给用户看的话。不暴露完整词表，只说命中了哪一类。"""
    where = {'block': '不允许发布', 'review': '已转人工审核', 'report': '已记录'}[hit['action']]
    return f'「{hit["hit"]}」属于{hit["category"]}，{where}。'
