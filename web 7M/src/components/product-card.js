'use strict';
// 组件层 · 商品卡片与配图
// 演示商品的配图是一张 4×4 拼图（9 格），用 background-position 裁出对应格；
// 真实上传的照片直接显示，不做裁切。

import { e, icon } from '../core/dom.js';
import { money } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { moderationButton } from './product-moderation.js';

// 返回拼图序号 0..8，不是演示图则返回 null。
export function demoPhoto(p){
  if (!p.simulation) return null;
  const url = p.photos?.[0]?.url || '';
  const b = url.match(/\/assets\/book([0-5])\.svg$/);
  const i = url.match(/\/assets\/item([0-2])\.svg$/);
  return b ? Number(b[1]) : i ? [6,7,8][Number(i[1])] : null;
}

// 书籍/宿舍用 AI 生成的拼图，电子产品用维基共享资源实拍 —— 署名要求不同，标注必须分开。
export function demoTag(p){ return demoPhoto(p) !== null ? 'AI演示图' : '演示配图'; }

export function productPicture(p, detail=false){
  const n = demoPhoto(p);
  if (n === null) return `<img ${detail?'id="main-photo"':''} src="${e(p.photos[0].url)}" alt="${e(p.title)}" loading="lazy">`;
  return `${detail?`<img id="main-photo" class="sprite-source" src="${e(p.photos[0].url)}" alt="${e(p.title)}">`:''}<div class="photo-sprite" role="img" aria-label="${e(p.title)}的${demoTag(p)}，非实拍" style="background-position:${(n%4)*100/3}% ${Math.floor(n/4)*100/3}%"></div>`;
}

export function priceLabel(p){
  if (p.delivery === 'both') return `自提 ¥${money(p.price)} <span>／送货 ¥${money(p.price+p.delivery_fee)}</span>`;
  return p.delivery === 'delivery'
    ? `¥${money(p.price+p.delivery_fee)} <span>含送货费 ¥${money(p.delivery_fee)}</span>`
    : `¥${money(p.price)} <span>自提</span>`;
}

export function shipLabel(p){
  return p.delivery === 'pickup' ? '仅自提' : (p.delivery === 'delivery' ? `送货 +¥${money(p.delivery_fee)}` : '自提/送货');
}

// 书籍看版次，其他看成色 —— 买家在列表页最关心的不是同一件事。
export function condBadge(p){
  const t = p.category === 'books' ? (p.edition || '版次待确认') : (p.condition || '正常使用');
  return `<span class="cond-badge">${e(t)}</span>`;
}

export function card(p){
  const orig = Number(p.original_price) || 0;
  const rate = orig > p.price ? Math.round(p.price/orig*1000)/100 : 0;
  const moderation = moderationButton(p, state.me);
  const trusted = p.seller_trusted ? '<span class="trusted-tag">诚信客户</span>' : '';
  return `<article class="product-card"><button class="card-photo" data-go="product/${p.id}" aria-label="查看${e(p.title)}">${productPicture(p)}${condBadge(p)}${p.under_review?`<span class="review-tag">审核中</span>`:''}${(p.promoted_until||0)>Date.now()/1000?`<span class="promote-tag">置顶</span>`:''}${trusted}${p.simulation?`<span class="demo-tag">${demoTag(p)}</span>`:''}${p.status!=='available'?`<span class="sold-tag">${e(statusNames[p.status])}</span>`:''}</button><div class="card-content"><button class="card-title" data-go="product/${p.id}">${e(p.title)}</button><div class="book-meta">${e(p.category==='books'?[p.notes,p.missing].filter(Boolean).join(' · '):p.condition||'日常闲置')}</div><div class="price-line"><i class="cur">¥</i><b>${money(p.price)}</b>${orig>p.price?`<s>¥${money(orig)}</s><em>${rate}折</em>`:''}</div><div class="card-tags"><span class="mini-tag">${shipLabel(p)}</span><span class="mini-tag ghost">${icon('pin')}${e(p.region)}</span></div><div class="card-user"><button data-go="profile/${p.seller_id}"><span class="avatar">${e(p.nickname[0])}</span>${e(p.nickname)}</button><button class="favorite-button ${p.favorited?'selected':''}" aria-label="${p.favorited?'取消收藏':'收藏'}${e(p.title)}" data-action="favorite" data-id="${p.id}" data-on="${!p.favorited}">${icon('heart')}</button></div>${moderation?`<div class="card-moderation">${moderation}</div>`:''}</div></article>`;
}
