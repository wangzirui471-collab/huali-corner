"""拉取开源敏感词库，转换成项目统一格式后放进 app/moderation/data/thirdparty/。

为什么是「拉取脚本」而不是「直接提交进仓库」：
  1. 体积 —— 上游单份词库最大到 700 KB，其中大部分是非法网址黑名单；
  2. 许可证 —— 各仓库许可不同，混进发布物要逐个合规审查；
  3. 时效 —— 词库会被上游持续更新，拉取比冻结一份快照更合理。

所以：**自建词表进仓库（data/*.txt），开源词表靠本脚本取（data/thirdparty/*.txt）。
后者已在 .gitignore 里排除。**

用法：
    cd "E:\\zi\\huali-corner-trial"
    python scripts/fetch_wordlists.py            # 只拉默认启用的
    python scripts/fetch_wordlists.py --list     # 只看有哪些源，不下载
    python scripts/fetch_wordlists.py --include-ads   # 连广告词库一起拉（需人工筛）
    python scripts/fetch_wordlists.py --all

关于「为什么不需要政治类词库」：
本模块只服务于两件事——校园违禁品审核、交易外流检测。政治类词库与这两件事无关，
误伤面却很大（大量日常词汇被收录），维护成本高、收益低，因此**不纳入**。
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'Backend mission' / 'app' / 'moderation' / 'data' / 'thirdparty'

# 只接受这几类许可。AGPL 有传染性，会波及整个发布物；无许可 = 默认保留所有权利，
# 两者都不能进发布物。已因此排除：
#   cjh0613/tencent-sensitive-words (AGPL-3.0)
#   cjh0613/strict-sensitive-word   (AGPL-3.0)
#   57ing/Sensitive-word            (无许可证)
#   fighting41love/funNLP           (无许可证，且 174 MB)
ALLOWED_LICENSES = {'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'CC0-1.0'}

SOURCES = [
    {
        'name': '涉枪涉爆',
        'slug': 'gunpowder',
        'repo': 'fwwdn/sensitive-stop-words',
        'path': '涉枪涉爆违法信息关键词.txt',
        'license': 'Apache-2.0',
        'category': '开源·涉枪涉爆',
        'level': '高',
        'action': 'block',
        'default_on': True,
        'note': '制爆配方、暴恐类关键词。对「能不能卖刀具」没有帮助——那是我们自建清单的活。',
    },
    {
        'name': '色情低俗',
        'slug': 'vulgar',
        'repo': 'fwwdn/sensitive-stop-words',
        'path': '色情类.txt',
        'license': 'Apache-2.0',
        'category': '开源·色情低俗',
        'level': '高',
        'action': 'block',
        'default_on': True,
        'note': '校园平台商品文案里出现这些词，一律拦截。',
    },
    {
        'name': '广告推广',
        'slug': 'ads',
        'repo': 'fwwdn/sensitive-stop-words',
        'path': '广告.txt',
        'license': 'Apache-2.0',
        'category': '开源·广告推广',
        'level': '中',
        'action': 'review',
        'default_on': False,
        'note': '⚠️ 默认关闭。这 123 条里混着「客服」「网络」「到货」「本店」这类本站合法词汇，'
                '直接用会大面积误伤，必须先人工筛一遍再启用。',
    },
]

HEADER = (
    '# 由 scripts/fetch_wordlists.py 自动生成，请勿手工编辑。\n'
    '# 来源：{repo} / {path}\n'
    '# 许可证：{license}\n'
    '# 拉取时间：{when}\n'
    '# 原始条目 {raw} 条 → 转换 {kept} 条（丢弃单字、超长、重复）\n'
)


def fetch(source, timeout=30):
    url = 'https://raw.githubusercontent.com/{}/master/{}'.format(
        source['repo'], urllib.parse.quote(source['path']))
    request = urllib.request.Request(url, headers={'User-Agent': 'huali-corner-wordlist-fetch'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return url, response.read()


def convert(raw_text, source):
    """上游是「一行一个词」，转成本项目统一的 词条|分类|级别|处置。"""
    seen, kept, dropped = set(), [], 0
    for line in raw_text.splitlines():
        word = line.strip().strip(',').strip()
        if not word or word.startswith('#'):
            continue
        # 单字一律不要：自动机按子串匹配，单字会引发大面积误伤。
        if len(word) < 2 or len(word) > 20:
            dropped += 1
            continue
        if word in seen:
            dropped += 1
            continue
        seen.add(word)
        kept.append('{}|{}|{}|{}'.format(word, source['category'], source['level'], source['action']))
    return kept, dropped


def write_source(source, kept, raw_count, url, when):
    TARGET.mkdir(parents=True, exist_ok=True)
    target = TARGET / (source['slug'] + '.txt')
    # 必须显式 utf-8：Windows 上 Python 3.8 默认编码是 GBK。
    target.write_text(
        HEADER.format(repo=source['repo'], path=source['path'], license=source['license'],
                      when=when, raw=raw_count, kept=len(kept))
        + '\n'.join(kept) + '\n',
        encoding='utf-8')
    return target


def write_attribution(entries, when):
    lines = [
        '# 开源词库署名与来源',
        '',
        '本目录下的词表由 `scripts/fetch_wordlists.py` 从下列开源仓库获取并转换，',
        '**不随仓库提交**（见 `.gitignore`）。各仓库许可如下，转换后的文件保留原许可。',
        '',
        f'生成时间：{when}',
        '',
        '| 文件 | 来源仓库 | 原文件 | 许可证 | 条目 | 原始大小 sha256 |',
        '| --- | --- | --- | --- | --- | --- |',
    ]
    for entry in entries:
        lines.append('| `{}` | [{}](https://github.com/{}) | {} | {} | {} | `{}` |'.format(
            entry['file'], entry['repo'], entry['repo'], entry['path'],
            entry['license'], entry['kept'], entry['sha256'][:16]))
    lines += [
        '',
        '## 已评估但未采用的开源词库',
        '',
        '| 仓库 | 许可 | 不采用的原因 |',
        '| --- | --- | --- |',
        '| `cjh0613/tencent-sensitive-words` | AGPL-3.0 | 传染性许可，会波及整个发布物 |',
        '| `cjh0613/strict-sensitive-word` | AGPL-3.0 | 同上 |',
        '| `57ing/Sensitive-word` | 无 | 无许可证 = 默认保留所有权利，不能进发布物 |',
        '| `fighting41love/funNLP` | 无 | 无许可证；且仓库 174 MB |',
        '| `konsheng/Sensitive-lexicon` | MIT | 许可可用，但主体是政治类与非法网址，'
        '与本模块的两项用途（违禁品、交易外流）无关 |',
        '',
        '`fwwdn/sensitive-stop-words` 的「网址.txt」有 14594 条，收录的是赌博色情小站域名；',
        '而本站学生真正的外流目标是闲鱼、转转、微信、QQ，两者交集几乎为零，故未采用。',
    ]
    (TARGET / 'ATTRIBUTION.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='拉取并转换开源敏感词库')
    parser.add_argument('--list', action='store_true', help='只列出可用的源，不下载')
    parser.add_argument('--include-ads', action='store_true', help='把默认关闭的广告词库也拉下来')
    parser.add_argument('--all', action='store_true', help='等同 --include-ads')
    args = parser.parse_args()

    sources = SOURCES
    if args.list:
        for source in sources:
            state = '默认启用' if source['default_on'] else '默认关闭'
            print('[{}] {name:<10} {repo} / {path}  ({license})'.format(
                state, **source))
            print('           ' + source['note'])
        return 0

    selected = [s for s in sources if s['default_on'] or args.include_ads or args.all]
    entries, failed = [], []
    for source in selected:
        if source['license'] not in ALLOWED_LICENSES:
            print('跳过 {repo}：许可证 {license} 不在白名单内'.format(**source))
            failed.append(source['name'])
            continue
        try:
            url, blob = fetch(source)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print('拉取失败 {}：{}'.format(source['name'], error))
            failed.append(source['name'])
            continue
        raw_text = blob.decode('utf-8', errors='replace')
        kept, dropped = convert(raw_text, source)
        when = time.strftime('%Y-%m-%d %H:%M:%S')
        target = write_source(source, kept, len(raw_text.splitlines()), url, when)
        entries.append({'file': target.name, 'repo': source['repo'], 'path': source['path'],
                        'license': source['license'], 'kept': len(kept),
                        'sha256': hashlib.sha256(blob).hexdigest()})
        print('{name:<10} {kept:>5} 条（丢弃 {dropped}）-> {file}'.format(
            kept=len(kept), dropped=dropped, file=target.name, **source))

    if entries:
        write_attribution(entries, time.strftime('%Y-%m-%d %H:%M:%S'))
        print('\n已写入 {}，共 {} 个词表。'.format(TARGET, len(entries)))
        print('自建词表仍然优先——开源词表只覆盖暴恐与低俗，违禁品和反引流靠 data/ 下的自建清单。')
    if failed:
        print('\n失败：' + '、'.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
