'use strict';
// 事件层 · 平台工作台与用户档案
//
// 与 actions/support.js 的分工：
//   support.js —— 用户侧（提工单、封禁入口等）；
//   staff.js   —— 工作台侧（列表筛选、商品处置、商品复核）。
// 两边都有的动作（例如封禁 ban）只在 support.js 里定义一次，这里直接复用，
// 因为 actions/index.js 是把各模块的 clicks 合并成一张表的。
//
// 筛选刻意不走 render()：工作台的痛点是「点一下就整页重画」，
// 过滤只是显隐行，直接改 hidden 更快，也不会丢滚动位置。

import { e, toast } from '../core/dom.js';
import { date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';

async function callDesk(path, payload, okMessage) {
  await api(path, payload);
  closeModal();
  toast(okMessage);
  await render();
}

// 行内筛选：同一分区只有一条 chip 组，单选。
function applyChips(group) {
  const scope = document.querySelector(`[data-chips="${group}"]`);
  if (!scope) return;
  const value = scope.querySelector('.chip.active')?.dataset.value || '';
  document.querySelectorAll(`.desk-row[data-group="${group}"]`).forEach(rowEl => {
    rowEl.hidden = !!value && !(rowEl.dataset.tags || '').split(' ').includes(value);
  });
}

function applySearch(group, q) {
  const needle = (q || '').trim().toLowerCase();
  document.querySelectorAll(`.desk-row[data-group="${group}"]`).forEach(rowEl => {
    rowEl.hidden = !!needle && !(rowEl.dataset.search || '').toLowerCase().includes(needle);
  });
}

export const clicks = {
  // 接待台手动刷新：客服盯着队列时不想整页重载（会丢筛选与滚动位置）。
  'desk-refresh': () => render(),

  // 管理端查看某个用户的会话正文：只读，且每次读取都会写 chat_view 审计。
  // 弹窗里如实标出「档案对象」是谁，避免把对方的发言看混。
  'chat-view': async b => {
    const userId = Number(b.dataset.id), roomId = Number(b.dataset.room);
    const name = b.dataset.name || ('会话 #' + roomId);
    modal(`<h2>${e(name)}</h2><p class="muted">正在读取会话…</p>`);
    let data;
    try { data = await api(`/admin/chat?user_id=${userId}&room_id=${roomId}`); }
    catch (err) {
      modal(`<h2>${e(name)}</h2><p class="muted">读取失败：${e(err.message)}</p>
        <button class="btn secondary full" data-action="close">关闭</button>`);
      return;
    }
    const rows = data.messages || [];
    const log = rows.length
      ? `<div class="chat-log">${rows.map(m => `<div class="chat-log-row${m.user_id === userId ? ' is-target' : ''}">
          <span class="chat-log-who">${e(m.nickname || ('#' + m.user_id))}${m.user_id === userId ? ' · 档案对象' : ''}</span>
          <span class="chat-log-time">${date(m.created)}</span>
          <p>${m.removed === 2 ? '<em class="muted">（已撤回）</em>' : e(m.body)}</p>
        </div>`).join('')}</div>`
      : '<p class="desk-empty">该会话还没有消息</p>';
    modal(`<h2>${e(name)}</h2>
      <p class="muted">只读查看；本次读取已写入审计（操作人 #${state.me.id} → 用户 #${userId} · 会话 #${roomId}）。</p>
      ${log}
      <button class="btn secondary full" data-action="close">关闭</button>`);
  },

  'desk-filter': (b, _id) => {
    const group = b.dataset.group;
    document.querySelectorAll(`[data-chips="${group}"] .chip`).forEach(c => c.classList.toggle('active', c === b));
    applyChips(group);
  },

  // 强制下架他人商品：必须填理由，理由会进审计并通知卖家。
  'moderate-product': async (b, id) => {
    const label = b.closest('.desk-row')?.querySelector('b')?.textContent || ('商品 #' + id);
    modal(`<h2>强制下架商品</h2>
      <p class="muted">${label}</p>
      <p class="muted">下架后商品立即从首页和分类消失，卖家会收到站内通知，并可在客服中心申诉。
      该商品在你复核通过前不能由卖家自行重新上架。</p>
      <form id="moderate-form" data-id="${id}" data-kind="product" data-action="delist">
        ${field('处置理由（必填）', 'reason', 'text', '', 'required maxlength="500"')}
        <button class="btn primary full">确认下架</button>
      </form>`);
  },

  // 恢复上架：把平台判过违规的商品放回市场，属于改判，只有管理员能做。
  'restore-product': async (b, id) => {
    modal(`<h2>恢复上架</h2>
      <p class="muted">该商品会重新出现在首页与分类里，卖家会收到站内通知。</p>
      <p class="muted">这是推翻平台之前的处置结论，请写清依据（申诉成立、误判、已整改等）。</p>
      <form id="moderate-form" data-id="${id}" data-kind="restore" data-action="restore">
        ${field('复核依据（必填，会写入审计）', 'reason', 'text', '', 'required maxlength="500"')}
        <button class="btn primary full">确认恢复上架</button>
      </form>`);
  },

  // 自动审核标记为中危的商品：通过 / 驳回并下架。
  'review-product': async (b, id) => {
    const decision = b.dataset.decision === 'approve' ? 'approve' : 'reject';
    const approve = decision === 'approve';
    modal(`<h2>${approve ? '复核通过' : '驳回并下架'}</h2>
      <p class="muted">${approve
        ? '通过后商品的「审核中」标记会撤下，恢复正常展示。'
        : '该商品会立即下架，卖家会收到站内通知并可在客服中心申诉。'}</p>
      <form id="moderate-form" data-id="${id}" data-kind="review" data-action="${decision}">
        ${field(approve ? '复核说明（选填）' : '驳回理由（必填，会展示给卖家）', 'reason', 'text', '',
          approve ? 'maxlength="500"' : 'required maxlength="500"')}
        <button class="btn primary full">${approve ? '确认通过' : '确认驳回并下架'}</button>
      </form>`);
  }
};

export const submits = {
  'desk-search-form': ({ form, d }) => {
    applySearch(form.dataset.group, d.q);
  },

  'moderate-form': async ({ form, d }) => {
    const id = Number(form.dataset.id);
    const kind = form.dataset.kind;
    const action = form.dataset.action;
    const reason = String(d.reason || '').trim();
    if (kind === 'review') {
      await callDesk('/product/review', { id, decision: action, reason },
        action === 'approve' ? '已复核通过，商品恢复正常展示' : '已驳回并下架，卖家已收到通知');
      return;
    }
    if (kind === 'restore') {
      await callDesk('/product/moderate', { id, action: 'restore', reason }, '已恢复上架，卖家已收到通知');
      return;
    }
    await callDesk('/product/moderate', { id, action, reason }, '已下架，卖家已收到通知');
  }
};
