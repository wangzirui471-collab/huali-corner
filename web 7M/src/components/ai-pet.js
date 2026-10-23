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
import { isOwner } from '../core/roles.js';

const SPRITE_W = 120;          // 单帧宽（与 ai-pet.css 里的 --pet-cell-w 一致）
const SPRITE_H = 147;
const ATLAS = '/assets/ai-pet/xiaozhuan-atlas.webp';
const POS_KEY = 'hc-pet-pos';
const SIZE_KEY = 'hc-pet-panel-size';
const HINT_KEY = 'hc-pet-hinted';
const MIN_PANEL_W = 300;       // 再窄按钮和输入框就挤成一条了
const MIN_PANEL_H = 320;
// 用户选的面板尺寸。和「夹到当前视口后的显示尺寸」是两回事：窗口临时变小
// 只该夹显示，不该把用户选的尺寸改掉，否则窗口放大后恢复不回去。
let panelSize = null;

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
// 初始值不能是 0：页面刚加载时 performance.now() 还不到 320ms，
// 「点一下开面板」会被当成拖动结束的补发 click 吞掉。
let lastDragEnd = -1e9;
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
    <header class="ai-pet-head" id="ai-pet-head">
      <span class="ai-pet-avatar"><img src="/assets/ai-pet/xiaozhuan-avatar.png" alt=""></span>
      <div><b>小转</b><small id="ai-pet-duty">客服在线 · 08:00–20:00</small></div>
      <button type="button" class="ai-pet-max" id="ai-pet-max" aria-label="放大对话窗口" title="放大 / 还原（双击标题也可以）">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 2H2v4M10 2h4v4M6 14H2v-4M10 14h4v-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
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
    ${isOwner(state.me) ? `<div class="ai-pet-mode" aria-label="对话模式">
      <button type="button" data-action="ai-pet-mode" data-mode="chat" class="active">客服问答</button>
      <button type="button" data-action="ai-pet-mode" data-mode="office">办公</button>
      <button type="button" data-action="ai-pet-mode" data-mode="work">工作</button>
    </div>
    <div class="ai-pet-chips ai-pet-office" id="ai-pet-office-chips" aria-label="所有者办公" hidden>
      <button type="button" data-action="ai-office" data-q="平台数据概览">数据概览</button>
      <button type="button" data-action="ai-office" data-q="把所有用户列出来">用户列表</button>
      <button type="button" data-action="ai-office" data-q="最近 10 笔订单">最近订单</button>
      <button type="button" data-action="ai-office" data-q="待处理工单">待处理工单</button>
      <button type="button" data-action="ai-office-tickets">工单办公</button>
      <button type="button" data-action="ai-office" data-mode="draft" data-q="写一条面向同学的客服公告，说明本周六晚系统维护、期间下单可能延迟。">写公告</button>
      <button type="button" data-action="ai-office-gen" data-q="宿舍好物">生成演示商品</button>
    </div>
    <div class="ai-pet-chips ai-pet-work" id="ai-pet-work-chips" aria-label="工作模式" hidden>
      <button type="button" data-action="ai-work" data-q="平台概览">平台概览</button>
      <button type="button" data-action="ai-work" data-q="待处理工单">待处理工单</button>
      <button type="button" data-action="ai-work" data-q="查用户">查用户</button>
      <button type="button" data-action="ai-work" data-q="查订单">查订单</button>
      <button type="button" data-action="ai-work" data-q="查商品">查商品</button>
      <button type="button" data-action="ai-work" data-q="看审计">看审计</button>
      <button type="button" data-action="ai-work" data-q="最近 7 天趋势">趋势</button>
      <button type="button" data-action="ai-work" data-q="查会话">会话</button>
      <button type="button" data-action="ai-work" data-q="内容治理">内容治理</button>
      <button type="button" data-action="ai-work" data-q="低信誉用户">信誉</button>
      <button type="button" data-action="ai-work" data-q="最近议价">议价</button>
      <button type="button" data-action="ai-work" data-q="社区内容">社区</button>
      <button type="button" data-action="ai-work" data-q="资金账本">账本</button>
      <button type="button" data-action="ai-work" data-q="卖家排行">卖家</button>
    </div>` : ''}
    <form id="ai-pet-form" class="ai-pet-form">
      <label class="ai-pet-sr" for="ai-pet-q">输入问题</label>
      <textarea id="ai-pet-q" name="q" maxlength="300" rows="1" placeholder="问问小转，例如：怎么发布？" required></textarea>
      <button type="submit" class="ai-pet-send">发送</button>
    </form>
    <p class="ai-pet-note">${state.config?.ai_local
      ? '回答仅供参考。模型跑在本机，问题不会离开这台电脑；仍请不要输入密码、恢复码等账号凭据。'
      : '回答仅供参考。问题会发送给第三方 AI 服务用于生成回答，请勿输入密码、手机号、恢复码等敏感信息。'}</p>
    <span class="ai-pet-rs" data-dir="n"></span>
    <span class="ai-pet-rs" data-dir="s"></span>
    <span class="ai-pet-rs" data-dir="w"></span>
    <span class="ai-pet-rs" data-dir="e"></span>
    <span class="ai-pet-rs" data-dir="nw"></span>
    <span class="ai-pet-rs" data-dir="ne"></span>
    <span class="ai-pet-rs" data-dir="sw"></span>
    <span class="ai-pet-rs" data-dir="se"></span>
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

