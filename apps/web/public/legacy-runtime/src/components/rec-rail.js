'use strict';
// 组件层 · 「小转推荐」横滑轨：紧凑卡 + 推荐理由标签。
// 数据来自 /products?rec=1（后端确定性打分，见 app/core/recommend.py），
// 不用大模型——推荐要的是稳。卡片只带跳转，收藏等操作去详情页做，
// 横滑轨里放按钮只会和手势打架。

import { e, icon } from '../core/dom.js';
import { money } from '../core/format.js';

export function recCard(p){
  const url = p.photos?.[0]?.url || '';
  const img = url
    ? `<img src="${e(url)}" alt="${e(p.title)}" loading="lazy">`
    : `<span class="photo-placeholder" role="img" aria-label="${e(p.title)}暂无实拍图">${icon('camera')}<span>暂无实拍</span></span>`;
  return `<button class="rec-card" data-go="product/${p.id}" aria-label="查看${e(p.title)}">
  <span class="rec-card-img">${img}<i class="rec-reason">${e(p.rec_reason || '编辑推荐')}</i></span>
  <b class="rec-card-title">${e(p.title)}</b>
  <span class="rec-card-price">¥${money(p.price)}</span>
</button>`;
}

export function recRail(items){
  if (!items || !items.length) return '';
  return `<section class="rec-rail" aria-label="小转为你推荐">
  <div class="rec-rail-head">
    <div><span class="home-section-kicker">XIAOZHUAN PICKS</span><h2>小转 · 为你推荐<small>按新鲜度、实拍图和卖家信誉挑的</small></h2></div>
    <button type="button" class="rec-refresh" data-action="rec-refresh" data-page="1">${icon('refresh')}换一批</button>
  </div>
  <div class="rec-rail-track">${items.map(recCard).join('')}</div>
</section>`;
}
