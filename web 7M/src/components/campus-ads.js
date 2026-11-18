import {e} from '../core/dom.js';
import {referenceMaps} from './campus-reference.js';

const aerial = new URL('../../assets/home-mint/campus-hd/lake-aerial.jpg', import.meta.url).href;
const campusMap = referenceMaps[0].photo;

/** 把照片和前景放在不同深度，作为首页横幅的一部分直接展示。 */
export function campusAdArt(topic, image) {
  const foreground = {
    books: () => `<div class="campus-ad-book">
      <div class="campus-ad-book-base"></div>
      <div class="campus-ad-page campus-ad-page-right"><span>极限</span><b>x → 1</b><i></i><i></i><i></i></div>
      <div class="campus-ad-page campus-ad-page-left"><span>教材试读</span><b>高等数学</b><i></i><i></i></div>
    </div>`,
    dorm: () => `<figure class="campus-ad-aerial"><img src="${e(aerial)}" alt="" loading="lazy" decoding="async"></figure>
      <figure class="campus-ad-map"><img src="${e(campusMap)}" alt="" width="1080" height="540" loading="lazy" decoding="async"></figure>`,
    swap: () => `<figure class="campus-ad-handover"><img src="${e(image)}" alt="" decoding="async"></figure>
      <div class="campus-ad-handover-book"><span>高等数学</span><i></i><i></i></div>`,
  }[topic];
  if (!foreground) return '';
  return `<div class="campus-ad-art" aria-hidden="true"><div class="campus-ad-orbit"><div class="campus-ad-scene">${foreground()}</div></div></div>`;
}

/** 用双层相片表现快捷广告的厚度，整张卡仍是原业务按钮。 */
export function campusSideArt(image) {
  return `<span class="mint-side-photo campus-side-art" aria-hidden="true"><span class="campus-side-print"><img class="mint-cover" src="${e(image)}" alt="" decoding="async"></span></span>`;
}

/** 鼠标移动时改变广告图层视角，触屏走入场动画并保留原点击操作。 */
export function mountCampusAds(root) {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  for (const ad of root.querySelectorAll('[data-campus-ad], [data-campus-side-ad]')) {
    ad.addEventListener('pointermove', event => {
      if (event.pointerType !== 'mouse' || reducedMotion.matches) return;
      const bounds = ad.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width - .5;
      const y = (event.clientY - bounds.top) / bounds.height - .5;
      ad.style.setProperty('--ad-yaw', `${x * 17}deg`);
      ad.style.setProperty('--ad-pitch', `${-y * 11}deg`);
      ad.style.setProperty('--ad-shift', `${x * -6}%`);
    });
    ad.addEventListener('pointerleave', () => {
      ad.style.removeProperty('--ad-yaw');
      ad.style.removeProperty('--ad-pitch');
      ad.style.removeProperty('--ad-shift');
    });
  }
}
