'use strict';
// AI 助手「小转」：全站悬浮桌宠。
//
// 三件事：
//   1. 常驻在页面最上层（挂 body，不随 #app 重渲染消失），可以拖到任意位置，位置记在 localStorage；
//   2. 有动作状态（待机 / 走 / 挥袖 / 跳 / 等待 / 查看 / 失败），由 setPetState 驱动；
//   3. 点一下打开对话面板，面板贴着宠物出现，靠近边缘会翻边。
//
// 只在 config.ai 为真时挂载：线上没开 AI 就不出现，避免出现一个点了没反应的宠物。

import { $ } from '../core/dom.js';
import { state } from '../core/state.js';

const SPRITE_W = 120;          // 单帧宽（与 ai-pet.css 里的 --pet-cell-w 一致）
const SPRITE_H = 147;
const ATLAS = '/assets/ai-pet/xiaozhuan-atlas.webp';
const POS_KEY = 'hc-pet-pos';
const HINT_KEY = 'hc-pet-hinted';

// 客服在不在线。按北京时间算，与后端 support_state()、消息页 supportOnDuty() 同一口径。
// 后端只回当前状态，面板上的状态灯由前端自己算，省一次请求。
export function dutyNow(){
  const raw = String(state.config?.support_hours || '08:00–20:00').replace('—', '–').replace('-', '–');
  const [a, b] = raw.split('–').map(s => s.trim());
  const toMin = s => { const [h, m] = s.split(':').map(Number); return h * 60 + (m || 0); };
  const now = new Date();
  const cur = now.getHours() * 60 + now.getMinutes();
  return { online: cur >= toMin(a) && cur < toMin(b), hours: raw };
}

// 面板标题下面那行小字：在线/已下班 + 服务时间。
// 优先用接口返回的 support（服务端按 UTC+8 算，客户电脑时钟不准也不会矛盾），
// 没拿到就按本地时间估。
export function paintDuty(server){
  const el = $('#ai-pet-duty');
  if (!el) return;
  const local = dutyNow();
  const online = server && typeof server.online === 'boolean' ? server.online : local.online;
  const hours = (server && server.hours) || local.hours;
  el.textContent = (online ? '客服在线 · ' : '客服已下班 · ') + hours;
  el.dataset.online = String(online);
}

let petEl = null;
let drag = null;
let lastDragEnd = 0;
let stateTimer = 0;
let lifeTimer = 0;

// --- 标记 ---------------------------------------------------------------
export function aiPet(){
  return `<div class="ai-pet" id="ai-pet" data-state="idle">
  <button type="button" class="ai-pet-body" id="ai-pet-body" aria-label="AI 助手小转，可拖动；点一下提问">
    <span class="ai-pet-sprite" aria-hidden="true"></span>
    <span class="ai-pet-fallback" aria-hidden="true">转</span>
  </button>
  <div class="ai-pet-hint" id="ai-pet-hint" hidden>按住我可以拖到任意位置</div>
  <section class="ai-pet-panel" id="ai-pet-panel" hidden aria-label="AI 助手小转">
    <header class="ai-pet-head">
      <span class="ai-pet-avatar"><img src="/assets/ai-pet/xiaozhuan-avatar.png" alt=""></span>
      <div><b>小转</b><small id="ai-pet-duty">客服在线 · 08:00–20:00</small></div>
      <button type="button" class="ai-pet-close" id="ai-pet-close" aria-label="收起对话">×</button>
    </header>
    <div class="ai-pet-log" id="ai-pet-log">
      <div class="ai-pet-msg bot">我是小转，转角里的那只桌宠。发布、退款、面交、客服时间都能问我——不想问正事，聊两句也行。</div>
    </div>
    <div class="ai-pet-chips" aria-label="常见问题">
      <button type="button" data-action="ai-pet-chip" data-q="怎么发布闲置？">怎么发布</button>
      <button type="button" data-action="ai-pet-chip" data-q="怎么退款？">怎么退款</button>
      <button type="button" data-action="ai-pet-chip" data-q="客服什么时候在线？">客服时间</button>
      <button type="button" data-action="ai-pet-chip" data-q="怎么注销账号？">注销账号</button>
    </div>
    <form id="ai-pet-form" class="ai-pet-form">
      <label class="ai-pet-sr" for="ai-pet-q">输入问题</label>
      <textarea id="ai-pet-q" name="q" maxlength="300" rows="1" placeholder="问问小转，例如：怎么发布？" required></textarea>
      <button type="submit" class="ai-pet-send">发送</button>
    </form>
    <p class="ai-pet-note">回答仅供参考。问题会发送给第三方 AI 服务用于生成回答，请勿输入密码、手机号、恢复码等敏感信息。</p>
  </section>
</div>`;
}

