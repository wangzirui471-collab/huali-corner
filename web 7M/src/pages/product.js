'use strict';
// 页面层 · 商品详情
// 2026-10-18 可读性重排 + 买家动线调整：主按钮改「立即下单」、补卖家/同类推荐位。
// 业务规则不变：金额整数分、状态名、演示图标注、审核提示、管理下架入口都保持原样。

import { $, e, icon } from '../core/dom.js';
import { money } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell } from '../core/shell.js';
import { priceLabel, productPicture, demoPhoto, demoTag, card } from '../components/product-card.js';
import { moderationButton } from '../components/product-moderation.js';

// 版本/出版信息只在「看起来是真实内容」时展示。
// 历史数据里 publisher/author 被填成 "1"，直接拼会渲染出「版本待确认 1」这种乱码。
function readable(text){
  const t = String(text || '').trim();
  return t && !/^\d+$/.test(t) ? t : '';
}

function editionLine(p){
  return [readable(p.edition) || p.condition || '', readable(p.publisher)].filter(Boolean).join(' · ');
}

// 卖家自述和成色自选字段可能矛盾（介绍写「全新」，成色选「正常使用痕迹」）。
// 不替卖家改口，也不下架，只提醒买家交付时当面核对。
function mismatchNotice(p){
  const desc = String(p.description || '');
  const cond = String(p.condition || '');
  if (!/全新|未使用|没用过|没有使用/.test(desc)) return '';
  if (/近乎全新|全新/.test(cond)) return '';
  return `<div class="notice warn">${icon('alert')}<span><b>卖家介绍与成色可能不一致</b><p>介绍中提到「全新」，成色标注为「${e(cond)}」。交付时请当面核对实物与描述。</p></span></div>`;
}

// 详情页此前是死胡同：看完只能返回。这里补两个兜底入口，
// 数据直接复用列表接口的 seller/category 下推过滤，不新增后端路由。
async function recommendations(p){
  // 必须排除当前商品，否则「该卖家的其他闲置」第一件就是它自己。
  const pick = list => (list || []).filter(x => x.id !== p.id && x.status === 'available').slice(0, 4);
  const [sameSeller, sameCategory] = await Promise.all([
    api('/products?seller=' + p.seller_id).catch(() => []),
    api('/products?category=' + p.category).catch(() => []),
  ]);
  const sections = [
    ['该卖家的其他闲置', pick(sameSeller)],
    ['同类的其他闲置', pick(sameCategory.filter(x => x.seller_id !== p.seller_id))],
  ];
  return sections.filter(([, items]) => items.length)
    .map(([title, items]) => `<section class="panel"><div class="section-heading"><h2>${e(title)}</h2></div><div class="product-grid">${items.map(card).join('')}</div></section>`)
    .join('');
}

export async function product(id){
  const p = await api('/product?id='+id);
  const thumbs = p.simulation ? [p.photos[0]] : p.photos;
  const extras = await recommendations(p);
  const available = p.status === 'available';
  const angleName = x => ({front:'正面', side:'侧面', top:'顶部', extra:'细节'}[x.angle] || '细节');
  shell(`<button class="back" data-go="home">← 返回逛逛</button>
<div class="detail-grid">
  <section>
    <div class="detail-photo">${productPicture(p, true)}${p.simulation ? `<span class="photo-tag">${demoTag(p)} · 非真实商品实拍</span>` : ''}</div>
    <div class="thumbnails">${thumbs.map(x => `<button data-action="photo" data-url="${e(x.url)}" aria-label="${p.simulation ? demoTag(p) : angleName(x)}">${demoPhoto(p) !== null ? productPicture(p) : `<img src="${e(x.url)}" alt="${angleName(x)}">`}</button>`).join('')}</div>
  </section>
  <section class="detail-info">
    <span class="tag">${e(statusNames[p.status])} · 广州校区</span>
    <h1>${e(p.title)}</h1>
    <p class="muted">${e(editionLine(p))}</p>
    <div class="detail-price">${priceLabel(p)}</div>
    <button class="seller-box" data-go="profile/${p.seller_id}"><span class="avatar large">${e(p.nickname[0])}</span><span><b>${e(p.nickname)}${p.seller_trusted ? '<span class="trusted-tag">诚信客户</span>' : ''}</b><small>${e(p.seller_college)} · 信誉 ${p.score}/100</small></span>${icon('arrow')}</button>
    <div class="facts">
      <div><span>交付地点</span><b>${e(p.region)}</b></div>
      <div><span>购买时间</span><b>${e(p.bought || '未确认')}</b></div>
      <div><span>成色</span><b>${e(p.condition || '见实拍与介绍')}</b></div>
      ${p.category === 'books' ? `<div><span>笔记</span><b>${e(p.notes)}</b></div><div><span>缺页</span><b>${e(p.missing)}</b></div><div><span>附件</span><b>${e(p.accessories)}</b></div>` : ''}
    </div>
    <h3>卖家介绍</h3>
    <p class="description">${e(p.description)}</p>
    ${mismatchNotice(p)}
    <div class="notice">${icon('check')} 交付时请核对版次、笔记、缺页和附件。三视图不等于正版鉴定；本平台不承诺包赔。</div>
    ${p.under_review ? `<div class="notice review">${icon('clock')}<span><b>该商品正在人工复核</b><p>复核期间可以正常浏览，但建议先联系客服确认后再下单；若确认违规将被下架。</p></span></div>` : ''}
    ${p.original_price ? `<div class="estimate">同类闲置常见成交 ¥${money(Math.round(p.original_price*.15))}—${money(Math.round(p.original_price*.5))}<small>按原价折旧粗略估算，只作比价参考，不代表平台定价或成交保证。</small></div>` : ''}
    <div class="detail-actions">
      <button class="btn secondary" data-action="favorite" data-id="${p.id}" data-on="${!p.favorited}">${icon('heart')}${p.favorited ? '已收藏' : '收藏'}</button>
      <button class="btn secondary" data-action="like" data-id="${p.id}" data-on="${!p.liked}">赞 ${p.likes}</button>
      <button class="btn secondary" data-action="share">${icon('share')}转发</button>
      <button class="btn secondary" data-action="add-cart" data-id="${p.id}" ${available ? '' : 'disabled'}>加入清单</button>
    </div>
    <button class="btn primary full buy-now" data-action="buy-now" data-id="${p.id}" ${available ? '' : 'disabled'}>${available ? '立即下单' : '已' + e(statusNames[p.status] || '')}</button>
    <div class="detail-actions">
      <button class="btn secondary" data-action="chat" data-id="${p.seller_id}">想要 · 私聊</button>
      <button class="btn secondary" data-action="offer" data-id="${p.id}">我来出价</button>
      ${moderationButton(p, state.me)}
      <button class="text-button" data-action="report" data-id="${p.id}">举报商品</button>
    </div>
  </section>
</div>${extras}`, 'product');
}
