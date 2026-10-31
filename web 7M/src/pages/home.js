'use strict';
// 页面层 · 逛逛首页与收藏页。
// 主视觉优先由 Element Plus 岛渲染（home-island.js），岛没到位就用同外观的原生兜底轮播；
// 频道、商品流、排序筛选、收藏和分页始终留在原生层，保证功能只有一套实现。
import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { card } from '../components/product-card.js';
import { recRail } from '../components/rec-rail.js';
import { mountHomeFeed } from '../actions/home-feed.js';
import { heroFallback, heroSlides, linkAttrs } from '../components/home-promos.js';
import { mountHomeChrome, preloadHomeIsland } from '../components/home-island.js';

const PAGE_SIZE=24;
// 一排频道：分类 + 免费送 + 校园求购。原来「分类行 + 快捷宫格行」两排功能重叠，
// 关键词快捷（台灯、收纳、球拍…）收进「筛选」弹窗，页面只留一排。
const CHANNELS=[
  {key:'',label:'为你推荐',icon:'star',action:'market-channel'},
  {key:'books',label:'教材书籍',icon:'book',action:'market-channel'},
  {key:'living',label:'宿舍生活',icon:'bed',action:'market-channel'},
  {key:'electronics',label:'电子数码',icon:'monitor',action:'market-channel'},
  {key:'sports',label:'运动好物',icon:'ball',action:'market-channel'},
  {key:'free',label:'免费送',icon:'gift',action:'free-shelf'},
  {key:'want',label:'校园求购',icon:'megaphone',go:'community'}
];

export function channelPills(){
  return CHANNELS.map(c=>({
    key:c.key, label:c.label, icon:icon(c.icon),
    action:c.action, go:c.go,
    value:c.action==='market-channel'?c.key:undefined,
    q:c.action==='market-channel'?'':undefined,
    active:c.action==='free-shelf'?state.freeShelf
      :c.action==='market-channel'?!state.freeShelf&&state.filter.category===c.key
      :false
  }));
}

function chromeFallback(){
  const slides=heroSlides();
  const pills=channelPills().map(c=>`<button class="hc-cat ${c.active?'active':''}" ${linkAttrs(c)} aria-pressed="${c.active}"><span class="hc-cat-icon">${c.icon}</span><span>${c.label}</span></button>`).join('');
  return `<section class="home-chrome" data-home-chrome>${heroFallback(slides)}<nav class="hc-cats" aria-label="商品频道">${pills}</nav></section>`;
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

export async function home(favorite=false){
  const epoch=state.renderId, token=state.token, filter={...state.filter};
  const free=state.freeShelf&&!favorite;
  const local=free||favorite;
  // 岛和首屏数据并行取：谁先到都行，挂载时通常已经不用等。
  if(!favorite) preloadHomeIsland();
  const params=homeParams(favorite);
  // 「小转推荐」轨和商品流并行拉；推荐失败只当没有这条轨，不拖垮首屏。
  const recPromise = local ? Promise.resolve([]) : api('/products?rec=1&limit=8').catch(() => []);
  let products=await api('/products?'+params);
  if(epoch!==state.renderId || token!==state.token) return;
  const rec=await recPromise;
  if(epoch!==state.renderId || token!==state.token) return;
  if(free) products=products.filter(product=>product.price===0);
  const initial=local?products.slice(0,PAGE_SIZE):products;
  const feed=createProductFeed({initial,size:PAGE_SIZE,fetchPage:async page=>{
    if(local) return products.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE);
    const query=new URLSearchParams(params);query.set('page',String(page));
    return api('/products?'+query);
  }});
  const title=favorite?'收藏好物':free?'免费好物':filter.q?'搜索结果':'转角发现';
  const note=favorite?'喜欢的好物，先收藏再慢慢挑。':free?'物品免费，送货费请查看详情':filter.q?'换个关键词，或去社区发布求购需求':'真正来自同学的闲置好物，等一个新主人';
  const context=filter.q?'搜索：'+filter.q:free?'物品免费，送货费请查看详情':favorite?'收藏不等于预留，成交前请确认状态':'来自同学的闲置，等一个新主人';
  // 推荐轨只出现在正常逛逛的首页：收藏页和免费送页各有各的语境。
  const rail=(!local&&Array.isArray(rec)&&rec.length)?recRail(rec):'';
  const cta=favorite?'':`<section class="home-cta"><div><strong>你闲置的，正是别人需要的。</strong><small>发布一本旧书、一盏台灯，让好物继续传递。</small></div><button class="home-cta-main" data-go="publish">${icon('plus')}发布我的闲置</button><button class="home-cta-ghost" data-action="free-shelf">我想送闲置</button></section>`;
  shell(`<div class="home-page">${favorite?heading('MY COLLECTION','我的收藏','喜欢的好物，先收藏再慢慢挑。'):chromeFallback()}${rail}
    <section class="home-feed" aria-label="${title}"><div class="home-feed-heading"><div><span class="home-section-kicker">${favorite?'MY FINDS':'CAMPUS FINDS'}</span><h2>${title}<small>${e(note)}</small></h2></div><div class="home-feed-tools"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新上架</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div></div>
    <div class="home-feed-context"><span>${e(context)}</span><small data-feed-count>已展示 ${initial.length} 件商品</small></div>
    <div class="product-grid" aria-busy="false">${initial.map(card).join('')}</div>
    ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
    <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div></section>
    ${cta}<button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  const root=$('.home-page');
  // 收藏页没有主视觉；逛逛页把岛挂进 [data-home-chrome]，替换掉兜底轮播。
  const chrome=favorite?null:await mountHomeChrome($('[data-home-chrome]'),{slides:heroSlides(),channels:channelPills()});
  mountHomeFeed({root,feed,favorite,chrome});
}
