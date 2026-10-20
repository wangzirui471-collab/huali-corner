'use strict';
// 事件层 · 管理员工作台
//
// 与 actions/staff.js 的分工：
//   staff.js —— 客服台：行内筛选、商品下架/复核/恢复（客服与管理员都会用）；
//   admin.js —— 管理员台：人员授权、整店下架、内容移除、词库维护、审计导出。
//
// 行内筛选（desk-filter）与搜索（desk-search-form）只在 staff.js 里定义一次，
// 因为 actions/index.js 会把各模块的 clicks / submits 合并成一张全局表。
// 管理员工作台的 chip 和搜索框直接复用那一套，所以这里没有重复实现。

import { toast, e } from '../core/dom.js';
import { api } from '../core/http.js';
import { render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { state } from '../core/state.js';
import { pbkdf2Hex, randomSaltHex } from '../core/pbkdf2.js';

async function staffCredential(password) {
  if (state.config.auth_mode !== 'client_kdf') return { password };
  const salt = randomSaltHex();
  const rounds = Number(state.config.pbkdf2_rounds) || 600000;
  return { salt, rounds, digest: await pbkdf2Hex(password, salt, rounds) };
}

async function call(path, payload, okMessage) {
  await api(path, payload);
  closeModal();
  toast(okMessage);
  await render();
}

// 通用确认弹窗。授权类操作一律要二次确认——这些按钮点错一次，
// 代价是某个人当场被踢下线或某个店铺整店消失。
function confirmForm(op, title, body, okText, attrs = '') {
  modal(`<h2>${title}</h2><p class="muted">${body}</p>
    <form id="admin-confirm-form" data-op="${op}" ${attrs}>
      <button class="btn primary full">${okText}</button>
    </form>`);
}

export const clicks = {
  'staff-create': () => {
    const roles = state.me?.role === 'developer'
      ? [['support', '客服（日常处置）'], ['admin', '管理员（授权与改判）'], ['developer', '开发者（最高权限）']]
      : [['support', '客服（日常处置）']];
    modal(`<h2>新建运营账号</h2>
      <p class="muted">客服负责日常处置；管理员还能恢复上架、授权、维护词库；开发者可任命管理员。
      账号一旦建好，口令只有对方知道，管理员也看不到——忘了用「重置密码」。</p>
      <form id="staff-create-form">
        ${field('账号（11 位手机号或邮箱）', 'phone', 'text', '', 'required autocomplete="off" placeholder="13900000000 或 name@qq.com"')}
        ${field('昵称', 'nickname', 'text', '', 'required maxlength="24" placeholder="如：夜班客服小陈"')}
        ${selectField('角色', 'role', roles)}
        ${field('初始密码', 'password', 'password', '', 'required minlength="6" maxlength="128" autocomplete="new-password"')}
        <button class="btn primary full">创建账号</button>
      </form>`);
  },

  // 改身份：四级权限。开发者可授任意角色；管理员只能设/废客服。
  'change-role': async (b, id) => {
    const name = b.closest('.desk-row')?.querySelector('b')?.textContent?.trim() || `#${id}`;
    const isDev = state.me?.role === 'developer';
    const options = isDev
      ? [['user', '普通用户'], ['support', '客服'], ['admin', '管理员'], ['developer', '开发者']]
      : [['user', '普通用户'], ['support', '客服']];
    modal(`<h2>调整身份 · ${name}</h2>
      <p class="muted">${isDev
        ? '你以开发者身份操作，可任命/降级管理员、设/废客服。改权立即生效并踢掉对方全部会话。'
        : '你以管理员身份操作，只能设置或废除客服。改权立即生效并踢掉对方全部会话。'}</p>
      <form id="change-role-form" data-id="${id}">
        ${selectField('新身份', 'role', options)}
        <button class="btn primary full">确认调整</button>
      </form>`);
  },

  'staff-status': async (b, id) => {
    const next = b.dataset.value === 'active';
    const name = b.closest('.desk-row')?.querySelector('b')?.textContent?.trim() || `#${id}`;
    confirmForm('staff-status',
      next ? '启用账号' : '停用账号',
      next
        ? `启用后「${name}」可以重新登录后台。`
        : `停用后「${name}」立即被踢下线且无法再登录。历史审计、工单记录全部保留——停用不是封禁，不会触碰他的商品与订单。`,
      next ? '确认启用' : '确认停用',
      `data-id="${id}" data-value="${next ? 'active' : 'disabled'}"`);
  },

  'staff-reset': async (b, id) => {
    const name = b.closest('.desk-row')?.querySelector('b')?.textContent?.trim() || `#${id}`;
    confirmForm('staff-reset', '重置密码',
      `系统会生成一个临时密码，只显示这一次；「${name}」的全部会话会同时失效，需要用新密码重新登录。`,
      '确认重置', `data-id="${id}"`);
  },

  'staff-revoke': async (b, id) => {
    const name = b.closest('.desk-row')?.querySelector('b')?.textContent?.trim() || `#${id}`;
    confirmForm('staff-revoke', '强制下线',
      `「${name}」在所有设备上的登录会立即失效，需要重新输入密码。商品与订单不受影响。`,
      '确认下线', `data-id="${id}"`);
  },

  'seller-delist': async (b, id) => {
    const name = b.closest('.desk-row')?.querySelector('b')?.textContent?.trim() || `#${id}`;
    modal(`<h2>批量下架整店</h2>
      <p class="muted">卖家：<b>${name}</b>（#${id}）</p>
      <p class="muted">该卖家全部<strong>在售</strong>商品会立即下架，卖家收到一条站内通知，
      可在客服中心申诉。已预留或已售出的商品不会动——它们挂在别人的订单上。</p>
      <form id="admin-reason-form" data-op="seller-delist" data-id="${id}">
        ${field('处置理由（必填，会展示给卖家）', 'reason', 'text', '', 'required maxlength="500" placeholder="如：商品描述多处引导站外交易"')}
        <button class="btn primary full">确认下架全部在售商品</button>
      </form>`);
  },

  'word-remove': async (b) => {
    const word = b.dataset.word;
    confirmForm('word-remove', '停用词条',
      `「${word}」将不再参与扫描。内置词条不会被删除，只是记进数据目录的停用列表——` +
      `这样下次更新词表时它不会复活。保存后立即生效。`,
      '确认停用', `data-word="${word}"`);
  },

  'word-restore': async (b) => {
    const word = b.dataset.word;
    confirmForm('word-restore', '启用词条', `「${word}」会重新参与扫描。`,
      '确认启用', `data-word="${word}"`);
  },

  'audit-export': async () => {
    const query = (location.hash.split('?')[1] || '');
    const res = await fetch('/api/audit/export' + (query ? '?' + query : ''),
      { headers: state.token ? { Authorization: 'Bearer ' + state.token } : {} });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || '导出失败');
    }
    // 必须走 arrayBuffer 而不是 text()：Response.text() 会用 UTF-8 解码，
    // 顺手把服务端加的 BOM（\ufeff）吃掉，落盘后 Excel 打开中文又是乱码。
    // 按字节取再塞进 Blob，才能原样保留。
    const buffer = await res.arrayBuffer();
    const blob = new Blob([buffer], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `审计记录-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    toast('已导出当前筛选条件下的审计记录');
  },

  // 清除账号（仅开发者）。不可逆，所以要求填理由 + 勾确认，
  // 不用通用 confirmForm——那个只有一个按钮，写不了处置依据。
  'purge-account': (b, id) => {
    const nick = b.dataset.nick || ('#' + id);
    modal(`<h2>清除账号</h2>
      <p class="muted">将清除「${e(nick)}」的登录信息与密码，手机号释放给本人重新注册；历史订单、工单、评价与审计保留，昵称显示为「已注销用户」。<b>此操作不可撤销。</b></p>
      <form id="purge-form" data-target="${Number(id)}">
        <label class="field"><span>清除理由（写入审计）</span><textarea name="reason" required maxlength="500" placeholder="例如：测试账号清理 / 本人申请重置 / 严重违规"></textarea></label>
        <label class="checkbox"><input type="checkbox" name="confirm" required>我确认清除该账号，且了解不可恢复</label>
        <button class="btn danger full">确认清除</button>
      </form>`);
  }
};

export const submits = {

  // 全部用户视图的搜索：搜索词进 URL，刷新/分享都能还原。
  'people-search-form': async ({ d }) => {
    const q = String(d.q || '').trim();
    location.hash = 'admin/people?scope=all' + (q ? '&q=' + encodeURIComponent(q) : '');
  },
  'change-role-form': async ({ form, d }) => {
    await call('/admin/role', { target: Number(form.dataset.id), role: d.role }, '身份已调整，对方会话已失效');
  },

  'staff-create-form': async ({ d }) => {
    const result = await api('/admin/staff', {
      phone: d.phone, nickname: d.nickname, role: d.role, ...await staffCredential(d.password)
    });
    closeModal();
    await render();
    // 恢复码只在创建时出现一次，必须让人当场看到并保存——
    // 用 toast 一闪而过等于没给。
    modal(`<h2>账号已创建</h2>
      <p class="muted">把这个账号交给对方，并让他首次登录后自行改密码。</p>
      <p class="muted">恢复码只显示这一次：忘记密码时用它自助重设，不用每次找管理员。</p>
      <p class="mono" style="word-break:break-all;background:var(--surface-2);padding:10px;border-radius:var(--r-xs)">${result.recovery_code}</p>
      <button class="btn primary full" data-action="close">我已保存</button>`);
  },

  'admin-confirm-form': async ({ form }) => {
    const op = form.dataset.op;
    const id = Number(form.dataset.id);
    if (op === 'staff-status') {
      await call('/admin/staff/status', { id, status: form.dataset.value },
        form.dataset.value === 'active' ? '账号已启用' : '账号已停用，会话已注销');
    } else if (op === 'staff-reset') {
      let temporaryPassword;
      let payload = { id };
      if (state.config.auth_mode === 'client_kdf') {
        const bytes = new Uint8Array(18);
        window.crypto.getRandomValues(bytes);
        temporaryPassword = Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('');
        payload = { id, ...await staffCredential(temporaryPassword) };
      }
      const result = await api('/admin/staff/password', payload);
      if (temporaryPassword) result.password = temporaryPassword;
      closeModal();
      await render();
      modal(`<h2>密码已重置</h2>
        <p class="muted">临时密码只显示这一次，请当面或通过可信渠道交给对方。
        对方的旧会话已全部失效。</p>
        <p class="mono" style="word-break:break-all;background:var(--surface-2);padding:10px;border-radius:var(--r-xs)">${result.password}</p>
        <p class="muted">恢复码（同样只显示一次，让对方保存）：</p>
        <p class="mono" style="word-break:break-all;background:var(--surface-2);padding:10px;border-radius:var(--r-xs)">${result.recovery_code}</p>
        <button class="btn primary full" data-action="close">我已保存</button>`);
    } else if (op === 'staff-revoke') {
      const result = await api('/admin/session/revoke', { id });
      closeModal();
      toast(`已注销 ${result.revoked} 个会话，对方需要重新登录`);
      await render();
    } else if (op === 'word-remove') {
      await call('/moderation/words', { op: 'remove', word: form.dataset.word }, '词条已停用，立即生效');
    } else if (op === 'word-restore') {
      await call('/moderation/words', { op: 'restore', word: form.dataset.word }, '词条已启用，立即生效');
    }
  },

  'admin-reason-form': async ({ form, d }) => {
    const id = Number(form.dataset.id);
    const reason = String(d.reason || '').trim();
    const result = await api('/admin/seller/delist', { seller_id: id, reason });
    closeModal();
    toast(`已下架 ${result.count} 件商品，卖家已收到通知`);
    await render();
  },

  'word-add-form': async ({ d }) => {
    // 注意不要在这之后 form.reset()：call() 里的 render() 已经把整个页面重画了，
    // 手里的 form 节点已经脱离文档，reset 一个没人看的旧节点没有意义。
    await call('/moderation/words', {
      op: 'add', word: d.word, category: d.category, action: d.action
    }, '词条已加入并立即生效');
  },

  'audit-filter-form': async ({ d }) => {
    const query = new URLSearchParams();
    for (const key of ['type', 'actor', 'since', 'until']) {
      const value = String(d[key] || '').trim();
      if (value) query.set(key, value);
    }
    const href = 'admin/audit' + (query.toString() ? '?' + query.toString() : '');
    // 用 hash 跳转而不是直接 render：筛选条件要能分享、能刷新后保留。
    location.hash = href;
  },

  'purge-form': async ({ form, d }) => {
    if (!d.confirm){ toast('请先勾选确认'); return; }
    await api('/admin/purge', { target: Number(form.dataset.target), reason: d.reason });
    closeModal();
    toast('账号已清除，该手机号可以重新注册了');
    // 档案页的对象已经不存在了，回用户列表而不是重画当前页。
    location.hash = 'staff/users';
    await render();
  }
};
