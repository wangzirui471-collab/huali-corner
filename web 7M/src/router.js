'use strict';
// 路由层 · 把 location.hash 映射到页面模块
// 对应 Java 里的 Controller：不做业务，只决定调用哪个页面、出错时兜底。

import { toast } from './core/dom.js';
import { state, bumpRenderId, clearPoll, demoFeatures } from './core/state.js';
import { shell, heading, empty } from './core/shell.js';
import { go, setRenderer } from './core/nav.js';
import { needLogin, loginModal } from './auth/login.js';
import { home } from './pages/home.js';
import { product } from './pages/product.js';
import { publish } from './pages/publish.js';
import { editProduct } from './pages/edit.js';
import { drafts } from './pages/drafts.js';
import { suspend } from './core/drafts.js';
import { attach } from './core/inbox.js';
import { releaseMedia } from './core/media.js';
import { context } from './core/context.js';
import { cartPage } from './pages/cart.js';
import { orders } from './pages/orders.js';
import { myProducts } from './pages/listings.js';
import { community } from './pages/community.js';
import { helpPage } from './pages/help.js';
import { chats } from './pages/messages.js';
import { profile, mine } from './pages/me.js';
import { supportPage as support, ticketPage } from './pages/support.js';
import { staffPage } from './pages/staff.js';

// 公开演示版只开放这四条只读路由。
const DEMO_ROUTES = ['home', 'product', 'profile', 'community'];
// 其余路由必须登录，未登录时先给一页说明再弹登录框。
const AUTH_ROUTES = ['favorites', 'publish', 'cart', 'orders', 'listings', 'selling', 'drafts', 'edit', 'messages', 'me', 'support', 'staff', 'ticket'];

function publicDemoFeature(route){
  const [title, description] = demoFeatures[route] || ['功能预览', '该操作只在本地模拟版中提供。'];
  shell(`${heading('PUBLIC PREVIEW',title,description)}<section class="panel" data-public-demo-feature><h2>公开演示 · 无需注册</h2><p>仅展示虚构样例，不收集手机号、收货地址或聊天内容，不接收商品发布、付款或客服工单。</p><button class="btn primary" data-go="home">返回逛逛</button></section>`, route);
}

export async function render(){
  await suspend();
  releaseMedia();
  const rid = bumpRenderId();
  attach(state.me && !window.HUALI_STATIC_DEMO ? context() : null);
  clearPoll();
  window.scrollTo(0, 0);
  const [path,query] = (location.hash.slice(1) || 'home').split('?');
  const [route,id]=path.split('/');
  if(route==='home' && query){const f=Object.fromEntries(new URLSearchParams(query));state.freeShelf=f.free==='1';delete f.free;state.filter={category:'',q:'',sort:'',...f};}
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
      publish:()=>publish(id),
      drafts,
      edit:()=>editProduct(id),
      selling:myProducts,
      cart: cartPage,
      orders,
      listings: myProducts,
      community,
      help:()=>helpPage(id,query),
      messages: () => chats(id),
      profile: () => profile(id),
      me: mine,
      support: () => support(false),
      staff: () => staffPage(id||'overview',query||''),
      ticket: () => ticketPage(id)
    };
    if (!funcs[route]) go('home');
    else await funcs[route]();
  }catch(err){
    // 只有「最后一次发起的渲染」才显示错误页，避免慢请求回来后盖掉新页面。
    if (rid === state.renderId){
      shell(heading('SOMETHING WENT WRONG', '暂时无法打开', err.message) + empty('请稍后重试'), 'home');
      toast(err.message);
    }
  }
}

// 页面和事件分发都要「重画当前页」，但它们不能反向 import 本文件（会成环）。
// 这里把 render 注册进 core/nav.js，让那边统一回调。
setRenderer(render);
