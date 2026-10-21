'use strict';
// 入口 · 拉配置、恢复会话、装好监听器、渲染首屏
// 模块加载顺序本身就是初始化顺序：router.js 被 import 时会把 render 注册进 core/nav.js。

import { $ } from './core/dom.js';
import { state, loadCart, clearPoll } from './core/state.js';
import { subscribeSession } from './core/session.js';
import { clearAccount } from './auth/login.js';
import { api, prefetch } from './core/http.js';
import { render } from './router.js';
import { productsURL } from './pages/home.js';
import { closeModal } from './core/shell.js';
import { aiPet } from './components/ai-pet.js';
import { registerActions } from './actions/index.js';
import { registerChangeHandlers } from './actions/change.js';

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
window.addEventListener('hashchange', () => setTimeout(schedulePrefetch, 900));
window.addEventListener('hashchange', syncAiPet);
window.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeModal(); });
// 顶栏是 sticky 的，高度随断点变化，CSS 的 --header-h 只能在运行时量出来。
window.addEventListener('resize', () => {
  const m = document.querySelector('.market-header');
  if (m) document.documentElement.style.setProperty('--header-h', m.offsetHeight+'px');
});

// 切页后空闲预取另一页的首屏列表，让第一次切换也能直接命中缓存。
// 只填缓存、不渲染，失败静默；跨页时 api() 的 renderId 守卫会自行放弃，不会盖错页面。
function schedulePrefetch(){
  const h = (location.hash || '#home').slice(1);
  const run = () => {
    try {
      if (h.startsWith('community')) prefetch(productsURL());
      else if (h.startsWith('home') || h === '') prefetch('/posts?limit=20');
    } catch {}
  };
  if ('requestIdleCallback' in window) requestIdleCallback(run, { timeout: 2000 });
  else setTimeout(run, 1200);
}

// AI 小助手：全站通用（登录用户 + AI 开启时挂到 body，后台页隐藏）。
// 挂在 body 而不是 #app，路由切换时聊天记录不会被清掉。
function syncAiPet(){
  const route = (location.hash.slice(1) || 'home').split('/')[0];
  const backoffice = ['staff', 'admin', 'dossier'].includes(route);
  let pet = document.getElementById('ai-pet');
  if (!state.me || !state.config.ai || window.HUALI_STATIC_DEMO){
    if (pet) pet.remove();
    return;
  }
  if (!pet){
    document.body.insertAdjacentHTML('beforeend', aiPet());
    pet = document.getElementById('ai-pet');
  }
  if (pet) pet.hidden = backoffice;
}

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
    syncAiPet();
    schedulePrefetch();
  }catch(err){
    $('#app').textContent = '服务暂不可用：'+err.message;
  }
})();