// --- 状态 ---------------------------------------------------------------
export function setPetState(name, holdMs){
  if (!petEl) return;
  clearTimeout(stateTimer);
  petEl.dataset.state = name || 'idle';
  if (holdMs) stateTimer = setTimeout(() => { if (petEl) petEl.dataset.state = 'idle'; }, holdMs);
}

// --- 位置 ---------------------------------------------------------------
function size(){
  const el = $('#ai-pet-body');
  return { w: el?.offsetWidth || SPRITE_W, h: el?.offsetHeight || SPRITE_H };
}

function clamp(x, y){
  const { w, h } = size();
  const maxX = Math.max(4, window.innerWidth - w - 4);
  const maxY = Math.max(4, window.innerHeight - h - 4);
  return { x: Math.min(Math.max(4, x), maxX), y: Math.min(Math.max(4, y), maxY) };
}

function moveTo(x, y){
  const p = clamp(x, y);
  petEl.style.left = p.x + 'px';
  petEl.style.top = p.y + 'px';
  return p;
}

function defaultPos(){
  const { w, h } = size();
  // 手机上抬，避开底部五个入口；桌面上贴右下角。
  const bottom = window.innerWidth <= 850 ? 96 : 28;
  return { x: window.innerWidth - w - 20, y: window.innerHeight - h - bottom };
}

function savePos(){
  try{
    localStorage.setItem(POS_KEY, JSON.stringify({ x: parseInt(petEl.style.left, 10), y: parseInt(petEl.style.top, 10) }));
  }catch(_){ /* 隐私模式下写不了，位置不记忆即可 */ }
}

function restorePos(){
  let p = null;
  try{ p = JSON.parse(localStorage.getItem(POS_KEY) || 'null'); }catch(_){ p = null; }
  const ok = p && Number.isFinite(p.x) && Number.isFinite(p.y);
  return moveTo(ok ? p.x : defaultPos().x, ok ? p.y : defaultPos().y);
}

// --- 面板 ---------------------------------------------------------------
function placePanel(){
  const panel = $('#ai-pet-panel');
  const body = $('#ai-pet-body');
  if (!panel || !body || panel.hidden) return;
  const b = body.getBoundingClientRect();
  const pw = panel.offsetWidth, ph = panel.offsetHeight;
  const gap = 10, edge = 12;

  let left = b.left + b.width / 2 - pw / 2;
  left = Math.min(Math.max(edge, left), Math.max(edge, window.innerWidth - pw - edge));

  let top = b.top - ph - gap;
  if (top < edge) top = Math.min(b.bottom + gap, window.innerHeight - ph - edge);
  top = Math.max(edge, top);

  panel.style.left = left + 'px';
  panel.style.top = top + 'px';
}

export function togglePetPanel(open){
  if (!petEl) return;
  const panel = $('#ai-pet-panel');
  if (!panel) return;
  const show = open === undefined ? panel.hidden : !!open;
  panel.hidden = !show;
  petEl.classList.toggle('is-open', show);
  $('#ai-pet-hint')?.setAttribute('hidden', '');
  if (show){
    placePanel();
    setPetState('wave', 900);
    paintDuty();                       // 每次打开都刷新客服在线状态
    setTimeout(() => $('#ai-pet-q')?.focus(), 60);
  }else{
    setPetState('idle');
  }
}

