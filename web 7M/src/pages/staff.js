'use strict';
// 页面层 · 平台工作台（管理端）
//
// 与 pages/support.js 的分工：
//   support.js —— 用户视角的「帮助与售后」，以及工单详情页；
//   staff.js   —— 平台视角的工作台：左侧分区导航 + 待办概览 + 各治理队列。
//
// 遵守本项目的两条前端硬约束：
//   1. 不 import router.js，也不被 router 以外的东西 import；跳转一律用 data-go；
//   2. 不自己挂事件监听，所有交互交给 actions/staff.js 的 clicks / submits 分发。
//
// 列表筛选刻意做成「行内 DOM 过滤」而不是重新渲染整页：
// 旧工作台每点一次操作就 await render()，整页重画会丢滚动位置、页面还会闪。
// 过滤只需要显隐行，所以在这里直接改 hidden，不经过 render。

import { e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const SECTIONS = [
  ['overview', '概览'],
  ['tickets', '工单'],
  ['products', '商品治理'],
  ['users', '用户'],
  ['funds', '资金'],
  ['audit', '审计']
];

const TICKET_TYPES = { refund: '售后', report: '举报', appeal: '申诉', reschedule: '改约', other: '咨询' };
const ROLE_NAMES = { user: '普通用户', support: '客服', admin: '平台管理员' };

// 这些动作登记在册，供前端提示与后端契约对齐（见 docs/工作台接口契约.md）。
const AUDIT_LABELS = {
  credit: '信誉调整', ban: '封禁账号', unban: '解封账号', promote: '付费置顶',
  moderation: '内容处置', appointment: '任命群管理员', ticket_claim: '认领工单',
  ticket_refund: '同意退款', ticket_reject: '驳回工单', ticket_resolved: '结案',
  ticket_review: '提交复核', dossier_view: '查阅用户档案',
  product_moderate: '平台处置商品', product_review: '审核商品'
};

// 当前登录者是不是平台管理员。客服与管理员看到的工作台不一样：
// 客服可以受理工单、下架违规商品、复核商品；恢复上架、信誉调整、封禁只有管理员能做。
// 后端也会逐次校验（server-side 才是真闸门），这里只是不给人看见必然失败的按钮。
const isAdmin = () => state.me?.role === 'admin';

function roleBanner() {
  if (isAdmin()) return '';
  return `<div class="notice">${icon('shield')}<span><b>你当前以客服身份登录。</b>
    可以受理工单、强制下架违规商品、复核待审商品、查阅用户档案；
    <b>恢复上架、信誉调整、封禁账号、人员授权</b>由平台管理员执行。</span></div>`;
}

function deskShell(section, title, desc, body) {
  return shell(
    `${heading('ADMIN DESK', title, desc)}<div class="desk">${deskNav(section)}<div class="desk-main">${body}</div></div>`,
    'staff'
  );
}

function deskNav(active) {
  return `<nav class="desk-nav" aria-label="工作台分区">${SECTIONS.map(([key, label]) =>
    `<button class="desk-tab ${key === active ? 'active' : ''}" data-go="staff/${key}">${label}</button>`
  ).join('')}</nav>`;
}

function statCards(items) {
  return `<div class="stat-grid">${items.map(([label, value, hint]) =>
    `<div class="stat-card"><span>${e(label)}</span><b>${e(String(value))}</b>${hint ? `<small>${e(hint)}</small>` : ''}</div>`
  ).join('')}</div>`;
}

// 单选筛选条。同一分区只放一条，避免多组筛选叠加带来的心智负担。
function chips(scope, options) {
  return `<div class="desk-chips" data-chips="${scope}">` +
    `<button class="chip active" data-action="desk-filter" data-group="${scope}" data-value="">全部</button>` +
    options.map(([value, label]) =>
      `<button class="chip" data-action="desk-filter" data-group="${scope}" data-value="${e(value)}">${e(label)}</button>`
    ).join('') +
    `</div>`;
}

function deskEmpty(text, hint = '') {
  return `<p class="desk-empty">${e(text)}${hint ? `<small>${e(hint)}</small>` : ''}</p>`;
}

function row(tags, search, inner) {
  return `<div class="desk-row" data-group="${e(search.group)}" data-tags="${e(tags.join(' '))}" data-search="${e(search.text)}">${inner}</div>`;
}

// --- 各分区 ---------------------------------------------------------------

function overviewSection({ tickets, admin, products }) {
  const byStatus = s => tickets.filter(t => t.status === s).length;
  const underReview = products.filter(p => p.under_review);
  const banned = admin.users.filter(u => u.status === 'banned');
  const pending = tickets.filter(t => t.status === 'open');
  const busy = tickets.filter(t => ['processing', 'review'].includes(t.status));

  const todo = [
    ['待处理工单', pending.length, '点「工单」认领', 'staff/tickets'],
    ['处理中 / 待复核', busy.length, '需要推进或复核', 'staff/tickets'],
    ['待人工复核商品', underReview.length, '自动审核标记为中危', 'staff/products'],
    ['已封禁账号', banned.length, '可在用户分区查看', 'staff/users']
  ];

  return statCards(todo.map(([a, b, c]) => [a, b, c])) +
    `<section class="panel"><h2>最近工单</h2>${tickets.length
      ? `<div class="desk-list">${tickets.slice(0, 6).map(ticketRow).join('')}</div>`
      : deskEmpty('暂无工单')}</section>` +
    (underReview.length
      ? `<section class="panel"><h2>待复核商品</h2><div class="desk-list">${underReview.slice(0, 6).map(productRow).join('')}</div></section>`
      : '');
}

function ticketRow(t) {
  const tag = `${e(TICKET_TYPES[t.type] || t.type)}`;
  return row(
    [t.status, t.type],
    { group: 'tickets', text: `#${t.id} ${t.subject} ${t.nickname}` },
    `<span class="desk-badge">${tag}</span>
     <div class="desk-row-main"><b>${e(t.subject)}</b><small>#${t.id} · ${e(t.nickname)} · ${date(t.created)}${t.assignee ? ' · 已认领' : ''}</small></div>
     <span class="tag">${e(statusNames[t.status] || t.status)}</span>
     <button class="btn secondary" data-go="ticket/${t.id}">查看</button>`
  );
}

function ticketsSection({ tickets }) {
  const body = tickets.length
    ? `<div class="desk-list">${tickets.map(ticketRow).join('')}</div>`
    : deskEmpty('暂无工单', '用户从订单页或客服中心发起反馈后会出现在这里。');
  return `${chips('tickets', [
    ['open', '待处理'], ['processing', '处理中'], ['review', '待复核'], ['resolved', '已解决']
  ])}<section class="panel">${body}</section>`;
}

function productRow(p) {
  const removed = p.status === 'removed';
  const review = p.under_review ? '<span class="review-tag inline">审核中</span>' : '';
  let acts;
  if (p.under_review) {
    acts = `<button class="btn secondary" data-action="review-product" data-id="${p.id}" data-decision="approve">通过</button>
       <button class="btn secondary danger" data-action="review-product" data-id="${p.id}" data-decision="reject">驳回并下架</button>`;
  } else if (removed) {
    // 恢复上架是改判，只有管理员能做；客服看到的是「找谁恢复」，不是一个点了会失败的按钮。
    acts = `<span class="tag ${p.delisted_by ? 'danger' : ''}">${p.delisted_by ? '平台处置' : '卖家下架'}</span>` +
      (p.delisted_by && isAdmin()
        ? ` <button class="btn secondary" data-action="restore-product" data-id="${p.id}">恢复上架</button>`
        : '');
  } else {
    acts = `<button class="btn secondary danger" data-action="moderate-product" data-id="${p.id}">强制下架</button>`;
  }
  const tags = [removed ? 'removed' : 'available'];
  if (p.under_review) tags.push('review');
  return row(
    tags,
    { group: 'products', text: `#${p.id} ${p.title} ${p.nickname}` },
    `<div class="desk-row-main"><b>${e(p.title)}</b>
       <small>#${p.id} · ${e(p.nickname)} · ¥${money(p.price)} · ${e(statusNames[p.status] || p.status)}</small></div>
     ${review}
     <button class="btn secondary" data-go="product/${p.id}">查看</button>
     ${acts}`
  );
}

function productsSection({ products, removed }) {
  const underReview = products.filter(p => p.under_review);
  const rows = [...products, ...removed];
  return `<section class="panel"><h2>商品治理</h2>
    <p class="muted">自动审核命中「平台限制」类目的商品会带「审核中」标记，放行展示但等人工判定。
    下架必须填理由，会写入审计并通知卖家，卖家可在客服中心申诉；被平台下架的商品
    卖家不能自行重新上架${isAdmin() ? '，由你复核后恢复' : '，恢复需平台管理员复核'}。</p>
    ${chips('products', [
      ['review', `待人工复核 ${underReview.length}`],
      ['available', `在售 ${products.length}`],
      ['removed', `已下架 ${removed.length}`]
    ])}
    ${rows.length ? `<div class="desk-list">${rows.map(p => productRow(p)).join('')}</div>`
      : deskEmpty('当前没有商品')}</section>`;
}

function userRow(u) {
  const banned = u.status === 'banned';
  // 封禁只有管理员能做，且不能封管理员自己或当前登录者。
  const canBan = isAdmin() && u.id !== state.me.id && u.role !== 'admin';
  const acts = `<button class="btn secondary" data-go="dossier/${u.id}">用户档案</button>
    ${canBan
      ? `<button class="text-button" data-action="ban" data-id="${u.id}" data-value="${banned ? 'false' : 'true'}">${banned ? '解封' : '封禁'}</button>`
      : ''}`;
  return row(
    [u.role, u.status],
    { group: 'users', text: `#${u.id} ${u.nickname} ${u.college}` },
    `<div class="desk-row-main"><b>${e(u.nickname)}</b>
       <small>#${u.id} · ${e(ROLE_NAMES[u.role] || u.role)} · ${e(u.college || '')}</small></div>
     ${banned ? '<span class="tag danger">已封禁</span>' : ''}
     <b class="score">${u.score}/100</b>
     ${acts}`
  );
}

function usersSection({ admin }) {
  const users = admin.users || [];
  const banned = users.filter(u => u.status === 'banned').length;
  return `<section class="panel"><h2>用户</h2>
    <p class="muted">按昵称、编号或学院搜索。手机号不在此展示；用户档案里也只给脱敏信息。</p>
    <form id="desk-search-form" data-group="users" class="desk-search">
      ${icon('search')}<input name="q" type="search" placeholder="搜昵称 / #编号 / 学院" aria-label="搜索用户">
      <button class="btn secondary">搜索</button>
    </form>
    ${chips('users', [['user', '普通用户'], ['support', '客服'], ['admin', '平台管理员'], ['banned', `已封禁 ${banned}`]])}
    <div class="desk-list">${users.map(userRow).join('')}</div></section>`;
}

function fundsSection({ rows }) {
  const off = rows.filter(r => !r.consistent);
  return `${statCards([
    ['订单总数', rows.length, '全部模拟账目'],
    ['账目不一致', off.length, off.length ? '需要人工核查' : '全部平账'],
    ['待结算合计', money(rows.reduce((s, r) => s + (r.held || 0), 0)), '托管中的模拟资金']
  ])}<section class="panel"><h2>模拟资金对账</h2>
    <p class="muted">对账口径：支付 ＝ 退款 ＋ 净结算 ＋ 待结算。所有金额为模拟记录，不代表真实到账。</p>
    ${rows.length ? `<div class="desk-table">${rows.map(r => `
      <div class="desk-row">
        <div class="desk-row-main"><b>订单 #${r.id}</b>
          <small>${e(statusNames[r.status] || r.status)} · 支付 ¥${money(r.payment)} · 退款 ¥${money(r.refund)} · 净结算 ¥${money(r.net_settlement)} · 待结算 ¥${money(r.held)}</small></div>
        <span class="tag ${r.consistent ? '' : 'danger'}">${r.consistent ? '账目一致' : '需要核查'}</span>
      </div>`).join('')}</div>` : deskEmpty('暂无资金记录')}
    <p class="muted">当前没有「按订单号查详情」的接口，所以这一栏只列账目。待办见 docs/管理端权限清单-v1.md 的 D2。</p></section>`;
}

function auditSection({ admin }) {
  const audit = admin.audit || [];
  const kinds = [...new Set(audit.map(a => a.type))];
  const body = `<div class="desk-list">${audit.map(a => row(
    [a.type],
    { group: 'audit', text: `${a.type} ${a.reason || ''} #${a.id}` },
    `<div class="desk-row-main"><b>${e(AUDIT_LABELS[a.type] || a.type)}</b>
       <small>#${a.id} · 操作人 #${a.actor}${a.target ? ` · 对象 #${a.target}` : ''} · ${date(a.created)}</small>
       <p>${e(a.reason || '')}</p></div>
     ${a.delta ? `<span class="tag ${a.delta < 0 ? 'danger' : ''}">${a.delta > 0 ? '+' : ''}${a.delta} 分</span>` : ''}
     ${a.ticket_id ? `<button class="btn secondary" data-go="ticket/${a.ticket_id}">工单 #${a.ticket_id}</button>` : ''}`)).join('')}</div>`;
  return `<section class="panel"><h2>操作审计</h2>
    <p class="muted">所有平台处置都在这里留痕。查阅用户档案本身也会留下记录。</p>
    ${chips('audit', kinds.slice(0, 8).map(k => [k, AUDIT_LABELS[k] || k]))}
    ${audit.length ? body : deskEmpty('暂无操作记录')}</section>`;
}

export async function staffDesk(section = 'overview') {
  if (!needLogin()) return;
  if (!['admin', 'support'].includes(state.me.role)) throw new Error('没有客服权限');
  const key = SECTIONS.some(([k]) => k === section) ? section : 'overview';

  let body;
  if (key === 'overview') {
    const [tickets, admin, products] = await Promise.all([api('/tickets'), api('/admin'), api('/products')]);
    body = overviewSection({ tickets, admin, products });
  } else if (key === 'tickets') {
    body = ticketsSection({ tickets: await api('/tickets') });
  } else if (key === 'products') {
    const [products, removed] = await Promise.all([api('/products'), api('/product/removed')]);
    body = productsSection({ products, removed });
  } else if (key === 'users') {
    body = usersSection({ admin: await api('/admin') });
  } else if (key === 'funds') {
    body = fundsSection({ rows: await api('/reconcile') });
  } else {
    body = auditSection({ admin: await api('/admin') });
  }

  const [, title] = SECTIONS.find(([k]) => k === key);
  const blurb = {
    overview: '待办优先：先看还有多少工单没认领、多少商品在等人工复核。',
    tickets: '认领、核实、处理、结案，每一步都留记录。',
    products: '违禁品与交易外流的处置入口，全部留痕并通知卖家。',
    users: '查看账号状态与信誉，进入用户档案看全貌。',
    funds: '模拟资金对账，只看服务端账本。',
    audit: '平台每一次处置都在这里，可追溯。'
  }[key];
  deskShell(key, title, blurb, roleBanner() + body);
}
