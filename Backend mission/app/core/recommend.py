"""「小转推荐」打分：本地服务与 Cloudflare Worker 共用同一份规则。

首页推荐轨不用「最新倒序」：那样满屏都是刚上架、九成没有实拍图的商品。
按「买家看得见好坏」的程度排：有实拍 > 新上架 > 卖家信誉 > 置顶；
免费送单独有入口不占推荐位，超 500 元在校园二手里偏贵也往后放。
全部确定性计算，不调模型——推荐要的是稳，不是惊喜。
"""


def rec_has_photo(p):
    photos = p.get('photos')
    return bool(photos) and isinstance(photos, list) and bool((photos[0] or {}).get('url'))


def rec_score(p, now):
    s = 0.0
    if rec_has_photo(p):
        s += 30
    # 年龄夹到非负：created 落在未来（时钟偏差、预置数据）时，
    # 负年龄会把「越新越好」那一项算成巨额加分，直接霸榜。
    age = max(0.0, now - float(p.get('created') or now))
    s += max(0.0, 24 - age / 86400 * 2)             # 越新越好，12 天后归零
    s += (float(p.get('score') or 100) - 90) * 0.8  # 卖家信誉 90 起加分
    if (p.get('promoted_until') or 0) > now:
        s += 6
    price = int(p.get('price') or 0)
    if price <= 0:
        s -= 6                                       # 免费送有专门入口
    elif price > 50000:
        s -= 4                                       # 超 500 元偏贵
    return s


def rec_reason(p, now):
    age = max(0.0, now - float(p.get('created') or now))
    if age < 86400:
        return '今天新上架'
    if age < 3 * 86400:
        return '刚上架'
    if rec_has_photo(p):
        return '带图实拍'
    if float(p.get('score') or 100) >= 95:
        return '诚信卖家'
    return '编辑推荐'


def recommend_order(base, now):
    """打分排序 + 分类打散（同类第 4 件起降权）+ 附推荐理由标签。"""
    scored = sorted(base, key=lambda p: rec_score(p, now), reverse=True)
    counts = {}
    for p in scored:
        c = p.get('category') or ''
        counts[c] = counts.get(c, 0) + 1
        p['_rec_penalty'] = max(0, counts[c] - 3) * 8
    scored.sort(key=lambda p: rec_score(p, now) - p['_rec_penalty'], reverse=True)
    for p in scored:
        p.pop('_rec_penalty', None)
        p['rec_reason'] = rec_reason(p, now)
    return scored
