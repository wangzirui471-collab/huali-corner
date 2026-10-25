'use strict';
// 桌宠皮肤表 + 帧播放器。
//
// 一张图集就是一只宠物：按「行 = 动作、列 = 帧」摆放，每行动作帧数可以不同。
// 之前小转的帧序列写死在 ai-pet.css 的 @keyframes 里（background-position 全用
// 固定像素），换一只宠物就得再抄 9 条关键帧。改成数据驱动：皮肤只声明
// 格子尺寸 + 每个动作在哪一行、几帧、多快，播放交给 playAct。
//
// 自定义桌宠走另一条路：用户传一张图，只有一帧，配一个呼吸动效。

import { api } from '../core/http.js';
import { state } from '../core/state.js';

export const SKINS = {
  // 女角色。图集沿用旧文件名（xiaozhuan-atlas），换名字只改这里，不动物理文件，
  // 免得 CDN 上多一份重复的大图。
  daqiao: {
    id: 'daqiao',
    name: '大乔',
    note: '女角色 · 转角原生',
    avatar: '/assets/ai-pet/xiaozhuan-avatar.png',
    atlas: '/assets/ai-pet/xiaozhuan-atlas.webp',
    cell: [120, 147],
    cols: 8,
    rows: 9,
    acts: {
      idle: { row: 0, n: 6, ms: 220 },
      move: { row: 1, n: 8, ms: 90 },          // 向右
      moveLeft: { row: 2, n: 8, ms: 90 },      // 向左（这段图集本来就有独立的一行）
      greet: { row: 3, n: 4, ms: 180, once: true },
      lie: { row: 6, n: 6, ms: 180 },
      look: { row: 7, n: 6, ms: 170 },
      fail: { row: 5, n: 8, ms: 140, once: true },
      run: { row: 8, n: 6, ms: 130 },
    },
  },
  // 橙团子。目前只有一张成图，没有动作表，靠呼吸动效显得是活的。
  // 以后作者给了分镜表，把 static 去掉、补 acts 即可，调用方不用改。
  zhuan: {
    id: 'zhuan',
    name: '小转',
    note: '橙团子 · 一只在等人的小兽',
    avatar: '/assets/ai-pet/xiaozhuan-pet.png',
    atlas: '/assets/ai-pet/xiaozhuan-pet.png',
    cell: [480, 464],
    cols: 1,
    rows: 1,
    static: true,
    acts: { idle: { row: 0, n: 1, ms: 0 } },
  },
  // 褐绒毛团。11 行动作表，按原作者的分镜摆位：
  //   0 捂鼻子摇手（移动）、9 抬头低头看（点一下）、5 摊平躺下（打字）、
  //   4 站着小幅晃（待机）、6 举手、7 垮掉、10 左右张望
  xiaomao: {
    id: 'xiaomao',
    name: '小毛',
    note: '褐绒毛团 · 会当场躺平',
    avatar: '/assets/ai-pet/xiaomao-avatar.png',
    atlas: '/assets/ai-pet/xiaomao-atlas.webp',
    cell: [171, 171],
    cols: 8,
    rows: 11,
    acts: {
      idle: { row: 4, n: 5, ms: 260 },
      move: { row: 0, n: 7, ms: 110 },
      look: { row: 9, n: 8, ms: 150 },
      lie: { row: 5, n: 8, ms: 180 },
      greet: { row: 6, n: 6, ms: 130, once: true },
      fail: { row: 7, n: 6, ms: 150, once: true },
      run: { row: 10, n: 8, ms: 120 },
    },
  },
};

// 还没画好形象的角色先占着位置：设置页里显示成灰色卡片，点了给一句提示。
// 有了素材就在 SKINS 里加一条同 id 的记录，这里自然不再出现。
export const PENDING_SKINS = [];

export const SKIN_LIST = [SKINS.zhuan, SKINS.daqiao, SKINS.xiaomao];
export const DEFAULT_SKIN = 'daqiao';

const SKIN_KEY = 'hc-pet-skin';
const CUSTOM_KEY = 'hc-pet-custom';
const SIZE_KEY = 'hc-pet-scale';
const LIFE_KEY = 'hc-pet-life';
const HIDE_KEY = 'hc-pet-hidden';
const NOTICE_KEY = 'hc-pet-notice';

function read(key, fallback){
  try{
    const v = localStorage.getItem(key);
    return v === null ? fallback : v;
  }catch(_){ return fallback; }
}

function write(key, val){
  try{ localStorage.setItem(key, val); }catch(_){ /* 隐私模式写不了，设置只是不记住 */ }
}

// --- 自定义桌宠：一张图 + 呼吸动效 ------------------------------------
// 存在 localStorage 里（压缩到 512 长边，约 60–120KB）。用 IndexedDB 更宽松，
// 但这是一次性小图，为它引入一套异步存储不值得。

