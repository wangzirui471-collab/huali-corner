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
    cta:'发布我的闲置', go:'publish', art:'gate', tab:'校园'
  },
  {
    eyebrow:'二手好物 · 教材接力', title:'下一本，就在校园', description:'教材和笔记接着用，版次和成色可以当面看。',
    cta:'逛二手教材', go:'home/books', art:'books', tab:'教材'
  },
  {
    eyebrow:'宿舍生活 · 桌边好物', title:'给日常添一点光', description:'台灯、收纳和桌边小物，让校园生活更舒服。',
    cta:'逛宿舍生活', go:'home/living', art:'dorm', tab:'宿舍'
  },
  {
    eyebrow:'好物循环 · 校园求购', title:'想找的，让同学知道', description:'说清想要的物品和预算，让同学带着好物来找你。',
    cta:'去校园求购', go:'forum/wants', art:'swap', tab:'求购'
  }
].map(slide => ({ ...slide, image: coverURLs[slide.art] }));

/** 首张照片和全部专题随首页渲染，切换只改变各专题的可见性。 */
export function homeHero(){
  const total = heroSlides.length;
  return `<section class="home-hero mint-hero" aria-label="校园闲置专题">
    <div class="mint-opening"><div><small>广州校区 · 同校闲置</small><h1>在校园，发现好物</h1></div><p>同学们刚刚上架的好物，慢慢逛。</p></div>
    <div class="mint-topics">
      <section class="mint-carousel" data-mint-carousel aria-label="校园专题" aria-roledescription="轮播">
        <div class="mint-carousel-stage">
          ${heroSlides.map((slide, index) => `<div class="mint-slide" data-art="${slide.art}" role="group" aria-roledescription="专题"
              aria-label="${index + 1} / ${total}，${e(slide.tab)}"${index ? ' hidden' : ''}>
            <div class="mint-slide-photo" aria-hidden="true"><img class="mint-cover" src="${e(slide.image)}" alt="" decoding="async"${index ? '' : ' fetchpriority="high"'}></div>
            <div class="mint-slide-copy"><small>${e(slide.eyebrow)}</small><h2>${e(slide.title)}</h2><p>${e(slide.description)}</p>
              <button type="button" class="mint-topic-link" data-go="${slide.go}">${e(slide.cta)} <span aria-hidden="true">↗</span></button>
            </div>
          </div>`).join('')}
        </div>
        <div class="mint-carousel-controls" role="group" aria-label="切换校园专题">
          <button type="button" class="mint-carousel-arrow" data-slide-step="-1" aria-label="上一张"><span aria-hidden="true">‹</span></button>
          <div class="mint-carousel-pages">${heroSlides.map((slide, index) => `<button type="button" data-slide-index="${index}" aria-label="第 ${index + 1} 张：${e(slide.tab)}"${index ? '' : ' aria-current="true"'}>${e(slide.tab)}</button>`).join('')}</div>
          <button type="button" class="mint-carousel-arrow" data-slide-step="1" aria-label="下一张"><span aria-hidden="true">›</span></button>
          <span class="mint-carousel-status" data-slide-status role="status">1 / ${total}</span>
        </div>
      </section>
      <div class="mint-side">
        <button type="button" data-go="home/books" data-art="books"><span class="mint-side-photo" aria-hidden="true"><img class="mint-cover" src="${e(coverURLs.books)}" alt=""></span><small>01 / 二手好物</small><strong>二手教材</strong><span>下一本，就在校园 →</span></button>
        <button type="button" data-go="home/free" data-art="swap"><span class="mint-side-photo" aria-hidden="true"><img class="mint-cover" src="${e(coverURLs.swap)}" alt=""></span><small>02 / 分享</small><strong>免费好物</strong><span>把闲置传给同学 →</span></button>
      </div>
    </div>
  </section>`;
}

/** 直接切换当前页面里的专题，离开首页时监听随节点一起释放。 */
export function mountHomeHero(root){
  const carousel = root.querySelector('[data-mint-carousel]');
  if (!carousel) return;
  const slides = [...carousel.querySelectorAll('.mint-slide')];
  const pages = [...carousel.querySelectorAll('[data-slide-index]')];
  const status = carousel.querySelector('[data-slide-status]');
  let current = 0;

  /** 显示目标专题，同步控制按钮和进度提示。 */
  function show(index){
    const next = (index + slides.length) % slides.length;
    if (current === next) return;
    slides[next].hidden = false;
    slides[current].hidden = true;
    pages[current].removeAttribute('aria-current');
    pages[next].setAttribute('aria-current', 'true');
    current = next;
    status.textContent = `${current + 1} / ${slides.length}`;
  }

  // 鼠标和触屏共用原生按钮，键盘在控制区也可用左右方向键。
  carousel.addEventListener('click', event => {
    const step = event.target.closest('[data-slide-step]');
    const page = event.target.closest('[data-slide-index]');
    if (step) show(current + Number(step.dataset.slideStep));
    if (page) show(Number(page.dataset.slideIndex));
  });
  carousel.querySelector('.mint-carousel-controls').addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    show(current + (event.key === 'ArrowLeft' ? -1 : 1));
  });
}
