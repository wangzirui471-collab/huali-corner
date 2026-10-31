'use strict';
// 事件层 · 逛逛、筛选、收藏、取货清单、出价、上下架

import { toast, $ } from '../core/dom.js';
import { state, saveCart } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { needLogin } from '../auth/login.js';

export const clicks = {
  // 发布页「AI 帮我写」：按标题/分类/成色生成商品介绍，填进介绍框。
  'ai-describe': async b => {
    const form = b.closest('form'); if (!form) return;
    const title = String(form.title?.value || '').trim();
    if (!title){ toast('先填商品标题，AI 才好写介绍'); return; }
    const cat = form.querySelector('input[name=category]:checked')?.value || '';
    const extra = ['edition','publisher','author','notes','course']
      .map(k => form[k]?.value ? k + ':' + form[k].value : '').filter(Boolean).join(' ');
    b.disabled = true; const label = b.textContent; b.textContent = '正在写…';
    try{
      const r = await api('/ai/describe', {title, category: cat, condition: form.condition?.value || '', extra});
      form.description.value = r.text || '';
      toast(r.mode === 'mock' ? 'AI 服务忙，先按模板写了一段，发布前请核对' : '已生成介绍，发布前请核对');
    }catch(err){ toast(err.message || '生成失败，请手动填写'); }
    finally{ b.disabled = false; b.textContent = label; }
  },
  // 发布页「AI 估价」：同类在售价 + 成色给区间，按中位数填入价格。
  'ai-price': async b => {
    const form = b.closest('form'); if (!form) return;
    const title = String(form.title?.value || '').trim();
    if (!title){ toast('先填商品标题'); return; }
    const cat = form.querySelector('input[name=category]:checked')?.value || '';
    const hint = $('#ai-price-hint');
    b.disabled = true; const label = b.textContent; b.textContent = '估价中…';
    try{
      const r = await api('/ai/price', {title, category: cat, condition: form.condition?.value || '',
        original_price: form.original_price?.value ? Math.round(Number(form.original_price.value) * 100) : null});
      if (hint){
        hint.hidden = false;
        hint.textContent = '建议 ¥' + (r.low / 100).toFixed(2) + '—¥' + (r.high / 100).toFixed(2)
          + '（参考 ' + r.samples + ' 件同类在售）：' + (r.reason || '');
      }
      if (form.price && r.suggest) form.price.value = (r.suggest / 100).toFixed(2);
      toast('已按建议价填入，可自行调整');
    }catch(err){ toast(err.message || '估价失败'); }
    finally{ b.disabled = false; b.textContent = label; }
  },
  'market-channel': b => { state.filter.category = b.dataset.value; state.filter.q = ''; state.freeShelf = false; state.homeLimit = 40; go('home'); },
  'market-shortcut': b => { state.filter.category = b.dataset.value; state.filter.q = b.dataset.q || ''; state.freeShelf = false; state.homeLimit = 40; go('home'); },
  'free-shelf': () => { state.filter.category = ''; state.filter.q = ''; state.freeShelf = true; state.homeLimit = 40; go('home'); },
  category: b => { state.filter.category = b.dataset.value; state.filter.q = ''; state.freeShelf = false; state.homeLimit = 40; go('home'); },
  'feed-tab': b => {
    state.filter.sort = '';
    state.filter.q = '';
    state.freeShelf = b.dataset.free === '1';
    state.filter.category = state.freeShelf ? '' : b.dataset.value;
    state.homeLimit = 40;
    go('home');
  },
  'feed-sort': b => { state.filter.sort = b.dataset.value; go('home'); },
  'load-more': () => state.homeView?.next(),
  'rec-refresh': b => state.homeView?.recRefresh(b),
  'home-slide': b => state.homeView?.slide(b),
  'home-promo-open': b => {
    const slide=b.querySelector('[data-promo-slide]:not([hidden])');
    if (!slide) return;
    if (slide.dataset.route) go(slide.dataset.route);
    else if (slide.dataset.free) clicks['free-shelf']();
    else clicks['market-shortcut']({dataset:{value:slide.dataset.category}});
  },
  'home-top': () => state.homeView?.top(),

  async favorite(b, id){
    if (!needLogin()) return;
    if (b.disabled) return;
    b.disabled=true;
    const on=b.dataset.on === 'true';
    try{
      await api('/react', {product_id:id, kind:'favorite', on});
      toast('收藏已更新');
      if (state.homeView?.retainFavorite && b.isConnected){
        b.dataset.on=String(!on);
        b.classList.toggle('selected',on);
        b.setAttribute('aria-pressed',String(on));
        b.setAttribute('aria-label',(on?'取消收藏':'收藏')+(b.dataset.title||''));
      }else await render();
    }finally{ b.disabled=false; }
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
  // 「立即下单」= 加入清单后直达结算页；不新增后端接口，与 add-cart 同一套数据。
  // 求购关联（pendingWant）不在这里动，交给 state.js 的既有清理规则判断。
  'buy-now': async (b, id) => {
    if (!needLogin()) return;
    const p = await api('/product?id='+id);
    if (p.seller_id === state.me.id) throw new Error('不能购买自己的商品');
    if (!state.cart.includes(id)) state.cart.push(id);
    saveCart();
    go('cart');
  },
  'remove-cart': async (b, id) => {
    state.cart = state.cart.filter(x => x !== id);
    saveCart();
    await render();
  },

  offer(b, id){
    if (!needLogin()) return;
    modal(`<h2>给商品出个价</h2><p class="muted">出价需低于商品价、至少 1 元。卖家接受后，订单将采用该价格，送货费另算，不支持订单外补款。</p><form id="offer-form" data-id="${id}">${field('商品出价（元）','amount','number','','required min="1" max="10000" step="0.01"')}<button class="btn primary">提交出价</button></form>`);
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
  },

  promote(b, id){
    modal(`<h2>置顶推广</h2><p class="muted">付费置顶让你的商品排在「猜你喜欢」和分类顶部。模拟支付，不扣真实款项，到期自动下沉。</p><form id="promote-form" data-id="${id}"><div class="promote-tiers">${[['1d','单日置顶','¥1'],['3d','3天置顶','¥3'],['7d','7天置顶','¥5']].map(([v,l,pr])=>`<label class="tier-option"><input type="radio" name="tier" value="${v}" ${v==='1d'?'checked':''}><span><b>${l}</b><small>${pr} / 次</small></span></label>`).join('')}</div><button class="btn primary full">模拟支付并置顶</button></form>`);
  }
};

export const submits = {
  // 三视图先逐张上传，拿到上传 id 后再随表单一起提交商品。
  'publish-form': async ({ d, fd }) => {
    const uploads = [];
    for (const angle of ['front','side','top','extra']){
      const files = angle === 'extra' ? fd.getAll('extra').filter(f => f.size) : [fd.get(angle)];
      for (const file of files){
        if (!file?.size) continue;
        if (file.size > 5*1024*1024) throw new Error('单张图片不能超过5MB');
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        const r = await api('/upload', {content, angle});
        uploads.push(r.id);
      }
    }
    const payload = {
      ...d,
      photos:uploads,
      price:Math.round(Number(d.price)*100),
      delivery_fee:Math.round(Number(d.delivery_fee)*100),
      original_price:Math.round(Number(d.original_price || 0)*100),
      region:d.building+' · '+d.point,
      college:state.me.college
    };
    const r = await api('/publish', payload);
    toast(r.moderation ? r.moderation.message : '发布成功');
    go('product/'+r.id);
  },

  'search-form': ({ d }) => { state.filter.q = d.q; state.freeShelf = false; state.homeLimit = 40; go('home'); },
  'filter-form': ({ d }) => {
    state.filter.category = d.category;
    state.filter.sort = d.sort;
    state.freeShelf = false;
    state.homeLimit = 40;
    closeModal();
    go('home');
  },
  'offer-form': async ({ form, d }) => {
    await api('/offer', {product_id:Number(form.dataset.id), amount:Math.round(Number(d.amount)*100)});
    closeModal();
    toast('出价已提交，可在订单页查看');
  },
  'promote-form': async ({ form, d }) => {
    const r = await api('/product/promote', {id:Number(form.dataset.id), tier:d.tier});
    closeModal();
    toast(`已置顶 ${r.days} 天（模拟支付 ¥${(r.price/100).toFixed(2)}）`);
    await render();
  }
};
