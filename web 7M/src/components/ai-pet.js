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
import {
  currentSkin, getScale, getLife, getHidden, setHidden,
  applySkinVars, applySkinFrame, resolveAct, stopFrames, pullPetPrefs,
} from './pet-skins.js';
import { openPetSettings, onPetPrefChange } from './pet-settings.js';

const SPRITE_W = 120;          // 旧图集的单帧宽，只在图集还没接管尺寸前兜底
const SPRITE_H = 147;
const POS_KEY = 'hc-pet-pos';
const SIZE_KEY = 'hc-pet-panel-size';
const HINT_KEY = 'hc-pet-hinted';
const CHIPS_KEY = 'hc-pet-chips-collapsed';   // 快捷指令收起了没有
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

// --- 快捷指令的收起 / 展开 ------------------------------------------------
// 办公 7 个、工作 14 个按钮，铺开能占四五行走廊，把消息区挤得只剩一两行。
// 收起状态写进 localStorage：重开面板、切模式、刷新页面都不会自己弹回来。
function chipsCollapsed(){
  try{ return localStorage.getItem(CHIPS_KEY) === '1'; }catch(_){ return false; }
}

export function applyPetChips(mode){
  const owner = isOwner(state.me);
  const collapsed = chipsCollapsed();
  const faq = $('#ai-pet-faq-chips');
  const head = $('#ai-pet-chips-head');
  const office = $('#ai-pet-office-chips');
  const work = $('#ai-pet-work-chips');
  // 办公/工作模式有工具指令，客服那排常见问和模式页签重复，先让位。
  if (faq) faq.hidden = mode !== 'chat';
  if (head) head.hidden = !owner || mode === 'chat';
  if (office) office.hidden = !owner || collapsed || mode !== 'office';
  if (work) work.hidden = !owner || collapsed || mode !== 'work';
  const btn = $('#ai-pet-chips-toggle');
  if (btn){
    btn.textContent = collapsed ? '展开' : '收起';
    btn.setAttribute('aria-expanded', String(!collapsed));
  }
}

export function togglePetChips(mode){
  // 隐私模式下 localStorage 可能抛错：退化成「本次有效」，不阻断点击。
  try{ localStorage.setItem(CHIPS_KEY, chipsCollapsed() ? '0' : '1'); }catch(_){ }
  applyPetChips(mode);
}

let petEl = null;
let drag = null;
let petHoldTimer = 0;
let petFeedbackTimer = 0;
let suppressPetClickUntil = 0;
let petReactionIndex = 0;
// 初始值不能是 0：页面刚加载时 performance.now() 还不到 320ms，
// 「点一下开面板」会被当成拖动结束的补发 click 吞掉。
let lastDragEnd = -1e9;
let stateTimer = 0;
let lifeTimer = 0;

