'use strict';
// 事件层 · 全站事件委托分发
// 页面只负责渲染，不自己挂监听器：所有 data-action 按钮和带 id 的表单
// 都由这里按名字查表分派，新增交互只要在对应业务文件里加一个 handler。

import { toast } from '../core/dom.js';
import { go } from '../core/nav.js';
import { publicDemoNotice } from '../auth/login.js';
import * as ui from './ui.js';
import * as catalog from './catalog.js';
import * as trade from './trade.js';
import * as social from './social.js';
import * as support from './support.js';
import * as account from './account.js';
import * as staff from './staff.js';
import * as admin from './admin.js';

// 公开演示版只放行这些只读交互，其余一律弹说明、不渲染任何表单。
const DEMO_CLICK_ALLOWED = ['market-channel','market-shortcut','free-shelf','feed-sort','category','login','close','photo','share'];

const clicks = {...ui.clicks, ...catalog.clicks, ...trade.clicks, ...social.clicks, ...support.clicks, ...account.clicks, ...staff.clicks, ...admin.clicks};
const submits = {...catalog.submits, ...trade.submits, ...social.submits, ...support.submits, ...account.submits, ...staff.submits, ...admin.submits};

export function registerActions(){
  document.addEventListener('click', async ev => {
    const goBtn = ev.target.closest('[data-go]');
    if (goBtn){ go(goBtn.dataset.go); return; }
    const b = ev.target.closest('[data-action]');
    if (!b) return;
    const a = b.dataset.action, id = Number(b.dataset.id);
    try{
      if (window.HUALI_STATIC_DEMO){
        if (a === 'comments'){ await social.demoComments(id); return; }
        if (!DEMO_CLICK_ALLOWED.includes(a)){ publicDemoNotice(); return; }
      }
      const handler = clicks[a];
      if (handler) await handler(b, id);
    }catch(err){ toast(err.message); }
    finally{ b.disabled = false; }
  });

  document.addEventListener('submit', async ev => {
    const form = ev.target;
    if (!form.id) return;
    ev.preventDefault();
    if (window.HUALI_STATIC_DEMO && form.id !== 'search-form'){ publicDemoNotice(); return; }
    const fd = new FormData(form), d = Object.fromEntries(fd), button = ev.submitter;
    if (button) button.disabled = true;
    try{
      const handler = submits[form.id];
      if (handler) await handler({form, d, fd, button});
    }catch(err){ toast(err.message); }
    finally{ if (button) button.disabled = false; }
  });
}
