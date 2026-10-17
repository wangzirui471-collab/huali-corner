'use strict';
// 组件层 · 工作台公共骨架
//
// 客服工作台（#staff）与管理员工作台（#admin）用同一套版式：
// 左侧分区导航 + 右侧内容区 + 统计卡 + 单选筛选条 + 行列表。
// 抽出来是因为两边几乎逐行相同——复制一份过去之后，
// 改一个间距要改两处，迟早会改漏一处，然后两个页面慢慢长歪。
//
// 注意：pages/staff.js 与 pages/admin-desk.js 都 import 这里。
// 改签名要同时看这两处；row() 的三个参数是行内筛选的契约
// （data-group / data-tags / data-search），改结构不能动这三个属性。

import { e } from '../core/dom.js';
import { shell, heading } from '../core/shell.js';

// route 决定顶栏哪个入口高亮（'staff' / 'admin'）。
export function deskShell(route, nav, title, desc, body, kicker = 'ADMIN DESK') {
  return shell(
    `${heading(kicker, title, desc)}<div class="desk">${nav}<div class="desk-main">${body}</div></div>`,
    route
  );
}

// sections: [[key, label], ...]；prefix 是路由前缀，决定点标签跳到 #staff/x 还是 #admin/x。
export function deskNav(prefix, sections, active) {
  return `<nav class="desk-nav" aria-label="工作台分区">${sections.map(([key, label]) =>
    `<button class="desk-tab ${key === active ? 'active' : ''}" data-go="${prefix}/${key}">${label}</button>`
  ).join('')}</nav>`;
}

export function statCards(items) {
  return `<div class="stat-grid">${items.map(([label, value, hint]) =>
    `<div class="stat-card"><span>${e(label)}</span><b>${e(String(value))}</b>${hint ? `<small>${e(hint)}</small>` : ''}</div>`
  ).join('')}</div>`;
}

// 单选筛选条。同一分区只放一条，避免多组筛选叠加带来的心智负担。
export function chips(scope, options) {
  return `<div class="desk-chips" data-chips="${scope}">` +
    `<button class="chip active" data-action="desk-filter" data-group="${scope}" data-value="">全部</button>` +
    options.map(([value, label]) =>
      `<button class="chip" data-action="desk-filter" data-group="${scope}" data-value="${e(value)}">${e(label)}</button>`
    ).join('') +
    `</div>`;
}

export function deskEmpty(text, hint = '') {
  return `<p class="desk-empty">${e(text)}${hint ? `<small>${e(hint)}</small>` : ''}</p>`;
}

// 一行 = 标签（用于筛选）+ 搜索文本（用于搜索框）+ 内容。
// 筛选与搜索都只改 hidden，不重绘整页——旧工作台每点一下就 render()，
// 会丢滚动位置、页面还会闪。
export function row(tags, search, inner) {
  return `<div class="desk-row" data-group="${e(search.group)}" data-tags="${e(tags.join(' '))}" data-search="${e(search.text)}">${inner}</div>`;
}
