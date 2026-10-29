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

// 切页预热：把目标页的首屏数据在「用户还没点下去」时取回来。
// 线上一次接口往返 0.7–3 秒，等点击后再发就来不及；hover / 触摸 / Tab 聚焦都算意图。
// 只预热可缓存接口，5 秒内同一路由只发一次，失败静默。
const PAGE_WARM = {
  home: () => prefetch(productsURL()),
  community: () => prefetch('/posts?limit=20'),
  me: () => prefetch('/me'),
  orders: () => prefetch('/orders'),
  listings: () => prefetch('/my-products'),
  favorites: () => prefetch(productsURL(true)),
  credit: () => prefetch('/credit/history'),
  support: () => prefetch('/tickets'),
};
const PUBLIC_WARM = ['home', 'community'];
const warmedAt = new Map();
function warmRoute(route){
  const run = PAGE_WARM[route];
  if (!run) return;
  if (!state.token && !PUBLIC_WARM.includes(route)) return;
  const now = Date.now();
  if (now - (warmedAt.get(route) || 0) < 5000) return;
  warmedAt.set(route, now);
  try { run(); } catch {}
}
function warmFromEvent(ev){
  const el = ev.target && ev.target.closest ? ev.target.closest('[data-go]') : null;
  if (!el) return;
  warmRoute(String(el.dataset.go || '').split('/')[0]);
}
document.addEventListener('pointerover', warmFromEvent, {passive: true});
document.addEventListener('pointerdown', warmFromEvent, {passive: true});
document.addEventListener('focusin', warmFromEvent);

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
      // 登录后最高频的两个去向，空闲时顺手预热；已经缓存过的会直接跳过。
      if (state.token && !h.startsWith('me')) prefetch('/me');
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
