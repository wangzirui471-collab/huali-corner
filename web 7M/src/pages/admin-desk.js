'use strict';
// 页面层 · 管理员工作台（#admin）
//
// 与 pages/staff.js 的分工（见 docs/管理员与客服分权方案.md）：
//   staff.js    客服日常处置：工单、商品、用户档案、内容治理、资金、审计（只看自己经手）；
//   admin-desk  管理员授权与改判：人员权限、整店处置、词库维护、审计导出。
//
// 内容治理（聊天/帖子的待判内容）放在客服工作台，不在这里重复一份：
// 那是每天都要处理的活，属于客服的日常；管理员需要看时，从概览的数据卡点过去。
//
// 为什么这里没有 import staff.js 里的 deskShell / row / chips：
// 那一套是 staff.js 的**模块内私有函数**（没有 export），而且该文件正在被另一路
// 视觉重构持续改写。跨文件依赖别人的私有实现，对方下一次保存就会把它改断。
// 这里按同一套类名（.kpi / .state-pill / .desk-panel / .row-glyph / .desk-summary）
// 自行拼装，样式与客服工作台一致，但两个文件互不依赖。
// 等视觉重构稳定后再抽公共组件，成本只有几十行。
//
// 遵守本项目的两条前端硬约束：
//   1. 不 import router.js，跳转一律用 data-go；
//   2. 不自己挂事件监听，所有交互交给 actions/admin.js 的 clicks / submits 分发。

import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const SECTIONS = [
  ['overview', '概览', 'home'],
  ['people', '人员与权限', 'user'],
  ['shops', '店铺处置', 'tag'],
  ['words', '敏感词库', 'shield'],
  ['audit', '审计', 'list']
];

const BLURBS = {
  overview: '只放需要管理员决定的事：谁在岗、哪些店铺要整体处置、词库有没有要补的。',
  people: '建号、停用、重置密码、强制下线。每一步都留审计，谁给谁开了权限都能查。',
  shops: '整店导流的处置入口：一次下架该卖家全部在售商品，只留一条审计和一条通知。',
  words: '改词条立即生效，不用改代码也不用重启。改动写在数据目录，不污染仓库。',
  audit: '客服只能看到自己经手的记录；管理员可按人、类型、时间筛选并导出 CSV。'
};

const ROLE_TONE = { support: 'info', admin: 'violet', developer: 'warn' };
const ROLE_NAMES = { support: '客服', admin: '平台管理员', developer: '开发者' };
const ROLE_RANK = { user: 0, support: 1, admin: 2, developer: 3 };
// 当前登录者是不是开发者——只有开发者能改管理员/开发者的身份，也能新建管理员。
const isDeveloper = () => state.me?.role === 'developer';
const ACTION_NAMES = { block: '拦截', review: '送审', report: '仅记录' };
const ACTION_TONE = { block: 'danger', review: 'warn', report: 'mute' };

const AUDIT_LABELS = {
  credit: '信誉调整', ban: '封禁账号', unban: '解封账号', promote: '付费置顶',
  moderation: '内容处置', appointment: '任命群管理员', ticket_claim: '认领工单',
  ticket_refund: '同意退款', ticket_reject: '驳回工单', ticket_resolved: '结案',
  ticket_review: '提交复核', dossier_view: '查阅用户档案',
  product_moderate: '平台处置商品', product_review: '审核商品',
  role_change: '角色变更', operator_password_reset: '重置密码',
  staff_create: '新建运营账号', staff_disable: '停用账号', staff_enable: '启用账号',
  staff_password_reset: '重置运营密码', session_revoke: '强制下线',
  seller_moderate: '整店下架', content_remove: '移除内容', content_restore: '恢复内容',
  wordlist_add: '新增词条', wordlist_remove: '停用词条', wordlist_restore: '启用词条'
};

const AUDIT_TONES = {
  staff_create: 'violet', staff_disable: 'danger', staff_enable: 'ok',
  staff_password_reset: 'warn', session_revoke: 'warn', seller_moderate: 'danger',
  content_remove: 'danger', content_restore: 'ok', wordlist_add: 'info',
  wordlist_remove: 'warn', wordlist_restore: 'ok', role_change: 'violet'
};

