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
//
// 视觉约定（2026-10-17 重做）：
//   - 所有状态用 `state-pill` + `data-tone`，tone 只有 6 个取值：
//     ok（绿）/ warn（橙）/ danger（红）/ info（蓝）/ violet（紫）/ mute（灰）。
//     同一个状态在工单、商品、用户三处必须长得一样，否则「黄色是待处理还是警告」
//     每换一页就得重新猜。
//   - 每行左侧留一个 34px 的 glyph 槽位，给图标一个固定的落脚点，
//     列表因此有了一条稳定的视觉轴，而不是一堆长短不齐的文字。

import { e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const SECTIONS = [
  ['overview', '概览', 'home'],
  ['support', '接待', 'message'],
  ['tickets', '工单', 'message'],
  ['products', '商品治理', 'tag'],
  ['content', '内容治理', 'alert'],
  ['users', '用户', 'user'],
  ['funds', '资金', 'wallet'],
  ['audit', '审计', 'list']
];

const TICKET_TYPES = { refund: '售后', report: '举报', appeal: '申诉', reschedule: '改约', other: '咨询' };
const ROLE_NAMES = { user: '普通用户', support: '客服', admin: '平台管理员', developer: '开发者', owner: '平台所有者' };

// 工单类型色：售后偏紫（要动钱）、举报偏红（要处置）、申诉偏橙（要复核）、改约偏蓝（只是协调）。
const TICKET_TONE = { refund: 'violet', report: 'danger', appeal: 'warn', reschedule: 'info', other: 'mute' };

// 状态色：全站唯一一份映射。新增状态时只改这里，不要在某个页面里单独写颜色。
const STATUS_TONE = {
  open: 'warn', processing: 'info', review: 'violet', resolved: 'ok',
  active: 'ok', banned: 'danger', deactivated: 'mute',
  available: 'ok', reserved: 'warn', sold: 'mute', removed: 'mute',
  awaiting_payment: 'warn', paid: 'info', awaiting_handover: 'info', awaiting_receipt: 'violet',
  completed: 'ok', cancelled: 'mute', disputed: 'danger', refunded: 'danger'
};

const ROLE_TONE = { user: 'mute', support: 'info', admin: 'violet', developer: 'warn' };

// 这些动作登记在册，供前端提示与后端契约对齐（见 docs/工作台接口契约.md）。
const AUDIT_LABELS = {
  credit: '信誉调整', ban: '封禁账号', unban: '解封账号', promote: '付费置顶',
  moderation: '内容处置', appointment: '任命群管理员', ticket_claim: '认领工单',
  ticket_refund: '同意退款', ticket_reject: '驳回工单', ticket_resolved: '结案',
  ticket_review: '提交复核', dossier_view: '查阅用户档案',
  product_moderate: '平台处置商品', product_review: '审核商品',
  // 这两个此前没有翻译，审计页直接漏出了英文 key（role_change / operator_password_reset）。
  role_change: '角色变更', operator_password_reset: '重置密码'
};

const AUDIT_TONES = {
  product_moderate: 'danger', product_review: 'warn', dossier_view: 'info',
  role_change: 'violet', operator_password_reset: 'warn', credit: 'warn',
  ban: 'danger', unban: 'ok', ticket_refund: 'ok', ticket_resolved: 'ok',
  appointment: 'info', promote: 'info', moderation: 'warn'
};

const AUDIT_GLYPHS = {
  product_moderate: 'trash', product_review: 'shield', dossier_view: 'user',
  role_change: 'user', operator_password_reset: 'refresh', credit: 'chart',
  ban: 'close', unban: 'check', ticket_refund: 'wallet', ticket_resolved: 'check',
  appointment: 'plus', promote: 'tag', moderation: 'alert'
};

// 当前登录者是不是平台管理员。客服与管理员看到的工作台不一样：
// 客服可以受理工单、下架违规商品、复核商品；恢复上架、信誉调整、封禁只有管理员能做。
// 后端也会逐次校验（server-side 才是真闸门），这里只是不给人看见必然失败的按钮。
const isAdmin = () => ['admin', 'developer', 'owner'].includes(state.me?.role);

const statePill = (label, tone = 'mute') =>
  `<span class="state-pill" data-tone="${tone}"><i aria-hidden="true"></i>${e(label)}</span>`;

const sepDot = '<span class="sep-dot" aria-hidden="true"></span>';

function roleBanner() {
  if (isAdmin()) return '';
  return `<div class="desk-banner">${icon('shield')}<span><b>你当前以客服身份登录。</b>
    可以受理工单、强制下架违规商品、复核待审商品、复核申诉后恢复商品上架、查阅用户档案；
    <b>信誉调整、封禁账号、人员授权</b>由平台管理员执行。</span></div>`;
}

// 工作台骨架。刻意**不抽到公共组件**：pages/admin-desk.js 是另一路并行改的，
// 两个文件各自持有私有实现、共用 market.css 的类名，谁保存都不会把对方改断。
// 等两边都稳定了再抽公共层，成本只有几十行。
function deskShell(section, title, desc, body) {
  return shell(
    `${heading('SUPPORT DESK', title, desc)}<div class="desk">${deskNav(section)}<div class="desk-main">${body}</div></div>`,
    'staff'
  );
}

function deskNav(active) {
  return `<nav class="desk-nav" aria-label="工作台分区"><span class="desk-nav-label">工作台</span>${SECTIONS.map(([key, label, ic]) =>
    `<button class="desk-tab ${key === active ? 'active' : ''}" data-go="staff/${key}">${icon(ic)}<span>${label}</span></button>`
  ).join('')}</nav>`;
}

// 身份条：进入工作台第一眼应该看到「我是谁、以什么身份在做事」，
// 而不是一上来就面对一张数据表。客服看到的是客服该做的，管理员看到的是全部。
function identityBar() {
  const me = state.me || {};
  const role = ROLE_NAMES[me.role] || me.role || '未知身份';
  const tone = ROLE_TONE[me.role] || 'mute';
  const line = isAdmin()
    ? '今天是平台管理员：可处置商品与内容、管理人员权限、复核每一笔对账。'
    : '今天以客服身份值守：受理工单、处置违规商品，需要动权限时找管理员。';
  return `<div class="desk-id">
    <span class="avatar role-avatar" data-tone="${tone}">${e((me.nickname || '?')[0])}</span>
    <div class="desk-id-main"><b>${e(me.nickname || '工作人员')}</b><small>${line}</small></div>
    ${statePill(role, tone)}
  </div>`;
}

// 概览的数据卡。这些卡**本身就是跳转入口** —— 文案写着「点工单认领」，
// 那卡片就必须真能点，否则这句提示只是一句正确的废话。
function kpiCard([label, value, hint, tone, glyph, to]) {
  const inner = `<span class="kpi-glyph" data-tone="${tone}">${icon(glyph)}</span>
    <span class="kpi-body">
      <span class="kpi-label">${e(label)}</span>
      <b class="kpi-value">${e(String(value))}</b>
      <small class="kpi-hint">${e(hint)}</small>
    </span>
    ${to ? `<span class="kpi-arrow" aria-hidden="true">${icon('arrow')}</span>` : ''}`;
  return to
    ? `<button class="kpi" data-tone="${tone}" data-empty="${value ? 0 : 1}" data-go="${to}">${inner}</button>`
    : `<div class="kpi" data-tone="${tone}" data-empty="${value ? 0 : 1}">${inner}</div>`;
}

function panelHead(title, action) {
  return `<header class="desk-panel-head"><h2>${e(title)}</h2>${action || ''}</header>`;
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

// 列表行的统一骨架。data-* 是行内筛选（actions/staff.js 的 applyChips /
// applySearch）的契约，改结构时这三个属性不能动。
// glyph 槽位保持在最左侧，行内第一个 <b> 必须是标题（moderate-product 用它取商品名）。
function row(tags, search, inner, opts = {}) {
  const glyph = opts.glyph
    ? `<span class="row-glyph" data-tone="${opts.tone || 'mute'}">${icon(opts.glyph)}</span>`
    : '';
  // opts.go：整行可点（进用户档案）。行内按钮由事件层优先处理。
  const go = opts.go ? ` data-go="${e(opts.go)}" role="link" tabindex="0"` : '';
  return `<div class="desk-row${opts.go ? ' is-clickable' : ''}"${go} data-group="${e(search.group)}" data-tags="${e(tags.join(' '))}" data-search="${e(search.text)}">${glyph}${inner}</div>`;
}

// --- 各分区 ---------------------------------------------------------------

function overviewSection({ tickets, admin, products }) {
  const underReview = products.filter(p => p.under_review);
  const banned = admin.users.filter(u => u.status === 'banned');
  const pending = tickets.filter(t => t.status === 'open');
  const busy = tickets.filter(t => ['processing', 'review'].includes(t.status));

  const kpis = [
    ['待处理工单', pending.length, pending.length ? '等待认领' : '全部已认领', 'warn', 'message', 'staff/tickets'],
    ['处理中 / 待复核', busy.length, busy.length ? '需要推进或复核' : '没有积压', 'info', 'clock', 'staff/tickets'],
    ['待人工复核商品', underReview.length, underReview.length ? '自动审核标记为中危' : '没有待审商品', 'violet', 'shield', 'staff/products'],
    ['已封禁账号', banned.length, banned.length ? '可在用户分区解封' : '没有封禁记录', 'danger', 'user', 'staff/users']
  ];

  return `<div class="kpi-grid">${kpis.map(kpiCard).join('')}</div>` +
    `<section class="panel desk-panel">
      ${panelHead('最近工单', `<button class="text-button" data-go="staff/tickets">全部工单${icon('arrow')}</button>`)}
      ${tickets.length
        ? `<div class="desk-list">${tickets.slice(0, 6).map(ticketRow).join('')}</div>`
        : deskEmpty('暂无工单', '用户从订单页或客服中心发起反馈后会出现在这里。')}
    </section>` +
    (underReview.length
      ? `<section class="panel desk-panel">
          ${panelHead('待复核商品', `<button class="text-button" data-go="staff/products">去处置${icon('arrow')}</button>`)}
          <div class="desk-list">${underReview.slice(0, 6).map(productRow).join('')}</div>
        </section>`
      : '');
}

function ticketRow(t) {
  const type = TICKET_TYPES[t.type] || t.type;
  const tone = TICKET_TONE[t.type] || 'mute';
  return row(
    [t.status, t.type],
    { group: 'tickets', text: `#${t.id} ${t.subject} ${t.nickname}` },
    `<div class="desk-row-main">
       <b>${e(t.subject)}</b>
       <small><span class="mono">#${t.id}</span>${sepDot}${e(t.nickname)}${sepDot}${date(t.created)}${t.assignee ? `${sepDot}<span class="claimed">已认领</span>` : ''}</small>
     </div>
     <span class="type-chip" data-tone="${tone}">${e(type)}</span>
     ${statePill(statusNames[t.status] || t.status, STATUS_TONE[t.status])}
     <button class="btn secondary" data-go="ticket/${t.id}">查看</button>`,
    { glyph: 'message', tone }
  );
}

function ticketsSection({ tickets }) {
  const open = tickets.filter(t => t.status === 'open').length;
  const body = tickets.length
    ? `<div class="desk-list">${tickets.map(ticketRow).join('')}</div>`
    : deskEmpty('暂无工单', '用户从订单页或客服中心发起反馈后会出现在这里。');
  return `<div class="desk-summary">
      <span>共 <b>${tickets.length}</b> 条工单</span>
      ${open ? `<span class="desk-summary-flag">其中 <b>${open}</b> 条待认领</span>` : '<span class="muted">没有待认领的工单</span>'}
    </div>
    ${chips('tickets', [
      ['open', '待处理'], ['processing', '处理中'], ['review', '待复核'], ['resolved', '已解决']
    ])}<section class="panel desk-panel">${body}</section>`;
}

function productRow(p) {
  const removed = p.status === 'removed';
  const tone = p.under_review ? 'warn' : removed ? (p.delisted_by ? 'danger' : 'mute') : 'ok';
  const review = p.under_review ? '<span class="review-tag inline">审核中</span>' : '';
  let acts;
  if (p.under_review) {
    acts = `<button class="btn secondary" data-action="review-product" data-id="${p.id}" data-decision="approve">通过</button>
       <button class="btn secondary danger" data-action="review-product" data-id="${p.id}" data-decision="reject">驳回并下架</button>`;
  } else if (removed) {
    // 恢复上架由客服/管理员复核执行（申诉工单的闭环出口）。delisted_by>0 是
    // 平台处置；delisted_by=0 但 relist_locked 是退款冻结——卷入过退款/争议，
    // 卖家同样不能自行上架，两类的出口都是这里的「恢复上架」。
    const locked = !!(p.delisted_by || p.relist_locked);
    acts = `<span class="tag ${p.delisted_by ? 'danger' : ''}">${p.delisted_by ? '平台处置' : (p.relist_locked ? '退款冻结' : '非平台下架')}</span>` +
      (locked
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
       <small><span class="mono">#${p.id}</span>${sepDot}${e(p.nickname)}${sepDot}<span class="amount">¥${money(p.price)}</span>${sepDot}${e(statusNames[p.status] || p.status)}</small></div>
     ${review}
     ${statePill(statusNames[p.status] || p.status, STATUS_TONE[p.status])}
     <button class="btn secondary" data-go="product/${p.id}">查看</button>
     ${acts}`,
    { glyph: 'tag', tone }
  );
}

function productsSection({ products, removed }) {
  const underReview = products.filter(p => p.under_review);
  const rows = [...products, ...removed];
  return `<section class="panel desk-panel">
    ${panelHead('全部商品')}
    <p class="desk-lead">命中「平台限制」类目的商品会带「审核中」标记，放行展示、等人判定；
    下架必须填理由并通知卖家，被平台下架的商品卖家不能自行重新上架。</p>
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
  const canBan = isAdmin() && u.id !== state.me.id && !['admin', 'developer', 'owner'].includes(u.role);
  const tone = ROLE_TONE[u.role] || 'mute';
  const score = Math.max(0, Math.min(100, Number(u.score) || 0));
  // 档案页仅平台管理员与开发者可看（后端同样收窄）；客服端不再显示入口，
  // 免得点了之后拿到 403 还以为系统坏了。
  const acts = `${isAdmin() ? `<button class="btn secondary" data-go="dossier/${u.id}">用户档案</button>` : ''}
    ${isAdmin() && u.id !== state.me.id
      ? `<button class="text-button" data-action="credit" data-id="${u.id}">信誉调整</button>`
      : ''}
    ${isAdmin() && u.id !== state.me.id && !['admin', 'developer'].includes(u.role)
      ? `<button class="text-button" data-action="stars" data-id="${u.id}">星级调整</button>`
      : ''}
    ${canBan
      ? `<button class="text-button ${banned ? '' : 'danger'}" data-action="ban" data-id="${u.id}" data-value="${banned ? 'false' : 'true'}">${banned ? '解封' : '封禁'}</button>`
      : ''}`;
  return row(
    [u.role, u.status],
    { group: 'users', text: `#${u.id} ${u.nickname} ${u.college}` },
    `<span class="avatar role-avatar" data-tone="${tone}">${e((u.nickname || '?')[0])}</span>
     <div class="desk-row-main"><b>${e(u.nickname)}</b>
       <small><span class="mono">#${u.id}</span>${sepDot}${e(ROLE_NAMES[u.role] || u.role)}${u.college ? `${sepDot}${e(u.college)}` : ''}</small></div>
     ${banned ? statePill('已封禁', 'danger') : ''}
     <div class="score-meter" data-low="${score < 60 ? 1 : 0}" title="信誉分 ${score}/100">
       <span class="score-num"><b>${score}</b><small>/100</small></span>
       <span class="meter" aria-hidden="true"><span style="width:${score}%"></span></span>
     </div>
     ${acts}`,
    { go: isAdmin() ? `dossier/${u.id}` : '' }
  );
}

function usersSection({ admin }) {
  const users = admin.users || [];
  const banned = users.filter(u => u.status === 'banned').length;
  const staff = users.filter(u => u.role !== 'user').length;
  return `<section class="panel desk-panel">
    ${panelHead('全部账号')}
    <p class="desk-lead">按昵称、编号或学院搜索。手机号不在此展示，用户档案里也只给脱敏信息。</p>
    <form id="desk-search-form" data-group="users" class="desk-search">
      ${icon('search')}<input name="q" type="search" placeholder="搜昵称 / #编号 / 学院" aria-label="搜索用户">
      <button class="btn secondary">搜索</button>
    </form>
    <div class="desk-summary">
      <span>共 <b>${users.length}</b> 个账号</span>
      <span><b>${staff}</b> 个工作人员</span>
      ${banned ? `<span class="desk-summary-flag">已封禁 <b>${banned}</b></span>` : ''}
    </div>
    ${chips('users', [['user', '普通用户'], ['support', '客服'], ['admin', '平台管理员'], ['banned', `已封禁 ${banned}`]])}
    <div class="desk-list">${users.map(userRow).join('')}</div></section>`;
}

function reconRow(r) {
  const tone = r.consistent ? 'ok' : 'danger';
  const cell = (label, value) => `<span><small>${label}</small><b>¥${money(value)}</b></span>`;
  return `<div class="desk-row recon-row">
    <span class="row-glyph" data-tone="${tone}">${icon(r.consistent ? 'check' : 'alert')}</span>
    <div class="desk-row-main">
      <b>订单 <span class="mono">#${r.id}</span></b>
      <small>${e(statusNames[r.status] || r.status)}</small>
    </div>
    <div class="recon-amounts">
      ${cell('支付', r.payment)}${cell('退款', r.refund)}${cell('净结算', r.net_settlement)}${cell('待结算', r.held)}
    </div>
    ${statePill(r.consistent ? '账目一致' : '需要核查', tone)}
  </div>`;
}

function fundsSection({ rows }) {
  const off = rows.filter(r => !r.consistent);
  const held = rows.reduce((s, r) => s + (r.held || 0), 0);
  const kpis = [
    ['订单总数', rows.length, '全部为模拟账目', 'info', 'list'],
    ['待结算合计', `¥${money(held)}`, '托管中的模拟资金', 'warn', 'wallet'],
    ['账目不一致', off.length, off.length ? '需要人工核查' : '全部平账', off.length ? 'danger' : 'ok', off.length ? 'alert' : 'check']
  ];
  return `<div class="kpi-grid">${kpis.map(kpiCard).join('')}</div>
    <section class="panel desk-panel">
      ${panelHead('模拟资金对账')}
      <p class="desk-lead">对账口径：支付 ＝ 退款 ＋ 净结算 ＋ 待结算。所有金额为模拟记录，不代表真实到账。</p>
      ${rows.length ? `<div class="desk-table">${rows.map(reconRow).join('')}</div>` : deskEmpty('暂无资金记录')}
    </section>`;
}

function auditRow(a, names) {
  const label = AUDIT_LABELS[a.type] || a.type;
  const tone = AUDIT_TONES[a.type] || 'info';
  const glyph = AUDIT_GLYPHS[a.type] || 'list';
  // 操作人只给 id 时退化成「#2」，有昵称就给人名 —— 审计是给人看的，不是给数据库看的。
  const who = id => names[id] || `#${id}`;
  const meta = [
    `<span class="mono">#${a.id}</span>`,
    `操作人 ${e(who(a.actor))}`,
    a.target ? `对象 ${e(who(a.target))}` : '',
    date(a.created)
  ].filter(Boolean).join(sepDot);
  return `<div class="desk-row audit-row" data-group="audit" data-tags="${e(a.type)}" data-search="${e(`${a.type} ${label} ${a.reason || ''} #${a.id} ${who(a.actor)}`)}">
    <span class="audit-dot" data-tone="${tone}">${icon(glyph)}</span>
    <div class="desk-row-main">
      <b>${e(label)}</b>
      <small>${meta}</small>
      ${a.reason ? `<p class="audit-reason">${e(a.reason)}</p>` : ''}
    </div>
    ${a.delta ? statePill(`${a.delta > 0 ? '+' : ''}${a.delta} 分`, a.delta < 0 ? 'danger' : 'ok') : ''}
    ${a.ticket_id ? `<button class="btn secondary" data-go="ticket/${a.ticket_id}">工单 #${a.ticket_id}</button>` : ''}
  </div>`;
}

function auditSection({ admin }) {
  const audit = admin.audit || [];
  const names = Object.fromEntries((admin.users || []).map(u => [u.id, u.nickname]));
  const kinds = [...new Set(audit.map(a => a.type))];
  return `<section class="panel desk-panel">
    ${panelHead('操作审计')}
    <p class="desk-lead">所有平台处置都在这里留痕。查阅用户档案本身也会留下记录。</p>
    ${chips('audit', kinds.slice(0, 8).map(k => [k, AUDIT_LABELS[k] || k]))}
    ${audit.length
      ? `<div class="desk-list audit-list">${audit.map(a => auditRow(a, names)).join('')}</div>`
      : deskEmpty('暂无操作记录')}
  </section>`;
}

function contentRow(item, kind) {
  const label = kind === 'message' ? '聊天消息' : '社区帖子';
  const verdict = item.moderation?.verdict || item.moderation?.level || 'review';
  const tone = verdict === 'report' ? 'danger' : 'warn';
  const hits = (item.moderation?.hits || []).map(h => h.word || h).filter(Boolean);
  // 治理列表用来判断「要不要点进去看」，不读全文；想看上下文去原帖。
  const flat = String(item.body || '').replace(/\s+/g, ' ');
  const excerpt = flat.length > 90 ? flat.slice(0, 90) + '…' : flat;
  const where = kind === 'message'
    ? `${e(item.nickname)} · ${e(item.room_name || '私聊')}`
    : `${e(item.nickname)} · ${e(item.topic || '无标题')}`;
  const tags = [kind, item.removed ? 'removed' : 'live', verdict];
  return row(
    tags,
    { group: 'content', text: `#${item.id} ${item.body || ''} ${item.nickname} ${hits.join(' ')}` },
    `<div class="desk-row-main"><b>${e(excerpt || '(空内容)')}</b>
       <small><span class="mono">${label} #${item.id}</span>${sepDot}${where}${sepDot}${date(item.created)}</small>
       ${hits.length ? `<small class="audit-reason">命中：${e(hits.slice(0, 6).join('、'))}</small>` : ''}</div>
     ${statePill(item.removed ? '已移除' : '展示中', item.removed ? 'mute' : 'ok')}
     ${item.removed
       ? `<button class="btn secondary" data-action="content-restore" data-kind="${kind}" data-id="${item.id}">恢复</button>`
       : `<button class="btn secondary danger" data-action="content-remove" data-kind="${kind}" data-id="${item.id}">移除</button>`}`,
    { glyph: kind === 'message' ? 'message' : 'community', tone }
  );
}

function contentSection({ messages, posts }) {
  const all = [
    ...(messages || []).map(m => ['message', m]),
    ...(posts || []).map(p => ['post', p])
  ].sort((a, b) => (b[1].created || 0) - (a[1].created || 0));
  const removed = all.filter(([, it]) => it.removed).length;
  return `<section class="panel desk-panel">
    ${panelHead('待判内容')}
    <p class="desk-lead">自动审核把命中「送审」级别的聊天与帖子放在这里——它们已经发出去了，
    等人判断。移除是软删除，正文留着，申诉或误判时可恢复；命中「拦截」级的当场就被拒绝，不会入库。</p>
    <div class="desk-summary">
      <span>共 <b>${all.length}</b> 条待判内容</span>
      ${removed ? `<span class="desk-summary-flag">已移除 <b>${removed}</b></span>` : '<span class="muted">全部仍在展示</span>'}
    </div>
    ${chips('content', [
      ['live', '展示中'], ['removed', '已移除'],
      ['message', '聊天消息'], ['post', '社区帖子']
    ])}
    ${all.length
      ? `<div class="desk-list">${all.map(([kind, it]) => contentRow(it, kind)).join('')}</div>`
      : deskEmpty('没有需要人工判断的内容', '自动审核只把 review / report 级别的内容送到这里。')}
  </section>`;
}

// --- 客服接待 -------------------------------------------------------------
// 同时来很多咨询时，客服需要的不是「聊天列表」，而是一个按「谁在等」
// 排序的接待台：待接入的排前面、等得久的排前面，接入即认领。
function sessionRow(s) {
  const waiting = s.waiting > 60 ? `${Math.floor(s.waiting / 60)} 分钟前` : s.waiting > 0 ? '刚刚' : '';
  return row(
    [String(s.id), s.assignee ? 'claimed' : 'waiting'],
    { group: 'support', text: `#${s.id} ${s.customer_name || ''} ${s.subject || ''}` },
    `<span class="avatar role-avatar" data-tone="${s.assignee ? 'info' : 'warn'}">${e((s.customer_name || '?')[0])}</span>
     <div class="desk-row-main">
       <b>${e(s.customer_name || '用户')}</b>
       <small><span class="mono">#${s.id}</span>${sepDot}${e(s.subject || '未关联工单')}${sepDot}${e(s.last_body || '暂无消息')}</small>
     </div>
     ${waiting ? `<span class="tag danger">${e(waiting)}未回</span>` : ''}
     ${s.assignee ? `<span class="tag">${e(s.assignee_name || '客服')} 接待中</span>` : '<span class="tag warn">待接入</span>'}
     <button class="btn primary" data-go="messages/${s.id}">${s.assignee ? '查看会话' : '接入会话'}</button>`,
    { glyph: 'message', tone: s.assignee ? 'info' : 'warn' }
  );
}

function supportSection({ sessions }) {
  const unclaimed = sessions.filter(s => !s.assignee).length;
  const waiting = sessions.filter(s => s.waiting > 0).length;
  return `<section class="panel desk-panel">
    ${panelHead('客服接待', '<button class="text-button" data-action="desk-refresh">刷新</button>')}
    <p class="desk-lead">进行中的在线客服会话。用户提交问题并点「联系在线客服」后进入这里；
    点「接入会话」即认领，其他客服会看到已由你接待，避免两个人回同一个用户。
    30 分钟没有新消息、或关联工单结案后，会话自动结束并归档。</p>
    <div class="desk-summary">
      <span>进行中 <b>${sessions.length}</b> 个会话</span>
      <span><b>${unclaimed}</b> 个待接入</span>
      <span><b>${waiting}</b> 个在等回复</span>
    </div>
    ${sessions.length
      ? `<div class="desk-list">${sessions.map(sessionRow).join('')}</div>`
      : deskEmpty('当前没有进行中的客服会话', '用户提交工单后点「联系在线客服」即可发起会话。')}
  </section>`;
}

export async function staffDesk(section = 'overview') {
  if (!needLogin()) return;
  // 普通用户走到这里通常是手输地址或旧书签。给一页说明 + 出口，
  // 不要 throw 到路由层变成「暂时无法打开」——那不是故障，不需要吓人。
  if (!['admin', 'support', 'developer', 'owner'].includes(state.me.role)){
    shell(heading('NO ACCESS', '客服工作台仅对客服开放',
      '你当前是普通用户，日常功能都在「我的」和「帮助与客服」里。')
      + `<section class="panel error-actions">
           <button class="btn primary" data-go="support">去帮助与客服</button>
           <button class="btn secondary" data-go="home">回到首页</button>
         </section>`, 'home');
    return;
  }
  const key = SECTIONS.some(([k]) => k === section) ? section : 'overview';

  let body;
  if (key === 'overview') {
    const [tickets, admin, products] = await Promise.all([api('/tickets'), api('/admin'), api('/products')]);
    body = overviewSection({ tickets, admin, products });
  } else if (key === 'support') {
    body = supportSection({ sessions: await api('/support/sessions') });
  } else if (key === 'tickets') {
    body = ticketsSection({ tickets: await api('/tickets') });
  } else if (key === 'products') {
    const [products, removed] = await Promise.all([api('/products'), api('/product/removed')]);
    body = productsSection({ products, removed });
  } else if (key === 'content') {
    body = contentSection(await api('/admin/content'));
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
    support: '进行中的客服会话：谁在等、等了多久、由谁接待，一眼看清再接。',
    tickets: '认领、核实、处理、结案，每一步都留记录。',
    products: '违禁品与交易外流的处置入口，全部留痕并通知卖家。',
    content: '自动审核送审的聊天与帖子，移除可回滚。',
    users: '查看账号状态与信誉，进入用户档案看全貌。',
    funds: '模拟资金对账，只看服务端账本。',
    audit: '平台每一次处置都在这里，可追溯。'
  }[key];
  return deskShell(key, title, blurb, identityBar() + roleBanner() + body);
}
