import { e } from '../core/dom.js';

const actors = {buyer:'买家',seller:'卖家',staff:'客服／管理员',admin:'管理员'};

export function orderProgress(order) {
  if (!order.progress) return '';
  return `<section class="order-progress" data-order-progress aria-label="订单各项进度">${[
    ['order','订单进度'],['delivery','交付进度'],['after_sales','售后进度'],['funds','模拟资金']
  ].map(([key,title])=>{
    const part=order.progress[key]||{};
    return `<div class="progress-item"><h4>${title}</h4><p>${e(part.label||'待核实')}</p>${part.next_actor?`<small>下一步：${e(actors[part.next_actor]||'待核实')}</small>`:''}</div>`;
  }).join('')}</section>`;
}
