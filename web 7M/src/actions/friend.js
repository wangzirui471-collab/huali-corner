'use strict';
// 事件层 · 好友申请与求购响应
//
// 规则（2026-10 用户确认）：加好友要先申请；同意前只能带一条 ≤15 字的
// 文字附言（没有图片/文件入口）；同意后才能自由聊天。求购的「我能卖」
// 也走好友申请，附言里带上求购关键词，对方同意后私聊协商。

import { $, e, toast } from '../core/dom.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const LIMIT = 15;

function openRequestModal({target, name, prefill='', wantId=0}){
  modal(`<h2>加「${e(name || '对方')}」为好友</h2>
  <p class="muted">对方同意后才能聊天。申请附言最多 ${LIMIT} 个字，不能发图片。</p>
  <form id="friend-request-form" data-id="${Number(target)}" data-want="${Number(wantId) || 0}">
    <label class="field"><span>申请附言（可选）</span>
      <textarea name="message" maxlength="${LIMIT}" rows="2" placeholder="比如：同班同学 / 想买你的书">${e(prefill)}</textarea>
      <small class="friend-counter"><span id="friend-count">${[...String(prefill)].length}</span>/${LIMIT} 字</small></label>
    <div class="user-profile-buttons"><button class="btn primary" type="submit">发送申请</button><button class="btn secondary" type="button" data-action="close">取消</button></div>
  </form>`);
  const ta = $('#friend-request-form [name=message]');
  const counter = $('#friend-count');
  ta?.addEventListener('input', () => {
    const n = [...ta.value].length;
    counter.textContent = String(n);
    counter.parentElement?.classList.toggle('over', n > LIMIT);
  });
}

export const clicks = {
  // 通用入口：data-id=对方用户 id，data-name=昵称（可选）。
  'add-friend': async (b) => {
    if (!needLogin()) return;
    const target = Number(b.dataset.id);
    try {
      const r = await api('/friend/state?user_id=' + target);
      if (r.state === 'self') return toast('不能加自己为好友');
      if (r.state === 'accepted') {                       // 已是好友：直接进私聊
        const room = await api('/rooms/private', {peer: target});
        return go('messages/' + room.id);
      }
      if (r.state === 'pending_out') return toast('申请已发送，等对方处理');
      if (r.state === 'pending_in') return toast('对方已向你发出申请，去「社区 · 新的朋友」处理');
      openRequestModal({target, name: b.dataset.name || ''});
    } catch (err) { toast(err.message || '操作失败'); }
  },

  // 求购响应：data-id=求购 id，data-user=求购者 id，data-keyword=关键词。
  'want-respond': async (b) => {
    if (!needLogin()) return;
    const target = Number(b.dataset.user);
    const keyword = b.dataset.keyword || '';
    try {
      const r = await api('/friend/state?user_id=' + target);
      if (r.state === 'accepted') {
        const room = await api('/rooms/private', {peer: target});
        return go('messages/' + room.id);
      }
      if (r.state === 'pending_out') return toast('你已经申请过了，等对方同意');
      if (r.state === 'pending_in') return toast('对方已向你发出申请，去「社区 · 新的朋友」处理');
      openRequestModal({target, name: b.dataset.name || '', prefill: ('求购：' + keyword).slice(0, LIMIT), wantId: Number(b.dataset.id) || 0});
    } catch (err) { toast(err.message || '操作失败'); }
  },

  'friend-accept': async (b) => {
    await api('/friend/decide', {id: Number(b.dataset.id), accept: true});
    toast('已同意，现在可以聊天了');
    await render();
  },
  'friend-reject': async (b) => {
    await api('/friend/decide', {id: Number(b.dataset.id), accept: false});
    toast('已拒绝');
    await render();
  },
  'friend-message': async (b) => {
    const room = await api('/rooms/private', {peer: Number(b.dataset.id)});
    go('messages/' + room.id);
  },
  'friend-open': () => go('community')
};

export const submits = {
  'friend-request-form': async ({ form, d }) => {
    const message = String(d.message || '').trim();
    if ([...message].length > LIMIT) throw new Error('附言最多 ' + LIMIT + ' 个字');
    const r = await api('/friend/request', {
      target: Number(form.dataset.id),
      message,
      want_id: Number(form.dataset.want) || 0
    });
    closeModal();
    toast(r.message || '申请已发送');
    await render();
  }
};
