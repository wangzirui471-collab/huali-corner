'use strict';
import { e, icon } from '../core/dom.js';
import { categoryArt } from './category-art.js';

// Read-only editorial content. Every card opens an existing campus feature.
export const promoPanels=[
  {key:'study',label:'书籍与生活专题',interval:7000,slides:[
    {title:'教材不必买新的',eyebrow:'旧书，也有新故事',description:'按版次找书 · 当面看书况',cta:'去挑一本',category:'books',art:'books'},
    {title:'宿舍好物，轻松焕新',eyebrow:'小小空间，也有新灵感',description:'桌椅、台灯和收纳 · 找到刚好需要的',cta:'逛逛宿舍好物',category:'living',art:'living'},
    {title:'运动装备，接着上场',eyebrow:'下一场，和同学一起',description:'球拍与运动好物 · 让热爱继续',cta:'看看运动装备',category:'sports',art:'sports'}
  ]},
  {key:'campus',label:'校园循环与互助专题',interval:8500,slides:[
    {title:'好物留在华立',eyebrow:'毕业季 · 轻装出发',description:'分享清仓信息，找需要它的人',cta:'去校园社区',route:'community',art:'campus'},
    {title:'免费送，也有新故事',eyebrow:'同学之间 · 分享一份善意',description:'物品免费转让 · 交付方式看详情',cta:'看看免费好物',free:true,art:'free'},
    {title:'闲置，遇见新主人',eyebrow:'整理生活 · 从一件闲置开始',description:'拍下真实书况和成色 · 清楚介绍好物',cta:'发布我的闲置',route:'publish',art:'publish'}
  ]}
];

function artwork(kind){
  if(kind==='books') return '<div class="promo-books" aria-hidden="true"><span class="mini-book b1">数学<br><small>MATH</small></span><span class="mini-book b2">数据结构<br><small>DATA</small></span><span class="mini-book b3">Python<br><small>CODE</small></span></div>';
  if(kind==='campus') return '<div class="promo-home" aria-hidden="true"><span class="box">↗</span><span class="little-plant">✳</span><span class="folded-book"></span></div>';
  if(['living','sports'].includes(kind)) return `<div class="home-promo-category-art" aria-hidden="true">${categoryArt(kind)}</div>`;
  return `<div class="home-promo-symbol home-promo-symbol-${kind}" aria-hidden="true"><span>${icon(kind==='free'?'heart':'plus')}</span><i>${kind==='free'?'分享，让好物继续':'给闲置一个新开始'}</i></div>`;
}

export function homePromos(){
  return `<section class="campus-promos home-promos" aria-label="校园闲置专题">${promoPanels.map((panel,windowIndex)=>`<section class="home-promo-window" data-home-carousel="${panel.key}" data-interval="${panel.interval}" aria-label="${panel.label}" aria-roledescription="轮播"><button class="campus-promo home-promo-open ${windowIndex?'graduate-promo':'book-promo'}" data-action="home-promo-open" aria-label="${panel.slides[0].title}，${panel.slides[0].cta}">${panel.slides.map((slide,index)=>`<span class="home-promo-slide" data-promo-slide="${index}" data-title="${e(slide.title)}，${e(slide.cta)}" ${slide.category?`data-category="${slide.category}"`:slide.route?`data-route="${slide.route}"`:'data-free="true"'} ${index?'hidden':''}><span class="home-promo-copy"><span class="promo-eyebrow">${slide.eyebrow}</span><strong class="home-promo-title">${slide.title}</strong><span class="home-promo-desc">${slide.description}</span><span class="promo-link">${slide.cta} ${icon('arrow')}</span></span>${artwork(slide.art)}</span>`).join('')}</button><div class="home-promo-dots" aria-label="切换${panel.label}">${panel.slides.map((_,index)=>`<button data-action="home-slide" data-window="${panel.key}" data-index="${index}" aria-label="${windowIndex?'右':'左'}侧专题第 ${index+1} 页" aria-pressed="${index===0}"></button>`).join('')}</div></section>`).join('')}</section>`;
}
