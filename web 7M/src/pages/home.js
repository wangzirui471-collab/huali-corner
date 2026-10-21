'use strict';
// 页面层 · 首页与收藏模板；交互和资源清理由 actions/home-feed 负责。
import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { card } from '../components/product-card.js';
import { mountHomeFeed } from '../actions/home-feed.js';
import { categoryArt } from '../components/category-art.js';
import { homePromos } from '../components/home-promos.js';

const PAGE_SIZE=24;
const channels=[['','推荐'],['books','二手书'],['living','宿舍生活'],['sports','运动好物'],['electronics','电子产品']];
const shortcuts=[['books','教材书籍','book',''],['electronics','电子产品','device',''],['living','宿舍桌椅','chair','凳'],['living','台灯照明','home','灯'],['living','收纳用品','bag','收纳'],['sports','球拍运动','ball','']];

function navigation(){
  return `<nav class="market-channels home-channels" aria-label="商品频道">${channels.map(([key,label])=>`<button class="channel ${state.filter.category===key&&!state.freeShelf?'active':''}" data-action="market-channel" data-value="${key}" aria-pressed="${state.filter.category===key&&!state.freeShelf}">${categoryArt(key||'all')}<span>${label}</span></button>`).join('')}</nav>
    <section class="category-grid home-shortcuts" data-home-shortcuts aria-label="快捷分类">${shortcuts.map(([category,label,ic,q],index)=>`<button data-action="market-shortcut" data-value="${category}" data-q="${q}"><span class="category-chip ${['coral','steel','gold','mint','blue','lilac'][index]}">${icon(ic)}</span>${label}</button>`).join('')}<button data-action="free-shelf"><span class="category-chip pink">${icon('heart')}</span>免费送</button><button data-go="community"><span class="category-chip sky">${icon('message')}</span>校园求购</button><button data-go="publish"><span class="category-chip apricot">${icon('plus')}</span>发布闲置</button></section>`;
}

export async function home(favorite=false){
  const epoch=state.renderId, token=state.token, filter={...state.filter};
  const free=state.freeShelf&&!favorite;
  const params=new URLSearchParams({...filter,...(favorite?{favorite:'1'}:{})});
  // Preserve the full free-only/favorite filtering semantics of the existing API.
  const local=free||favorite;
  if(!local){params.set('limit',String(PAGE_SIZE));params.set('page','1');}
  let products=await api('/products?'+params);
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
  shell(`<div class="home-page">${favorite?heading('MY COLLECTION','我的收藏','喜欢的好物，先收藏再慢慢挑。'):navigation()+homePromos()}
    <section class="home-feed" aria-label="${title}"><div class="home-feed-heading"><div><span class="home-section-kicker">${favorite?'MY FINDS':'CAMPUS FINDS'}</span><h2>${title}<small>好物不闲置，生活有转角</small></h2></div><div class="home-feed-tools"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div></div>
    <div class="home-feed-context"><span>${e(context)}</span><small data-feed-count>已展示 ${initial.length} 件商品</small></div>
    <div class="product-grid" aria-busy="false">${initial.map(card).join('')}</div>
    ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
    <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div></section>
    <button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  mountHomeFeed({root:$('.home-page'),feed,favorite});
}
