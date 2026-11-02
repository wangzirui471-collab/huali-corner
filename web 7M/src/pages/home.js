'use strict';
// 页面层 · 逛逛（首页）与收藏模板
//
// 逛逛页的身份由地址栏决定：`#home` 是全部好物，`#home/books` 是教材频道，
// `#home/free` 是免费送。这样每个入口都有自己的地址、自己的标题和自己的返回路径，
// 不再是「点哪个都停在同一个页面」。交互和资源清理由 actions/home-feed 负责。

import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { card } from '../components/product-card.js';
import { mountHomeFeed } from '../actions/home-feed.js';
import { categoryArt } from '../components/category-art.js';
import { homeHero } from '../components/home-hero.js';

const PAGE_SIZE=24;

// 频道行的唯一数据源：key 同时是地址段和后端分类值（want 例外，它去论坛求购）。
// tone 只用来上色，和业务无关，所以留在页面层而不是样式里写死七组选择器。
const channels=[
  {key:'',label:'推荐',art:'all',tone:'amber'},
  {key:'books',label:'教材书籍',art:'books',tone:'coral'},
  {key:'living',label:'宿舍生活',art:'living',tone:'mint'},
  {key:'electronics',label:'电子产品',art:'electronics',tone:'blue'},
  {key:'sports',label:'运动好物',art:'sports',tone:'lilac'},
  {key:'free',label:'免费送',art:'free',tone:'pink'},
  {key:'want',label:'校园求购',art:'want',tone:'teal',go:'forum/wants'}
];

const CATEGORY_LABEL={books:'教材书籍',living:'宿舍生活',electronics:'电子产品',sports:'运动好物'};

// 地址栏里 `#home/<channel>` 的第二段就是这个页面的频道。
// 收藏页（#favorites）没有频道，返回空串。
function routeChannel(){
  const [route,id='']=(location.hash.slice(1)||'home').split('/');
  return route==='home'?id:'';
}

function navigation(){
  return `<nav class="home-channels" aria-label="商品频道">${channels.map(channel=>{
    const {key,label,art,tone,go}=channel;
    const active=key?state.filter.category===key||(key==='free'&&state.freeShelf):(!state.filter.category&&!state.freeShelf);
    // want 是论坛求购，不是商品分类，所以走真正的页面跳转；
    // 其余六个是本站商品的筛选视角，带上地址段，让每个入口都有自己的页面。
    // 求购是真实页面跳转，不该带 aria-pressed；其余六个才是「当前选中哪个频道」。
    const attrs=go?` data-go="${go}"`:` data-action="home-channel" data-value="${key}" aria-pressed="${active}"`;
    return `<button class="home-channel" data-tone="${tone}"${attrs}>${categoryArt(art)}<span>${label}</span></button>`;
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
  if(favorite) return {title:'收藏好物',kicker:'MY FINDS',context:'收藏不等于预留，成交前请确认状态',channel:''};
  if(free) return {title:'免费好物',kicker:'FREE SHELF',context:'物品免费，送货费请查看详情',channel:'free'};
  if(category) return {title:CATEGORY_LABEL[category],kicker:'CHANNEL',context:`正在看${CATEGORY_LABEL[category]} · 换一个频道看看别的`,channel:category};
  return {title:'猜你喜欢',kicker:'CAMPUS FINDS',context:'来自同学的闲置，等一个新主人',channel:''};
}

// 处在频道里时给一条可返回的路径，避免用户被筛选困住。
function crumbBar(channel){
  if(!channel) return '';
  const label=channel==='free'?'免费送':CATEGORY_LABEL[channel];
  return `<div class="home-crumb"><button class="home-crumb-back" data-action="home-channel" data-value="">${icon('arrow')}全部好物</button><span class="home-crumb-sep">/</span><b>${label}</b></div>`;
}

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
  let products=await api('/products?'+params);
  if(epoch!==state.renderId || token!==state.token) return;
  if(free) products=products.filter(product=>product.price===0);
  const local=free||favorite;
  const initial=local?products.slice(0,PAGE_SIZE):products;
  const feed=createProductFeed({initial,size:PAGE_SIZE,fetchPage:async page=>{
    if(local) return products.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE);
    const query=new URLSearchParams(params);query.set('page',String(page));
    return api('/products?'+query);
  }});

  const {title,kicker,context,channel:active}=pageIdentity(favorite,free,category);
  const head=favorite
    ? heading('MY COLLECTION','我的收藏','喜欢的好物，先收藏再慢慢挑。')
    : navigation()+homeHero();

  shell(`<div class="home-page">${head}
    <section class="home-feed" aria-label="${e(title)}">${crumbBar(active)}
      <div class="home-feed-heading"><div><span class="home-section-kicker">${kicker}</span><h2>${e(title)}<small>好物不闲置，生活有转角</small></h2></div>
        <div class="home-feed-tools"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div></div>
      <div class="home-feed-context"><span>${e(context)}</span><small data-feed-count>已展示 ${initial.length} 件商品</small></div>
      <div class="product-grid" aria-busy="false">${initial.map(card).join('')}</div>
      ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
      <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div>
    </section>
    ${favorite?'':`<section class="home-cta"><div class="home-cta-copy"><strong>让闲置，遇见下一位主人</strong><p>发布你的闲置物品，让好物继续发光，也让校园生活更美好。</p></div><button class="btn primary" data-go="publish">${icon('plus')}发布闲置</button></section>`}
    <button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  mountHomeFeed({root:$('.home-page'),feed,favorite});
}
