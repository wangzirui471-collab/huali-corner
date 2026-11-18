/** 校园专题交互只展示样例，通过原导航进入商品和求购业务。 */
import {mapBlocks, referenceMaps, referencePhotos} from './campus-reference.js';
export const tradePhoto = new URL('../../assets/home-mint/campus-handover.webp', import.meta.url).href;

const topics = {
  tour: {label: '3D 校园导览', title: '从空中看华立', note: '广州增城校区', route: 'home/living', cta: '逛宿舍生活'},
  books: {label: '翻开高数', title: '翻一页，高数继续读', note: '原创高数试读 · 3 页', route: 'home/books', cta: '逛二手教材'},
  dorm: {label: '探索宿舍地图', title: '宿舍与教学楼', note: '广州增城校区', route: 'home/living', cta: '逛宿舍生活'},
  swap: {label: '看面交演示', title: '一本书，交到下一位同学手里', note: '校园面交情景演示', route: 'forum/wants', cta: '浏览校园求购'},
};

const pages = [
  {unit: '01　极限', title: '越来越接近', formula: 'lim (x² − 1) / (x − 1) = 2', body: '当 x 趋近于 1 时，先把分子拆成 (x − 1)(x + 1)，再约去公共因子。', foot: '提示：x 不等于 1，约分后的式子是 x + 1。'},
  {unit: '02　导数', title: '变化有多快', formula: 'f′(x) = 2x', body: '设 f(x) = x²。把 f(x + h) − f(x) 除以 h，得到 2x + h。让 h 趋近于 0，就得到导数。', foot: '练一练：x = 2 时，切线的斜率是多少？'},
  {unit: '03　积分', title: '把小块加起来', formula: '∫₀¹ 2x dx = 1', body: '先找到 2x 的一个原函数 x²，再计算两端的差 1² − 0²。它也是直线下方三角形的面积。', foot: '复习：同一条曲线，用导数看斜率，用积分算面积。'},
];

const dorms = [
  {name: 'B 区', buildings: 'B1–B4 栋', shape: [6, 33, 12, 16], color: 'b'},
  {name: 'C 区', buildings: 'C1–C8 栋', shape: [22, 61, 15, 15], color: 'c'},
  {name: 'D 区', buildings: 'D1–D6 栋', shape: [78, 67, 17, 15], color: 'd'},
  {name: '教学区', buildings: '可选择建筑查看实景', shape: [58, 57, 17, 16], color: 'study'},
];

const campusGallery = 'https://www.hualixy.edu.cn/zsb/xxgk/xyfg__xxgk/xyfg/content_11';
const campusTour = 'https://www.hualixy.edu.cn/yyxy';
const views = [
  {title:'校园航拍', photo:new URL('../../assets/home-mint/campus-official/aerial.jpg', import.meta.url).href, source:'https://www.hualixy.edu.cn/xxgk/xyfg/content_14'},
  {title:'图书馆', landmark:6, form:'terrace', photo:new URL('../../assets/home-mint/campus-official/library.jpg', import.meta.url).href},
  {title:'二教', landmark:7, form:'classroom', photo:new URL('../../assets/home-mint/campus-official/second.jpg', import.meta.url).href},
  {title:'五教', landmark:8, form:'classroom', photo:new URL('../../assets/home-mint/campus-official/fifth.jpg', import.meta.url).href},
  ...referencePhotos,
  {title:'四教', landmark:0, form:'classroom', photo:new URL('../../assets/home-mint/campus-official/fourth.jpg', import.meta.url).href},
  {title:'六教', landmark:3, form:'classroom', photo:new URL('../../assets/home-mint/campus-official/sixth.jpg', import.meta.url).href},
  {title:'八号楼与十号楼', landmark:9, form:'towers', photo:new URL('../../assets/home-mint/campus-official/eighth-tenth.jpg', import.meta.url).href},
  {title:'文体楼', landmark:4, form:'hall', photo:new URL('../../assets/home-mint/campus-official/sports-hall.jpg', import.meta.url).href},
  {title:'综合楼', landmark:2, form:'terrace', photo:new URL('../../assets/home-mint/campus-official/main-building.jpg', import.meta.url).href},
];
const galleryGroups = [['official','官网图集'],['learning','学习空间'],['buildings','校园建筑'],['scenery','校园风景'],['life','生活设施']];

const steps = [
  {title: '约个见面的地方', detail: '先在站内沟通时间和公开地点。'},
  {title: '两人当面验书', detail: '核对教材版次、笔记和缺页情况。'},
  {title: '确认后完成交接', detail: '双方确认实物和约定，再回到站内完成模拟交易。'},
];

