'use strict';
// 组件层 · 逛逛页双卡主视觉
//
// 两张卡各是一个小型轮播：左卡讲教材，右卡讲宿舍好物。
// 与旧版的关键差别：每张 slide 都带一个独立去处（频道页 / 求购页），
// 点卡片按「当前可见的那张」跳，不再像旧版那样三个入口都落回同一个商品流。
// 轮播的自动播放、圆点切换、键盘可达都由 actions/home-feed 统一挂载。

import { e, icon } from '../core/dom.js';

export const heroPanels = [
  {
    key:'books',
    label:'教材专区',
    interval:7000,
    slides:[
      {eyebrow:'教材专区 · 学长学姐的旧书',title:'教材不必买新的',description:'笔记、版次、缺页都写在详情里，当面翻开再付钱。',cta:'逛逛教材',go:'home/books',art:'books'},
      {eyebrow:'计算机工程学院 · 逐本上架',title:'一本书，也是一个学期的账',description:'按书名和版次找，比在群里问「谁有」快得多。',cta:'按版次找书',go:'home/books',art:'books'},
      {eyebrow:'毕业季 · 书架清空中',title:'你的旧课本，正是别人的开学',description:'拍正面、侧面、顶部三张，买家看得清再决定。',cta:'发布我的闲置',go:'publish',art:'books'}
    ]
  },
  {
    key:'living',
    label:'宿舍好物',
    interval:8000,
    slides:[
      {eyebrow:'宿舍焕新 · 台灯收纳桌椅',title:'好物留在华立',description:'台灯、收纳架、小书桌，毕业时转给下一届。',cta:'发现生活好物',go:'home/living',art:'rack'},
      {eyebrow:'毕业季 · 带不走的东西',title:'带不走的，留给还在这栋楼的人',description:'宿舍楼下当面交接，省一趟快递，也少一份浪费。',cta:'逛宿舍生活',go:'home/living',art:'rack'},
      {eyebrow:'校园求购 · 说清你要什么',title:'没找到？发个求购试试',description:'写清预算和版本，卖家能主动找上你。',cta:'去校园求购',go:'forum/wants',art:'want'}
    ]
  }
];

