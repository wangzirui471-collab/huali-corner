'use strict';
import { state } from '../core/state.js';
import { card } from '../components/product-card.js';

// The router disposes the feed, listeners and carousel before changing pages.
export function mountHomeFeed({root, feed, favorite}){
  const epoch=state.renderId, token=state.token;
  const grid=root.querySelector('.product-grid');
  const more=root.querySelector('[data-action="load-more"]');
  const status=root.querySelector('[data-feed-status]');
  const count=root.querySelector('[data-feed-count]');
  const banner=root.querySelector('.home-banner');
  const slides=[...root.querySelectorAll('[data-home-slide]')];
  const dots=[...root.querySelectorAll('[data-action="home-slide"][data-index]')];
  const pause=root.querySelector('[data-action="home-pause"]');
  const back=root.querySelector('[data-action="home-top"]');
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let disposed=false, observer, timer, index=0, paused=false, hover=false, focused=false;
  const alive=()=>!disposed && root.isConnected && state.renderId===epoch && state.token===token;
  const cleanup=[];
  function listen(target,event,handler){
    target?.addEventListener(event,handler);
    cleanup.push(()=>target?.removeEventListener(event,handler));
  }
  function schedule(){
    clearInterval(timer);
    if (alive() && slides.length>1 && !paused && !hover && !focused && !document.hidden && !motion.matches)
      timer=setInterval(()=>select(index+1,false),7000);
  }
  function select(next,manual=true){
    if (!alive() || !slides.length) return;
    index=(next+slides.length)%slides.length;
    slides.forEach((slide,i)=>{slide.hidden=i!==index;});
    dots.forEach((dot,i)=>{dot.setAttribute('aria-pressed',String(i===index));});
    if (manual){ paused=true; updatePause(); }
  }
  function updatePause(){
    if (pause){
      pause.textContent=paused?'自动播放':'暂停轮播';
      pause.setAttribute('aria-pressed',String(paused));
    }
    schedule();
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
  const view={
    retainFavorite:!favorite,
    next,
    slide(button){ select(button.dataset.index!==undefined?Number(button.dataset.index):index+Number(button.dataset.step)); },
    pause(){ if (alive()){paused=!paused;updatePause();} },
    top(){ window.scrollTo({top:0,behavior:motion.matches?'instant':'smooth'}); },
    dispose(){
      disposed=true; feed.dispose(); clearInterval(timer); observer?.disconnect();
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
  listen(banner,'mouseenter',()=>{hover=true;schedule();});
  listen(banner,'mouseleave',()=>{hover=false;schedule();});
  listen(banner,'focusin',()=>{focused=true;schedule();});
  listen(banner,'focusout',event=>{focused=banner.contains(event.relatedTarget);schedule();});
  listen(document,'visibilitychange',schedule); listen(motion,'change',schedule);
  const scroll=()=>{back.hidden=window.scrollY<600;};
  listen(window,'scroll',scroll); scroll(); updateCount(); schedule();
  return view;
}
