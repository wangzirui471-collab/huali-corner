'use strict';
// 页面层 · 用户档案（管理端）
//
// 目标：把「这个人是谁、有没有前科、现在什么状态」集中到一屏，
// 不用在工单、商品、审计三处来回翻。
//
// 数据来源（全部走既有接口，不新增后端依赖）：
//   /api/profile?id=   公开资料 + 在售商品
//   /api/admin         员工可见的用户表（含 role / status / score）+ 审计记录
//   /api/tickets       员工可见的全部工单，前端按 user_id 过滤
// 说明：订单列表接口只返回「自己的订单」，拿不到他人的，
// 所以本页的订单区先留占位，等 /api/user/dossier 落地后替换。

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
  moderation: '内容处置', appointment: '任命群管理员', dossier_view: '查阅档案',
  product_moderate: '平台处置商品', product_review: '审核商品'
};

export async function dossier(id) {
  if (!needLogin()) return;
  if (!['admin', 'support'].includes(state.me.role)) throw new Error('仅客服或管理员可查看用户档案');
  const target = Number(id);
  if (!Number.isInteger(target) || target <= 0) throw new Error('用户编号无效');

  const [profile, admin, tickets] = await Promise.all([
    api('/profile?id=' + target),
    api('/admin'),
    api('/tickets')
  ]);

  const user = (admin.users || []).find(u => u.id === target);
  if (!user) throw new Error('用户不存在');
  const products = profile.products || [];
  const about = profile.user || {};
  const received = (admin.audit || []).filter(a => a.target === target);
  const performed = (admin.audit || []).filter(a => a.actor === target);
  const mine = (tickets || []).filter(t => t.user_id === target);
  const credits = received.filter(a => a.type === 'credit' || a.type === 'ban' || a.type === 'unban');

  const status = USER_STATUS[user.status] || user.status;
  const head = `<section class="panel dossier-head">
    <span class="avatar jumbo">${e(user.nickname[0])}</span>
    <div>
      <h2>${e(user.nickname)}</h2>
      <p class="muted">#${user.id} · ${e(ROLE_NAMES[user.role] || user.role)} · ${e(status)}
        ${user.college ? ' · ' + e(user.college) : ''}${about.major ? ' · ' + e(about.major) : ''}</p>
      <p>${e(about.bio || '未填写简介')}</p>
    </div>
    <div class="dossier-score"><span>信誉分</span><b class="${user.score < 60 ? 'low' : ''}">${user.score}</b><small>/100</small></div>
  </section>`;

  const stats = `<div class="stat-grid">
    <div class="stat-card"><span>在售商品</span><b>${products.length}</b></div>
    <div class="stat-card"><span>提交工单</span><b>${mine.length}</b></div>
    <div class="stat-card"><span>被处置次数</span><b>${credits.length}</b></div>
    <div class="stat-card"><span>操作留痕</span><b>${performed.length}</b></div>
  </div>`;

  const creditList = credits.length
    ? `<div class="desk-list">${credits.map(a => `<div class="desk-row">
        <div class="desk-row-main"><b>${e(AUDIT_LABELS[a.type] || a.type)}</b>
          <small>${date(a.created)} · 操作人 #${a.actor}${a.ticket_id ? ' · 工单 #' + a.ticket_id : ''}</small>
          <p>${e(a.reason || '')}</p></div>
        ${a.delta ? `<span class="tag ${a.delta < 0 ? 'danger' : ''}">${a.delta > 0 ? '+' : ''}${a.delta} 分</span>` : ''}
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有信誉调整或封禁记录</p>';

  const productList = products.length
    ? `<div class="desk-list">${products.map(p => `<div class="desk-row">
        <div class="desk-row-main"><b>${e(p.title)}</b>
          <small>#${p.id} · ¥${money(p.price)} · ${e(statusNames[p.status] || p.status)}${p.under_review ? ' · 审核中' : ''}</small></div>
        <button class="btn secondary" data-go="product/${p.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有在售商品</p>';

  const ticketList = mine.length
    ? `<div class="desk-list">${mine.map(t => `<div class="desk-row">
        <span class="desk-badge">${e(TICKET_TYPES[t.type] || t.type)}</span>
        <div class="desk-row-main"><b>${e(t.subject)}</b><small>#${t.id} · ${date(t.created)}</small></div>
        <span class="tag">${e(statusNames[t.status] || t.status)}</span>
        <button class="btn secondary" data-go="ticket/${t.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有提交过工单</p>';

  shell(`${heading('DOSSIER', '用户档案 · ' + user.nickname,
    '仅客服与管理员可见；本次查阅已写入审计记录。')}
    <button class="back" data-go="staff/users">← 返回工作台</button>
    ${head}${stats}
    <div class="dossier-grid">
      <section class="panel"><h2>信誉与处置记录</h2>${creditList}</section>
      <section class="panel"><h2>在售商品</h2>${productList}</section>
      <section class="panel"><h2>提交的工单</h2>${ticketList}</section>
      <section class="panel"><h2>订单</h2>
        <p class="desk-empty">订单明细需要「按用户查询订单」的后端接口，尚未提供。
        <small>当前可从该用户的工单进入关联订单。契约见 docs/工作台接口契约.md。</small></p>
      </section>
    </div>`, 'staff');
}