// --- 拖动 ---------------------------------------------------------------
function bindDrag(body){
  body.addEventListener('pointerdown', ev => {
    if (ev.pointerType === 'mouse' && ev.button !== 0) return;
    const r = petEl.getBoundingClientRect();
    drag = { id: ev.pointerId, sx: ev.clientX, sy: ev.clientY, ox: r.left, oy: r.top, moved: false };
    petEl.classList.add('is-dragging');
    try{ body.setPointerCapture(ev.pointerId); }catch(_){ /* 老浏览器没有捕获也能靠 move 兜住 */ }
  });

  body.addEventListener('pointermove', ev => {
    if (!drag || ev.pointerId !== drag.id) return;
    const dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;   // 手抖不算拖动
    drag.moved = true;
    moveTo(drag.ox + dx, drag.oy + dy);
    // 只在真的往某一侧移动时换朝向；dx 恰好为 0 时保持当前朝向，不要无端翻面。
    if (dx > 0) setPetState('right', 0);
    else if (dx < 0) setPetState('left', 0);
    placePanel();
  });

  const end = ev => {
    if (!drag || ev.pointerId !== drag.id) return;
    const moved = drag.moved;
    drag = null;
    petEl.classList.remove('is-dragging');
    try{ body.releasePointerCapture(ev.pointerId); }catch(_){ }
    if (moved){
      lastDragEnd = performance.now();
      savePos();
      setPetState('idle');
    }
  };
  body.addEventListener('pointerup', end);
  body.addEventListener('pointercancel', end);

  // 拖动结束后浏览器仍会补一个 click，用时间戳挡掉，避免一松手就弹面板。
  body.addEventListener('click', ev => {
    if (performance.now() - lastDragEnd < 320){ ev.preventDefault(); ev.stopPropagation(); return; }
    togglePetPanel();
  });
}

// --- 待机小动作 ---------------------------------------------------------
function scheduleLife(){
  clearTimeout(lifeTimer);
  lifeTimer = setTimeout(() => {
    if (petEl && !drag && !petEl.classList.contains('is-open')){
      setPetState(Math.random() < .6 ? 'wave' : 'jump', 900);
    }
    scheduleLife();
  }, 11000 + Math.random() * 9000);
}

// --- 挂载 ---------------------------------------------------------------
export function mountPet(){
  // 登录用户才挂载：/api/ai/chat 需要登录，匿名点开会 401。
  if (petEl || !state.config?.ai || !state.me) return;
  // 旧版本把宠物写在客服页里，缓存没刷干净时页面上会出现两只。先清干净再挂一只。
  document.querySelectorAll('#ai-pet').forEach(el => el.remove());

  document.body.insertAdjacentHTML('beforeend', aiPet());
  petEl = $('#ai-pet');
  const body = $('#ai-pet-body');
  restorePos();
  bindDrag(body);
  $('#ai-pet-close')?.addEventListener('click', () => togglePetPanel(false));

  // 输入框里 Enter 直接发，Shift+Enter 换行。中文输入法拼字期间的 Enter 不能拦，
  // 否则选词会把半截拼音发出去。
  $('#ai-pet-q')?.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter' || ev.shiftKey || ev.isComposing) return;
    ev.preventDefault();
    $('#ai-pet-form')?.requestSubmit();
  });

  // 图集 334KB：不等它下载完才显形。元素本身是透明的，图解码好自然就画出来；
  // 只有真的加载失败才换成「转」字圆钮，功能不至于消失。
  const img = new Image();
  img.onload = () => petEl?.classList.add('is-ready');
  img.onerror = () => petEl?.classList.add('is-fallback');
  img.src = ATLAS;

  // 第一次来提示一次可以拖，之后不再打扰。
  try{
    if (!localStorage.getItem(HINT_KEY)){
      const hint = $('#ai-pet-hint');
      if (hint){
        setTimeout(() => { hint.hidden = false; }, 900);
        setTimeout(() => { hint.hidden = true; localStorage.setItem(HINT_KEY, '1'); }, 6000);
      }
    }
  }catch(_){ }

  scheduleLife();

  window.addEventListener('resize', () => {
    if (!petEl) return;
    restorePos();
    placePanel();
  });
}
