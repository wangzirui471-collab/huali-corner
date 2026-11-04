'use strict';
// 事件层 · 逛逛页的商品流、主视觉轮播与回到顶部
//
// 页面只负责渲染，这里负责把渲染好的 DOM 挂上行为：
// 商品流分页（IntersectionObserver + 显式按钮）、薄荷专题轮播的挂载与卸载、
// 回到顶部的显隐。路由切页前会调用 dispose()，把观察器、计时器和监听全部释放。

import { state } from '../core/state.js';
import { mountHomeHero } from '../components/home-hero.js?v=market-covers';

/** 路由切页时统一释放分页观察器、滚动监听和专题轮播。 */
export function mountHomeFeed({root, feed, favorite, renderCard}){
  const epoch=state.renderId, token=state.token;
  const grid=root.querySelector('.product-grid');
  const more=root.querySelector('[data-action="load-more"]');
  const status=root.querySelector('[data-feed-status]');
  const count=root.querySelector('[data-feed-count]');
  const back=root.querySelector('[data-action="home-top"]');
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let disposed=false, observer;
  const alive=()=>!disposed && root.isConnected && state.renderId===epoch && state.token===token;
  const cleanup=[];
  function listen(target,event,handler){
    target?.addEventListener(event,handler);
    cleanup.push(()=>target?.removeEventListener(event,handler));
  }
  const disposeHero=mountHomeHero(root, alive);
  /** 公布已渲染数量，失败或取消不会修改计数。 */
  function updateCount(){ count.textContent=`已展示 ${grid.children.length} 件${favorite?'收藏':'商品'}`; }
  async function next(){
    if (!alive() || feed.loading || !feed.hasMore) return;
    observer?.disconnect(); more.disabled=true; more.textContent='正在加载…';
    grid.setAttribute('aria-busy','true'); status.textContent='正在加载更多好物';
    let failed=false;
    try{
      const products=await feed.next();
      if (!alive()) return;
      grid.insertAdjacentHTML('beforeend',products.map(renderCard).join(''));
      updateCount(); status.textContent=feed.hasMore?'继续向下，发现更多好物':'已经看到全部好物了';
    }catch(error){
      if (!alive()) return;
      failed=true; status.textContent='加载未成功，已展示的商品仍保留，请点击重试。';
    }finally{
      if (alive()){
        grid.setAttribute('aria-busy','false'); more.disabled=false; more.hidden=!feed.hasMore;
        more.textContent=failed?'重新加载':'加载更多好物';
        // Do not retry in a loop while offline.
        if (!failed && feed.hasMore) observer?.observe(more);
      }
    }
  }
  const view={
    retainFavorite:!favorite,
    next,
    top(){ window.scrollTo({top:0,behavior:motion.matches?'instant':'smooth'}); },
    dispose(){
      disposed=true; feed.dispose(); disposeHero(); observer?.disconnect();
      cleanup.forEach(fn=>fn());
      if(state.homeView===view) state.homeView=null;
    }
  };
  state.homeView=view;
  more.hidden=!feed.hasMore;
  if ('IntersectionObserver' in window && feed.hasMore){
    observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting)) void next();
    },{rootMargin:'350px 0px'});
    observer.observe(more);
  }
  const scroll=()=>{back.hidden=window.scrollY<600;};
  listen(window,'scroll',scroll); scroll(); updateCount();
  return view;
}