const AUDIT_GLYPHS = {
  staff_create: 'plus', staff_disable: 'close', staff_enable: 'check',
  staff_password_reset: 'refresh', session_revoke: 'logout', seller_moderate: 'trash',
  content_remove: 'trash', content_restore: 'check', wordlist_add: 'plus',
  wordlist_remove: 'close', wordlist_restore: 'check'
};

const statePill = (label, tone = 'mute') =>
  `<span class="state-pill" data-tone="${tone}"><i aria-hidden="true"></i>${e(label)}</span>`;

const sepDot = '<span class="sep-dot" aria-hidden="true"></span>';

// 与后端 SupportService.mask_phone 同一口径：手机留前 3 后 4，邮箱留用户名前 2 位 + 域名。
// 人员管理里也需要脱敏——管理员要区分「是谁」，不需要拿到完整联系方式。
function maskAccount(value) {
  const text = String(value || '');
  if (text.includes('@')) {
    const [name, domain] = text.split('@');
    if (!domain) return text;
    return (name.length > 2 ? name.slice(0, 2) : name.slice(0, 1)) + '***@' + domain;
  }
  return text.length >= 7 ? text.slice(0, 3) + '****' + text.slice(-4) : text;
}

function deskShell(section, title, desc, body) {
  return shell(
    `${heading('ADMIN DESK', title, desc)}<div class="desk">${deskNav(section)}<div class="desk-main">${body}</div></div>`,
    'admin'
  );
}

function deskNav(active) {
  return `<nav class="desk-nav" aria-label="管理员工作台分区"><span class="desk-nav-label">管理员</span>${SECTIONS.map(([key, label, ic]) =>
    `<button class="desk-tab ${key === active ? 'active' : ''}" data-go="admin/${key}">${icon(ic)}<span>${label}</span></button>`
  ).join('')}</nav>`;
}

// 身份条：管理员台的首页里，第一眼该看到「我是谁、以什么身份在做事」。
function identityBar() {
  const me = state.me || {};
  const role = me.role === 'developer' ? '开发者' : '平台管理员';
  const tone = me.role === 'developer' ? 'warn' : 'violet';
  return `<div class="desk-id">
    <span class="avatar role-avatar" data-tone="${tone}">${e((me.nickname || '?')[0])}</span>
    <div class="desk-id-main"><b>${e(me.nickname || role)}</b>
      <small>${me.role === 'developer'
        ? '以开发者身份登录：可任命管理员、调整任何账号角色，其余与管理员一致。'
        : '以平台管理员身份登录：设置/废除客服、封号、整店处置、词库维护、审计导出。'}</small></div>
    ${statePill(role, tone)}
  </div>`;
}

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

function chips(scope, options) {
  return `<div class="desk-chips" data-chips="${scope}">` +
    `<button class="chip active" data-action="desk-filter" data-group="${scope}" data-value="">全部</button>` +
    options.map(([value, label]) =>
      `<button class="chip" data-action="desk-filter" data-group="${scope}" data-value="${e(value)}">${e(label)}</button>`
    ).join('') +
    `</div>`;
}

const deskEmpty = (text, hint = '') =>
  `<p class="desk-empty">${e(text)}${hint ? `<small>${e(hint)}</small>` : ''}</p>`;

const panelHead = (title, action = '') =>
  `<header class="desk-panel-head"><h2>${e(title)}</h2>${action}</header>`;

function row(tags, search, inner, opts = {}) {
  const glyph = opts.glyph
    ? `<span class="row-glyph" data-tone="${opts.tone || 'mute'}">${icon(opts.glyph)}</span>`
    : '';
  return `<div class="desk-row" data-group="${e(search.group)}" data-tags="${e(tags.join(' '))}" data-search="${e(search.text)}">${glyph}${inner}</div>`;
}

// --- 概览 -----------------------------------------------------------------