/** 生成可访问的专题触发按钮，避免覆盖原 data-go 按钮。 */
export function experienceButton(topic, className = 'campus-experience-button') {
  return `<button type="button" class="${className}" data-campus-open="${topic}" aria-haspopup="dialog">${topics[topic].label} <span aria-hidden="true">↗</span></button>`;
}

/** 立体校园示意用 CSS 三维面搭建，楼区点击和下方按钮共用状态。 */
function campusModel() {
  return `<div class="campus-model" data-campus-model><div class="campus-model-plane">
    <span class="campus-model-path"></span><span class="campus-model-path campus-model-avenue"></span><span class="campus-model-lawn"></span><span class="campus-model-track"></span><span class="campus-model-trees"></span>
    ${mapBlocks.map((block,index) => {
      const building = views.find(view => view.landmark === index);
      return `<span class="campus-model-building${building ? ' campus-form-'+building.form : ''}" data-landmark="${index}" style="--x:${block.x}%;--y:${block.y}%;--w:${block.w}%;--h:${block.h}%" aria-hidden="true"></span>`;
    }).join('')}
    ${dorms.map(({name,color,shape:[x,y,w,h]}, index) => {
      return `<button type="button" data-campus-dorm="${index}" aria-label="选择${name}" class="campus-block campus-block-${color}" style="--x:${x}%;--y:${y}%;--w:${w}%;--h:${h}%"><i></i><b>${name}</b></button>`;
    }).join('')}</div></div>`;
}

/** 求购页面与首页共享同一个面交情景。 */
export function wantExperienceBanner() {
  return `<section class="campus-want-banner" aria-label="校园面交情景" style="--trade-photo:url('${tradePhoto}')"><div><h2>同校面交，先看实物</h2><p>从约地点到验货，看看两位同学怎么交接。</p>${experienceButton('swap')}</div></section>`;
}

/** 试读页使用可读正文和双面翻页，不引用实际教材扫描页。 */
function bookContent() {
  return `<div class="campus-book" data-campus-book aria-live="polite"></div><div class="campus-controls"><button type="button" data-book-step="-1">上一页</button><output data-book-position></output><button type="button" data-book-step="1">翻到下一页</button></div>`;
}

/** 宿舍选择与旋转均提供按钮，拖动为额外控制。 */
function dormContent() {
  return `<div class="campus-view-switch" role="group" aria-label="校园展示方式"><button type="button" data-campus-mode="map">立体示意</button><button type="button" data-campus-mode="photos">校园实景</button><button type="button" data-campus-mode="reference">参考地图</button></div>
  <div data-campus-view="map">${campusModel()}
    <div class="campus-controls campus-map-controls" aria-label="操作校园地图"><button type="button" data-map-turn="-25" aria-label="向左旋转">↶</button><button type="button" data-map-turn="25" aria-label="向右旋转">↷</button><button type="button" data-map-zoom="-.15" aria-label="缩小地图">−</button><button type="button" data-map-zoom=".15" aria-label="放大地图">＋</button><button type="button" data-map-reset>复位</button></div>
    <div class="campus-controls campus-dorm-choices" aria-label="选择校园分区">${dorms.map(({name}, index) => `<button type="button" data-campus-dorm="${index}">${name}</button>`).join('')}</div>
    <div class="campus-map-summary"><p class="campus-map-selection" data-map-selection aria-live="polite"></p></div>
    <div class="campus-landmark-select" data-campus-landmark-tools hidden>
      <label>建筑 <select data-campus-landmark>${views.map((view,index)=>view.landmark !== undefined ? `<option value="${index}"${index===2?' selected':''}>${view.title}</option>` : '').join('')}</select></label>
      <button class="campus-source" type="button" data-campus-teaching-photo>查看实景 ↗</button>
    </div>
    <p class="campus-map-note">依据参考图绘制湖、道路和楼群。分区位置仅供示意，请以学校导览为准。</p>
  </div>
  <div data-campus-view="photos" hidden>
    <div class="campus-photo-groups" role="group" aria-label="选择照片分类">${galleryGroups.map(([id,label])=>`<button type="button" data-campus-gallery="${id}">${label}</button>`).join('')}</div>
    <figure class="campus-photo-card"><img alt="" data-campus-photo><figcaption data-campus-caption></figcaption></figure>
    <div class="campus-controls campus-photo-choices" aria-label="选择校内照片">${views.map(({title, group}, index) => `<button type="button" data-campus-photo-index="${index}" data-photo-group="${group || 'official'}">${title}</button>`).join('')}</div>
  </div>
  <div data-campus-view="reference" hidden><div class="campus-photo-groups" role="group" aria-label="选择参考地图">${referenceMaps.map(({title},index)=>`<button type="button" data-reference-index="${index}">${title}</button>`).join('')}</div><figure class="campus-reference-card"><img data-reference-map alt="提供的华立校园导览参考缩略图"><figcaption>参考缩略图 · 楼号和小字有待高清原图核对</figcaption></figure></div>
  <div class="campus-map-sources"><a class="campus-source" href="${views[0].source}" target="_blank" rel="noopener noreferrer">学校官网航拍 ↗</a><a class="campus-source" href="${campusGallery}" target="_blank" rel="noopener noreferrer">教学楼原图集 ↗</a><a class="campus-source" href="${campusTour}" target="_blank" rel="noopener noreferrer">学校全景漫游 ↗</a></div>`;
}