// 两张卡的插画都用内联 SVG：不为一张主视觉再发一次图片请求，
// 配色跟着逛逛页的墨绿 / 陶土橙走，和商品照片放在一起不打架。
const artwork = {
  books:`<svg class="home-hero-art-svg" viewBox="0 0 200 170" aria-hidden="true">
    <ellipse cx="100" cy="152" rx="64" ry="9" fill="#1e3a33" opacity=".10"/>
    <g transform="rotate(-6 100 122)"><rect x="32" y="110" width="136" height="26" rx="5" fill="#4f7a68"/><rect x="41" y="116" width="112" height="5" rx="2.5" fill="#a9c9b7" opacity=".65"/></g>
    <g transform="rotate(2 100 96)"><rect x="28" y="84" width="144" height="27" rx="5" fill="#d98a5f"/><rect x="37" y="90" width="118" height="5" rx="2.5" fill="#f6c9ae" opacity=".8"/></g>
    <g transform="rotate(-2 100 62)"><rect x="36" y="52" width="128" height="28" rx="5" fill="#e9c46a"/><rect x="45" y="58" width="100" height="5" rx="2.5" fill="#fff0c4" opacity=".9"/></g>
    <g transform="rotate(7 168 40)"><rect x="142" y="20" width="54" height="35" rx="10" fill="#fff" opacity=".97"/><text x="169" y="44" text-anchor="middle" font-size="14" font-weight="700" fill="#c9542c">¥18</text></g>
  </svg>`,
  rack:`<svg class="home-hero-art-svg" viewBox="0 0 200 170" aria-hidden="true">
    <ellipse cx="100" cy="156" rx="64" ry="8" fill="#1e3a33" opacity=".10"/>
    <rect x="44" y="56" width="9" height="96" rx="4.5" fill="#4f7a68"/>
    <rect x="147" y="56" width="9" height="96" rx="4.5" fill="#4f7a68"/>
    <rect x="38" y="64" width="124" height="9" rx="4.5" fill="#8fb3a0"/>
    <rect x="38" y="100" width="124" height="9" rx="4.5" fill="#8fb3a0"/>
    <rect x="38" y="140" width="124" height="9" rx="4.5" fill="#8fb3a0"/>
    <rect x="94" y="46" width="26" height="18" rx="5" fill="#cf7a52"/>
    <path d="M107 46V32" stroke="#5d8f74" stroke-width="3" stroke-linecap="round"/>
    <ellipse cx="99" cy="34" rx="9" ry="6.5" fill="#7aa189"/>
    <ellipse cx="115" cy="30" rx="8" ry="6" fill="#9dc3ab"/>
    <rect x="52" y="86" width="40" height="14" rx="3" fill="#d98a5f"/>
    <rect x="58" y="74" width="34" height="12" rx="3" fill="#e9c46a"/>
    <rect x="116" y="84" width="16" height="16" rx="4" fill="#eb754d"/>
    <path d="M132 89h5a4 4 0 0 1 0 7h-5" stroke="#eb754d" stroke-width="3" fill="none" stroke-linecap="round"/>
    <rect x="52" y="118" width="48" height="22" rx="5" fill="#e6f1e9"/>
    <path d="M64 118v22M86 118v22" stroke="#c8dbcd" stroke-width="2"/>
  </svg>`,
  want:`<svg class="home-hero-art-svg" viewBox="0 0 200 170" aria-hidden="true">
    <ellipse cx="100" cy="152" rx="58" ry="9" fill="#1e3a33" opacity=".10"/>
    <rect x="44" y="34" width="108" height="92" rx="13" fill="#fff" opacity=".97"/>
    <rect x="57" y="52" width="64" height="7" rx="3.5" fill="#dfe7dd"/>
    <rect x="57" y="71" width="82" height="7" rx="3.5" fill="#e9efe6"/>
    <rect x="57" y="90" width="50" height="7" rx="3.5" fill="#e9efe6"/>
    <circle cx="152" cy="112" r="23" fill="#4f7a68"/>
    <path d="M143 112l6 6 12-13" stroke="#fff" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M36 32l2.4 6 6 2.4-6 2.4L36 49l-2.4-6.2-6-2.4 6-2.4z" fill="#e9c46a" opacity=".9"/>
  </svg>`
};

function slideHTML(panel, slide, index){
  return `<span class="home-hero-slide" data-promo-slide="${index}" data-go="${e(slide.go)}" data-title="${e(slide.title)}，${e(slide.cta)}" ${index?'hidden':''}>
    <span class="home-hero-copy">
      <span class="home-hero-eyebrow">${e(slide.eyebrow)}</span>
      <strong class="home-hero-title">${e(slide.title)}</strong>
      <span class="home-hero-desc">${e(slide.description)}</span>
      <span class="home-hero-link">${e(slide.cta)}${icon('arrow')}</span>
    </span>
    <span class="home-hero-art" aria-hidden="true">${artwork[slide.art]||''}</span>
  </span>`;
}

export function homeHero(){
  return `<section class="home-hero" aria-label="校园闲置专题">${heroPanels.map(panel=>`
    <section class="home-hero-card" data-tone="${panel.key}" data-home-carousel="${panel.key}" data-interval="${panel.interval}" aria-roledescription="轮播" aria-label="${panel.label}">
      <button class="home-hero-open" type="button" data-action="home-promo-open" aria-label="${e(panel.slides[0].title)}，${e(panel.slides[0].cta)}">
        ${panel.slides.map((slide,index)=>slideHTML(panel,slide,index)).join('')}
      </button>
      <div class="home-hero-dots" aria-label="切换${panel.label}">${panel.slides.map((_,index)=>
        `<button type="button" data-action="home-slide" data-window="${panel.key}" data-index="${index}" aria-label="${panel.label}第 ${index+1} 页" aria-pressed="${index===0}"></button>`).join('')}</div>
    </section>`).join('')}</section>`;
}
