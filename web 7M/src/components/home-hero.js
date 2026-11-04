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
      {eyebrow:'宿舍焕新 · 台灯收纳桌椅',title:'好物留在华立',description:'台灯、收纳架、小书桌，毕业时转给下一届。',cta:'发现生活好物',go:'home/living',art:'lamp'},
      {eyebrow:'毕业季 · 带不走的东西',title:'带不走的，留给还在这栋楼的人',description:'宿舍楼下当面交接，省一趟快递，也少一份浪费。',cta:'逛宿舍生活',go:'home/living',art:'lamp'},
      {eyebrow:'校园求购 · 说清你要什么',title:'没找到？发个求购试试',description:'写清预算和版本，卖家能主动找上你。',cta:'去校园求购',go:'forum/wants',art:'want'}
    ]
  }
];

// 两张卡的插画都用内联 SVG：不为一张主视觉再发一次图片请求，
// 也让配色跟品牌黄、墨色、珊瑚红保持一致。
const artwork = {
  books:`<svg class="home-hero-art-svg" viewBox="0 0 210 168" aria-hidden="true">
    <ellipse cx="106" cy="150" rx="68" ry="9" fill="#8a5a1e" opacity=".1"/>
    <g transform="rotate(-7 105 120)"><rect x="44" y="112" width="118" height="24" rx="5" fill="#2f6f8f"/><rect x="50" y="117" width="104" height="5" rx="2.5" fill="#8dc0d4" opacity=".6"/></g>
    <g transform="rotate(3 105 96)"><rect x="40" y="86" width="122" height="25" rx="5" fill="#c2532f"/><rect x="46" y="91" width="108" height="5" rx="2.5" fill="#f2a283" opacity=".65"/></g>
    <g transform="rotate(-3 105 62)"><rect x="48" y="58" width="104" height="26" rx="5" fill="#f2b134"/><rect x="54" y="63" width="90" height="5" rx="2.5" fill="#ffe0a2" opacity=".8"/></g>
    <g transform="rotate(8 172 44)"><rect x="152" y="24" width="42" height="30" rx="8" fill="#fff" opacity=".94"/><text x="173" y="44" text-anchor="middle" font-size="13" font-weight="700" fill="#b4532f">¥18</text></g>
  </svg>`,
  lamp:`<svg class="home-hero-art-svg" viewBox="0 0 210 168" aria-hidden="true">
    <ellipse cx="104" cy="150" rx="62" ry="9" fill="#5b4bd6" opacity=".1"/>
    <path d="M54 148h44" stroke="#8b79b4" stroke-width="7" stroke-linecap="round"/>
    <path d="M76 148V96c0-19 13-34 31-38" stroke="#8b79b4" stroke-width="7" stroke-linecap="round" fill="none"/>
    <path d="M104 24l40 26-22 30-40-26z" fill="#6c5ce7"/>
    <path d="M107 40l26 17-14 19-26-17z" fill="#a99cff" opacity=".65"/>
    <path d="M104 76l-18 34h58z" fill="#ffd85c" opacity=".28"/>
    <g transform="rotate(6 160 128)"><rect x="140" y="112" width="40" height="30" rx="9" fill="#7bbf9f"/><path d="M160 112V92" stroke="#4f9887" stroke-width="5" stroke-linecap="round"/><circle cx="160" cy="86" r="10" fill="#9fd9bb"/></g>
  </svg>`,
  want:`<svg class="home-hero-art-svg" viewBox="0 0 210 168" aria-hidden="true">
    <ellipse cx="104" cy="150" rx="60" ry="9" fill="#2b7a8c" opacity=".1"/>
    <rect x="52" y="42" width="104" height="88" rx="12" fill="#fff" opacity=".95"/>
    <rect x="64" y="58" width="66" height="7" rx="3.5" fill="#cfe3e8"/>
    <rect x="64" y="74" width="80" height="7" rx="3.5" fill="#e3eff2"/>
    <rect x="64" y="90" width="52" height="7" rx="3.5" fill="#e3eff2"/>
    <circle cx="150" cy="112" r="22" fill="#2b7a8c"/>
    <path d="M141 112l6 6 12-13" stroke="#fff" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
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