/** 面交镜头配三步操作，播放可以暂停、重放，也可以逐步查看。 */
function tradeContent() {
  return `<div class="campus-trade" data-campus-trade data-step="0" style="--trade-photo:url('${tradePhoto}')"><div class="campus-trade-image"></div><p data-trade-caption aria-live="polite"></p></div><div class="campus-controls campus-trade-controls" aria-label="面交流程">${steps.map(({title}, index) => `<button type="button" data-trade-step="${index}" aria-label="${title}">${['约见', '验书', '交接'][index]}</button>`).join('')}<button type="button" data-trade-play>播放</button></div>`;
}

/** 教材翻页时只替换场景内部，读屏仍能读取当前页。 */
function bindBook(dialog) {
  const book = dialog.querySelector('[data-campus-book]');
  const position = dialog.querySelector('[data-book-position]');
  const controls = [...dialog.querySelectorAll('[data-book-step]')];
  let current = 0;
  /** 按页号绘制正文，公式提示 x 的趋近方向。 */
  function pageMarkup(index) {
    const page = pages[index];
    return `<div class="campus-book-paper"><small>${page.unit}</small><h3>${page.title}</h3><p class="campus-formula">${index === 0 ? 'x → 1 · ' : ''}${page.formula}</p><p>${page.body}</p><small>${page.foot}</small></div>`;
  }
  /** 背景页先更新，旧纸叶绕书脊翻过，动画结束后移除。 */
  function show(index, turn = false) {
    if (index < 0 || index >= pages.length) return;
    const oldPage = current;
    current = index;
    book.innerHTML = pageMarkup(index);
    if (turn && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const leaf = document.createElement('div');
      leaf.className = 'campus-leaf';
      leaf.setAttribute('aria-hidden', 'true');
      leaf.innerHTML = pageMarkup(oldPage);
      book.append(leaf);
      const direction = index > oldPage ? 1 : -1;
      leaf.animate([{transform:'rotateY(0deg)'},{transform:`rotateY(${-178 * direction}deg)`}], {duration:550, easing:'cubic-bezier(.34,.06,.22,1)'}).finished.then(() => leaf.remove(), () => leaf.remove());
    }
    position.textContent = `${index + 1} / ${pages.length}`;
    controls[0].disabled = index === 0;
    controls[1].disabled = index === pages.length - 1;
  }
  controls.forEach(button => button.addEventListener('click', () => show(current + Number(button.dataset.bookStep), true)));
  dialog.addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    show(current + (event.key === 'ArrowRight' ? 1 : -1), true);
  });
  show(0);
}

