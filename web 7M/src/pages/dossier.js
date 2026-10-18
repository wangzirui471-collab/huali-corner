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

import { e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { isAdmin, isDeveloper } from '../core/roles.js';
import { needLogin } from '../auth/login.js';

const ROLE_NAMES = { user: '普通用户', support: '客服', admin: '平台管理员', developer: '开发者' };
const ROLE_TONE = { user: 'mute', support: 'info', admin: 'violet', developer: 'warn' };
const USER_STATUS = { active: '正常', banned: '已封禁', deactivated: '已注销', deleted: '已清除' };
const USER_TONE = { active: 'ok', banned: 'danger', deactivated: 'mute' };
const TICKET_TYPES = { refund: '售后', report: '举报', appeal: '申诉', reschedule: '改约', other: '咨询' };
const TICKET_TONE = { refund: 'violet', report: 'danger', appeal: 'warn', reschedule: 'info', other: 'mute' };
const AUDIT_LABELS = {
  credit: '信誉调整', ban: '封禁账号', unban: '解封账号', promote: '付费置顶',
  moderation: '内容处置', appointment: '任命群管理员', dossier_view: '查阅用户档案',
  product_moderate: '平台处置商品', product_review: '审核商品'
};

const statePill = (label, tone = 'mute') =>
  `<span class="state-pill" data-tone="${tone}"><i aria-hidden="true"></i>${e(label)}</span>`;

const sectionHead = (ic, title) =>
  `<header class="desk-panel-head"><h2>${icon(ic)}${e(title)}</h2></header>`;

export async function dossier(id) {
  if (!needLogin()) return;
  // 档案聚合了一个账号的全部痕迹（订单、评论、帖子、评价、求购、处置记录），
  // 2026-10-18 起仅平台管理员与开发者可看；客服的日常处置用不到全量档案。
  if (!isAdmin(state.me)) throw new Error('仅平台管理员或开发者可查看用户档案');
  const target = Number(id);
  if (!Number.isInteger(target) || target <= 0) throw new Error('用户编号无效');

  const data = await api('/user/dossier?id=' + target);
  const user = data.user || {};
  const products = data.products || [];
  const orders = data.orders || [];
  const mine = data.tickets || [];
  const received = data.audit || [];
  const comments = data.comments || [];
  const posts = data.posts || [];
  const reviews = data.reviews || [];
  const wants = data.wants || [];
  const credits = received.filter(a => ['credit', 'ban', 'unban'].includes(a.type));
  const status = USER_STATUS[user.status] || user.status || '未知';
  const roleTone = ROLE_TONE[user.role] || 'mute';
  const score = Math.max(0, Math.min(100, Number(user.score) || 0));

  const head = `<section class="panel dossier-head">
    <span class="avatar role-avatar" data-tone="${roleTone}">${e((user.nickname || '?')[0])}</span>
    <div>
      <h2>${e(user.nickname || '')}${statePill(ROLE_NAMES[user.role] || user.role || '未知', roleTone)}</h2>
      <p class="muted">#${user.id} · ${e(status)}${user.college ? ' · ' + e(user.college) : ''}${user.major ? ' · ' + e(user.major) : ''}</p>
      <p>${e(user.bio || '未填写简介')}</p>
      <p class="muted">联系方式：${data.phone ? e(data.phone) + '（已脱敏）' : '未绑定'}</p>
    </div>
    <div class="dossier-score">
      <span>信誉分</span>
      <b class="${score < 60 ? 'low' : ''}">${score}</b><small>/100</small>
      <span class="meter" aria-hidden="true"><span style="width:${score}%"></span></span>
    </div>
  </section>`;

  const stats = `<div class="stat-grid">
    <div class="stat-card"><span>在售商品</span><b>${products.length}</b></div>
    <div class="stat-card"><span>参与订单</span><b>${orders.length}</b></div>
    <div class="stat-card"><span>提交工单</span><b>${mine.length}</b></div>
    <div class="stat-card"><span>被处置次数</span><b>${credits.length}</b><small>${credits.length ? '含封禁与信誉调整' : '无违规记录'}</small></div>
  </div>`;

  const creditList = credits.length
    ? `<div class="desk-list">${credits.map(a => `<div class="desk-row">
        <span class="row-glyph" data-tone="${a.delta < 0 ? 'danger' : 'ok'}">${icon('chart')}</span>
        <div class="desk-row-main"><b>${e(AUDIT_LABELS[a.type] || a.type)}</b>
          <small>${date(a.created)} · 操作人 #${a.actor}${a.ticket_id ? ' · 工单 #' + a.ticket_id : ''}</small>
          <p>${e(a.reason || '')}</p></div>
        ${a.delta ? statePill(`${a.delta > 0 ? '+' : ''}${a.delta} 分`, a.delta < 0 ? 'danger' : 'ok') : ''}
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有信誉调整或封禁记录</p>';

  const orderList = orders.length
    ? `<div class="desk-list">${orders.map(o => `<div class="desk-row">
        <span class="row-glyph" data-tone="${o.role === 'buyer' ? 'info' : 'violet'}">${icon(o.role === 'buyer' ? 'bag' : 'tag')}</span>
        <div class="desk-row-main"><b>订单 #${o.id}</b>
          <small><span class="amount">¥${money(o.total)}</span> · ${e(statusNames[o.status] || o.status)} · ${date(o.created)}</small></div>
        ${statePill(o.role === 'buyer' ? '买入' : '卖出', o.role === 'buyer' ? 'info' : 'violet')}
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有参与过订单</p>';

  const productList = products.length
    ? `<div class="desk-list">${products.map(p => `<div class="desk-row">
        <span class="row-glyph" data-tone="mute">${icon('tag')}</span>
        <div class="desk-row-main"><b>${e(p.title)}</b>
          <small>#${p.id} · <span class="amount">¥${money(p.price)}</span> · ${e(statusNames[p.status] || p.status)}${p.under_review ? ' · 审核中' : ''}${p.delisted_by ? ' · 平台处置' : ''}</small></div>
        <button class="btn secondary" data-go="product/${p.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发布过商品</p>';

  const ticketList = mine.length
    ? `<div class="desk-list">${mine.map(t => `<div class="desk-row">
        <span class="type-chip" data-tone="${TICKET_TONE[t.type] || 'mute'}">${e(TICKET_TYPES[t.type] || t.type)}</span>
        <div class="desk-row-main"><b>${e(t.subject)}</b><small>#${t.id} · ${date(t.created)}</small></div>
        ${statePill(statusNames[t.status] || t.status)}
        <button class="btn secondary" data-go="ticket/${t.id}">查看</button>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有提交过工单</p>';

  // --- 社区与交易痕迹：评论、帖子、评价、求购 -------------------------------
  const commentList = comments.length
    ? `<div class="desk-list">${comments.map(c => `<div class="desk-row">
        <span class="row-glyph" data-tone="info">${icon('message')}</span>
        <div class="desk-row-main"><b>${e(c.topic || '校园社区')}</b>
          <small>${date(c.created)} · 帖子 #${c.post_id}</small>
          <p>${e(c.body)}</p></div>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发表过评论</p>';

  const postList = posts.length
    ? `<div class="desk-list">${posts.map(p => `<div class="desk-row">
        <span class="row-glyph" data-tone="violet">${icon('message')}</span>
        <div class="desk-row-main"><b>${e(p.topic || '帖子')}</b>
          <small>${date(p.created)}${p.removed ? ' · 已被处置' : ''}</small>
          <p>${e(p.body)}</p></div>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发表过帖子</p>';

  const reviewList = reviews.length
    ? `<div class="desk-list">${reviews.map(r => `<div class="desk-row">
        <span class="row-glyph" data-tone="${r.rating >= 4 ? 'ok' : 'warn'}">${icon('chart')}</span>
        <div class="desk-row-main"><b>${'★'.repeat(Math.max(1, Math.min(5, Number(r.rating) || 1)))}</b>
          <small>订单 #${r.order_id} · ${date(r.created)}</small>
          <p>${e(r.body)}</p></div>
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发出过评价</p>';

  const wantList = wants.length
    ? `<div class="desk-list">${wants.map(w => `<div class="desk-row">
        <span class="row-glyph" data-tone="mute">${icon('search')}</span>
        <div class="desk-row-main"><b>${e(w.keyword)}</b>
          <small>预算 <span class="amount">¥${money(w.budget)}</span> · ${date(w.created)}</small></div>
        ${statePill(statusNames[w.status] || w.status)}
      </div>`).join('')}</div>`
    : '<p class="desk-empty">没有发布过求购</p>';

  // 清除账号：仅开发者可见，且不能作用在管理员/开发者身上。
  // 放在页面最底部，避免误触——它不可撤销。
  const canPurge = isDeveloper(state.me) && user.id !== state.me.id && !['admin', 'developer'].includes(user.role);
  const dangerZone = canPurge ? `<section class="panel dossier-danger">
    <h2>危险操作</h2>
    <p class="muted">清除后该账号的登录信息与密码将被移除，手机号${data.phone ? `（${e(data.phone)}）` : ''}释放给本人重新注册；历史订单、工单、评价与审计记录全部保留，昵称显示为「已注销用户」。此操作不可撤销。</p>
    <button class="btn danger" data-action="purge-account" data-id="${user.id}" data-nick="${e(user.nickname || '')}">清除账号</button>
  </section>` : '';

  shell(`${heading('DOSSIER', '用户档案 · ' + (user.nickname || ''),
    '仅平台管理员与开发者可见；本次查阅已写入审计记录。')}
    <button class="back" data-go="admin/people?scope=all">← 返回用户列表</button>
    ${head}${stats}
    <div class="dossier-grid">
      <section class="panel">${sectionHead('chart', '信誉与处置记录')}${creditList}</section>
      <section class="panel">${sectionHead('bag', '参与订单')}${orderList}</section>
      <section class="panel">${sectionHead('tag', '商品')}${productList}</section>
      <section class="panel">${sectionHead('message', '提交的工单')}${ticketList}</section>
      <section class="panel">${sectionHead('message', '发表的评论')}${commentList}</section>
      <section class="panel">${sectionHead('message', '发表的帖子')}${postList}</section>
      <section class="panel">${sectionHead('chart', '发出的评价')}${reviewList}</section>
      <section class="panel">${sectionHead('search', '发布的求购')}${wantList}</section>
    </div>
    ${dangerZone}`, 'staff');
}
