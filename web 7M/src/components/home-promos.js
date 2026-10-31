'use strict';
// 组件层 · 首页主视觉数据
// 六个专题合成一条轮播，每张都指向一个真实去处（分类 / 路由 / 免费送）。
// Element Plus 岛和原生兜底轮播共用同一份数据，避免两套内容各说各话。

import { e, icon } from '../core/dom.js';
import { categoryArt } from './category-art.js';

// Read-only editorial content. Every card opens an existing campus feature.
export const promoPanels=[
  {key:'study',label:'书籍与生活专题',interval:7000,slides:[
    {title:'教材不必买新的',eyebrow:'旧书，也有新故事',description:'按版次找书 · 当面看书况',cta:'去挑一本',category:'books',art:'books',tone:'mint'},
    {title:'宿舍好物，轻松焕新',eyebrow:'小小空间，也有新灵感',description:'桌椅、台灯和收纳 · 找到刚好需要的',cta:'逛逛宿舍好物',category:'living',art:'living',tone:'sage'},
    {title:'运动装备，接着上场',eyebrow:'下一场，和同学一起',description:'球拍与运动好物 · 让热爱继续',cta:'看看运动装备',category:'sports',art:'sports',tone:'sky'}
  ]},
  {key:'campus',label:'校园循环与互助专题',interval:8500,slides:[
    {title:'好物留在华立',eyebrow:'毕业季 · 轻装出发',description:'分享清仓信息，找需要它的人',cta:'去校园社区',route:'community',art:'campus',tone:'sand'},
    {title:'免费送，也有新故事',eyebrow:'同学之间 · 分享一份善意',description:'物品免费转让 · 交付方式看详情',cta:'看看免费好物',free:true,art:'free',tone:'blush'},
    {title:'闲置，遇见新主人',eyebrow:'整理生活 · 从一件闲置开始',description:'拍下真实书况和成色 · 清楚介绍好物',cta:'发布我的闲置',route:'publish',art:'publish',tone:'deep'}
  ]}
];

function artwork(kind){
  if(kind==='books') return '<div class="promo-books" aria-hidden="true"><span class="mini-book b1">数学<br><small>MATH</small></span><span class="mini-book b2">数据结构<br><small>DATA</small></span><span class="mini-book b3">Python<br><small>CODE</small></span></div>';
  if(kind==='campus') return '<div class="promo-home" aria-hidden="true"><span class="box">↗</span><span class="little-plant">✳</span><span class="folded-book"></span></div>';
  if(['living','sports'].includes(kind)) return `<div class="hero-category-art" aria-hidden="true">${categoryArt(kind)}</div>`;
  return `<div class="hero-symbol hero-symbol-${kind}" aria-hidden="true"><span>${icon(kind==='free'?'heart':'plus')}</span><i>${kind==='free'?'分享，让好物继续':'给闲置一个新开始'}</i></div>`;
}

// 岛与兜底共用的跳转参数：直接写成 data-action / data-go，交给原生事件层分发。
export function linkAttrs(link){
  return [
    link.action ? `data-action="${link.action}"` : '',
    link.value !== undefined ? `data-value="${e(link.value)}"` : '',
    link.q !== undefined ? `data-q="${e(link.q)}"` : '',
    link.go ? `data-go="${link.go}"` : ''
  ].filter(Boolean).join(' ');
}

export function heroSlides(){
  return promoPanels.flatMap(panel => panel.slides.map((slide,index) => ({
    key: panel.key + '-' + index,
    tone: slide.tone,
    eyebrow: slide.eyebrow,
    title: slide.title,
    description: slide.description,
    cta: slide.cta,
    arrow: icon('arrow'),
    art: artwork(slide.art),
    link: slide.route ? { go: slide.route }
      : slide.free ? { action: 'free-shelf' }
      : { action: 'market-shortcut', value: slide.category, q: '' }
  })));
}

// Element Plus 岛没到位时的静态轮播：外观同一套 class，切换靠 mountHomeFeed 的定时器。
export function heroFallback(slides){
  return `<div class="hc-hero" data-home-carousel="hero" data-interval="7000" aria-roledescription="轮播" aria-label="校园闲置专题">
    ${slides.map((slide,index)=>`<button class="hc-slide hc-tone-${slide.tone}" ${linkAttrs(slide.link)} data-promo-slide="${index}" aria-label="${e(slide.title+'，'+slide.cta)}" ${index?'hidden':''}>
      <span class="hc-copy"><span class="hc-eyebrow">${e(slide.eyebrow)}</span><strong class="hc-title">${e(slide.title)}</strong><span class="hc-desc">${e(slide.description)}</span><span class="hc-cta">${e(slide.cta)}<span class="hc-cta-icon">${slide.arrow}</span></span></span>
      <span class="hc-art">${slide.art}</span></button>`).join('')}
    <div class="hc-dots" aria-label="切换专题">${slides.map((_,index)=>`<button data-action="home-slide" data-window="hero" data-index="${index}" aria-label="专题第 ${index+1} 页" aria-pressed="${index===0}"></button>`).join('')}</div>
  </div>`;
}
