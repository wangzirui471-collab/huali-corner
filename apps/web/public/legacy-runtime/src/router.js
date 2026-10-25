'use strict';
// 路由层 · 把 location.hash 映射到页面模块
// 对应 Java 里的 Controller：不做业务，只决定调用哪个页面、出错时兜底。

import { toast } from './core/dom.js';
import { state, bumpRenderId, clearPoll, demoFeatures } from './core/state.js';
import { shell, heading, empty } from './core/shell.js';
import { go, setRenderer } from './core/nav.js';
import { startProgress, stopProgress } from './core/progress.js';
import { refreshBadges } from './core/badges.js';
import { needLogin, loginModal } from './auth/login.js';
import { home } from './pages/home.js';
import { product } from './pages/product.js';
import { publish } from './pages/publish.js';
import { cartPage } from './pages/cart.js';
import { orders } from './pages/orders.js';
import { myProducts } from './pages/listings.js';
import { community } from './pages/community.js';
import { forum,forumPost,forumWant,forumCompose } from './pages/forum.js';
import { chats } from './pages/messages.js';
import { profile, mine } from './pages/me.js';
import { support, ticketPage } from './pages/support.js';
import { staffDesk } from './pages/staff.js';
import { adminDesk } from './pages/admin-desk.js';
import { dossier } from './pages/dossier.js';
import { credit } from './pages/credit.js';

// 公开演示版只开放这四条只读路由。
const DEMO_ROUTES = ['home', 'product', 'profile', 'community'];
// 其余路由必须登录，未登录时先给一页说明再弹登录框。
const AUTH_ROUTES = ['favorites', 'publish', 'cart', 'orders', 'listings', 'messages', 'me', 'support', 'staff', 'admin', 'dossier', 'ticket', 'credit', 'forum','forum-post','forum-want','forum-compose'];

function publicDemoFeature(route){
  const [title, description] = demoFeatures[route] || ['功能预览', '该操作只在本地模拟版中提供。'];
  shell(`${heading('PUBLIC PREVIEW',title,description)}<section class="panel" data-public-demo-feature><h2>公开演示 · 无需注册</h2><p>仅展示虚构样例，不收集手机号、收货地址或聊天内容，不接收商品发布、付款或客服工单。</p><button class="btn primary" data-go="home">返回逛逛</button></section>`, route);
}

// blob: URL 只对本次渲染有意义（头像本地预览）。换页统一回收，
// 否则每换一次头像就漏一份内存，来回切页越积越多。
function releaseMediaURLs(){
  for (const url of state.mediaURLs){ try{ URL.revokeObjectURL(url); }catch{} }
  state.mediaURLs.clear();
}

// 错误页：按状态码分三类，每类都给一条明确的出路。
// 以前一律显示「暂时无法打开 + 原始错误文案」——普通用户点到一个无权页面，
// 会以为自己把应用点坏了，这是最伤信任的失败方式。权限不足不是故障，
// 缺内容也不是故障，只有真正的服务异常才该说「稍后重试」。
function renderError(err){
  const status = Number(err?.status) || 0;
  const message = String(err?.message || '');
  const forbidden = status === 403 || /权限|无权|仅.{0,12}可/.test(message);
  const missing = status === 404;
  if (forbidden){
    shell(heading('NO ACCESS', '这个页面不对你开放',
      '当前账号没有访问权限。如果你觉得这里应该能进，可以在「帮助与客服」里提交问题。')
      + `<section class="panel error-actions">
           <button class="btn primary" data-go="home">回到首页</button>
           <button class="btn secondary" data-go="support">帮助与客服</button>
         </section>`, 'home');
    return;
  }
  if (missing){
    shell(heading('NOT FOUND', '内容不存在或已被删除',
      message && message !== '请求失败' ? message : '这条内容可能已被作者删除，或者链接已经失效。')
      + `<section class="panel error-actions">
           <button class="btn primary" data-go="home">回到首页</button>
           <button class="btn secondary" data-go="community">去社区看看</button>
         </section>`, 'home');
    return;
  }
  shell(heading('SOMETHING WENT WRONG', '暂时无法打开',
    '服务这次没有响应成功，请重新加载试试。你的登录状态和已有数据都还在。')
    + `<section class="panel error-actions">
         <button class="btn primary" data-action="reload-page">重新加载</button>
         <button class="btn secondary" data-go="home">回到首页</button>
       </section>`, 'home');
}

export async function render(){
  // config 未就绪时放弃本次渲染：main.js 的初始化流程拿到 /api/config 之后
  // 还会再渲染一次当前路由。若不放弃，登录框会在 auth_mode 还没到位时被画出
  // ——弹的是早已废弃的「验证码 + 管理员一键登录」旧框，在试用版里那个按钮
  // 点了必然 403。慢网络下首屏直接点「我的订单」即可稳定复现。
  if (!state.config.name) return;
  const rid = bumpRenderId();
  state.homeView?.dispose();
  clearPoll();
  releaseMediaURLs();
  window.scrollTo(0, 0);
  // 路由一变就亮进度条（含浏览器前进/后退触发的 hashchange，不只是点按钮）。
  startProgress();
  const [route, id] = (location.hash.slice(1) || 'home').split('/');
  try{
    if (window.HUALI_STATIC_DEMO && !DEMO_ROUTES.includes(route)){ publicDemoFeature(route); return; }
    if (!state.me && AUTH_ROUTES.includes(route)){
      shell(heading('WELCOME BACK', '请先登录', '登录后继续使用个人功能。'));
      loginModal();
      return;
    }
    const funcs = {
      home: () => home(),
      favorites: () => needLogin() && home(true),
      product: () => product(id),
      publish,
      cart: cartPage,
      orders,
      listings: myProducts,
      community,
      forum:()=>forum(id),
      'forum-post':()=>forumPost(id),
      'forum-want':()=>forumWant(id),
      'forum-compose':()=>forumCompose(id),
      messages: () => chats(id),
      profile: () => profile(id),
      me: mine,
      support: () => support(false),
      staff: () => staffDesk(id),
      admin: () => adminDesk(id),
      dossier: () => dossier(id),
      credit: () => credit(),
      ticket: () => ticketPage(id)
    };
    if (!funcs[route]) go('home');
    else await funcs[route]();
    // 页面画完再刷角标：消息页 / 我的页刚发生过「标记已读」，强制绕过缓存。
    refreshBadges(route === 'messages' || route === 'me');
  }catch(err){
    // 只有「最后一次发起的渲染」才显示错误页，避免慢请求回来后盖掉新页面。
    if (rid === state.renderId){
      renderError(err);
      toast(err?.message || '加载失败');
    }
  }finally{
    // 只有最后一次渲染能收进度条：慢请求回来后不能把新页面的进度条关掉。
    if (rid === state.renderId) stopProgress();
  }
}

// 页面和事件分发都要「重画当前页」，但它们不能反向 import 本文件（会成环）。
// 这里把 render 注册进 core/nav.js，让那边统一回调。
setRenderer(render);
