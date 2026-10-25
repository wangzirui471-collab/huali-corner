'use strict';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { card } from '../components/product-card.js';
import { recCard } from '../components/rec-rail.js';

// The router disposes the feed, listeners and carousel before changing pages.
export function mountHomeFeed({root, feed, favorite}){
  const epoch=state.renderId, token=state.token;
  const grid=root.querySelector('.product-grid');
  const more=root.querySelector('[data-action="load-more"]');
  const status=root.querySelector('[data-feed-status]');
  const count=root.querySelector('[data-feed-count]');
  const carousels=[...root.querySelectorAll('[data-home-carousel]')].map(element=>({
    element,
    slides:[...element.querySelectorAll('[data-promo-slide]')],
    dots:[...element.querySelectorAll('[data-action="home-slide"]')],
    button:element.querySelector('[data-action="home-promo-open"]'),
    index:0
  }));
  const back=root.querySelector('[data-action="home-top"]');
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let disposed=false, observer;
  const timers=[];
  const alive=()=>!disposed && root.isConnected && state.renderId===epoch && state.token===token;
  const cleanup=[];
  function listen(target,event,handler){
    target?.addEventListener(event,handler);
    cleanup.push(()=>target?.removeEventListener(event,handler));
  }
  function select(carousel,next){
    if (!alive() || !carousel || !carousel.slides.length) return;
    carousel.index=(next+carousel.slides.length)%carousel.slides.length;
    carousel.slides.forEach((slide,index)=>{slide.hidden=index!==carousel.index;});
    carousel.dots.forEach((dot,index)=>{dot.setAttribute('aria-pressed',String(index===carousel.index));});
    carousel.button.setAttribute('aria-label',carousel.slides[carousel.index].dataset.title);
  }
  function updateCount(){ count.textContent=`已展示 ${grid.children.length} 件${favorite?'收藏':'商品'}`; }
  async function next(){
    if (!alive() || feed.loading || !feed.hasMore) return;
    observer?.disconnect(); more.disabled=true; more.textContent='正在加载…';
    grid.setAttribute('aria-busy','true'); status.textContent='正在加载更多好物';
    let failed=false;
    try{
      const products=await feed.next();
      if (!alive()) return;
      grid.insertAdjacentHTML('beforeend',products.map(card).join(''));
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
  // 「小转推荐」换一批：后端按 rec 打分排序，翻页就是下一批；
  // 翻过第 3 页回第 1 页（在售商品通常没那么多页，翻到空反而像坏了）。
  async function recRefresh(b){
    if (!alive() || !b) return;
    const track = root.querySelector('.rec-rail-track');
    if (!track) return;
    const page = (Number(b.dataset.page) || 1) + 1;
    b.disabled = true;
    try{
      const items = await api('/products?rec=1&limit=8&page=' + page);
      if (!alive() || !Array.isArray(items) || !items.length) return;
      track.innerHTML = items.map(recCard).join('');
      b.dataset.page = String(page >= 3 ? 1 : page);
    }catch(_){ /* 换一批失败就保持当前这批，不打扰用户 */ }
    finally{ if (alive()) b.disabled = false; }
  }
  const view={
    retainFavorite:!favorite,
    next,
    recRefresh,
    slide(button){ select(carousels.find(carousel=>carousel.element.dataset.homeCarousel===button.dataset.window),Number(button.dataset.index)); },
    top(){ window.scrollTo({top:0,behavior:motion.matches?'instant':'smooth'}); },
    dispose(){
      disposed=true; feed.dispose(); timers.forEach(clearInterval); observer?.disconnect();
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
  // Both windows keep playing after pointer, keyboard or manual navigation.
  // Reduced motion removes visual transitions in CSS, not content rotation.
  carousels.forEach(carousel=>{
    if(carousel.slides.length>1) timers.push(setInterval(()=>select(carousel,carousel.index+1),Number(carousel.element.dataset.interval)));
  });
  const scroll=()=>{back.hidden=window.scrollY<600;};
  listen(window,'scroll',scroll); scroll(); updateCount();
  return view;
}