function overviewSection({ content, staff, sellers, audit }) {
  const flagged = [...content.messages, ...content.posts];
  const pending = flagged.filter(x => !x.removed).length;
  const online = staff.filter(a => a.online).length;
  const disabled = staff.filter(a => a.status === 'disabled').length;
  const shops = sellers.filter(s => s.available > 0).length;

  const kpis = [
    ['待处理内容', pending, pending ? '在客服工作台的内容分区处理' : '队列是空的',
      pending ? 'warn' : 'ok', pending ? 'alert' : 'check', 'staff/content'],
    ['运营账号', staff.length, `${online} 个在线 · ${disabled} 个停用`, 'info', 'user', 'admin/people'],
    ['有货店铺', shops, shops ? '可整店处置' : '当前没有在售商品', 'violet', 'tag', 'admin/shops'],
    ['最近处置', audit.length, '审计里可查全部记录', 'mute', 'list', 'admin/audit']
  ];

  const names = Object.fromEntries(staff.map(a => [a.id, a.nickname]));
  return `<div class="kpi-grid">${kpis.map(kpiCard).join('')}</div>
    <section class="panel desk-panel">
      ${panelHead('最近处置', `<button class="text-button" data-go="admin/audit">全部审计${icon('arrow')}</button>`)}
      ${audit.length
        ? `<div class="desk-list">${audit.map(a => auditRow(a, names)).join('')}</div>`
        : deskEmpty('还没有处置记录')}
    </section>`;
}

// --- 人员与权限 -----------------------------------------------------------

const OPS_ROLES = ['support', 'admin', 'developer'];
const USER_STATUS_LABEL = { active: '正常', banned: '已封禁', disabled: '已停用', deactivated: '已注销', deleted: '已清除' };
const USER_STATUS_TONE = { active: 'ok', banned: 'danger', disabled: 'mute', deactivated: 'mute', deleted: 'mute' };

function personRow(a) {
  const isOps = OPS_ROLES.includes(a.role);
  const disabled = a.status === 'disabled';
  const self = a.id === state.me.id;
  const tone = disabled ? 'mute' : a.online ? 'ok' : 'info';
  // 状态角标：在岗账号看「在线 / 停用」，普通用户看账号状态（封禁 / 注销 / 已清除）。
  const pill = a.status !== 'active'
    ? statePill(USER_STATUS_LABEL[a.status] || a.status, USER_STATUS_TONE[a.status] || 'mute')
    : a.online ? statePill(`在线 ${a.sessions}`, 'ok') : statePill('离线', 'mute');
  const acts = self
    ? '<span class="tag">当前登录</span>'
    : // 档案页聚合了该账号的全部痕迹（商品/订单/评论/帖子/评价/求购/处置记录），
      // 仅平台管理员与开发者可看；管理台本来就只有 admin 及以上能进。
      `<button class="btn secondary" data-go="dossier/${a.id}">用户档案</button>`+
      `<button class="btn secondary" data-action="change-role" data-id="${a.id}">改身份</button>`+
      // 停用 / 重置密码只对运营账号开放：普通用户的账号状态归封禁与注销管，
      // 密码也有恢复码自助找回。两套混用会让「停用」和「封禁」分不清。
      (isOps
        ? `<button class="btn secondary" data-action="staff-status" data-id="${a.id}" data-value="${disabled ? 'active' : 'disabled'}">${disabled ? '启用' : '停用'}</button>`+
          `<button class="btn secondary" data-action="staff-reset" data-id="${a.id}">重置密码</button>`
        : '')+
      (a.online ? `<button class="text-button danger" data-action="staff-revoke" data-id="${a.id}">强制下线</button>` : '');
  return row(
    [a.role, a.status],
    { group: 'people', text: `#${a.id} ${a.nickname} ${a.phone} ${a.role_name}` },
    `<span class="avatar role-avatar" data-tone="${ROLE_TONE[a.role] || 'mute'}">${e((a.nickname || '?')[0])}</span>
     <div class="desk-row-main">
       <b>${e(a.nickname)}</b>
       <small><span class="mono">#${a.id}</span>${sepDot}${e(a.role_name)}${sepDot}${e(maskAccount(a.phone))}${a.college ? sepDot + e(a.college) : ''}${sepDot}最近登录 ${a.last_login ? date(a.last_login) : '从未'}</small>
     </div>
     ${pill}
     ${acts}`,
    { glyph: 'user', tone }
  );
}

