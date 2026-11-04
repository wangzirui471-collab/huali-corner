'use strict';

import { e } from '../core/dom.js';

export const heroSlides = [
  { eyebrow:'宿舍灵感 · 生活专题', title:'把宿舍布置成\n喜欢的样子', description:'一盏灯、一本书，给课后的时间留点温柔。', cta:'逛宿舍生活', go:'home/living', art:'dorm' },
  { eyebrow:'课堂好物 · 教材专题', title:'下一本，就在校园', description:'和同学当面交接，版次和笔记都能先看清。', cta:'逛二手教材', go:'home/books', art:'books' },
  { eyebrow:'校园求购 · 让同学找到你', title:'没找到？发个求购试试', description:'写清预算和版本，让有闲置的同学找到你。', cta:'去校园求购', go:'forum/wants', art:'camera' },
  { eyebrow:'毕业季 · 把好物传下去', title:'闲置小物，遇见新主人', description:'拍几张照片，把用不到的留给刚好需要的人。', cta:'发布我的闲置', go:'publish', art:'bag' }
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
        <button type="button" data-go="home/free" data-art="camera"><span class="mint-side-photo" aria-hidden="true"></span><small>02 / 分享</small><strong>免费好物</strong><span>把闲置传给同学 →</span></button>
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
  import(new URL('../../assets/home-mint/carousel.js?v=1', import.meta.url))
    .then(({mountMintCarousel}) => {
      if (alive()) unmount = mountMintCarousel(target, heroSlides);
    })
    .catch(() => {
      if (alive() && !target.querySelector('.mint-fallback-links')) target.innerHTML = fallback;
    });
  return () => unmount?.();
}
