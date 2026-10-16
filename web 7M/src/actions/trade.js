'use strict';
// 事件层 · 订单流转、付款前改单、结算、改约、评价

import { toast } from '../core/dom.js';
import { state, saveCart } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { orderEditModal } from '../pages/orders.js';
import { ticketModal } from '../pages/support.js';

export const clicks = {
  order: async (b, id) => {
    const action = b.dataset.value;
    // 收货和取消不可逆，先让买家/卖家确认一次。
    if (['receive','cancel'].includes(action) && !confirm(action === 'receive'
      ? '请先检查实物、版次和缺陷，确认收到后进入模拟结算。'
      : '确认取消此订单？已模拟支付的款项将模拟退款。')) return;
    await api('/order/action', {id, action});
    toast('订单已更新 · 模拟交易');
    await render();
  },

  'order-edit': async (b, id) => {
    const o = (await api('/orders')).find(x => x.id === id);
    if (!o) throw new Error('订单不存在');
    orderEditModal(o);
  },

  refund: (b, id) => ticketModal('refund', id),

  reschedule(b, id){
    modal(`<h2>申请改约</h2><p class="muted">对方接受前原约定继续有效，不能变更金额。</p><form id="reschedule-form" data-id="${id}">${field('新的交付时间','appointment','datetime-local','','required')}${field('公共碰面地点','address','text','','required maxlength="150"')}<button class="btn primary">提交给对方确认</button></form>`);
  },

  'respond-change': async (b, id) => {
    await api('/order/change', {id, accept:b.dataset.value === 'true'});
    toast('改约已处理');
    await render();
  },

  review(b, id){
    modal(`<h2>订单评价</h2><form id="review-form" data-id="${id}">${selectField('评分','rating',['5','4','3','2','1'])}<label class="field"><span>评价</span><textarea name="body" required></textarea></label><p class="muted">当前订单为模拟，仅用于验证评价权限，不作真实成交背书。</p><button class="btn primary">提交评价</button></form>`);
  }
};

export const submits = {
  'order-edit-form': async ({ form, d, fd }) => {
    const keep = fd.getAll('keep').map(Number);
    if (!keep.length) throw new Error('订单至少要保留一件商品');
    await api('/order/update', {
      id:Number(form.dataset.id),
      product_ids:keep,
      delivery:d.delivery,
      address:d.address,
      appointment:new Date(d.appointment).getTime()/1000
    });
    closeModal();
    toast('订单已修改');
    await render();
  },

  'checkout-form': async ({ d }) => {
    await api('/checkout', {
      product_ids:state.cart,
      delivery:d.delivery,
      address:d.address,
      appointment:new Date(d.appointment).getTime()/1000,
      // 同一笔订单重复提交时用它做幂等，避免生成两张单。
      key:crypto.randomUUID()
    });
    state.cart = [];
    saveCart();
    go('orders');
    toast('订单已生成，当前仅模拟付款');
  },

  'reschedule-form': async ({ form, d }) => {
    await api('/order/action', {
      id:Number(form.dataset.id),
      action:'reschedule',
      appointment:new Date(d.appointment).getTime()/1000,
      address:d.address
    });
    closeModal();
    toast('改约等待对方确认');
    await render();
  },

  'review-form': async ({ form, d }) => {
    await api('/review', {order_id:Number(form.dataset.id), rating:Number(d.rating), body:d.body});
    closeModal();
    toast('模拟订单评价已保存');
  }
};
