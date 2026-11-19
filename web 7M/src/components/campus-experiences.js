/** 校园专题交互只展示样例，通过原导航进入商品和求购业务。 */
import {campusMapSize, campusMapPoints, referenceMaps, referencePhotos} from './campus-reference.js';
import {chapterSource, chapters} from './calculus-preview.js';
export const tradePhoto = new URL('../../assets/home-mint/campus-handover.webp', import.meta.url).href;

const topics = {
  tour: {label: '校园地图导览', title: '沿着原图逛华立', note: '广州增城校区', route: 'home/living', cta: '逛宿舍生活'},
  books: {label: '翻开高数', title: '翻一页，高数继续读', note: '同济第八版上册目录 · 原创试读', route: 'home/books', cta: '逛二手教材'},
  dorm: {label: '探索宿舍地图', title: '宿舍与教学楼', note: '广州增城校区', route: 'home/living', cta: '逛宿舍生活'},
  swap: {label: '看面交演示', title: '一本书，交到下一位同学手里', note: '校园面交情景演示', route: 'forum/wants', cta: '浏览校园求购'},
};

const campusGallery = 'https://www.hualixy.edu.cn/zsb/xxgk/xyfg__xxgk/xyfg/content_11';
const campusTour = 'https://www.hualixy.edu.cn/yyxy';
const views = [
  {title:'校园航拍', photo:new URL('../../assets/home-mint/campus-official/aerial.jpg', import.meta.url).href, source:'https://www.hualixy.edu.cn/xxgk/xyfg/content_14'},
  {title:'图书馆', photo:new URL('../../assets/home-mint/campus-official/library.jpg', import.meta.url).href},
  {title:'二教', photo:new URL('../../assets/home-mint/campus-official/second.jpg', import.meta.url).href},
  {title:'五教', photo:new URL('../../assets/home-mint/campus-official/fifth.jpg', import.meta.url).href},
  ...referencePhotos,
  {title:'四教', photo:new URL('../../assets/home-mint/campus-official/fourth.jpg', import.meta.url).href},
  {title:'六教', photo:new URL('../../assets/home-mint/campus-official/sixth.jpg', import.meta.url).href},
  {title:'八号楼与十号楼', photo:new URL('../../assets/home-mint/campus-official/eighth-tenth.jpg', import.meta.url).href},
  {title:'文体楼', photo:new URL('../../assets/home-mint/campus-official/sports-hall.jpg', import.meta.url).href},
  {title:'综合楼', photo:new URL('../../assets/home-mint/campus-official/main-building.jpg', import.meta.url).href},
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

/** 将原图与同坐标热点放在同一个可缩放、可倾斜的平面。 */
function campusModel() {
  const [width, height] = campusMapSize;
  return `<div class="campus-model" data-campus-model role="region" aria-label="可滚动的校园地图" tabindex="0"><div class="campus-model-plane" data-map-plane>
    <img src="${referenceMaps[0].photo}" width="${width}" height="${height}" alt="广州华立学院广州校区校园平面图，含宿舍、华立湖、教学区和出入口">
    ${campusMapPoints.map(({name,x,y},index) => `<button type="button" class="campus-pin" data-campus-point="${index}" style="--x:${x / width * 100}%;--y:${y / height * 100}%" aria-label="地图标记：${name}"><span aria-hidden="true">${index + 1}</span></button>`).join('')}
    </div></div>`;
}

/** 求购页面与首页共享同一个面交情景。 */
export function wantExperienceBanner() {
  return `<section class="campus-want-banner" aria-label="校园面交情景" style="--trade-photo:url('${tradePhoto}')"><div><h2>同校面交，先看实物</h2><p>从约地点到验货，看看两位同学怎么交接。</p>${experienceButton('swap')}</div></section>`;
}

/** 试读保留纸页交互，并提供可直接跳转的章节目录。 */
function bookContent() {
  return `<div class="campus-book-meta"><label for="campus-book-chapter">试读目录</label><select id="campus-book-chapter" data-book-chapter>${chapters.map(({title},index) => `<option value="${index}">${index + 1}. ${title}</option>`).join('')}</select><a class="campus-source" href="${chapterSource}" target="_blank" rel="noopener noreferrer">出版社目录 ↗</a></div>
    <div class="campus-book" data-campus-book></div><div class="campus-controls"><button type="button" data-book-step="-1">上一页</button><output data-book-position aria-live="polite"></output><button type="button" data-book-step="1">翻到下一页</button></div>
    <p class="campus-book-source">参考：同济大学数学科学学院编《高等数学》第八版上册（ISBN 978-7-04-058981-8）。讲解、例题及自测为网站原创试读。</p>`;
}

/** 地图提供可点的编号和对应地点，原图与实景仍可独立查看。 */
function dormContent() {
  return `<div class="campus-view-switch" role="group" aria-label="校园展示方式"><button type="button" data-campus-mode="map">校园地图</button><button type="button" data-campus-mode="photos">校园实景</button><button type="button" data-campus-mode="reference">参考原图</button></div>
  <div data-campus-view="map">${campusModel()}
    <div class="campus-controls campus-map-controls" aria-label="操作校园地图"><button type="button" data-map-tilt aria-pressed="false">立体视角</button><button type="button" data-map-zoom="-.25" aria-label="缩小地图">−</button><button type="button" data-map-zoom=".25" aria-label="放大地图">＋</button><button type="button" data-map-reset>复位</button></div>
    <div class="campus-map-summary"><p class="campus-map-selection" data-map-selection aria-live="polite"></p><button class="campus-source" type="button" data-campus-teaching-photo hidden>查看实景 ↗</button></div>
    <div class="campus-controls campus-dorm-choices" aria-label="选择地点">${campusMapPoints.map(({label},index) => `<button type="button" data-campus-list="${index}"><span aria-hidden="true">${index + 1} · </span>${label}</button>`).join('')}</div>
    <p class="campus-map-note">点选编号或地点定位；放大后可滑动查看。底图为校园手绘参考图，现场路线以学校指引为准。</p>
  </div>
  <div data-campus-view="photos" hidden>
    <div class="campus-photo-groups" role="group" aria-label="选择照片分类">${galleryGroups.map(([id,label])=>`<button type="button" data-campus-gallery="${id}">${label}</button>`).join('')}</div>
    <figure class="campus-photo-card"><img alt="" data-campus-photo><figcaption><span data-campus-caption aria-live="polite"></span><a class="campus-source" data-campus-photo-original target="_blank" rel="noopener noreferrer">查看原图 ↗</a></figcaption></figure>
    <div class="campus-controls campus-photo-choices" aria-label="选择校内照片">${views.map(({title, group}, index) => `<button type="button" data-campus-photo-index="${index}" data-photo-group="${group || 'official'}">${title}</button>`).join('')}</div>
  </div>
  <div data-campus-view="reference" hidden><div class="campus-photo-groups" role="group" aria-label="选择参考地图">${referenceMaps.map(({title},index)=>`<button type="button" data-reference-index="${index}">${title}</button>`).join('')}</div><figure class="campus-reference-card"><img data-reference-map alt=""><figcaption><span>校园导览参考图</span><a class="campus-source" data-reference-original target="_blank" rel="noopener noreferrer">查看原图 ↗</a></figcaption></figure></div>
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
  const picker = dialog.querySelector('[data-book-chapter]');
  let current = 0;
  /** 按章构建公式、例题推导以及可独立展开的答案。 */
  function pageMarkup(index, active = true) {
    const chapter = chapters[index];
    return `<article class="campus-book-paper"><small>上册 · 第 ${index + 1} 章</small><h3>${chapter.title}</h3><p>${chapter.intro}</p>
      <ul class="campus-book-formulas" aria-label="本章公式">${chapter.formulas.map(formula => `<li>${formula}</li>`).join('')}</ul>
      <section class="campus-book-example"><h4>例题 · ${chapter.example}</h4><ol>${chapter.steps.map(step => `<li>${step}</li>`).join('')}</ol></section>
      <p class="campus-book-exercise"><strong>自测</strong> ${chapter.exercise}</p>
      ${active ? `<details><summary>展开答案</summary><p>${chapter.answer}</p></details>` : ''}</article>`;
  }
  /** 背景页先更新，旧纸叶绕书脊翻过，动画结束后移除。 */
  function show(index, turn = false) {
    if (index < 0 || index >= chapters.length) return;
    const oldPage = current;
    current = index;
    book.innerHTML = pageMarkup(index);
    if (turn && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const leaf = document.createElement('div');
      leaf.className = 'campus-leaf';
      leaf.setAttribute('aria-hidden', 'true');
      leaf.innerHTML = pageMarkup(oldPage, false);
      book.append(leaf);
      const direction = index > oldPage ? 1 : -1;
      leaf.animate([{transform:'rotateY(0deg)'},{transform:`rotateY(${-178 * direction}deg)`}], {duration:550, easing:'cubic-bezier(.34,.06,.22,1)'}).finished.then(() => leaf.remove(), () => leaf.remove());
    }
    picker.value = String(index);
    position.textContent = `${index + 1} / ${chapters.length}`;
    controls[0].disabled = index === 0;
    controls[1].disabled = index === chapters.length - 1;
  }
  picker.addEventListener('change', () => show(Number(picker.value), true));
  controls.forEach(button => button.addEventListener('click', () => show(current + Number(button.dataset.bookStep), true)));
  dialog.addEventListener('keydown', event => {
    if (event.target === picker || !['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    show(current + (event.key === 'ArrowRight' ? 1 : -1), true);
  });
  show(0);
}

/** 地图、地点列表和实景照片共用原图锚点。 */
function bindDorm(dialog) {
  const map = dialog.querySelector('[data-campus-model]');
  const plane = dialog.querySelector('[data-map-plane]');
  const tilt = dialog.querySelector('[data-map-tilt]');
  const pins = [...map.querySelectorAll('[data-campus-point]')];
  const choices = [...dialog.querySelectorAll('[data-campus-list]')];
  const selection = dialog.querySelector('[data-map-selection]');
  const teachingPhoto = dialog.querySelector('[data-campus-teaching-photo]');
  const referenceImage = dialog.querySelector('[data-reference-map]');
  const referenceOriginal = dialog.querySelector('[data-reference-original]');
  const referenceButtons = [...dialog.querySelectorAll('[data-reference-index]')];
  const modeButtons = [...dialog.querySelectorAll('[data-campus-mode]')];
  const photoButtons = [...dialog.querySelectorAll('[data-campus-photo-index]')];
  const groupButtons = [...dialog.querySelectorAll('[data-campus-gallery]')];
  const photo = dialog.querySelector('[data-campus-photo]');
  const photoOriginal = dialog.querySelector('[data-campus-photo-original]');
  const caption = dialog.querySelector('[data-campus-caption]');
  let zoom = 1;
  let mode = 'map';
  let photoIndex = 0;
  let group = 'official';
  let selected = -1;
  /** 放大时把所选锚点移入视野，不滚动弹窗或背景页面。 */
  function centerSelected() {
    if (selected < 0 || zoom === 1) return;
    const pin = pins[selected].getBoundingClientRect();
    const frame = map.getBoundingClientRect();
    map.scrollLeft += pin.left + pin.width / 2 - frame.left - map.clientWidth / 2;
    map.scrollTop += pin.top + pin.height / 2 - frame.top - map.clientHeight / 2;
  }
  /** 两处控件同步选中态，并仅为有实景的地点提供照片入口。 */
  function select(index, center = true) {
    selected = index;
    const point = campusMapPoints[index];
    [pins, choices].forEach(items => items.forEach((button,i) => button.setAttribute('aria-pressed', String(i === index))));
    selection.textContent = `${index + 1} · ${point.name}`;
    teachingPhoto.hidden = !point.photo;
    if (center) centerSelected();
  }
  /** 参考图保持完整画幅，分别查看手绘地图和带图例的版式。 */
  function showReference(index) {
    const view = referenceMaps[index];
    referenceImage.src = view.photo;
    referenceImage.alt = `${view.title}，广州华立学院校园导览参考图`;
    referenceOriginal.href = view.photo;
    referenceButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
  }
  /** 切换照片时同步清晰标题，让来源始终可见。 */
  function showPhoto(index) {
    photoIndex = index;
    const view = views[photoIndex];
    photo.src = view.photo;
    photo.alt = view.group ? view.title : `广州华立学院广州校区${view.title}实景`;
    photoOriginal.href = view.photo;
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
  const zoomButtons = [...dialog.querySelectorAll('[data-map-zoom]')];
  /** 缩放只改变地图滚动区的内容尺寸，原图与标记一起缩放。 */
  function scale(next) {
    zoom = Math.max(1, Math.min(2.5, next));
    plane.style.width = `${zoom * 100}%`;
    zoomButtons[0].disabled = zoom === 1;
    zoomButtons[1].disabled = zoom === 2.5;
    if (zoom === 1) map.scrollTo(0, 0);
    else centerSelected();
  }
  /** 倾斜完整底图作为立体展示，平面模式可随时复位。 */
  function setTilt(enabled) {
    tilt.setAttribute('aria-pressed', String(enabled));
    map.classList.toggle('is-tilted', enabled);
    centerSelected();
  }
  modeButtons.forEach(button => button.addEventListener('click', () => showMode(button.dataset.campusMode)));
  groupButtons.forEach(button => button.addEventListener('click', () => showGallery(button.dataset.campusGallery)));
  referenceButtons.forEach((button,index) => button.addEventListener('click', () => showReference(index)));
  teachingPhoto.addEventListener('click', () => {
    const index = views.findIndex(view => view.title === campusMapPoints[selected]?.photo);
    if (index < 0) return;
    showMode('photos');
    showGallery(views[index].group || 'official');
    showPhoto(index);
    photoButtons[index].focus({preventScroll:true});
  });
  photoButtons.forEach((button,i) => button.addEventListener('click', () => showPhoto(i)));
  dialog.addEventListener('keydown', event => {
    if (mode !== 'photos' || !['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const indexes = photoButtons.filter(button => !button.hidden).map(button => Number(button.dataset.campusPhotoIndex));
    const step = event.key === 'ArrowRight' ? 1 : -1;
    showPhoto(indexes[(indexes.indexOf(photoIndex) + step + indexes.length) % indexes.length]);
  });
  pins.forEach((button,index) => button.addEventListener('click', () => select(index, false)));
  choices.forEach((button,index) => button.addEventListener('click', () => select(index)));
  zoomButtons.forEach(button => button.addEventListener('click', () => scale(zoom + Number(button.dataset.mapZoom))));
  tilt.addEventListener('click', () => setTilt(tilt.getAttribute('aria-pressed') !== 'true'));
  dialog.querySelector('[data-map-reset]').addEventListener('click', () => { scale(1); setTilt(false); });
  scale(1);
  select(0, false);
  showMode('map');
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
    const dispose = mapTopic ? bindDorm(dialog) : key === 'books' ? bindBook(dialog) : bindTrade(dialog);
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
