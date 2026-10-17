'use strict';
// 事件层 · 全站事件委托分发
// 页面只负责渲染，不自己挂监听器：所有 data-action 按钮和带 id 的表单
// 都由这里按名字查表分派，新增交互只要在对应业务文件里加一个 handler。

import { toast } from '../core/dom.js';
import { go } from '../core/nav.js';
import { publicDemoNotice } from '../auth/login.js';
import * as ui from './ui.js';
import * as catalog from './catalog.js';
import * as moderation from './moderation.js';
import * as staff from './staff.js';
import * as trade from './trade.js';
import * as social from './social.js';
import * as support from './support.js';
import * as account from './account.js';
import * as help from './help.js';
import * as publishing from './publishing.js';
import * as catalogFilters from './catalog-filters.js';
import { operationClick, operationSubmit, filterCases } from './support-operations.js';
import { inboxClick } from './inbox.js';

// 公开演示版只放行这些只读交互，其余一律弹说明、不渲染任何表单。
const DEMO_CLICK_ALLOWED = ['market-channel','market-shortcut','free-shelf','feed-sort','category','login','close','photo','share','open-filter','clear-filters','share-filters','feed-tab','more-products'];

const clicks = {...ui.clicks, ...catalog.clicks, ...moderation.clicks, ...staff.clicks, ...trade.clicks, ...social.clicks, ...support.clicks, ...account.clicks, ...publishing.clicks,...catalogFilters.clicks,...help.clicks};
const submits = {...catalog.submits, ...moderation.submits, ...staff.submits, ...trade.submits, ...social.submits, ...support.submits, ...account.submits, ...publishing.submits,...catalogFilters.submits,...help.submits};

export function registerActions(){
  document.addEventListener('change',ev=>{
    if(ev.target.matches('#op-case-reply [name="internal"]')) {
      const send=ev.target.closest('form').querySelector('[data-case-reply-send]');
      if(send)send.textContent=ev.target.checked?'保存内部备注（当事人不可见）':'发送给当事人';
    }
  });
  document.addEventListener('input',ev=>{if(['queue_query','queue_type','queue_status'].includes(ev.target.name))filterCases();});
  document.addEventListener('click', async ev => {
    const goBtn = ev.target.closest('[data-go]');
    if (goBtn){ go(goBtn.dataset.go); return; }
    const extra=ev.target.closest('[data-operation],[data-credit-user],[data-inbox-action]');
    if(extra){if(window.HUALI_STATIC_DEMO){publicDemoNotice();return;}try{await (extra.hasAttribute('data-inbox-action')?inboxClick(extra):operationClick(extra));}catch(err){toast(err.message);}return;}
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
    if (window.HUALI_STATIC_DEMO && !['search-form','catalog-filter-form'].includes(form.id)){ publicDemoNotice(); return; }
    const fd = new FormData(form), d = Object.fromEntries(fd), button = ev.submitter;
    if (button) button.disabled = true;
    try{
      if(form.hasAttribute('data-operation-form')){await operationSubmit({form,button});return;}
      const handler = submits[form.id];
      if (handler) await handler({form, d, fd, button});
    }catch(err){ toast(err.message); }
    finally{ if (button) button.disabled = false; }
  });
}
