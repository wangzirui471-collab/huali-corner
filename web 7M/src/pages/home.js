'use strict';
// 页面层 · 首页与收藏模板；交互和资源清理由 actions/home-feed 负责。
import { $, e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { createProductFeed } from '../core/product-feed.js';
import { card } from '../components/product-card.js';
import { mountHomeFeed } from '../actions/home-feed.js';

const PAGE_SIZE=24;
const channels=[['','推荐'],['books','二手书'],['living','宿舍生活'],['sports','运动好物'],['electronics','电子产品']];
const shortcuts=[['books','教材书籍','book',''],['electronics','电子产品','device',''],['living','宿舍桌椅','chair','凳'],['living','台灯照明','home','灯'],['living','收纳用品','bag','收纳'],['sports','球拍运动','ball','']];

function banner(){
  return `<section class="home-banner" aria-label="校园闲置专题" aria-roledescription="轮播">
    <div class="home-slide home-slide-books" data-home-slide role="group" aria-label="第 1 张，共 2 张">
      <div class="home-banner-copy"><span class="home-eyebrow">华立好物 · 循环新生</span><h1>教材不必买新的<span>知识，接着传下去。</span></h1><p>按版次找书，当面看看书况。<br>让读过的每一页，开启下一段校园时光。</p><button class="home-banner-link" data-action="market-shortcut" data-value="books">去挑一本好书 ${icon('arrow')}</button></div>
      <div class="home-banner-art" aria-hidden="true"><div class="home-art-orbit"></div><div class="home-art-caption">SECOND HAND<br><b>FIRST CHOICE.</b></div><div class="home-book-stack"><span class="home-book home-book-math"><small>校园书架 / 01</small><strong>高等<br>数学</strong><i>MATHEMATICS</i></span><span class="home-book home-book-code"><small>校园书架 / 02</small><strong>数据<br>结构</strong><i>DATA STRUCTURES</i></span><span class="home-book home-book-life"><small>校园书架 / 03</small><strong>读过的书<br>新的故事</strong><i>A NEW CHAPTER</i></span></div><span class="home-art-note">好书，值得再读一次</span></div>
    </div>
    <div class="home-slide home-slide-campus" data-home-slide role="group" aria-label="第 2 张，共 2 张" hidden>
      <div class="home-banner-copy"><span class="home-eyebrow">校园闲置 · 同学之间</span><h1>好物留在华立<span>让喜欢，继续被喜欢。</span></h1><p>用过的好物，分享给需要它的人。<br>在校园里，给闲置找一个新主人。</p><button class="home-banner-link" data-go="community">去校园社区 ${icon('arrow')}</button></div>
      <div class="home-campus-art" aria-hidden="true"><span class="home-art-orbit"></span><span class="home-box"><i>转角</i><small>下一站，新的校园生活</small></span><span class="home-desk-lamp"></span><span class="home-plant"><i></i><b></b></span><span class="home-art-note">闲置有去处，同学有照应</span></div>
    </div>
    <div class="home-banner-controls"><div class="home-banner-dots"><button data-action="home-slide" data-index="0" aria-label="查看教材专题" aria-pressed="true"></button><button data-action="home-slide" data-index="1" aria-label="查看校园好物专题" aria-pressed="false"></button></div><button class="home-pause" data-action="home-pause" aria-pressed="false">暂停轮播</button><button class="home-banner-arrow" data-action="home-slide" data-step="-1" aria-label="上一张">‹</button><button class="home-banner-arrow" data-action="home-slide" data-step="1" aria-label="下一张">›</button></div>
  </section>`;
}

function navigation(){
  return `<nav class="home-channels" aria-label="商品频道">${channels.map(([key,label])=>`<button class="${state.filter.category===key&&!state.freeShelf?'active':''}" data-action="market-channel" data-value="${key}" aria-pressed="${state.filter.category===key&&!state.freeShelf}">${label}</button>`).join('')}<span>校园好物，随心发现</span></nav>
    <section class="home-shortcuts" aria-label="快捷分类">${shortcuts.map(([category,label,ic,q])=>`<button data-action="market-shortcut" data-value="${category}" data-q="${q}"><span>${icon(ic)}</span>${label}</button>`).join('')}<button data-action="free-shelf"><span>${icon('heart')}</span>免费送</button><button data-go="community"><span>${icon('message')}</span>校园求购</button><button data-go="publish"><span class="home-shortcut-publish">${icon('plus')}</span>发布闲置</button></section>`;
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
  shell(`<div class="home-page">${favorite?heading('MY COLLECTION','我的收藏','喜欢的好物，先收藏再慢慢挑。'):banner()+navigation()}
    <section class="home-feed" aria-label="${title}"><div class="home-feed-heading"><div><span class="home-section-kicker">${favorite?'MY FINDS':'CAMPUS FINDS'}</span><h2>${title}<small>好物不闲置，生活有转角</small></h2></div><div class="home-feed-tools"><button class="${!filter.sort?'active':''}" data-action="feed-sort" data-value="" aria-pressed="${!filter.sort}">最新</button><button class="${filter.sort==='price'?'active':''}" data-action="feed-sort" data-value="price" aria-pressed="${filter.sort==='price'}">价格 ↑</button><button class="feed-filter" data-action="open-filter">${icon('filter')}筛选</button></div></div>
    <div class="home-feed-context"><span>${e(context)}</span><small data-feed-count>已展示 ${initial.length} 件商品</small></div>
    <div class="product-grid" aria-busy="false">${initial.map(card).join('')}</div>
    ${!initial.length?empty(free?'暂时没有免费转让的物品':'暂时没有匹配的商品','可以换个关键词，或去社区发布求购需求。'):''}
    <div class="home-feed-end"><p data-feed-status role="status" aria-live="polite">${feed.hasMore?'继续向下，发现更多好物':initial.length?'已经看到全部好物了':''}</p><button class="btn secondary load-more" data-action="load-more" ${feed.hasMore?'':'hidden'}>加载更多好物</button></div></section>
    <button class="home-back-top" data-action="home-top" aria-label="回到顶部" hidden>↑<span>顶部</span></button></div>`,'home');
  mountHomeFeed({root:$('.home-page'),feed,favorite});
}
