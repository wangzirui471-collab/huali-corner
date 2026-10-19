'use strict';
// 事件层 · 社区、私聊、群聊、群管理员

import { $, e, toast, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, saveCart, clearPendingWant } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { needLogin } from '../auth/login.js';
import { isStaff } from '../core/roles.js';
import { chatClicks } from '../pages/messages.js';
import { postCard } from '../pages/community.js';

// 评论条目：抖音评论区风格。头像、昵称、时间，子回复明确标出「回复 @谁」。
// moderatable：当前用户能否处置这条内容（客服/管理员/开发者），且不能是作者自己。
function commentItem(c, editable, moderatable){
  const at = c.parent_nickname
    ? `<span class="reply-at">回复 @${e(c.parent_nickname)}：</span>`
    : '';
  return `<div class="comment-item">
    <span class="comment-avatar">${e((c.nickname||'?')[0])}</span>
    <div class="comment-main">
      <div class="comment-meta"><b>${e(c.nickname)}</b><small>${date(c.created)}</small></div>
      <p class="comment-text">${at}${e(c.body)}</p>
      ${editable ? `<button type="button" class="comment-reply" data-action="reply-comment" data-id="${c.id}" data-nick="${e(c.nickname)}" data-post="${c.post_id}">回复</button>` : ''}
      ${moderatable ? `<button type="button" class="comment-remove" data-action="remove-comment" data-id="${c.id}" data-post="${c.post_id}">删除</button>` : ''}
    </div>
  </div>`;
}

// 扁平评论组装成「主评论 + 缩进子回复」。父评论不在本次加载范围时，
// 该回复按主评论展示，但「回复 @谁」标记保留，对话关系不会丢。
function commentsHtml(comments, editable, moderatable){
  const ids = new Set(comments.map(c => c.id));
  const children = new Map(), tops = [];
  for (const c of comments){
    if (c.parent_id && ids.has(c.parent_id)){
      if (!children.has(c.parent_id)) children.set(c.parent_id, []);
      children.get(c.parent_id).push(c);
    } else tops.push(c);
  }
  return tops.map(top => {
    const kids = children.get(top.id);
    return `<div class="comment-block">${commentItem(top, editable, moderatable)}${kids && kids.length ? `<div class="comment-children">${kids.map(k => commentItem(k, editable, moderatable)).join('')}</div>` : ''}</div>`;
  }).join('') || '<p class="muted comments-empty">还没有评论，来说两句吧。</p>';
}

// 删除内容（帖子 / 评论）的确认框：必须写理由，理由会进审计并通知作者。
// 用软删除，误删能在后台恢复；所以文案不说「永久删除」，避免吓退处置人。
function contentRemoveForm(kind, id, label){
  modal(`<h2>删除${label}</h2>
    <p class="muted">删除后这条${label}不再对任何人展示，作者会收到通知并可在客服中心申诉。记录仍保留在后台，误删可以恢复。</p>
    <form id="remove-content-form" data-kind="${kind}" data-id="${Number(id)}">
      <label class="field"><span>处置理由（写入审计，作者可见）</span><textarea name="reason" required maxlength="500" placeholder="例如：含违法交易信息 / 人身攻击 / 泄露他人隐私"></textarea></label>
      <button class="btn danger full">确认删除</button>
    </form>`);
}

// 评论区面板：头部（评论数 + 收起）、加载更早、评论列表、底部「说点什么」。
function commentsPanel(id, comments, editable, moderatable){
  const head = `<div class="comments-head"><b>评论 ${comments.length}</b><button type="button" class="comments-close" data-action="close-comments" aria-label="收起评论">${icon('close')}</button></div>`;
  const more = comments.length >= 100
    ? `<button class="text-button more-comments" data-action="more-comments" data-id="${id}" data-before="${comments[0].id}">加载更早的评论</button>`
    : '';
  const list = `<div class="comments-body">${commentsHtml(comments, editable, moderatable)}</div>`;
  const form = editable
    ? `<form id="comment-form" data-post="${id}"><div class="comment-composer"><textarea name="body" required maxlength="1000" placeholder="说点什么…"></textarea><button class="btn primary">发布</button></div></form>`
    : '';
  return head + more + list + form;
}

