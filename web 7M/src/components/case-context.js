import { e } from '../core/dom.js';
import { amountText } from './support-fields.js';

export function caseSources(data, staff, admin=false) {
  const sources=data.sources||{}, product=sources.product, post=sources.post;
  if (!product&&!post) return '';
  return `<section class="panel" data-case-sources><h2>关联原内容</h2><p class="muted">${sources.captured?'提交时快照，后续修改不会覆盖此记录':'历史工单未保存快照，以下为当前内容'}</p>${product?`<h3>${e(product.title)}</h3><p>发布者：${e(product.nickname)} · 商品 #${product.id} · ¥${amountText(product.price)}</p><p class="description">${e(product.description)}</p><p class="muted">${e([product.edition,product.notes,product.missing].filter(Boolean).join(' · '))}</p>${staff&&(product.photos||[]).length?`<div class="case-source-photos">${product.photos.filter(p=>p.id).map((p,i)=>`<button class="btn secondary" data-operation="evidence" data-id="${e(p.id)}">商品图片${i+1}</button>`).join('')}</div>`:''}<button class="text-button" data-go="product/${product.id}">查看当前商品详情</button>${admin?`<button class="text-button" data-credit-user="${product.seller_id}" data-credit-case="${data.id}">处理卖家信誉</button>`:''}`:''}${post?`<h3>${e(post.title||post.topic||'社区帖子')}</h3><p>发布者：${e(post.nickname)} · 原帖 #${post.id}</p><p class="description">${e(post.body)}</p>${post.place?`<p>地点：${e(post.place)}</p>`:''}${post.title?`<button class="text-button" data-go="help/${post.id}">查看当前互助信息</button>`:'<button class="text-button" data-go="community">查看社区</button>'}${admin?`<button class="text-button" data-credit-user="${post.user_id}" data-credit-case="${data.id}">处理发布者信誉</button>`:''}`:''}</section>`;
}

export function refundContext(data, order) {
  if (!order||data.type!=='refund') return '';
  return `<div class="notice refund-summary"><strong>退款核对</strong><span>商品 ¥${amountText(order.subtotal)} ＋ 配送 ¥${amountText(order.delivery_fee)} ＝ 订单总价 ¥${amountText(order.total)}</span><span>${data.refund_mode==='return_refund'?'退货退款：'+(data.return_received_at?'实物已退回':'尚未确认收到退货'):'仅退款：不自动恢复商品库存'}</span><span>本次退款后订单结案；部分退款的剩余款项按现有模拟结算规则处理。信誉处罚另行核实。</span></div>`;
}
