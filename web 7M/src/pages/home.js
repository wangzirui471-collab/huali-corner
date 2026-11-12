import {routePath} from '../core/route-path.js';
'use strict';
// 页面层 · 逛逛（首页）与收藏模板
//
// 逛逛页的身份由地址栏决定：`#home` 是全部好物，`#home/books` 是教材频道，
// `#home/free` 是免费送。这样每个入口都有自己的地址、自己的标题和自己的返回路径，
// 不再是「点哪个都停在同一个页面」。交互和资源清理由 actions/home-feed 负责。
//
// 版面顺序照参考图：主视觉 → 频道条 → 转角发现 → 商品流 → 发布 CTA。
// 频道条紧贴商品流上方，是因为它就是这一屏的筛选器，放在主视觉和列表之间最顺。

import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { browseCard, card } from '../components/product-card.js';
import { mountHomeFeed } from '../actions/home-feed.js?v=market-carousel-v2';
import { homeHero, mountHomeHero } from '../components/home-hero.js?v=market-carousel-v2';

const PAGE_SIZE=24;

// 频道行的唯一数据源：key 同时是地址段和后端分类值（want 例外，它去论坛求购）。
// 图标走全站同一套线性图标——参考图用的也是细笔画图标，比七张彩色插画更克制。
const channels=[
  {key:'',label:'为你推荐',ic:'home'},
  {key:'books',label:'教材书籍',ic:'book'},
  {key:'living',label:'宿舍生活',ic:'chair'},
  {key:'electronics',label:'电子数码',ic:'device'},
  {key:'sports',label:'运动好物',ic:'ball'},
  {key:'free',label:'免费送',ic:'tag'},
  {key:'want',label:'校园求购',ic:'search',go:'forum/wants'}
];

const CATEGORY_LABEL={books:'教材书籍',living:'宿舍生活',electronics:'电子数码',sports:'运动好物'};

// 地址栏里 `#home/<channel>` 的第二段就是这个页面的频道。
// 收藏页（#favorites）没有频道，返回空串。
function routeChannel(){
  const [route,id='']=routePath().split('/');
  return route==='home'?id:'';
}

function navigation(){
  return `<nav class="home-channels" aria-label="商品频道">${channels.map(channel=>{
    const {key,label,ic,go}=channel;
    const active=key?state.filter.category===key||(key==='free'&&state.freeShelf):(!state.filter.category&&!state.freeShelf);
    // want 是论坛求购，不是商品分类，所以走真正的页面跳转；
    // 其余六个是本站商品的筛选视角，带上地址段，让每个入口都有自己的页面。
    // 求购是真实页面跳转，不该带 aria-pressed；其余六个才是「当前选中哪个频道」。
    const attrs=go?` data-go="${go}"`:` data-action="home-channel" data-value="${key}" aria-pressed="${active}"`;
    return `<button class="home-channel"${attrs}>${icon(ic)}<span>${label}</span></button>`;
  }).join('')}</nav>`;
}

// 首屏商品列表的查询串：home 与 main.js 的空闲预取共用，保证预取命中同一份缓存。
function homeParams(favorite=false){
  const filter={...state.filter};
  const free=state.freeShelf&&!favorite;
  const params=new URLSearchParams({...filter,...(favorite?{favorite:'1'}:{})});
  if(!(free||favorite)){params.set('limit',String(PAGE_SIZE));params.set('page','1');}
  return params;
}
export function productsURL(favorite=false){ return '/products?'+homeParams(favorite); }

// 当前页的身份：标题、说明、以及是否处在某个频道里。
function pageIdentity(favorite,free,category){
  if(favorite) return {title:'我的收藏',context:'喜欢的好物，先收藏再慢慢挑',channel:''};
  if(free) return {title:'免费好物',context:'物品免费，送货费请查看详情',channel:'free'};
  if(category) return {title:CATEGORY_LABEL[category],context:`正在看${CATEGORY_LABEL[category]} · 换一个频道看看别的`,channel:category};
  return {title:'同学刚上架',context:'校园自提，见面交接更方便。',channel:''};
}

// 处在频道里时给一条可返回的路径，避免用户被筛选困住。
function crumbBar(channel){
  if(!channel) return '';
  const label=channel==='free'?'免费送':CATEGORY_LABEL[channel];
  return `<div class="home-crumb"><button class="home-crumb-back" data-action="home-channel" data-value="">${icon('arrow')}全部好物</button><span class="home-crumb-sep">/</span><b>${label}</b></div>`;
}