function peopleSection({ staff, scope = 'staff', q = '' }) {
  const all = scope === 'all';
  const disabled = staff.filter(a => a.status === 'disabled').length;
  const roleChips = all
    ? [['user', '普通用户'], ['support', '客服'], ['admin', '管理员'], ['developer', '开发者'], ['banned', '已封禁'], ['deleted', '已清除']]
    : [['developer', '开发者'], ['admin', '管理员'], ['support', '客服'], ['disabled', '已停用']];
  return `<section class="panel desk-panel">
    ${panelHead(all ? '全部注册账号' : '运营账号',
      all
        ? '<button class="btn secondary" data-go="admin/people">返回运营账号</button>'
        : '<button class="btn primary" data-action="staff-create">新建账号</button>')}
    <div class="desk-view-switch">
      <button class="desk-tab ${all ? '' : 'active'}" data-go="admin/people">运营账号</button>
      <button class="desk-tab ${all ? 'active' : ''}" data-go="admin/people?scope=all">全部用户</button>
    </div>
    <p class="desk-lead">${all
      ? '所有在平台注册过的账号，包括从没进过后台的普通同学。点「改身份」可以把任何人提成客服、管理员或开发者——改权立即生效并踢掉对方全部会话，操作全程留痕。'
      : '这里管的是<strong>平台自己人</strong>：客服、管理员、开发者。四级权限——开发者任命管理员，管理员设置/废除客服并封号，客服日常值守。改身份立即生效并踢掉对方全部会话，操作全程留痕。'}</p>
    ${all ? `<form class="desk-search" id="people-search-form">${icon('search')}<input type="search" name="q" value="${e(q)}" placeholder="搜昵称或手机号" aria-label="搜索账号"><button class="btn secondary">搜索</button></form>` : ''}
    <div class="desk-summary">
      <span>共 <b>${staff.length}</b> 个账号</span>
      <span><b>${staff.filter(a => a.online).length}</b> 个在线</span>
      ${disabled ? `<span class="desk-summary-flag">已停用 <b>${disabled}</b></span>` : ''}
    </div>
    ${chips('people', roleChips)}
    ${staff.length
      ? `<div class="desk-list">${staff.map(personRow).join('')}</div>`
      : deskEmpty(all ? (q ? '没有匹配的账号，换个关键词试试' : '还没有注册账号') : '还没有运营账号')}
  </section>`;
}

// --- 店铺处置 -------------------------------------------------------------

function shopRow(s) {
  const tone = s.available > 0 ? 'info' : 'mute';
  return row(
    [s.available > 0 ? 'active' : 'empty'],
    { group: 'shops', text: `#${s.id} ${s.nickname}` },
    `<div class="desk-row-main">
       <b>${e(s.nickname)}</b>
       <small><span class="mono">#${s.id}</span>${sepDot}在售 ${s.available} 件${sepDot}已下架 ${s.removed} 件${sepDot}信誉 ${s.score}/100</small>
     </div>
     <button class="btn secondary" data-go="dossier/${s.id}">用户档案</button>
     ${s.available > 0
       ? `<button class="btn secondary danger" data-action="seller-delist" data-id="${s.id}">批量下架 ${s.available} 件</button>`
       : statePill('无在售', 'mute')}`,
    { glyph: 'tag', tone }
  );
}

function shopsSection({ sellers }) {
  const live = sellers.filter(s => s.available > 0);
  return `<section class="panel desk-panel">
    ${panelHead('店铺处置')}
    <p class="desk-lead">反引流实战里最常见的是「这个人整店都在导流」。批量下架一次处理该卖家全部
    <strong>在售</strong>商品，只写一条审计、发一条通知；已预留/已售出的商品不动，它们挂在别人的订单上。</p>
    <div class="desk-summary">
      <span>共 <b>${sellers.length}</b> 个有商品的卖家</span>
      <span>其中 <b>${live.length}</b> 个还有在售</span>
    </div>
    ${chips('shops', [['active', `有在售 ${live.length}`]])}
    ${sellers.length ? `<div class="desk-list">${sellers.map(shopRow).join('')}</div>`
      : deskEmpty('还没有卖家发布过商品')}
  </section>`;
}

// --- 敏感词库 -------------------------------------------------------------

