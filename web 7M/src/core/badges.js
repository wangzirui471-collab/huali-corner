'use strict';
// 基础设施层 · 顶栏未读角标
//
// 「我的」页签和消息图标上的红色数字（1 就显示 1，2 就显示 2）。
// 每次路由渲染后刷新一次；15 秒内的重复渲染复用上次结果——
// 路由切换很频繁，角标不值得每次都打后端。消息页 / 我的页上强制刷新，
// 因为用户刚在那里把消息读掉，旧缓存会把已经归零的角标留在屏幕上。
//
// F-03：卖家停在首页不动时，新订单到了角标也不会动（旧逻辑只在路由
// 渲染时刷新）。登录态下加一个 20 秒的强制轮询：页面开着，红点就该
// 自己跟上。这只是「站内角标」，不是手机系统通知，两者不能混称。

import { api } from './http.js';
import { state } from './state.js';

const REFRESH_CACHE_MS = 15000;
const POLL_MS = 20000;

let fetchedAt = 0;
let cache = { notifications: 0, chat: 0 };
let pollTimer = null;

function apply(){
  // 「我的」聚合两类未读：通知 + 聊天。用户视角只有一个问题——
  // 「有没有人在等我」，不关心消息存在哪张表里。
  const set = (sel, n) => {
    document.querySelectorAll(sel).forEach(el => {
      el.textContent = n > 99 ? '99+' : String(n);
      el.hidden = !n;
    });
  };
  set('[data-nav-badge="me"]', (cache.notifications || 0) + (cache.chat || 0));
  set('[data-nav-badge="messages"]', cache.chat || 0);
}

function stopPolling(){
  if (pollTimer){ clearInterval(pollTimer); pollTimer = null; }
}

export function refreshBadges(force = false){
  if (!state.token){
    cache = { notifications: 0, chat: 0 }; apply();
    stopPolling();                       // 登出后不再轮询
    return;
  }
  if (!pollTimer && typeof document !== 'undefined'){
    pollTimer = setInterval(() => refreshBadges(true), POLL_MS);
  }
  const now = Date.now();
  if (!force && now - fetchedAt < REFRESH_CACHE_MS){ apply(); return; }
  fetchedAt = now;
  api('/badges').then(d => { cache = d; apply(); }).catch(() => {});
}
