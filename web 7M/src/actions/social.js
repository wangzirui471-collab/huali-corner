'use strict';
// 事件层 · 社区、私聊、群聊、群管理员

import { $, e, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { needLogin } from '../auth/login.js';
import { appendMessages } from '../pages/messages.js';

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
    if(!stream)return;
    appendMessages(messages);
    if(document.visibilityState!=='hidden'&&state.messageCursor)await api('/messages/read',{room_id:Number(form.dataset.room),through_id:state.messageCursor});
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
  }
};
