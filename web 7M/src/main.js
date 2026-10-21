'use strict';
// 入口 · 拉配置、恢复会话、装好监听器、渲染首屏
// 模块加载顺序本身就是初始化顺序：router.js 被 import 时会把 render 注册进 core/nav.js。

import { $ } from './core/dom.js';
import { state, loadCart, clearPoll } from './core/state.js';
import { isStaff } from './core/roles.js';
import { subscribeSession } from './core/session.js';
import { clearAccount } from './auth/login.js';
import { api, prefetch } from './core/http.js';
import { render } from './router.js';
import { productsURL } from './pages/home.js';
import { closeModal } from './core/shell.js';
import { mountPet } from './components/ai-pet.js';
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
// 小转由 mountPet() 挂在 body 上，不随路由重渲染。
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
  // 客服/管理员：渲染后立即预热工作台数据（不阻塞渲染、失败静默），
  // 进工作台时直接命中缓存，不用再等 /admin + /tickets 的 D1 查询。
  if (isStaff(state.me) && !h.startsWith('staff') && !h.startsWith('admin')){
    prefetch('/admin');
    prefetch('/tickets');
  }
  const run = () => {
    try {
      if (h.startsWith('community')) prefetch(productsURL());
      else if (h.startsWith('home') || h === '') prefetch('/posts?limit=20');
    } catch {}
  };
  if ('requestIdleCallback' in window) requestIdleCallback(run, { timeout: 1200 });
  else setTimeout(run, 600);
}

// 小转由 ai-pet.js 的 mountPet() 挂载（body 上，跨路由保留），这里只保留预取逻辑。

(async () => {
  try{
    // /config 与 /me 互不依赖，并行请求，少等一个往返，首屏更快。
    const token = state.token;
    const mePromise = token
      ? api('/me').then(me => ({ me })).catch(err => {
          // 只有明确的 401 才让会话失效；网络/服务异常保留登录态。
          if (err.status !== 401) throw err;
          clearAccount();
          return { me: null };
        })
      : Promise.resolve({ me: null });
    const [config, meResult] = await Promise.all([api('/config'), mePromise]);
    state.config = config;
    if (meResult.me){ state.me = meResult.me; loadCart(); }
    await render();
    mountPet();
    schedulePrefetch();
  }catch(err){
    $('#app').textContent = '服务暂不可用：'+err.message;
  }
})();