/** 转动俯瞰视角，保留地图和可访问区域选择的一致性。 */
function bindDorm(dialog, initialMode = 'map') {
  const map = dialog.querySelector('[data-campus-model]');
  const choices = [...dialog.querySelectorAll('[data-campus-dorm]')];
  const selection = dialog.querySelector('[data-map-selection]');
  const teachingPhoto = dialog.querySelector('[data-campus-teaching-photo]');
  const landmarkTools = dialog.querySelector('[data-campus-landmark-tools]');
  const landmark = dialog.querySelector('[data-campus-landmark]');
  const referenceImage = dialog.querySelector('[data-reference-map]');
  const referenceButtons = [...dialog.querySelectorAll('[data-reference-index]')];
  const modeButtons = [...dialog.querySelectorAll('[data-campus-mode]')];
  const photoButtons = [...dialog.querySelectorAll('[data-campus-photo-index]')];
  const groupButtons = [...dialog.querySelectorAll('[data-campus-gallery]')];
  const photo = dialog.querySelector('[data-campus-photo]');
  const photoCard = photo.closest('figure');
  const caption = dialog.querySelector('[data-campus-caption]');
  let angle = -22;
  let zoom = 1;
  let mode = 'map';
  let photoIndex = 0;
  let group = 'official';
  let drag = null;
  let photoMotion;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  photo.addEventListener('load', () => {
    if (reducedMotion.matches) return;
    photoMotion?.cancel();
    photoMotion = photo.animate([{opacity:.72,scale:'1.045'},{opacity:1,scale:'1'}], {duration:540,easing:'ease-out'});
  });
  photoCard.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' || reducedMotion.matches) return;
    const box = photoCard.getBoundingClientRect();
    photo.style.setProperty('--photo-lean', `${((event.clientX - box.left) / box.width - .5) * 7}deg`);
  });
  photoCard.addEventListener('pointerleave', () => photo.style.removeProperty('--photo-lean'));
  /** 用真实三维变换更新地图朝向。 */
  function rotate(next) { angle = next; map.style.setProperty('--map-turn', `${angle}deg`); }
  /** 同步模型与平面控制按钮的选中态。 */
  function select(index) {
    choices.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.campusDorm) === index)));
    selection.textContent = `已选 ${dorms[index].name} · ${dorms[index].buildings}`;
    landmarkTools.hidden = dorms[index].color !== 'study';
    highlightLandmark();
  }
  /** 只突出当前选中的建筑体量，位置仍按参考图作示意。 */
  function highlightLandmark() {
    const id = views[Number(landmark.value)].landmark;
    map.querySelectorAll('[data-landmark]').forEach(item=>item.classList.toggle('is-landmark', !landmarkTools.hidden && Number(item.dataset.landmark) === id));
  }
  /** 参考图保持完整画幅，分别查看手绘地图和带图例的版式。 */
  function showReference(index) {
    const view = referenceMaps[index];
    referenceImage.src = view.photo;
    referenceImage.alt = `${view.title}参考缩略图`;
    referenceButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
  }
  /** 切换照片时同步清晰标题，让来源始终可见。 */
  function showPhoto(index) {
    photoIndex = index;
    const view = views[photoIndex];
    photo.src = view.photo;
    photo.alt = view.group ? view.title : `广州华立学院广州校区${view.title}实景`;
    photoCard.classList.toggle('is-reference-photo', Boolean(view.group));
    caption.textContent = `${view.title} · ${view.group ? '参考照片' : '广州华立学院官网'}`;
    photoButtons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === photoIndex)));
  }
  /** 用分类缩小可选范围，键盘翻阅与当前分类保持一致。 */
  function showGallery(next) {
    group = next;
    groupButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.campusGallery === group)));
    photoButtons.forEach(button => { button.hidden = button.dataset.photoGroup !== group; });
    showPhoto(Number(photoButtons.find(button => !button.hidden).dataset.campusPhotoIndex));
  }
  /** 切换标签时保留地图朝向、照片和参考图的选中项。 */
  function showMode(next) {
    mode = next;
    dialog.querySelectorAll('[data-campus-view]').forEach(view => { view.hidden = view.dataset.campusView !== mode; });
    modeButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.campusMode === mode)));
    if (mode === 'photos' && !photo.hasAttribute('src')) showGallery('official');
    if (mode === 'reference' && !referenceImage.hasAttribute('src')) showReference(0);
  }
  /** 限制缩放范围，保证场景在窄屏里仍容易操作。 */
  function scale(next) {
    zoom = Math.max(.75, Math.min(1.3, next));
    map.style.setProperty('--map-zoom', String(zoom));
  }
  modeButtons.forEach(button => button.addEventListener('click', () => showMode(button.dataset.campusMode)));
  groupButtons.forEach(button => button.addEventListener('click', () => showGallery(button.dataset.campusGallery)));
  referenceButtons.forEach((button,index) => button.addEventListener('click', () => showReference(index)));
  landmark.addEventListener('change', highlightLandmark);
  teachingPhoto.addEventListener('click', () => {
    showMode('photos');
    if (group !== 'official') showGallery('official');
    const selected = Number(landmark.value);
    showPhoto(selected);
    photoButtons[selected].focus({preventScroll:true});
  });
  photoButtons.forEach((button,i) => button.addEventListener('click', () => showPhoto(i)));
  dialog.addEventListener('keydown', event => {
    if (mode !== 'photos' || !['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const indexes = photoButtons.filter(button => !button.hidden).map(button => Number(button.dataset.campusPhotoIndex));
    const step = event.key === 'ArrowRight' ? 1 : -1;
    showPhoto(indexes[(indexes.indexOf(photoIndex) + step + indexes.length) % indexes.length]);
  });
  choices.forEach(button => button.addEventListener('click', () => select(Number(button.dataset.campusDorm))));
  dialog.querySelectorAll('[data-map-turn]').forEach(button => button.addEventListener('click', () => rotate(angle + Number(button.dataset.mapTurn))));
  dialog.querySelectorAll('[data-map-zoom]').forEach(button => button.addEventListener('click', () => scale(zoom + Number(button.dataset.mapZoom))));
  dialog.querySelector('[data-map-reset]').addEventListener('click', () => { rotate(-22); scale(1); });
  map.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('button')) return;
    drag = {id:event.pointerId, x:event.clientX, angle};
    map.setPointerCapture(event.pointerId);
  });
  map.addEventListener('pointermove', event => {
    if (drag?.id === event.pointerId) rotate(drag.angle + (event.clientX - drag.x) * .55);
  });
  map.addEventListener('lostpointercapture', () => { drag = null; });
  select(0);
  showMode(initialMode);
}