export function customSkin(){
  let raw = '';
  try{ raw = localStorage.getItem(CUSTOM_KEY) || ''; }catch(_){ return null; }
  if (!raw) return null;
  try{
    const d = JSON.parse(raw);
    if (!d || !d.atlas) return null;
    return {
      id: 'custom',
      name: String(d.name || '我的桌宠').slice(0, 12),
      custom: true,
      // 换设备时本机没有 dataURL，用账号同步下来的 /media/pet_xxx
      atlas: d.atlas || d.remote || '',
      avatar: d.atlas || d.remote || '',
      remote: d.remote || '',
      cell: [Number(d.w) || 200, Number(d.h) || 200],
      cols: 1,
      rows: 1,
      acts: { idle: { row: 0, n: 1, ms: 0 } },
    };
  }catch(_){ return null; }
}

export function saveCustomSkin(dataUrl, w, h, name){
  write(CUSTOM_KEY, JSON.stringify({ atlas: dataUrl, w, h, name: name || '自定义' }));
  setSkinId('custom');
}

export function clearCustomSkin(){
  try{ localStorage.removeItem(CUSTOM_KEY); }catch(_){ }
  if (getSkinId() === 'custom') setSkinId(DEFAULT_SKIN);
}

// --- 偏好 -------------------------------------------------------------

export function getSkinId(){
  const id = read(SKIN_KEY, DEFAULT_SKIN);
  if (id === 'custom') return customSkin() ? 'custom' : DEFAULT_SKIN;
  return SKINS[id] ? id : DEFAULT_SKIN;
}

export function setSkinId(id){
  write(SKIN_KEY, String(id || DEFAULT_SKIN));
}

export function currentSkin(){
  const id = getSkinId();
  return id === 'custom' ? customSkin() : SKINS[id];
}

export function getScale(){
  const v = Number(read(SIZE_KEY, '1'));
  return Number.isFinite(v) ? Math.min(1.6, Math.max(.6, v)) : 1;
}

export function setScale(v){ write(SIZE_KEY, String(Math.min(1.6, Math.max(.6, Number(v) || 1)))); }

export function getLife(){ return read(LIFE_KEY, '1') !== '0'; }
export function setLife(on){ write(LIFE_KEY, on ? '1' : '0'); }

export function getHidden(){ return read(HIDE_KEY, '0') === '1'; }
export function setHidden(on){ write(HIDE_KEY, on ? '1' : '0'); }

export function hasReadNotice(){ return read(NOTICE_KEY, '0') === '1'; }
export function markNoticeRead(){ write(NOTICE_KEY, '1'); }

export function forgetPosition(){
  try{ localStorage.removeItem('hc-pet-pos'); }catch(_){ }
}

// --- 帧播放 -----------------------------------------------------------
// 每只宠物的帧数不同，用 CSS @keyframes 写死就意味着一只宠物一套关键帧。
// 这里用定时器改 background-position：一个元素、8~12fps，开销可以忽略。

const REDUCE = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
let frameTimer = 0;

export function stopFrames(){
  clearInterval(frameTimer);
  frameTimer = 0;
}

export function applySkinFrame(sprite, skin, actName){
  if (!sprite || !skin) return;
  const act = skin.acts[actName] || skin.acts.idle;
  const [cw, ch] = skin.cell;
  const paint = i => {
    sprite.style.backgroundPosition = `${-i * cw}px ${-act.row * ch}px`;
  };
  stopFrames();
  paint(0);
  const n = Math.max(1, act.n || 1);
  const ms = Math.max(60, act.ms || 160);
  if (n === 1 || REDUCE) return;
  let i = 0;
  frameTimer = setInterval(() => {
    i = (i + 1) % n;
    paint(i);
  }, ms);
}

// 把皮肤的静态信息写进 CSS 变量：图集地址、格子尺寸、整张图尺寸、色调。
// 翻转不在这里做——它随动作变化，由 setPetState 切 is-flip。
export function applySkinVars(el, skin, userScale){
  if (!el || !skin) return;
  const [cw, ch] = skin.cell;
  const s = (userScale || 1) * (100 / ch);       // 显示高度固定 100px 起步
  el.style.setProperty('--pet-cell-w', cw + 'px');
  el.style.setProperty('--pet-cell-h', ch + 'px');
  el.style.setProperty('--pet-atlas-w', (cw * (skin.cols || 1)) + 'px');
  el.style.setProperty('--pet-atlas-h', (ch * (skin.rows || 1)) + 'px');
  el.style.setProperty('--pet-s', s.toFixed(4));
  el.style.setProperty('--pet-atlas', `url("${skin.atlas}")`);
  el.style.setProperty('--pet-tint', skin.tint || 'none');
  el.dataset.skin = skin.id;
  el.classList.toggle('is-custom', !!skin.custom);
  el.classList.toggle('is-static', !!skin.static || !!skin.custom);
  applySkinFrame(el.querySelector('.ai-pet-sprite'), skin, 'idle');
}