// 重新拉取并重绘评论区（提交评论 / 加载更早后调用），保持展开状态。
async function refreshComments(box){
  const id = Number(box.dataset.post);
  const comments = await api('/comments?id='+id);
  box._comments = comments;
  box.innerHTML = commentsPanel(id, comments, true, isStaff(state.me));
  const card = box.previousElementSibling;
  const btn = card && card.querySelector('.post-action[data-action="comments"]');
  if (!btn) return;
  const badge = btn.querySelector('.reply-count'), n = comments.length;
  if (badge) badge.textContent = n;
  else if (n) btn.insertAdjacentHTML('beforeend', `<span class="reply-count">${n}</span>`);
}

// 聊天室专属交互（撤回/移除/成员抽屉/表情面板）定义在 pages/messages.js，
// 这里合并进全站事件表，页面保持零监听器风格。
export const clicks = {
  ...chatClicks,

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

  // 帖子流按 offset 游标累积：后端 limit 封顶 50，若沿用「加大 limit」会在第 51 条处
  // 卡死（按钮判断条件永不成立）。这里改为每页 20 条追加，翻到多少加载多少。
  'load-more-posts': async () => {
    const more = await api('/posts?limit=20&offset='+state.postsFeed.length);
    if (!more.length) return;
    state.postsFeed = state.postsFeed.concat(more);
    $('#post-list').insertAdjacentHTML('beforeend', more.map(postCard).join(''));
    if (more.length < 20) $('#post-more')?.remove();
  },

  // 评论区就地展开在帖子卡片下方（手风琴：同一时间只展开一个帖子），
  // 不再弹窗 —— 回复关系靠嵌套缩进 + 「回复 @谁」表达，一眼看得清。
  comments: async (b, id) => {
    document.querySelectorAll('.post-comments').forEach(el => el.remove());
    const card = b.closest('.post-card');
    if (!card) return;
    const comments = await api('/comments?id='+id);
    const box = document.createElement('div');
    box.className = 'post-comments';
    box.dataset.post = id;
    box._comments = comments;
    box.innerHTML = commentsPanel(id, comments, true, isStaff(state.me));
    card.insertAdjacentElement('afterend', box);
    box.scrollIntoView({ block:'nearest', behavior:'smooth' });
  },

  // 评论游标「加载更早」：后端每次最多回最新 100 条，用最早一条的 id 作 before 往前翻。
  // 旧评论与已加载评论合并后整块重绘，保证嵌套结构重新组装正确。
  'more-comments': async (b, id) => {
    const box = b.closest('.post-comments');
    const older = await api('/comments?id='+id+'&before='+b.dataset.before);
    if (!older.length){ b.remove(); return; }
    const merged = [...older, ...(box._comments || [])];
    box._comments = merged;
    const list = box.querySelector('.comments-body');
    if (list) list.innerHTML = commentsHtml(merged, true);
    const count = box.querySelector('.comments-head b');
    if (count) count.textContent = '评论 ' + merged.length;
    b.dataset.before = older[0].id;
    if (older.length < 100) b.remove();
  },

  // 点某条评论的「回复」：在它下面就地展开输入框（手风琴，一次只回一条）。
  'reply-comment': (b, id) => {
    const item = b.closest('.comment-item');
    const box = item.closest('.post-comments');
    box.querySelectorAll('.comment-inline').forEach(el => el.remove());
    const wrap = document.createElement('div');
    wrap.className = 'comment-inline';
    wrap.innerHTML = `<form id="comment-reply-form" data-post="${b.dataset.post}" data-parent="${id}" data-nick="${b.dataset.nick}"><div class="comment-composer inline"><span class="reply-hint">回复 @${b.dataset.nick}：</span><textarea name="body" required maxlength="1000" placeholder="回复 @${b.dataset.nick}…"></textarea><button class="btn primary sm">回复</button><button type="button" class="btn ghost sm" data-action="cancel-inline-reply">取消</button></div></form>`;
    item.after(wrap);
    wrap.querySelector('textarea').focus();
  },

  'cancel-inline-reply': b => { b.closest('.comment-inline').remove(); },

  // 收起评论区
  'close-comments': b => { b.closest('.post-comments').remove(); },

  // 删除违法/辱骂内容：只有客服及以上能看到按钮（页面渲染时判断），
  // 后端同样校验权限，且不允许处置自己发布的内容。
  'remove-post': (b, id) => contentRemoveForm('post', id, '帖子'),
  'remove-comment': (b, id) => contentRemoveForm('comment', id, '评论'),

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
    if (!room || !room.pair) throw new Error('会话不存在或已失效');
    const peer = room.pair.split(':').map(Number).find(x => x !== state.me.id);
    await api('/block', {target:peer, enabled:true});
    toast('已屏蔽，对方不能继续发消息');
  },

  // 买家在取货清单上可以主动放弃求购关联，避免下一笔无关订单被记服务费。
  'clear-want': () => {
    clearPendingWant();
    toast('已取消求购关联，本次结算按普通下单处理');
    render();
  },

  // 「全部标记已读」的处理器已删：打开通知页时页面会自动全部标读
  // （messages.js 通知视图的自动标记块），这个动作再无触发点。

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
    // 记住来源商品：该商品被移出清单或清单被清空时，这份求购关联要一起失效，
    // 否则之后买任何东西都会带着这个 want_id（见 core/state.js 的 syncPendingWant）。
    state.pendingWant = {want:Number(b.dataset.want), product:id};
    saveCart();
    closeModal();
    go('cart');
    toast('已加入取货清单，结算时记入 5% 撮合服务费');
  }
};

