/** 原站初始化与数据预热；由 Vue 管理启动与释放。 */
import {routePath} from '../core/route-path.js';
import { $ } from '../core/dom.js';
import { state, loadCart, clearPoll } from '../core/state.js';
import { isStaff } from '../core/roles.js';
import { subscribeSession } from '../core/session.js';
import { clearAccount } from '../auth/login.js';
import { api, prefetch } from '../core/http.js';
import { render } from '../router.js?v=market-carousel-v2';
import { productsURL } from '../pages/home.js?v=market-carousel-v2';
import { closeModal } from '../core/shell.js';
import { mountPet } from '../components/ai-pet.js';
import { registerActions } from '../actions/index.js';
import { registerChangeHandlers } from '../actions/change.js';

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
let applicationActive = false;
let idlePrefetch = null;
let timerPrefetch = null;

/** 释放尚未开始的空闲预热，卸载后不继续请求数据。 */
function cancelPrefetch(){
  if (idlePrefetch !== null) window.cancelIdleCallback?.(idlePrefetch);
  clearTimeout(timerPrefetch);
  idlePrefetch = null;
  timerPrefetch = null;
}

/** 用户表达切页意图时仅预取允许缓存的数据。 */
function warmRoute(route){
  if (!applicationActive) return;
  const run = PAGE_WARM[route];
  if (!run) return;
  if (!state.token && !PUBLIC_WARM.includes(route)) return;
  const now = Date.now();
  if (now - (warmedAt.get(route) || 0) < 5000) return;
  warmedAt.set(route, now);
  try { run(); } catch {}
}
/** 复用原站 data-go 意图事件，不新增点击或业务写入。 */
function warmFromEvent(ev){
  const el = ev.target && ev.target.closest ? ev.target.closest('[data-go]') : null;
  if (!el) return;
  warmRoute(String(el.dataset.go || '').split('/')[0]);
}

// 切页后空闲预取另一页的首屏列表，让第一次切换也能直接命中缓存。
// 只填缓存、不渲染，失败静默；跨页时 api() 的 renderId 守卫会自行放弃，不会盖错页面。
/** 原站切页后的空闲预热，只在应用存活期间安排且能统一取消。 */
export function schedulePrefetch(){
  if (!applicationActive) return;
  cancelPrefetch();
  const h = routePath();
  // 客服/管理员：渲染后立即预热工作台数据（不阻塞渲染、失败静默），
  // 进工作台时直接命中缓存，不用再等 /admin + /tickets 的 D1 查询。
  if (isStaff(state.me) && !h.startsWith('staff') && !h.startsWith('admin')){
    prefetch('/admin');
    prefetch('/tickets');
  }
  const run = () => {
    idlePrefetch = null;
    timerPrefetch = null;
    if (!applicationActive) return;
    try {
      if (h.startsWith('community')) prefetch(productsURL());
      else if (h.startsWith('home') || h === '') prefetch('/posts?limit=20');
      // 登录后最高频的两个去向，空闲时顺手预热；已经缓存过的会直接跳过。
      if (state.token && !h.startsWith('me')) prefetch('/me');
    } catch {}
  };
  if ('requestIdleCallback' in window) idlePrefetch = window.requestIdleCallback(run, { timeout: 1200 });
  else timerPrefetch = setTimeout(run, 600);
}

// 小转由 ai-pet.js 的 mountPet() 挂载（body 上，跨路由保留），这里只保留预取逻辑。


/** 由 Vue 页面挂载调用一次，释放函数终止原站全局事件和跨标签订阅。 */
export function startApplication(){
  applicationActive = true;
  let alive = true;
  let syncingAccount = false;
  const controller = new AbortController();
  const {signal} = controller;
  const disposeActions = registerActions();
  const disposeChanges = registerChangeHandlers();
  const disposeSession = subscribeSession(token => {
    if (window.HUALI_STATIC_DEMO || syncingAccount || token === state.token) return;
    syncingAccount = true;
    clearPoll();
    state.token = token; state.me = null; state.cart = []; state.pendingWant = null;
    $('#app').textContent = '正在同步登录状态…';
    location.hash = '#home';
    location.reload();
  });
  window.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeModal(); }, {signal});
  window.addEventListener('resize', () => {
    const m = document.querySelector('.market-header');
    if (m) document.documentElement.style.setProperty('--header-h', m.offsetHeight+'px');
  }, {signal});
  document.addEventListener('pointerover', warmFromEvent, {passive: true, signal});
  document.addEventListener('pointerdown', warmFromEvent, {passive: true, signal});
  document.addEventListener('focusin', warmFromEvent, {signal});
  (async () => {
  try{
    // /config 与 /me 互不依赖，并行请求，少等一个往返，首屏更快。
    const token = state.token;
    const mePromise = token
      ? api('/me').then(me => ({ me })).catch(err => {
          if (!alive) throw err;
          // 只有本站JSON明确拒绝身份才退出；代理HTML401属于协议故障，不清除会话。
          if (err.status !== 401 || err.code === 'INVALID_API_RESPONSE') throw err;
          clearAccount();
          return { me: null };
        })
      : Promise.resolve({ me: null });
    const [config, meResult] = await Promise.all([api('/config'), mePromise]);
    if (!alive) return;
    state.config = config;
    if (meResult.me){ state.me = meResult.me; loadCart(); }
    await render();
    if (!alive) return;
    mountPet();
    schedulePrefetch();
  }catch(err){
    if (alive) $('#app').textContent = '服务暂不可用：'+err.message;
  }
})();

  return () => {
    alive = false;
    applicationActive = false;
    cancelPrefetch();
    controller.abort();
    disposeSession();
    disposeActions();
    disposeChanges();
  };
}