// 状态名 → 动作名。桌宠的状态来自各处调用（拖动、点开面板、等接口、出错），
// 但每只宠物的动作表不一样：小毛只有「捂鼻子摇手」一段能表达移动，
// 大乔却分左右两段。这层映射放在皮肤系统里，调用方只管说自己在干什么。
const STATE_TO_ACT = {
  right: 'move',
  left: 'moveLeft',
  run: 'move',
  review: 'lie',     // 等接口回来：躺下
  waiting: 'lie',
  typing: 'lie',     // 用户在打字：也躺下
  wave: 'greet',
  jump: 'greet',
  point: 'look',     // 点一下桌宠：抬头看看你
};

export function resolveAct(skin, state){
  if (!skin || !skin.acts) return { act: 'idle', flip: false };
  const want = STATE_TO_ACT[state] || state;
  if (skin.acts[want]) return { act: want, flip: !!skin.acts[want].flip };
  // 图集里没有单独的「向左」，就把「向右」那段翻过来用。
  if (want === 'moveLeft' && skin.acts.move) return { act: 'move', flip: true };
  if (want === 'move' && skin.acts.moveLeft) return { act: 'moveLeft', flip: true };
  return { act: skin.acts.idle ? 'idle' : 'idle', flip: false };
}

// --- 账号同步 ---------------------------------------------------------
// localStorage 仍是第一落点：没登录、断网、本地纯开都能用。
// 服务端只是让「换设备之后形象还在」成立，任何一步失败都静默降级——
// 同步失败不该挡住用户换皮肤。

let pushTimer = 0;
let pulling = false;

function prefsPayload(){
  const c = customSkin();
  return {
    skin: getSkinId(),
    scale: getScale(),
    hidden: getHidden(),
    life: getLife(),
    custom_url: (c && c.remote) || '',
    custom_w: c ? c.cell[0] : 0,
    custom_h: c ? c.cell[1] : 0,
  };
}

function writeCustom(raw){
  try{ localStorage.setItem(CUSTOM_KEY, JSON.stringify(raw)); }catch(_){ }
}

function applyRemote(d){
  if (!d || !d.synced) return false;
  // 远端有自定义图而本机没有：把地址落到本地记录里，尺寸也一起带回来
  if (d.custom_url){
    let cur = null;
    try{ cur = JSON.parse(localStorage.getItem(CUSTOM_KEY) || 'null'); }catch(_){ cur = null; }
    if (!cur || !cur.atlas){
      writeCustom({
        atlas: '', remote: d.custom_url,
        w: d.custom_w || 220, h: d.custom_h || 220,
        name: '我的桌宠',
      });
    }else if (cur.remote !== d.custom_url){
      cur.remote = d.custom_url;
      writeCustom(cur);
    }
  }
  if (d.skin){
    // 远端选了自定义但本机确实没有那张图，退回默认，别留一个加载不出来的桌宠
    const want = d.skin === 'custom' && !customSkin() ? DEFAULT_SKIN : d.skin;
    if (SKINS[want] || want === 'custom') setSkinId(want);
  }
  if (Number.isFinite(d.scale)) setScale(d.scale);
  setHidden(!!d.hidden);
  setLife(!!d.life);
  return true;
}

/** 登录后拉一次。服务端没有记录时，把这台设备的设置反推上去。 */
export async function pullPetPrefs(){
  if (pulling || !state.token) return false;
  pulling = true;
  try{
    const d = await api('/pet/prefs', undefined, { global: true });
    if (d && d.synced) return applyRemote(d);
    schedulePushPetPrefs(0);
    return false;
  }catch(_){
    return false;   // 老后端没有这个接口，或者断网：当作纯本地模式
  }finally{
    pulling = false;
  }
}

/** 本地改动后节流推送：拖滑块会连着触发，别每一下都打一次接口。 */
export function schedulePushPetPrefs(delay = 900){
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    if (!state.token) return;
    api('/pet/prefs/save', prefsPayload(), { global: true }).catch(() => {});
  }, Math.max(0, delay));
}

/** 把自定义形象上传到 R2，成功后把远端地址记在本地并推一次偏好。 */
export async function uploadCustomSkin(dataUrl){
  try{
    const d = await api('/pet/avatar', { data: dataUrl }, { global: true });
    if (!d || !d.url) return '';
    let cur = null;
    try{ cur = JSON.parse(localStorage.getItem(CUSTOM_KEY) || 'null'); }catch(_){ cur = null; }
    if (cur){ cur.remote = d.url; writeCustom(cur); }
    schedulePushPetPrefs(0);
    return d.url;
  }catch(_){
    return '';      // 传不上去就只留本地，下次换设备再传
  }
}
