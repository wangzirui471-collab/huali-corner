'use strict';
// 事件层 · 逛逛、筛选、收藏、取货清单、出价、上下架

import { toast } from '../core/dom.js';
import { state, saveCart } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { needLogin } from '../auth/login.js';

export const clicks = {
  'market-channel': b => { state.filter.category = b.dataset.value; state.filter.q = ''; state.freeShelf = false; go('home'); },
  'market-shortcut': b => { state.filter.category = b.dataset.value; state.filter.q = b.dataset.q || ''; state.freeShelf = false; go('home'); },
  'free-shelf': () => { state.filter.category = ''; state.filter.q = ''; state.freeShelf = true; go('home'); },
  category: b => { state.filter.category = b.dataset.value; state.filter.q = ''; state.freeShelf = false; go('home'); },
  'feed-tab': b => {
    state.filter.sort = '';
    state.filter.q = '';
    state.freeShelf = b.dataset.free === '1';
    state.filter.category = state.freeShelf ? '' : b.dataset.value;
    go('home');
  },
  'feed-sort': b => { state.filter.sort = b.dataset.value; go('home'); },

  async favorite(b, id){
    if (!needLogin()) return;
    await api('/react', {product_id:id, kind:'favorite', on:b.dataset.on === 'true'});
    toast('收藏已更新');
    await render();
  },
  async like(b, id){
    if (!needLogin()) return;
    await api('/react', {product_id:id, kind:'like', on:b.dataset.on === 'true'});
    toast('点赞已更新');
    await render();
  },

  'add-cart': async (b, id) => {
    if (!needLogin()) return;
    const p = await api('/product?id='+id);
    if (p.seller_id === state.me.id) throw new Error('不能购买自己的商品');
    if (!state.cart.includes(id)) state.cart.push(id);
    saveCart();
    toast('已加入取货清单，可合并同卖家商品');
    await render();
  },
  'remove-cart': async (b, id) => {
    state.cart = state.cart.filter(x => x !== id);
    saveCart();
    await render();
  },

  offer(b, id){
    if (!needLogin()) return;
    modal(`<h2>给商品出个价</h2><p class="muted">卖家接受后，订单将采用该价格。送货费另算，不支持订单外补款。</p><form id="offer-form" data-id="${id}">${field('商品出价（元）','amount','number','','required min="0" max="10000" step="0.01"')}<button class="btn primary">提交出价</button></form>`);
  },
  'accept-offer': async (b, id) => {
    await api('/offer/accept', {id, accept:b.dataset.value === 'true'});
    toast('报价状态已更新');
    await render();
  },

  delist: async (b, id) => {
    if (!confirm('下架后买家看不到这件商品，可以随时重新上架。确认下架？')) return;
    await api('/product/status', {id, action:'delist'});
    toast('已下架，可在「我发布的」里重新上架');
    await render();
  },
  relist: async (b, id) => {
    if (!confirm('重新上架后买家可以再次看到并下单。确认上架？')) return;
    await api('/product/status', {id, action:'relist'});
    toast('已重新上架');
    await render();
  }
};

export const submits = {
  'search-form': ({ d }) => { state.filter.q = d.q; state.freeShelf = false; go('home'); },
  'filter-form': ({ d }) => {
    state.filter.category = d.category;
    state.filter.sort = d.sort;
    state.freeShelf = false;
    closeModal();
    go('home');
  },
  'offer-form': async ({ form, d }) => {
    await api('/offer', {product_id:Number(form.dataset.id), amount:Math.round(Number(d.amount)*100)});
    closeModal();
    toast('出价已提交，可在订单页查看');
  }
};
