'use strict';
// 事件层 · 社区、私聊、群聊、群管理员

import { $, e, toast } from '../core/dom.js';
import { money } from '../core/format.js';
import { state, saveCart } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { needLogin } from '../auth/login.js';
import { messageBubble } from '../pages/messages.js';

export const clicks = {
  chat: async (b, id) => {
    if (!needLogin()) return;
    const r = await api('/rooms/private', {peer:id});
    go('messages/'+r.id);
  },

  join: async b => {
    if (!needLogin()) return;
    const r = await api('/rooms/join', {kind:b.dataset.value});
    go('messages/'+r.id);
  },

  comments: async (b, id) => {
    const comments = await api('/comments?id='+id);
    modal(`<h2>评论与回复</h2><div class="comments">${comments.map(c=>`<div><b>${e(c.nickname)}</b><p>${e(c.body)}</p></div>`).join('')||'<p class="muted">还没有评论</p>'}</div><form id="comment-form" data-id="${id}"><label class="field"><span>回复</span><textarea name="body" required maxlength="1000"></textarea></label><button class="btn primary">发布回复</button></form>`);
  },

  nominate(b, id){
    modal(`<h2>申请群管理员</h2><form id="nominate-form" data-id="${id}"><label class="field"><span>申请理由</span><textarea name="reason" required></textarea></label><button class="btn primary">提交申请</button></form>`);
  },

  appoint: async (b, id) => {
    await api('/admin/nominate', {id});
    toast('已任命群管理员，不包含客服/资金权限');
    await render();
  },

  'block-room': async (b, id) => {
    const r = await api('/rooms');
    const room = r.joined.find(x => x.id === id);
    const peer = room.pair.split(':').map(Number).find(x => x !== state.me.id);
    await api('/block', {target:peer, enabled:true});
    toast('已屏蔽，对方不能继续发消息');
  },

  'open-want': () => {
    if (!needLogin()) return;
    modal(`<h2>发布求购</h2><p class="muted">说明想买什么和预算，平台帮你匹配在售卖家；成交收 5% 撮合服务费（模拟）。</p><form id="want-form">${field('求购物品','keyword','text','','required maxlength="40" placeholder="如：笔记本电脑、羽毛球拍、高等数学上册"')}${field('预算上限（元）','budget','number','','required min="1" max="10000" step="0.01"')}<label class="field"><span>补充说明</span><textarea name="description" maxlength="1000" placeholder="想要的成色、版次、配置等"></textarea></label><button class="btn primary full">发布求购</button></form>`);
  },

  'want-matches': async (b, id) => {
    const w = await api('/want?id='+id);
    modal(`<h2>求购「${e(w.keyword)}」的匹配</h2><p class="muted">预算 ¥${money(w.budget)} · ${w.matches.length} 件匹配</p>${w.matches.length?`<div class="want-matches">${w.matches.map(p=>`<div class="match-row"><img src="${e(p.photos?.[0]?.url)}" alt=""><div class="match-info"><b>${e(p.title)}</b><small>${e(p.nickname)} · ${e(p.region)}</small><span class="price">¥${money(p.price)}</span></div>${p.seller_id!==state.me?.id?`<button class="btn primary sm" data-action="want-buy" data-id="${p.id}" data-want="${w.id}">我要这个</button>`:''}</div>`).join('')}</div>`:'<p class="muted">暂时没有匹配的在售商品，稍后再来看看。</p>'}`);
  },

  'want-buy': async (b, id) => {
    if (!needLogin()) return;
    const p = await api('/product?id='+id);
    if (p.seller_id === state.me.id) throw new Error('不能购买自己的商品');
    if (!state.cart.includes(id)) state.cart.push(id);
    saveCart();
    state.pendingWant = Number(b.dataset.want);
    closeModal();
    go('cart');
    toast('已加入取货清单，结算时记入 5% 撮合服务费');
  }
};

// 公开演示版下点击评论：只给只读样例，不给输入框。
export async function demoComments(id){
  const comments = await api('/comments?id='+id);
  modal(`<h2>社区评论样例</h2>${comments.map(c=>`<p><b>${e(c.nickname)}</b> ${e(c.body)}</p>`).join('')||'<p>暂无评论样例</p>'}<p class="muted">公开演示不接收评论或个人信息。</p>`);
}

export const submits = {
  'post-form': async ({ d }) => {
    if (!needLogin()) return;
    await api('/posts', d);
    toast('帖子已发布');
    await render();
  },

  // 聊天不整页重绘，只把新消息追加到当前会话流里，避免滚动位置和输入状态被重置。
  'message-form': async ({ form, d }) => {
    await api('/messages', {room_id:Number(form.dataset.room), body:d.message, key:crypto.randomUUID()});
    form.reset();
    const messages = await api('/messages?room_id='+form.dataset.room+'&after='+state.messageCursor);
    const stream = $('#chat-stream');
    for (const m of messages){
      stream.insertAdjacentHTML('beforeend', messageBubble(m));
      state.messageCursor = m.id;
    }
    stream.scrollTop = stream.scrollHeight;
  },

  'comment-form': async ({ form, d }) => {
    if (!needLogin()) return;
    await api('/comments', {post_id:Number(form.dataset.id), body:d.body});
    closeModal();
    toast('回复已发布');
    await render();
  },

  'nominate-form': async ({ form, d }) => {
    await api('/nominate', {room_id:Number(form.dataset.id), reason:d.reason});
    closeModal();
    toast('申请已提交，等待平台审核');
  },

  'want-form': async ({ d }) => {
    if (!needLogin()) return;
    const r = await api('/wants', {keyword:d.keyword, budget:Math.round(Number(d.budget)*100), description:d.description||''});
    closeModal();
    toast(r.matches.length ? `求购已发布，已匹配 ${r.matches.length} 件在售商品` : '求购已发布，暂时没有匹配商品');
    await render();
  }
};