// 「回到顶部」按钮的区域。宠物默认位在右下角，正好压住它
// （按钮 z-index 25 < 宠物 60，fixed 定位还跟着滚动走），真实用户也点不到，
// 之前只有 smoke 抓到了。默认位先避开这块；用户手动拖到哪里都不干预。
function backTopZone(){
  const el = document.querySelector('.home-back-top');
  if (!el) return null;
  const cs = getComputedStyle(el);
  if (cs.position !== 'fixed') return null;
  // hidden 时元素 display:none，取不到布局盒，但 computed value 仍按 CSS 算得出来，
  // 按钮一滚动显现就是这块区域，所以照常读。
  const w = parseFloat(cs.width) || 46, h = parseFloat(cs.height) || 58;
  const right = parseFloat(cs.right) || 16, bottom = parseFloat(cs.bottom) || 42;
  return { left: window.innerWidth - right - w, right: window.innerWidth - right,
           top: window.innerHeight - bottom - h, bottom: window.innerHeight - bottom };
}

function defaultPos(){
  const { w, h } = size();
  // 手机上抬，避开底部五个入口；桌面上贴右下角。
  const bottom = window.innerWidth <= 850 ? 96 : 28;
  let x = window.innerWidth - w - 20;
  let y = window.innerHeight - h - bottom;
  const zone = backTopZone();
  if (zone){
    const hit = x + w > zone.left && x < zone.right && y + h > zone.top && y < zone.bottom;
    if (hit){
      if (window.innerWidth <= 850) x = Math.max(4, zone.left - w - 10);  // 手机：挪到按钮左边，继续贴底
      else y = Math.max(4, zone.top - h - 10);                            // 桌面：跳到按钮上方
    }
  }
  return { x, y };
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
// 面板高度会随消息变长：不重新夹回视口的话，底部（输入框、隐私提示）会被
// 推到屏幕外，overflow:hidden 直接切掉——这就是「底部被裁」的根因。
function placePanel(){
  const panel = $('#ai-pet-panel');
  const body = $('#ai-pet-body');
  if (!panel || !body || panel.hidden || panel.classList.contains('is-max')) return;
  const b = body.getBoundingClientRect();
  const pw = panel.offsetWidth, ph = panel.offsetHeight;
  const gap = 10, edge = 12;

  let left = b.left + b.width / 2 - pw / 2;
  left = Math.min(Math.max(edge, left), Math.max(edge, window.innerWidth - pw - edge));

  // 优先放在宠物上方；放不下翻到下方；再放不下就夹在视口内（整块必须可见）。
  let top = b.top - ph - gap;
  if (top < edge) top = b.bottom + gap;
  top = Math.min(Math.max(edge, top), Math.max(edge, window.innerHeight - ph - edge));

  panel.style.left = left + 'px';
  panel.style.top = top + 'px';
}

// 面板最小高度不能拍脑袋：头 + 快捷问 + 模式 + 输入框 + 隐私提示都是固定行，
// 加上消息区的下限，才是「不裁掉底部」的真实下限。所有者模式多了办公那一行。
function panelContentMinH(){
  const panel = $('#ai-pet-panel');
  if (!panel) return MIN_PANEL_H;
  let fixed = 2;   // 上下边框
  for (const el of panel.children){
    if (el.classList.contains('ai-pet-rs') || el.classList.contains('ai-pet-log')) continue;
    fixed += el.offsetHeight;
  }
  return Math.max(MIN_PANEL_H, fixed + 96);   // 96 = .ai-pet-log 的 min-height
}

/** 按当前视口约束显示宽度，保留用户原始尺寸。 */
function clampPanelW(w){
  const maxW = Math.max(240, window.innerWidth - 24);
  return Math.min(Math.max(Math.min(MIN_PANEL_W, maxW), w), maxW);
}

// 尺寸上限按当前视口算，窗口缩小后旧尺寸要收回来。
function clampPanelSize(w, h){
  const maxH = Math.max(280, window.innerHeight - 24);
  const minH = Math.min(panelContentMinH(), maxH);
  return {
    w: clampPanelW(w),
    h: Math.min(Math.max(minH, h), maxH),
  };
}

function applyPanelSize(w, h){
  const panel = $('#ai-pet-panel');
  if (!panel) return;
  panelSize = { w: w, h: h };   // 记用户选的尺寸；夹到视口内只影响显示
  // 先把宽度落下再量高度下限：快捷问行会随宽度换行，内容下限是跟着宽度变的。
  // 不先落宽度，就会拿旧宽度的下限去卡新宽度——刷新后尺寸和拖出来的对不上。
  panel.style.width = clampPanelW(w) + 'px';
  const s = clampPanelSize(w, h);
  panel.style.width = s.w + 'px';
  panel.style.height = s.h + 'px';
  // 拖过尺寸后高度由 JS 统一管；继续留着 max-height 会让实际高度和记录值不一致。
  panel.style.maxHeight = 'none';
}

// 存用户选的尺寸，不是当前显示尺寸：窗口临时变小会把面板夹小，
// 若不区分，夹出来的小尺寸会覆盖原设置，窗口放大后就恢复不回去了。
function savePanelSize(){
  const panel = $('#ai-pet-panel');
  if (!panel || panel.classList.contains('is-max')) return;
  const s = panelSize || { w: panel.offsetWidth, h: panel.offsetHeight };
  try{ localStorage.setItem(SIZE_KEY, JSON.stringify(s)); }catch(_){ }
}

function restorePanelSize(){
  let s = null;
  try{ s = JSON.parse(localStorage.getItem(SIZE_KEY) || 'null'); }catch(_){ s = null; }
  if (s && Number.isFinite(s.w) && Number.isFinite(s.h)) applyPanelSize(s.w, s.h);
}

function setPanelMax(on){
  const panel = $('#ai-pet-panel');
  if (!panel) return;
  const isMax = panel.classList.contains('is-max');
  if (on === isMax) return;
  const btn = $('#ai-pet-max');
  if (on){
    panel.dataset.prev = JSON.stringify(panelSize || { w: panel.offsetWidth, h: panel.offsetHeight });
    panel.style.width = '';
    panel.style.height = '';
    panel.style.maxHeight = '';
    panel.style.left = '';
    panel.style.top = '';
    panel.classList.add('is-max');
    if (btn){ btn.setAttribute('aria-label', '还原对话窗口'); btn.classList.add('is-max'); }
  }else{
    panel.classList.remove('is-max');
    let prev = null;
    try{ prev = JSON.parse(panel.dataset.prev || 'null'); }catch(_){ prev = null; }
    if (prev && Number.isFinite(prev.w) && Number.isFinite(prev.h)) applyPanelSize(prev.w, prev.h);
    else { panel.style.width = ''; panel.style.height = ''; panel.style.maxHeight = ''; }
    if (btn){ btn.setAttribute('aria-label', '放大对话窗口'); btn.classList.remove('is-max'); }
    placePanel();
  }
}

// 八个方向的拖拽手柄：改宽高，拖西/北边时同时挪左上角，对边保持不动。
function bindPanelResize(panel){
  panel.querySelectorAll('.ai-pet-rs').forEach(handle => {
    handle.addEventListener('pointerdown', ev => {
      if (panel.classList.contains('is-max')) return;
      if (ev.pointerType === 'mouse' && ev.button !== 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      const r = panel.getBoundingClientRect();
      const dir = handle.dataset.dir || 'se';
      const st = { id: ev.pointerId, sx: ev.clientX, sy: ev.clientY, w: r.width, h: r.height, left: r.left, top: r.top, right: r.right, bottom: r.bottom };
      panel.classList.add('is-resizing');

      const move = e => {
        if (e.pointerId !== st.id) return;
        const dx = e.clientX - st.sx, dy = e.clientY - st.sy;
        let w = st.w, h = st.h;
        if (dir.includes('e')) w = st.w + dx;
        if (dir.includes('s')) h = st.h + dy;
        if (dir.includes('w')) w = st.w - dx;
        if (dir.includes('n')) h = st.h - dy;
        panelSize = { w: w, h: h };   // 记用户拖到的目标尺寸，夹到视口内只影响显示
        panel.style.width = clampPanelW(w) + 'px';   // 先落宽度，内容下限才按新宽度算
        const c = clampPanelSize(w, h);
        const edge = 12;
        let left = dir.includes('w') ? st.right - c.w : st.left;
        let top = dir.includes('n') ? st.bottom - c.h : st.top;
        left = Math.min(Math.max(edge, left), Math.max(edge, window.innerWidth - c.w - edge));
        top = Math.min(Math.max(edge, top), Math.max(edge, window.innerHeight - c.h - edge));
        panel.style.width = c.w + 'px';
        panel.style.height = c.h + 'px';
        panel.style.maxHeight = 'none';
        panel.style.left = left + 'px';
        panel.style.top = top + 'px';
      };
      const end = e => {
        if (e.pointerId !== st.id) return;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', end);
        window.removeEventListener('pointercancel', end);
        panel.classList.remove('is-resizing');
        savePanelSize();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', end);
      window.addEventListener('pointercancel', end);
    });
  });
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
    if (!panel.classList.contains('is-max')) restorePanelSize();   // 上次拖过的尺寸接着用
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
  bindPanelResize($('#ai-pet-panel'));
  $('#ai-pet-close')?.addEventListener('click', () => togglePetPanel(false));

  // 放大 / 还原：标题栏右上角的按钮，或双击标题栏空白处。
  $('#ai-pet-max')?.addEventListener('click', () => {
    const panel = $('#ai-pet-panel');
    setPanelMax(!panel?.classList.contains('is-max'));
  });
  $('#ai-pet-head')?.addEventListener('dblclick', ev => {
    if (ev.target.closest('button')) return;
    const panel = $('#ai-pet-panel');
    setPanelMax(!panel?.classList.contains('is-max'));
  });

  // 消息变长会把面板撑高；一旦超出视口就重新贴回宠物旁边，避免底部被切。
  if ('ResizeObserver' in window){
    const panel = $('#ai-pet-panel');
    new ResizeObserver(() => {
      if (!panel || panel.hidden || panel.classList.contains('is-max') || panel.classList.contains('is-resizing')) return;
      const r = panel.getBoundingClientRect();
      if (r.bottom > window.innerHeight - 11 || r.top < 11 || r.right > window.innerWidth - 11 || r.left < 11) placePanel();
    }).observe(panel);
  }

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
    const panel = $('#ai-pet-panel');
    if (!panel || panel.hidden) return;
    if (panel.classList.contains('is-max')) return;   // 最大化由 CSS 的 dvh 自适应
    // 用用户选的尺寸重新夹一次：窗口变小夹进去，放大还他原来的大小
    if (panelSize) applyPanelSize(panelSize.w, panelSize.h);   // 窗口变小，旧尺寸收回屏内
    placePanel();
  });
}