// --- 标记 ---------------------------------------------------------------
export function aiPet(){
  return `<div class="ai-pet" id="ai-pet" data-state="idle">
  <button type="button" class="ai-pet-body" id="ai-pet-body" aria-label="AI 助手小转，点一下聊天，长按摸摸，拖动移动">
    <span class="ai-pet-sprite" aria-hidden="true"></span>
    <span class="ai-pet-fallback" aria-hidden="true">转</span>
  </button>
  <span class="ai-pet-reaction" id="ai-pet-reaction" role="status" aria-live="polite">被你摸到啦，好开心！</span>
  <div class="ai-pet-hint" id="ai-pet-hint" hidden>点我聊天 · 长按摸摸 · 拖动换位置</div>
  <section class="ai-pet-panel" id="ai-pet-panel" hidden aria-label="AI 助手小转">
    <header class="ai-pet-head" id="ai-pet-head">
      <span class="ai-pet-avatar"><img id="ai-pet-avatar" src="/assets/ai-pet/xiaozhuan-avatar.png" alt=""></span>
      <div><b id="ai-pet-name">小转</b><small id="ai-pet-duty">客服在线 · 08:00–20:00</small></div>
      <button type="button" class="ai-pet-pat" id="ai-pet-pat" aria-label="摸摸小转" title="摸摸小转">
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M10 17s-6.5-3.9-6.5-8.2A3.6 3.6 0 0 1 10 6.9a3.6 3.6 0 0 1 6.5 1.9C16.5 13.1 10 17 10 17Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>
      </button>
      <button type="button" class="ai-pet-gear" id="ai-pet-set" aria-label="桌宠设置" title="桌宠设置：换形象、大小、须知">
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M2.6 4.4h10.8M2.6 8h10.8M2.6 11.6h10.8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="5.6" cy="4.4" r="1.7" fill="currentColor"/><circle cx="10.4" cy="8" r="1.7" fill="currentColor"/><circle cx="6.2" cy="11.6" r="1.7" fill="currentColor"/></svg>
      </button>
      <button type="button" class="ai-pet-max" id="ai-pet-max" aria-label="放大对话窗口" title="放大 / 还原（双击标题也可以）">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 2H2v4M10 2h4v4M6 14H2v-4M10 14h4v-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <button type="button" class="ai-pet-close" id="ai-pet-close" aria-label="收起对话">×</button>
    </header>
    <div class="ai-pet-log" id="ai-pet-log">
      <div class="ai-pet-msg bot">我是转角的桌宠。发布、退款、面交、客服时间都能问我——不想问正事，聊两句也行。</div>
    </div>
    <div class="ai-pet-chips" id="ai-pet-faq-chips" aria-label="常见问题">
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
    <div class="ai-pet-chips-head" id="ai-pet-chips-head" hidden>
      <span>快捷指令</span>
      <button type="button" id="ai-pet-chips-toggle" data-action="ai-pet-chips-toggle"
              aria-controls="ai-pet-office-chips ai-pet-work-chips" aria-expanded="true">收起</button>
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
      <textarea id="ai-pet-q" name="q" maxlength="300" rows="1" placeholder="问问我，例如：怎么发布？" required></textarea>
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
// 动作名 → 皮肤里的一段帧序列。帧数、行号、快慢都由皮肤声明，
// 这里只负责「换动作」和「播完回待机」。
export function setPetState(name, holdMs){
  if (!petEl) return;
  clearTimeout(stateTimer);
  const state = name || 'idle';
  petEl.dataset.state = state;
  const skin = currentSkin();
  if (skin){
    // 状态名到帧序列的换算交给皮肤：小毛的「移动」其实是一段捂鼻子摇手，
    // 大乔的「移动」分左右两行。调用方只说自己正在干什么。
    const { act, flip } = resolveAct(skin, state);
    petEl.classList.toggle('is-flip', flip);
    applySkinFrame(petEl.querySelector('.ai-pet-sprite'), skin, act);
  }
  if (holdMs) stateTimer = setTimeout(() => setPetState('idle'), holdMs);
}

// 摸摸时给小转一个短暂的挥袖反馈；连续触发会重新播放动画并轮换一句回应。
function petReaction(){
  if (!petEl) return;
  clearTimeout(petFeedbackTimer);
  const messages = ['被你摸到啦，好开心！', '转一圈，电量回满！', '嘿嘿，我也摸摸你！'];
  const bubble = $('#ai-pet-reaction');
  if (bubble) bubble.textContent = messages[petReactionIndex++ % messages.length];
  petEl.classList.remove('is-petted');
  // 等一帧再加类，让连续点击也能重启动画。
  requestAnimationFrame(() => {
    if (!petEl) return;
    petEl.classList.add('is-petted');
    setPetState('wave', 900);
    petFeedbackTimer = setTimeout(() => petEl?.classList.remove('is-petted'), 1500);
  });
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
    setPetState('point', 900);
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
    drag = { id: ev.pointerId, sx: ev.clientX, sy: ev.clientY, ox: r.left, oy: r.top, moved: false, petted: false };
    const activeDrag = drag;
    clearTimeout(petHoldTimer);
    // 轻触继续打开对话；只有静止长按才摸摸，开始拖动时立即取消这个计时。
    petHoldTimer = setTimeout(() => {
      if (drag !== activeDrag || drag.moved) return;
      activeDrag.petted = true;
      petReaction();
    }, 620);
    petEl.classList.add('is-dragging');
    try{ body.setPointerCapture(ev.pointerId); }catch(_){ /* 老浏览器没有捕获也能靠 move 兜住 */ }
  });

  body.addEventListener('pointermove', ev => {
    if (!drag || ev.pointerId !== drag.id) return;
    const dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;   // 手抖不算拖动
    if (!drag.moved) clearTimeout(petHoldTimer);
    drag.moved = true;
    moveTo(drag.ox + dx, drag.oy + dy);
    // 只在真的往某一侧移动时换朝向；dx 恰好为 0 时保持当前朝向，不要无端翻面。
    if (dx > 0) setPetState('right', 0);
    else if (dx < 0) setPetState('left', 0);
    placePanel();
  });

  const end = ev => {
    if (!drag || ev.pointerId !== drag.id) return;
    clearTimeout(petHoldTimer);
    const moved = drag.moved;
    // 长按后的浏览器 click 是合成事件，拦一次，避免摸摸意外打开聊天框。
    if (drag.petted && !moved && ev.type === 'pointerup') suppressPetClickUntil = performance.now() + 600;
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
    if (performance.now() < suppressPetClickUntil){ ev.preventDefault(); ev.stopPropagation(); return; }
    if (performance.now() - lastDragEnd < 320){ ev.preventDefault(); ev.stopPropagation(); return; }
    togglePetPanel();
  });
}

// --- 待机小动作 ---------------------------------------------------------
function scheduleLife(){
  clearTimeout(lifeTimer);
  lifeTimer = setTimeout(() => {
    if (getLife() && petEl && !drag && !petEl.classList.contains('is-open')){
      setPetState(Math.random() < .55 ? 'greet' : 'look', 1400);
    }
    scheduleLife();
  }, 11000 + Math.random() * 9000);
}

// --- 皮肤 ---------------------------------------------------------------
// 换皮肤时只改 CSS 变量和名字头像，元素本身不重建——重建会丢拖动绑定和面板状态。
function applySkin(){
  if (!petEl) return;
  const skin = currentSkin();
  if (!skin) return;
  applySkinVars(petEl, skin, getScale());
  const avatar = $('#ai-pet-avatar');
  if (avatar) avatar.src = skin.avatar;
  const name = $('#ai-pet-name');
  if (name) name.textContent = skin.name;
  const body = $('#ai-pet-body');
  if (body) body.setAttribute('aria-label', `AI 助手${skin.name}，点一下聊天，长按摸摸，拖动移动`);
  petEl.hidden = getHidden();

  // 图集（或用户上传的图）能不能解码，决定用精灵还是降级成字钮。
  const probe = new Image();
  probe.onload = () => petEl?.classList.add('is-ready');
  probe.onerror = () => petEl?.classList.add('is-fallback');
  probe.src = skin.atlas;
  petEl.classList.remove('is-ready');
  setPetState('idle');
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
  applyPetChips('chat');     // 上次收起过就保持收起，别一挂载又铺满
  // 先把皮肤贴上去再定位：桌宠的宽高由皮肤的格子尺寸算出来，
  // 顺序反了会按上一只的尺寸夹位置，换宠物后可能半个身子在屏幕外。
  applySkin();
  restorePos();
  bindDrag(body);
  bindPanelResize($('#ai-pet-panel'));
  $('#ai-pet-pat')?.addEventListener('click', petReaction);
  $('#ai-pet-close')?.addEventListener('click', () => togglePetPanel(false));
  $('#ai-pet-set')?.addEventListener('click', () => openPetSettings('pet'));

  // 设置面板每改一项就回调：换皮肤、调大小、显示隐藏、复位位置。
  onPetPrefChange(what => {
    if (!petEl) return;
    if (what === 'position'){
      try{ localStorage.removeItem(POS_KEY); }catch(_){ }
      restorePos();
      placePanel();
      return;
    }
    if (what === 'show'){
      petEl.hidden = getHidden();
      if (!petEl.hidden) { restorePos(); setPetState('wave', 900); }
      return;
    }
    if (what === 'scale'){ applySkin(); return; }
    if (what === 'life'){ scheduleLife(); return; }
    if (what === 'skin'){ applySkin(); return; }
  });

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

  // 你在输入框里打字，它就当场躺下等着；停手两秒自己爬起来。
  // 输入法拼字期间 value 会反复变，这里只按「有没有内容」判断，不打断拼字。
  $('#ai-pet-q')?.addEventListener('input', ev => {
    if (String(ev.target.value || '').trim()) setPetState('typing', 2000);
    else setPetState('idle');
  });

  // 皮肤（图集地址、帧尺寸、色调）走 CSS 变量，图解码好之前元素是透明的，
  // 解码失败才降级成字钮，功能不至于消失。
  // 拉一次账号里的偏好：这台设备第一次用、或者换了浏览器时，
  // 形象和大小应该还是上次调好的样子。失败就用本地的，不打扰。
  pullPetPrefs().then(changed => { if (changed) applySkin(); });

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