// 排序与筛选：参考图把它们放成标题右边的三个纯文字按钮，
// 选中项加粗并在下方留一条短横线，不用整块胶囊按钮抢视线。
function feedTools(filter){
  return `<div class="home-feed-tools" role="group" aria-label="排序与筛选"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新上架</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div>`;
}

// 底部 CTA 的线稿纸箱：不额外请求图片，笔触和全站图标一致。
const CTA_ART = `<svg class="home-cta-art" viewBox="0 0 168 120" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round">
  <path d="M34 48h78v54H34z"/><path d="M34 48 48 24h78l-14 24"/><path d="M112 48l14-24"/>
  <path d="M73 24v24M34 48h78"/><path d="M48 34h42" opacity=".55"/>
  <path d="M124 82c6-4 12-4 18 0" opacity=".55"/><path d="M130 96h16" opacity=".55"/>
  <path d="M138 16l2.6 6.4 6.4 2.6-6.4 2.6L138 34l-2.6-6.4L129 25l6.4-2.6z" fill="currentColor" stroke="none" opacity=".8"/>
</svg>`;

/** 保留原首页渲染与加载失败重试，兼容 Vue Router 的频道 hash。 */
export async function home(favorite=false){
  const epoch=state.renderId, token=state.token;

  // 地址栏是频道的第一来源：进入 #home/books 就直接落到教材，
  // 从 #home 进来就是全部。排序、筛选只改查询条件，不改频道。
  const channel=favorite?'':routeChannel();
  const free=channel==='free';
  const category=CATEGORY_LABEL[channel]?channel:'';
  state.freeShelf=free;
  state.filter.category=category;

  const filter={...state.filter};
  const params=homeParams(favorite);
  const {title,context,channel:active}=pageIdentity(favorite,free,category);
  // 收藏页没有主视觉和频道条：它不是一个可以换频道的商品流。
  const head=favorite?'':homeHero();
  const renderCard=favorite?card:browseCard;

  shell(`<div class="home-page${favorite ? '' : ' mint-browse'}">${head}${favorite?'':navigation()}
    <div data-home-catalog aria-busy="true"><p class="loading" role="status">正在加载商品…</p></div>
    ${favorite?'':`<section class="home-cta"><div class="home-cta-copy"><small>GOOD THINGS GO AROUND</small><strong>你闲置的，正是别人需要的。</strong><p>发布一本旧书、一盏台灯，让好物在校园里继续传递。</p></div><button class="btn primary" data-go="publish">${icon('plus')}发布我的闲置</button>${CTA_ART}</section>`}
    <button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  const root = $('.home-page');
  const catalog = root.querySelector('[data-home-catalog]');
  mountHomeHero(root);

  // 商品列表慢或请求失败时，首屏专题和频道仍能浏览。
  let products;
  try {
    products = await api('/products?'+params);
  } catch (error) {
    if (epoch!==state.renderId || token!==state.token || !root.isConnected) return;
    if (favorite) throw error;
    catalog.innerHTML = `<section class="home-feed panel" aria-label="${e(title)}">
      <h2>商品暂时无法加载</h2><p>可以继续浏览校园专题，或稍后重试。</p>
      <button type="button" class="btn secondary" data-go="${e(routePath())}">重新加载商品</button>
    </section>`;
    catalog.setAttribute('aria-busy', 'false');
    return;
  }
  if(epoch!==state.renderId || token!==state.token || !root.isConnected) return;
  if(free) products=products.filter(product=>product.price===0);
  const local=free||favorite;
  const initial=local?products.slice(0,PAGE_SIZE):products;
  const feed=createProductFeed({initial,size:PAGE_SIZE,fetchPage:async page=>{
    if(local) return products.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE);
    const query=new URLSearchParams(params);query.set('page',String(page));
    return api('/products?'+query);
  }});

  catalog.innerHTML = `<section class="home-feed" aria-label="${e(title)}">
      ${crumbBar(active)}
      <header class="home-feed-heading"><div class="home-feed-title">${favorite?`<h1>${e(title)}</h1>`:`<h2>${e(title)}</h2>`}<p class="home-feed-sub">${e(context)}<small data-feed-count>已展示 ${initial.length} 件商品</small></p></div>${feedTools(filter)}</header>
      <div class="product-grid" aria-busy="false">${initial.map(renderCard).join('')}</div>
      ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
      <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div>
    </section>`;
  catalog.setAttribute('aria-busy', 'false');
  mountHomeFeed({root,feed,favorite,renderCard});
}