// 公开演示版下点击评论：同样内嵌展开，但只读展示，不给输入框和回复按钮。
export async function demoComments(id){
  document.querySelectorAll('.post-comments').forEach(el => el.remove());
  const btn = document.querySelector(`.post-action[data-action="comments"][data-id="${id}"]`);
  const card = btn && btn.closest('.post-card');
  if (!card) return;
  const comments = await api('/comments?id='+id);
  const box = document.createElement('div');
  box.className = 'post-comments demo';
  box.dataset.post = id;
  box.innerHTML = commentsPanel(id, comments, false, false);
  card.insertAdjacentElement('afterend', box);
}

export const submits = {
  // 执行删除：评论删完就地刷新评论区，帖子删完把卡片和它的评论区一起摘掉，
  // 都不整页重画——管理员巡视时往往连着删好几条，重画会把滚动位置顶回去。
  'remove-content-form': async ({ form, d }) => {
    const kind = form.dataset.kind;
    const id = Number(form.dataset.id);
    await api('/admin/content/action', { kind, id, action: 'remove', reason: d.reason });
    closeModal();
    toast(kind === 'post' ? '帖子已删除' : '评论已删除');
    if (kind === 'comment'){
      const box = document.querySelector('.post-comments');
      if (box) await refreshComments(box);
    } else if (kind === 'post'){
      const card = document.querySelector(`.post-card[data-post="${id}"]`);
      if (card){
        const next = card.nextElementSibling;
        if (next && next.classList.contains('post-comments')) next.remove();
        card.remove();
      }
    }
  },

  'post-form': async ({ d }) => {
    if (!needLogin()) return;
    await api('/posts', d);
    toast('帖子已发布');
    await render();
  },

  // 聊天发送已改由聊天页内的 wx-form 本地处理（需要读光标/滚动位置等局部状态），
  // 这里不再有 message-form；公开演示版的说明页不涉及发送。

  // 底部「说点什么」：发布后局部刷新评论区，不再整页重画。
  'comment-form': async ({ form, d }) => {
    if (!needLogin()) return;
    await api('/comments', {post_id:Number(form.dataset.post), body:d.body});
    toast('评论已发布');
    await refreshComments(form.closest('.post-comments'));
  },

  // 内联回复：回复某条评论，带上 parent_id，刷新后显示「回复 @谁」。
  'comment-reply-form': async ({ form, d }) => {
    if (!needLogin()) return;
    await api('/comments', {post_id:Number(form.dataset.post), parent_id:Number(form.dataset.parent), body:d.body});
    toast('回复已发布');
    await refreshComments(form.closest('.post-comments'));
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
