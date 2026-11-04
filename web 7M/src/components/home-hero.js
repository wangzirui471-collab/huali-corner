'use strict';

import { e } from '../core/dom.js';

// 模块地址也支持公开演示部署在子目录，图片都从站点自身加载。
const coverURLs = {
  gate: new URL('../../assets/home-mint/campus-gate.webp', import.meta.url).pathname,
  books: new URL('../../assets/home-mint/market-books.webp', import.meta.url).pathname,
  dorm: new URL('../../assets/home-mint/market-desk.webp', import.meta.url).pathname,
  swap: new URL('../../assets/home-mint/market-share.webp', import.meta.url).pathname
};

// 轮播与快捷卡使用同一组来源，标题用可缩放的页面文字。
export const heroSlides = [
  {
    eyebrow:'广州校区 · 校门', title:'好物，从华立出发', description:'把闲置留在校园，交给刚好需要的同学。',
    cta:'发布我的闲置', go:'publish', art:'gate'
  },
  {
    eyebrow:'二手好物 · 教材接力', title:'下一本，就在校园', description:'教材和笔记接着用，版次和成色可以当面看。',
    cta:'逛二手教材', go:'home/books', art:'books'
  },
  {
    eyebrow:'宿舍生活 · 桌边好物', title:'给日常添一点光', description:'台灯、收纳和桌边小物，让校园生活更舒服。',
    cta:'逛宿舍生活', go:'home/living', art:'dorm'
  },
  {
    eyebrow:'好物循环 · 校园求购', title:'想找的，让同学知道', description:'说清想要的物品和预算，让同学带着好物来找你。',
    cta:'去校园求购', go:'forum/wants', art:'swap'
  }
].map(slide => ({ ...slide, image: coverURLs[slide.art] }));

/** 绘制首屏专题，轮播加载前也能直接进入各个频道。 */
export function homeHero(){
  const [first, ...rest] = heroSlides;
  return `<section class="home-hero mint-hero" aria-label="校园闲置专题">
    <div class="mint-opening"><div><small>ON CAMPUS · 华立校园</small><h1>在校园，发现好物</h1></div><p>同学们刚刚上架的好物，慢慢逛。</p></div>
    <div class="mint-topics">
      <div data-mint-carousel aria-label="校园专题轮播">
        <div class="mint-slide" data-art="${first.art}">
          <div class="mint-slide-photo" aria-hidden="true"><img class="mint-cover" src="${e(first.image)}" alt="" fetchpriority="high"></div>
          <div class="mint-slide-copy"><small>${e(first.eyebrow)}</small><h2>${e(first.title)}</h2><p>${e(first.description)}</p>
            <button type="button" class="mint-topic-link" data-go="${first.go}">${e(first.cta)} <span aria-hidden="true">↗</span></button>
          </div>
        </div>
        <div class="mint-fallback-links">${rest.map(slide=>`<button type="button" data-go="${slide.go}">${e(slide.cta)}</button>`).join('')}</div>
      </div>
      <div class="mint-side">
        <button type="button" data-go="home/books" data-art="books"><span class="mint-side-photo" aria-hidden="true"><img class="mint-cover" src="${e(coverURLs.books)}" alt=""></span><small>01 / 二手好物</small><strong>二手教材</strong><span>下一本，就在校园 →</span></button>
        <button type="button" data-go="home/free" data-art="swap"><span class="mint-side-photo" aria-hidden="true"><img class="mint-cover" src="${e(coverURLs.swap)}" alt=""></span><small>02 / 分享</small><strong>免费好物</strong><span>把闲置传给同学 →</span></button>
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
  import(new URL('../../assets/home-mint/carousel-market.js', import.meta.url))
    .then(({mountMintCarousel}) => {
      if (alive()) unmount = mountMintCarousel(target, heroSlides);
    })
    .catch(() => {
      if (alive() && !target.querySelector('.mint-fallback-links')) target.innerHTML = fallback;
    });
  return () => unmount?.();
}