function wordRow(w) {
  const tone = ACTION_TONE[w.action] || 'mute';
  return row(
    [w.action, w.custom ? 'custom' : 'builtin'],
    { group: 'words', text: `${w.word} ${w.category}` },
    `<div class="desk-row-main">
       <b>${e(w.word)}</b>
       <small>${e(w.category)}${sepDot}${e(ACTION_NAMES[w.action] || w.action)}${sepDot}来源 ${e(w.source)}</small>
     </div>
     ${statePill(ACTION_NAMES[w.action] || w.action, tone)}
     <button class="text-button danger" data-action="word-remove" data-word="${e(w.word)}">停用</button>`,
    { glyph: 'shield', tone }
  );
}

function wordsSection({ data }) {
  const words = data.words || [];
  const disabled = data.disabled || [];
  return `<div class="kpi-grid">${[
    ['启用中词条', data.total, '参与实时扫描', 'info', 'shield'],
    ['运营自定义', data.custom_count, '随时可停用', 'violet', 'plus'],
    ['已停用', disabled.length, '不参与扫描', disabled.length ? 'warn' : 'ok', 'close']
  ].map(kpiCard).join('')}</div>
  <section class="panel desk-panel">
    ${panelHead('新增词条')}
    <p class="desk-lead">词条至少 2 个字符：收单字会大面积误伤——收了「刀」，
    「剪刀」「水果刀」「&lt;刀锋&gt;」全部中招。保存后立即生效，无需重启。</p>
    <form id="word-add-form" class="desk-form-row" data-group="words">
      <label class="field"><span>词条</span><input name="word" required minlength="2" maxlength="40" placeholder="如：代跑体测"></label>
      <label class="field"><span>分类</span><input name="category" maxlength="20" placeholder="如：校园违规"></label>
      <label class="field"><span>处置</span>
        <select name="action">
          <option value="block">拦截（直接拒绝发送）</option>
          <option value="review">送审（放行但进队列）</option>
          <option value="report">仅记录</option>
        </select>
      </label>
      <button class="btn primary">新增</button>
    </form>
  </section>
  <section class="panel desk-panel">
    ${panelHead('词条列表', `<span class="desk-hint">共 ${words.length} 条</span>`)}
    <form id="desk-search-form" data-group="words" class="desk-search">
      ${icon('search')}<input name="q" type="search" placeholder="搜词条或分类" aria-label="搜索词条">
      <button class="btn secondary">搜索</button>
    </form>
    ${chips('words', [['block', '拦截'], ['review', '送审'], ['report', '仅记录'], ['custom', '运营自定义']])}
    ${words.length ? `<div class="desk-list">${words.map(wordRow).join('')}</div>` : deskEmpty('词表是空的')}
  </section>
  ${disabled.length ? `<section class="panel desk-panel">
    ${panelHead('已停用的词条', `<span class="desk-hint">共 ${disabled.length} 条</span>`)}
    <p class="desk-lead">停用不改内置词表，只记在数据目录的 disabled.txt 里——
    否则下次拉取代码更新词表，这些词会原样复活。</p>
    <div class="desk-list">${disabled.map(w => `<div class="desk-row">
      <div class="desk-row-main"><b>${e(w)}</b><small>当前不参与扫描</small></div>
      <button class="btn secondary" data-action="word-restore" data-word="${e(w)}">启用</button>
    </div>`).join('')}</div>
  </section>` : ''}`;
}

// --- 审计 -----------------------------------------------------------------

