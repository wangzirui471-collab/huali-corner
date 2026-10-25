'use strict';
// 基础设施层 · 顶栏未读角标
//
// 「我的」页签和消息图标上的红色数字（1 就显示 1，2 就显示 2）。
// 每次路由渲染后刷新一次；15 秒内的重复渲染复用上次结果——
// 路由切换很频繁，角标不值得每次都打后端。消息页 / 我的页上强制刷新，
// 因为用户刚在那里把消息读掉，旧缓存会把已经归零的角标留在屏幕上。

import { api } from './http.js';
import { state } from './state.js';

let fetchedAt = 0;
let cache = { notifications: 0, chat: 0 };

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

export function refreshBadges(force = false){
  if (!state.token){ cache = { notifications: 0, chat: 0 }; apply(); return; }
  const now = Date.now();
  if (!force && now - fetchedAt < 15000){ apply(); return; }
  fetchedAt = now;
  api('/badges').then(d => { cache = d; apply(); }).catch(() => {});
}
