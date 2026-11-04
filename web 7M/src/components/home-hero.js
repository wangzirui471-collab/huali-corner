'use strict';

import { e } from '../core/dom.js';

// 主视觉文案用页面文字，插画单独交付，保证小屏也能阅读。
export const heroSlides = [
  {
    eyebrow:'广州校区 · 校门插画', title:'好物，从华立出发', description:'把闲置留在校园，交给刚好需要的同学。',
    cta:'发布我的闲置', go:'publish', art:'gate'
  },
  {
    eyebrow:'华立书角 · 教材专题', title:'下一本，就在校园', description:'教材和笔记接着用，版次和成色可以当面看。',
    cta:'逛二手教材', go:'home/books', art:'books'
  },
  {
    eyebrow:'课后时光 · 宿舍专题', title:'给宿舍添一点光', description:'台灯、收纳和桌边小物，让回宿舍这件事更舒服。',
    cta:'逛宿舍生活', go:'home/living', art:'dorm'
  },
  {
    eyebrow:'校园互助 · 求购专题', title:'想找的，让同学知道', description:'说清想要的物品和预算，让同学带着好物来找你。',
    cta:'去校园求购', go:'forum/wants', art:'swap'
  }
];

/** 绘制首屏专题，轮播加载前也能直接进入各个频道。 */
export function homeHero(){
  const [first, ...rest] = heroSlides;
  return `<section class="home-hero mint-hero" aria-label="校园闲置专题">
    <div class="mint-opening"><div><small>ON CAMPUS · 华立校园</small><h1>在校园，发现好物</h1></div><p>同学们刚刚上架的好物，慢慢逛。</p></div>
    <div class="mint-topics">
      <div data-mint-carousel aria-label="校园专题轮播">
        <div class="mint-slide" data-art="${first.art}">
          <div class="mint-slide-photo" aria-hidden="true"></div>
          <div class="mint-slide-copy"><small>${e(first.eyebrow)}</small><h2>${e(first.title)}</h2><p>${e(first.description)}</p>
            <button type="button" class="mint-topic-link" data-go="${first.go}">${e(first.cta)} <span aria-hidden="true">↗</span></button>
          </div>
        </div>
        <div class="mint-fallback-links">${rest.map(slide=>`<button type="button" data-go="${slide.go}">${e(slide.cta)}</button>`).join('')}</div>
      </div>
      <div class="mint-side">
        <button type="button" data-go="home/books" data-art="books"><span class="mint-side-photo" aria-hidden="true"></span><small>01 / 课堂</small><strong>二手教材</strong><span>下一本，就在校园 →</span></button>
        <button type="button" data-go="home/free" data-art="swap"><span class="mint-side-photo" aria-hidden="true"></span><small>02 / 分享</small><strong>免费好物</strong><span>把闲置传给同学 →</span></button>
      </div>
    </div>
  </section>`;
}

/** 首屏只在逛逛加载 Element Plus，切页后丢弃迟到的模块并卸载已挂载的实例。 */
export function mountHomeHero(root, alive){
  const target = root.querySelector('[data-mint-carousel]');
  if (!target) return () => {};
  let unmount;
  const fallback = target.innerHTML;
  import(new URL('../../assets/home-mint/carousel.js?v=2', import.meta.url))
    .then(({mountMintCarousel}) => {
      if (alive()) unmount = mountMintCarousel(target, heroSlides);
    })
    .catch(() => {
      if (alive() && !target.querySelector('.mint-fallback-links')) target.innerHTML = fallback;
    });
  return () => unmount?.();
}
