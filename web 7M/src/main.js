'use strict';
// 入口 · 拉配置、恢复会话、装好监听器、渲染首屏
// 模块加载顺序本身就是初始化顺序：router.js 被 import 时会把 render 注册进 core/nav.js。

import { $ } from './core/dom.js';
import { state, loadCart, clearPoll } from './core/state.js';
import { subscribeSession } from './core/session.js';
import { clearAccount } from './auth/login.js';
import { api } from './core/http.js';
import { render } from './router.js';
import { closeModal } from './core/shell.js';
import { registerActions } from './actions/index.js';
import { registerChangeHandlers } from './actions/change.js';
import { mountPet } from './components/ai-pet.js';

registerActions();
registerChangeHandlers();

let syncingAccount = false;
subscribeSession(token => {
  if (window.HUALI_STATIC_DEMO || syncingAccount || token === state.token) return;
  syncingAccount = true;
  clearPoll();
  state.token = token; state.me = null; state.cart = []; state.pendingWant = null;
  // Clear visible private content before verifying the new account in this tab.
  $('#app').textContent = '正在同步登录状态…';
  location.hash = '#home';
  location.reload();
});

window.addEventListener('hashchange', render);
window.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeModal(); });
// 顶栏是 sticky 的，高度随断点变化，CSS 的 --header-h 只能在运行时量出来。
window.addEventListener('resize', () => {
  const m = document.querySelector('.market-header');
  if (m) document.documentElement.style.setProperty('--header-h', m.offsetHeight+'px');
});

(async () => {
  try{
    state.config = await api('/config');
    if (state.token){
      try{
        state.me = await api('/me');
        loadCart();
      }catch(err){
        // Only an explicit authentication rejection expires the session.
        // Network errors, proxy HTML and server failures must preserve it.
        if (err.status !== 401) throw err;
        clearAccount();
      }
    }
    await render();
    // 小转挂在 body 上，跟 #app 的每次重渲染无关：换页不会消失，位置也不会被重置。
    mountPet();
  }catch(err){
    $('#app').textContent = '服务暂不可用：'+err.message;
  }
})();
