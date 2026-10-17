'use strict';
// 页面层 · 用户档案（管理端）
//
// 目标：把「这个人是谁、有没有前科、现在什么状态」集中到一屏，
// 不用在工单、商品、审计三处来回翻。
//
// 数据来自 GET /api/user/dossier?id=（仅客服/管理员）。它与 /api/profile 的区别：
//   /api/profile       —— 给所有人看的公开主页，已收敛掉 role / status；
//   /api/user/dossier  —— 服务端专属，带 role、status、脱敏手机号和订单，
//                         且**每次调用都会写一条 dossier_view 审计**。
// 所以打开本页就会留痕，这是有意的：查档案本身是高敏操作。

import { e } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const ROLE_NAMES = { user: '普通用户', support: '客服', admin: '平台管理员' };
const USER_STATUS = { active: '正常', banned: '已封禁', deactivated: '已注销' };
const TICKET_TYPES = { refund: '售后', report: '举报', appeal: '申诉', reschedule: '改约', other: '咨询' };
const AUDIT_LABELS = {
  credit: '信誉调整', ban: '封禁账号', unban: '解封账号', promote: '付费置顶',
  moderation: '内容处置', appointment: '任命群管理员', dossier_view: '查阅用户档案',
  product_moderate: '平台处置商品', product_review: '审核商品'
};

export async function dossier(id) {
  if (!needLogin()) return;
  if (!['admin', 'support'].includes(state.me.role)) throw new Error('仅客服或管理员可查看用户档案');
  const target = Number(id);
  if (!Number.isInteger(target) || target <= 0) throw new Error('用户编号无效');

  const data = await api('/user/dossier?id=' + target);
  const user = data.user || {};
  const products = data.products || [];
  const orders = data.orders || [];
  const mine = data.tickets || [];
  const received = data.audit || [];
  const credits = received.filter(a => ['credit', 'ban', 'unban'].includes(a.type));
  const status = USER_STATUS[user.status] || user.status || '未知';

  const head = `<section class="panel dossier-head">
    <span class="avatar jumbo">${e((user.nickname || '?')[0])}</span>
    <div>
      <h2>${e(user.nickname || '')}</h2>
      <p class="muted">#${user.id} · ${e(ROLE_NAMES[user.role] || user.role || '')} · ${e(status)}
        ${user.college ? ' · ' + e(user.college) : ''}${user.major ? ' · ' + e(user.major) : ''}</p>
      <p>${e(user.bio || '未填写简介')}</p>
      <p class="muted">联系方式：${data.phone ? e(data.phone) + '（已脱敏）' : '未绑定'}</p>
    </div>
    <div class="dossier-score"><span>信誉分</span><b class="${user.score < 60 ? 'low' : ''}">${user.score}</b><small>/100</small></div>
  </section>`;

  const stats = `<div class="stat-grid">
    <div class="stat-card"><span>在售商品</span><b>${products.length}</b></div>
    <div class="stat-card"><span>参与订单</span><b>${orders.length}</b></div>
    <div class="stat-card"><span>提交工单</span><b>${mine.length}</b></div>
    <div class="stat-card"><span>被处置次数</span><b>${credits.length}</b><small>${credits.length ? '含封禁与信誉调整' : '无违规记录'}</small></div>
  </div>`;

  const creditList = credits.length
    ? `<div class="desk-list">${credits.map(a => `<div class="desk-row">
        <div class="desk-row-main"><b>${e(AUDIT_LABELS[a.type] || a.type)}</b>
          <small>${date(a.created)} · 操作人 #${a.actor}${a.ticket_id ? ' · 工单 #' + a.ticket_id : ''}</small>
          <p>${e(a.reason || '')}</p></div>
        ${a.delta ? `<span class="tag ${a.delta < 0 ? 'danger' : ''}">${a.delta > 0 ? '+' : ''}${a.delta} 分</span>` : ''}
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有信誉调整或封禁记录</p>';

  const orderList = orders.length
    ? `<div class="desk-list">${orders.map(o => `<div class="desk-row">
        <span class="desk-badge">${o.role === 'buyer' ? '买入' : '卖出'}</span>
        <div class="desk-row-main"><b>订单 #${o.id}</b>
          <small>¥${money(o.total)} · ${e(statusNames[o.status] || o.status)} · ${date(o.created)}</small></div>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有参与过订单</p>';

  const productList = products.length
    ? `<div class="desk-list">${products.map(p => `<div class="desk-row">
        <div class="desk-row-main"><b>${e(p.title)}</b>
          <small>#${p.id} · ¥${money(p.price)} · ${e(statusNames[p.status] || p.status)}${p.under_review ? ' · 审核中' : ''}${p.delisted_by ? ' · 平台处置' : ''}</small></div>
        <button class="btn secondary" data-go="product/${p.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发布过商品</p>';

  const ticketList = mine.length
    ? `<div class="desk-list">${mine.map(t => `<div class="desk-row">
        <span class="desk-badge">${e(TICKET_TYPES[t.type] || t.type)}</span>
        <div class="desk-row-main"><b>${e(t.subject)}</b><small>#${t.id} · ${date(t.created)}</small></div>
        <span class="tag">${e(statusNames[t.status] || t.status)}</span>
        <button class="btn secondary" data-go="ticket/${t.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有提交过工单</p>';

  shell(`${heading('DOSSIER', '用户档案 · ' + (user.nickname || ''),
    '仅客服与管理员可见；本次查阅已写入审计记录。')}
    <button class="back" data-go="staff/users">← 返回工作台</button>
    ${head}${stats}
    <div class="dossier-grid">
      <section class="panel"><h2>信誉与处置记录</h2>${creditList}</section>
      <section class="panel"><h2>参与订单</h2>${orderList}</section>
      <section class="panel"><h2>商品</h2>${productList}</section>
      <section class="panel"><h2>提交的工单</h2>${ticketList}</section>
    </div>`, 'staff');
}