function auditRow(a, names) {
  const label = AUDIT_LABELS[a.type] || a.type;
  const tone = AUDIT_TONES[a.type] || 'info';
  const glyph = AUDIT_GLYPHS[a.type] || 'list';
  const who = id => names[id] || a.actor_name && id === a.actor ? a.actor_name : `#${id}`;
  const meta = [
    `<span class="mono">#${a.id}</span>`,
    `操作人 ${e(who(a.actor))}`,
    a.target ? `对象 ${e(who(a.target))}` : '',
    date(a.created)
  ].filter(Boolean).join(sepDot);
  return `<div class="desk-row audit-row" data-group="audit" data-tags="${e(a.type)}" data-search="${e(`${a.type} ${label} ${a.reason || ''} #${a.id}`)}">
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

function auditSection({ rows, params }) {
  const type = params.get('type') || '';
  const actor = params.get('actor') || '';
  const since = params.get('since') || '';
  const until = params.get('until') || '';
  const names = {};
  return `<section class="panel desk-panel">
    ${panelHead('操作审计', `<button class="btn secondary" data-action="audit-export">导出 CSV</button>`)}
    <p class="desk-lead">客服只能看到自己经手的记录；管理员可按人、类型、时间筛选，用于回答「这个客服上个月做了什么」。</p>
    <form id="audit-filter-form" class="desk-form-row">
      <label class="field"><span>类型</span>
        <select name="type">
          <option value="">全部类型</option>
          ${Object.entries(AUDIT_LABELS).map(([k, v]) =>
            `<option value="${k}" ${type === k ? 'selected' : ''}>${e(v)}</option>`).join('')}
        </select>
      </label>
      <label class="field"><span>操作人用户编号</span><input name="actor" inputmode="numeric" placeholder="留空=全部" value="${e(actor)}"></label>
      <label class="field"><span>起始日期</span><input name="since" type="date" value="${e(since)}"></label>
      <label class="field"><span>截止日期</span><input name="until" type="date" value="${e(until)}"></label>
      <button class="btn primary">筛选</button>
    </form>
    ${rows.length
      ? `<div class="desk-list audit-list">${rows.map(a => auditRow(a, names)).join('')}</div>`
      : deskEmpty('没有符合条件的记录')}
  </section>`;
}

// --- 入口 -----------------------------------------------------------------

export async function adminDesk(raw = '') {
  if (!needLogin()) return;
  if (!['admin', 'developer'].includes(state.me.role)) {
    shell(heading('ACCESS DENIED', '这里只对平台管理员或开发者开放',
      '客服的日常工作在「客服工作台」，恢复上架、人员授权、词库维护由管理员负责。') +
      `<section class="panel"><p>如果你是客服，请点顶栏的「客服工作台」。</p>
       <button class="btn primary" data-go="staff">去客服工作台</button></section>`, 'staff');
    return;
  }

  const [section, qs] = String(raw || '').split('?');
  const params = new URLSearchParams(qs || '');
  const key = SECTIONS.some(([k]) => k === section) ? section : 'overview';

  let body;
  if (key === 'overview') {
    const [content, staff, sellers, audit] = await Promise.all([
      api('/admin/content'), api('/admin/staff'), api('/admin/sellers'), api('/audit?limit=6')
    ]);
    body = overviewSection({ content, staff, sellers, audit });
  } else if (key === 'people') {
    // scope=all 是全量注册账号（含普通用户），默认仍看运营账号。
    const scope = params.get('scope') === 'all' ? 'all' : 'staff';
    const q = params.get('q') || '';
    const staff = scope === 'all'
      ? await api('/admin/accounts?q=' + encodeURIComponent(q))
      : await api('/admin/staff');
    body = peopleSection({ staff, scope, q });
  } else if (key === 'shops') {
    body = shopsSection({ sellers: await api('/admin/sellers') });
  } else if (key === 'words') {
    body = wordsSection({ data: await api('/moderation/words') });
  } else {
    const query = new URLSearchParams();
    if (params.get('type')) query.set('type', params.get('type'));
    if (params.get('actor')) query.set('actor', params.get('actor'));
    if (params.get('since')) query.set('since', toEpoch(params.get('since')));
    if (params.get('until')) query.set('until', toEpoch(params.get('until'), true));
    query.set('limit', '300');
    body = auditSection({ rows: await api('/audit?' + query.toString()), params });
  }

  deskShell(key, SECTIONS.find(([k]) => k === key)[1], BLURBS[key], identityBar() + body);
}

// 日期选择器给的是 YYYY-MM-DD（本地日），后端要秒级时间戳。
// 截止日期取当天 23:59:59，否则「查 10 月 17 日」会漏掉当天的全部记录。
function toEpoch(value, endOfDay = false) {
  if (!value) return '';
  const stamp = new Date(`${value}T${endOfDay ? '23:59:59' : '00:00:00'}`).getTime() / 1000;
  return Number.isFinite(stamp) ? String(Math.floor(stamp)) : '';
}
