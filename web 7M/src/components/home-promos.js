'use strict';
import { e, icon } from '../core/dom.js';
import { categoryArt } from './category-art.js';

// 首页只保留一条专题轮播。
// 三张卡片指向「频道行表达不了」的窄口径搜索（宿舍桌椅 / 台灯 / 收纳），
// 不再重复分类、社区、免费送、发布闲置——那些入口首页只留一个。
export const promoPanels=[
  {key:'dorm',label:'宿舍好物专题',interval:7000,slides:[
    {title:'台灯照明，先看亮度',eyebrow:'宿舍焕新 · 三档调光',description:'暖光护眼 · 当面插电试给同学看',cta:'逛台灯',category:'living',q:'灯',art:'living'},
    {title:'收纳用品，桌面立正',eyebrow:'一格一格 · 找得着',description:'置物架与收纳盒 · 量好尺寸再下单',cta:'逛收纳',category:'living',q:'收纳',art:'living'},
    {title:'宿舍桌椅，稳当为先',eyebrow:'坐着写论文',description:'凳子与小桌 · 当面看承重和晃动',cta:'逛桌椅',category:'living',q:'凳',art:'living'}
  ]}
];

function artwork(kind){
  if(kind==='books') return '<div class="promo-books" aria-hidden="true"><span class="mini-book b1">数学<br><small>MATH</small></span><span class="mini-book b2">数据结构<br><small>DATA</small></span><span class="mini-book b3">Python<br><small>CODE</small></span></div>';
  if(kind==='campus') return '<div class="promo-home" aria-hidden="true"><span class="box">↗</span><span class="little-plant">✳</span><span class="folded-book"></span></div>';
  if(['living','sports'].includes(kind)) return `<div class="home-promo-category-art" aria-hidden="true">${categoryArt(kind)}</div>`;
  return `<div class="home-promo-symbol home-promo-symbol-${kind}" aria-hidden="true"><span>${icon(kind==='free'?'heart':'plus')}</span><i>${kind==='free'?'分享，让好物继续':'给闲置一个新开始'}</i></div>`;
}

export function homePromos(){
  return `<section class="campus-promos home-promos" aria-label="校园闲置专题">${promoPanels.map(panel=>`<section class="home-promo-window" data-home-carousel="${panel.key}" data-interval="${panel.interval}" aria-label="${panel.label}" aria-roledescription="轮播"><button class="campus-promo home-promo-open book-promo" data-action="home-promo-open" aria-label="${panel.slides[0].title}，${panel.slides[0].cta}">${panel.slides.map((slide,index)=>`<span class="home-promo-slide" data-promo-slide="${index}" data-title="${e(slide.title)}，${e(slide.cta)}" data-category="${slide.category}" data-q="${e(slide.q||'')}" ${index?'hidden':''}><span class="home-promo-copy"><span class="promo-eyebrow">${slide.eyebrow}</span><strong class="home-promo-title">${slide.title}</strong><span class="home-promo-desc">${slide.description}</span><span class="promo-link">${slide.cta} ${icon('arrow')}</span></span>${artwork(slide.art)}</span>`).join('')}</button><div class="home-promo-dots" aria-label="切换${panel.label}">${panel.slides.map((_,index)=>`<button data-action="home-slide" data-window="${panel.key}" data-index="${index}" aria-label="专题第 ${index+1} 页" aria-pressed="${index===0}"></button>`).join('')}</div></section>`).join('')}</section>`;
}