/** 只有用户操作才播放镜头，离开、关闭或手动选步都会停止计时。 */
function bindTrade(dialog) {
  const scene = dialog.querySelector('[data-campus-trade]');
  const caption = dialog.querySelector('[data-trade-caption]');
  const choices = [...dialog.querySelectorAll('[data-trade-step]')];
  const play = dialog.querySelector('[data-trade-play]');
  let current = 0;
  let timer;
  /** 切换镜头、文字和进度。 */
  function show(index) {
    current = index;
    scene.dataset.step = String(index);
    caption.textContent = `${steps[index].title} · ${steps[index].detail}`;
    choices.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
  }
  /** 清除播放定时，关闭和切页可重复调用。 */
  function pause() {
    clearInterval(timer);
    timer = undefined;
    play.textContent = current === steps.length - 1 ? '重播' : '播放';
  }
  play.addEventListener('click', () => {
    if (timer) return pause();
    if (current === steps.length - 1) show(0);
    play.textContent = '暂停';
    timer = setInterval(() => {
      if (current < steps.length - 1) show(current + 1);
      else pause();
    }, 2400);
  });
  choices.forEach((button, index) => button.addEventListener('click', () => {show(index); pause();}));
  scene.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const bounds = scene.getBoundingClientRect();
    scene.style.setProperty('--scene-yaw', `${(event.clientX - bounds.left - bounds.width / 2) / bounds.width * 10}deg`);
    scene.style.setProperty('--scene-pitch', `${(bounds.height / 2 - event.clientY + bounds.top) / bounds.height * 8}deg`);
  });
  scene.addEventListener('pointerleave', () => {
    scene.style.removeProperty('--scene-yaw');
    scene.style.removeProperty('--scene-pitch');
  });
  show(0);
  return pause;
}

/** 将弹层放在页面内部，原路由替换页面时会移除；观察器负责停止可能仍在播放的镜头。 */
export function bindCampusExperiences(root) {
  root.addEventListener('click', event => {
    const opener = event.target.closest('[data-campus-open]');
    if (!opener || !root.contains(opener) || root.querySelector('dialog.campus-dialog')) return;
    const key = opener.dataset.campusOpen;
    const topic = topics[key];
    const dialog = document.createElement('dialog');
    dialog.className = 'campus-dialog';
    dialog.setAttribute('aria-label', topic.title);
    const mapTopic = key === 'dorm' || key === 'tour';
    const content = mapTopic ? dormContent() : key === 'books' ? bookContent() : tradeContent();
    dialog.innerHTML = `<header><div><small>${topic.note}</small><h2>${topic.title}</h2></div><button class="campus-close" type="button" aria-label="关闭专题" autofocus>×</button></header>${content}<footer>${location.hash.replace(/^#\/?/,'') === topic.route ? '' : `<button type="button" data-go="${topic.route}" class="campus-topic-cta">${topic.cta} ↗</button>`}</footer>`;
    root.append(dialog);
    const dispose = mapTopic ? bindDorm(dialog, key === 'tour' ? 'photos' : 'map') : key === 'books' ? bindBook(dialog) : bindTrade(dialog);
    const observer = new MutationObserver(() => {if (!dialog.isConnected) cleanup();});
    /** 释放定时和路由观察，正常关闭时将焦点交还原按钮。 */
    function cleanup() {
      observer.disconnect();
      dispose?.();
      dialog.remove();
      if (opener.isConnected) opener.focus({preventScroll:true});
    }
    dialog.addEventListener('close', cleanup, {once:true});
    dialog.querySelector('.campus-close').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-go]')?.addEventListener('click', () => dialog.close());
    dialog.showModal();
    observer.observe(document.querySelector('#app'), {childList:true});
  });
}
