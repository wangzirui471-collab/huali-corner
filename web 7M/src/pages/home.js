'use strict';
// 页面层 · 首页与收藏模板；交互和资源清理由 actions/home-feed 负责。
import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { card } from '../components/product-card.js';
import { recRail } from '../components/rec-rail.js';
import { mountHomeFeed } from '../actions/home-feed.js';
import { categoryArt } from '../components/category-art.js';
import { homePromos } from '../components/home-promos.js';

const PAGE_SIZE=24;
// 一个去处只留一个入口：分类走 market-channel，免费送走 free-shelf（它是价格过滤，不是分类）。
// 原来的九格快捷宫格里，「教材书籍 / 电子产品 / 球拍运动」与这一行同页，
// 「校园求购 / 发布闲置」与顶栏同页，全部删掉；真正更窄的三个关键词（台灯 / 收纳 / 桌椅）挪进专题轮播。
const channels=[
  ['','推荐','all','market-channel'],
  ['books','二手书','books','market-channel'],
  ['living','宿舍生活','living','market-channel'],
  ['sports','运动好物','sports','market-channel'],
  ['electronics','电子产品','electronics','market-channel'],
  ['free','免费送','free','free-shelf']
];

function navigation(){
  return `<nav class="market-channels home-channels" aria-label="商品频道">${channels.map(([key,label,art,action])=>{
    const active=action==='free-shelf'?state.freeShelf:(state.filter.category===key&&!state.freeShelf);
    // 免费送没有「分类值」可带，不写 data-value，免得和「推荐」频道长得一模一样难区分。
    const value=action==='market-channel'?` data-value="${key}"`:'';
    return `<button class="channel ${active?'active':''}" data-action="${action}"${value} aria-pressed="${active}">${categoryArt(art)}<span>${label}</span></button>`;
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

export async function home(favorite=false){
  const epoch=state.renderId, token=state.token, filter={...state.filter};
  const free=state.freeShelf&&!favorite;
  const local=free||favorite;
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
  const title=favorite?'收藏好物':free?'免费好物':'猜你喜欢';
  const context=filter.q?'搜索：'+filter.q:free?'物品免费，送货费请查看详情':favorite?'收藏不等于预留，成交前请确认状态':'来自同学的闲置，等一个新主人';
  // 推荐轨只出现在正常逛逛的首页：收藏页和免费送页各有各的语境。
  const rail=(!local&&Array.isArray(rec)&&rec.length)?recRail(rec):'';
  shell(`<div class="home-page">${favorite?heading('MY COLLECTION','我的收藏','喜欢的好物，先收藏再慢慢挑。'):navigation()+homePromos()}${rail}
    <section class="home-feed" aria-label="${title}"><div class="home-feed-heading"><div><span class="home-section-kicker">${favorite?'MY FINDS':'CAMPUS FINDS'}</span><h2>${title}<small>好物不闲置，生活有转角</small></h2></div><div class="home-feed-tools"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div></div>
    <div class="home-feed-context"><span>${e(context)}</span><small data-feed-count>已展示 ${initial.length} 件商品</small></div>
    <div class="product-grid" aria-busy="false">${initial.map(card).join('')}</div>
    ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
    <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div></section>
    <button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  mountHomeFeed({root:$('.home-page'),feed,favorite});
}
