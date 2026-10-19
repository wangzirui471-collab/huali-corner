'use strict';
// 页面层 · 微信风格聊天室（私聊 / 学院群 / 总聊 / 订单通知）
// 布局：左侧会话列表（搜索、摘要、未读角标），右侧聊天窗
//（标题栏、成员抽屉、头像气泡、日期分隔、表情面板、撤回）。
import { $, e, icon, toast, uid } from '../core/dom.js';
import { date } from '../core/format.js';
import { state, clearPoll } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, empty } from '../core/shell.js';
import { isAdmin } from '../core/roles.js';
import { needLogin } from '../auth/login.js';
import { refreshBadges } from '../core/badges.js';
import { go } from '../core/nav.js';

// 客服会话的常用语：客服同时接几个用户时，八成问题都是同一批答案，
// 点一下就能发，不必每次手打。借鉴淘宝/京东客服的快捷短语。
const QUICK_REPLIES = [
  '你好，我在的，请说～',
  '稍等，我核对一下订单',
  '这个问题需要提交工单处理，我帮你转过去',
  '已为你处理，请留意站内通知',
  '还有别的可以帮你吗？'
];

// 用户侧的「猜你想问」：新会话还没有消息时先给几条常见问题，
// 用户点一下就能把问题发出来，比对着空白输入框发呆强。
const SUPPORT_FAQS = [
  '怎么申请退款？',
  '订单多久能交付？',
  '卖家一直不回复怎么办？',
  '怎么取消订单？'
];

// 头像底色：按用户/房间 id 取模轮换 6 组配色，稳定且不刺眼。
const AVATAR_TONES = 6;

function avatar(nick, id, cls=''){
  return `<span class="wx-avatar ${cls}" data-tone="${(Number(id)||0)%AVATAR_TONES}">${e(String(nick||'转')[0])}</span>`;
}

// 单条时间：今天只显示 时:分，昨天带「昨天」，更早带日期。
function hhmm(t){
  const d = new Date(t*1000), p = n => String(n).padStart(2,'0');
  return p(d.getHours())+':'+p(d.getMinutes());
}
function timeLabel(t){
  const d = new Date(t*1000), now = new Date(), p = n => String(n).padStart(2,'0');
  const day = x => new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime();
  const diff = (day(now)-day(d)) / 86400000;
  const hm = p(d.getHours())+':'+p(d.getMinutes());
  if (diff === 0) return hm;
  if (diff === 1) return '昨天 '+hm;
  const md = (d.getMonth()+1)+'月'+d.getDate()+'日 '+hm;
  return d.getFullYear()===now.getFullYear() ? md : d.getFullYear()+'年'+md;
}
// 两条消息间隔超过 10 分钟就插一条居中时间分隔。
function timeSep(prev, cur){
  return !prev || cur.created - prev.created > 600;
}

// --- 消息渲染 ------------------------------------------------------------
// removed：0=正常 1=被移除 2=已撤回。撤回/移除渲染成居中系统行，
// 不再渲染气泡——正文也不会下发（后端已替换/清空）。
//
// 撤回后的原文只留在本页内存（recalledDrafts）里，供「重新编辑」回填。
// 刷新后服务端已清空正文，这条链接自然消失——和微信一致：撤回不是存草稿。
export const recalledDrafts = new Map();

export function renderMessage(m, room){
  if (m.removed === 2){
    const mine = m.user_id === state.me.id;
    const draft = mine && recalledDrafts.has(m.id);
    return `<div class="wx-sys wx-recalled" data-mid="${m.id}">${mine?'你撤回了一条消息':e(m.nickname)+' 撤回了一条消息'}${draft?` <button type="button" class="wx-reedit" data-action="reedit" data-id="${m.id}">重新编辑</button>`:''}</div>`;
  }
  if (m.removed === 1) return `<div class="wx-sys" data-mid="${m.id}">${e(m.body)}</div>`;
  const mine = m.user_id === state.me.id;
  const showNick = room.kind !== 'private' && !mine;
  // 撤回 / 删除 / 移除不再挂在气泡上：统一走右键（桌面）或长按（手机）菜单。
  // 悬浮按钮会挡住消息，而右键菜单和微信的操作习惯一致。
  // data-* 属性供菜单判断「能不能撤回、是不是自己的」。
  return `<div class="wx-msg ${mine?'mine':''}" data-mid="${m.id}" data-mine="${mine?1:0}" data-created="${m.created}">`+
    `<span class="wx-avatar-link" data-go="profile/${m.user_id}">${avatar(m.nickname, m.user_id)}</span>`+
    `<div class="wx-bubble-wrap">${showNick?`<span class="wx-nick">${e(m.nickname)}</span>`:''}`+
    `<p class="wx-bubble">${e(m.body)}</p>`+
    // 已读回执只挂在自己的消息上：群聊显示「n/总人数」，私聊只有对方一人。
    // 具体数字由 applyReceipts() 依据 /messages/receipts 的位点计算后填入，
    // 这样轮询到别人读了消息时，旧气泡上的回执也会跟着更新。
    (mine?`<span class="wx-receipt" data-receipt-for="${m.id}"></span>`:'')+
    `</div></div>`;
}

// 把一批消息追加进消息流（自动补时间分隔），返回这批里最大的 id。
export function appendMessages(stream, msgs, room){
  const sepAfter = [];
  let last = null;
  for (const m of msgs){
    if (timeSep(last, m)) sepAfter.push(m.id);
    last = m;
  }
  for (const m of msgs){
    if (sepAfter.includes(m.id)) stream.insertAdjacentHTML('beforeend', `<div class="wx-time-sep">${e(timeLabel(m.created))}</div>`);
    stream.insertAdjacentHTML('beforeend', renderMessage(m, room));
  }
  return msgs.length ? msgs[msgs.length-1].id : null;
}

// --- 左侧会话列表 --------------------------------------------------------
// 搜索词存模块变量：轮询刷新列表时保留过滤状态，不把输入框清掉。
let searchWord = '';

// 客服在线状态：按 config.support_hours（如 08:00–20:00）判断，
// 下班后仍然可以留言，只是告诉用户「现在没人守着」，别让用户对着
// 「客服在线」干等。时间解析失败时按在线处理，宁可不吓人。
function supportOnDuty(){
  try{
    const raw = String(state.config.support_hours || '08:00–20:00').replace('—','–').replace('-','–');
    const [a, b] = raw.split('–').map(s => s.trim());
    const toMin = s => { const [h, m] = s.split(':').map(Number); return h * 60 + (m || 0); };
    const now = new Date(); const cur = now.getHours() * 60 + now.getMinutes();
    return cur >= toMin(a) && cur < toMin(b);
  }catch{ return true; }
}

function roomItem(r, activeId){
  const me = state.me;
  const isStaff = me && ['support','admin','developer'].includes(me.role);
  const isSupport = !!r.support;
  // 客服视角：显示认领状态，避免两个客服同时回同一个用户。
  let tag = '';
  if (isSupport && isStaff){
    if (!r.assignee) tag = '<i class="wx-role pending">待接入</i>';
    else if (r.assignee === me.id) tag = '<i class="wx-role ok">我认领</i>';
    else tag = `<i class="wx-role muted-t">已由 ${e(r.assignee_name||'')} 认领</i>`;
  }
  // 用户视角：客服会话在认领后显示具体客服昵称，而不是笼统的「转角客服」。
  const title = isSupport && !isStaff && r.assignee_name ? '客服 · '+r.assignee_name : r.name;
  // 置顶视觉提示：标题前一个细钉子图标，跟微信一致。已置顶时列表里要明显。
  const pinIc = r.pinned ? `<i class="wx-room-pin" title="已置顶" aria-label="已置顶">${icon('pin')}</i>` : '';
  // 屏蔽提示：私聊里我屏蔽了对方时，标题后面加一个小红点提示。
  const blockBadge = r.blocked ? `<i class="wx-room-blocked" title="已屏蔽对方" aria-label="已屏蔽对方">🚫</i>` : '';
  // 行内的「…」按钮：点击会弹一个上下文菜单（置顶、删除聊天记录、屏蔽切换）。
  // 桌面 hover 才显示，手机常显——触屏没有 hover。
  return `<button class="wx-room ${r.id===activeId?'sel':''} ${r.pinned?'pinned':''}" data-go="messages/${r.id}" data-name="${e(r.name)}" data-room-id="${r.id}" data-room-kind="${r.kind}">`+
    avatar(isSupport && !isStaff ? (r.assignee_name||'客服') : r.name, r.id, isSupport?'support':'')+
    `<span class="wx-room-main"><span class="wx-room-top"><b>${pinIc}${e(title)}${blockBadge}</b>${tag}`+
    `<small class="wx-room-time">${r.last_at?e(hhmm(r.last_at)):''}</small></span>`+
    `<span class="wx-room-preview">${e(roomPreview(r))}${r.muted?icon('bell','wx-mute-ic'):''}</span></span>`+
    (r.unread?`<i class="wx-badge">${r.unread>99?'99+':r.unread}</i>`:'')+
    // 阻止冒泡到 wx-room，否则点「…」也会跳进会话。
    `<span class="wx-room-more" data-action="room-menu" data-id="${r.id}" data-room-kind="${r.kind}" data-blocked="${r.blocked?1:0}" data-pinned="${r.pinned?1:0}" data-peer-id="${r.peer_id||0}" role="button" tabindex="0" aria-label="更多">${icon('more')}</span>`+
    `</button>`;
}

// 三点图标的 SVG 路径在 core/dom.js 的 icons 字典里，名字叫 'more'。这里不再重复。
function roomPreview(r){
  if (r.last_body) return (r.last_nick && r.kind!=='private' ? r.last_nick+'：' : '') + r.last_body;
  return '暂无消息';
}

function renderRoomList(rooms, notices, activeId){
  const list = $('#wx-list');
  if (!list) return;
  const kw = searchWord.trim().toLowerCase();
  // 后端 rooms() 已经按 pinned desc, last_at desc 排过序；这里只做搜索过滤。
  // 重新排序会把置顶的甩回原位，所以不要二次排。
  const joined = rooms.joined.filter(r => !kw || String(r.name).toLowerCase().includes(kw));
  list.innerHTML =
    `<button class="wx-room ${String(activeId)==='notice'?'sel':''}" data-go="messages/notice" data-name="订单与售后通知">`+
    `<span class="wx-avatar notice" data-tone="notice">${icon('bell')}</span>`+
    `<span class="wx-room-main"><span class="wx-room-top"><b>订单与售后通知</b></span>`+
    `<span class="wx-room-preview">${notices.unread?notices.unread+' 条未读':'全部已读'}</span></span>`+
    (notices.unread?`<i class="wx-badge">${notices.unread}</i>`:'')+`</button>`+
    // 「在线客服」只是入口：已经有客服会话的人直接看会话，不再重复摆一个按钮。
    (state.me?.role==='user' && !rooms.joined.some(r=>r.support)
      ? `<button class="wx-room" data-action="chat-support" data-name="在线客服"><span class="wx-avatar support" data-tone="support">${icon('message')}</span>`+
        `<span class="wx-room-main"><span class="wx-room-top"><b>在线客服</b></span>`+
        `<span class="wx-room-preview">先提交问题，受理后可实时沟通</span></span></button>`
      : '')+
    (joined.map(r => roomItem(r, activeId)).join('') ||
      `<p class="muted wx-empty-tip">还没有会话<br>去社区加入群聊，或在商品页联系卖家</p>`);
}

// --- 成员抽屉 ------------------------------------------------------------
// 挂在聊天窗右侧，群聊可看成员、群主/管理员可就地禁言。
export async function toggleMembers(roomId){
  const drawer = $('#wx-members');
  if (!drawer) return;
  if (!drawer.hidden){ drawer.hidden = true; return; }
  const data = await api('/room/members?room_id='+roomId);
  const iAm = data.members.find(x => x.user_id === state.me.id);
  const canMute = (iAm && ['owner','moderator'].includes(iAm.role)) || isAdmin(state.me);
  const roleTag = r => r==='owner'?'<i class="wx-role">群主</i>':r==='moderator'?'<i class="wx-role mod">管理员</i>':'';
  drawer.innerHTML = `<div class="wx-members-head"><b>群成员</b><small>${data.members.length} 人</small>`+
    `<button class="wx-drawer-close" data-action="toggle-members" data-id="${roomId}">${icon('close')}</button></div>`+
    `<div class="wx-members-list">`+data.members.map(m =>
      `<div class="wx-member">${avatar(m.nickname, m.user_id)}`+
      `<span class="wx-member-name">${e(m.nickname)}${roleTag(m.role)}${m.muted?'<i class="wx-role muted-t">已禁言</i>':''}</span>`+
      (canMute && m.user_id!==state.me.id ? `<button class="text-button" data-action="mute-member" data-id="${m.user_id}" data-room="${roomId}" data-muted="${m.muted?0:1}">${m.muted?'解除禁言':'禁言'}</button>`:'')+
      `</div>`).join('')+`</div>`;
  drawer.hidden = false;
}

// --- 消息右键菜单 ---------------------------------------------------------
// 桌面右键、手机长按共用同一个菜单。位置按视口夹紧；点外面 / Esc / 滚动都关闭，
// 避免菜单浮在页面上收不掉。
let menuEl = null, menuBound = false;
function closeMessageMenu(){ if (menuEl){ menuEl.remove(); menuEl = null; } }
function ensureMenuBound(){
  if (menuBound) return;
  menuBound = true;
  document.addEventListener('mousedown', ev => { if (menuEl && !menuEl.contains(ev.target)) closeMessageMenu(); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeMessageMenu(); });
  window.addEventListener('scroll', closeMessageMenu, true);
}
function openMessageMenu(x, y, items){
  closeMessageMenu(); ensureMenuBound();
  const el = document.createElement('div');
  el.className = 'wx-menu';
  el.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}"${it.danger?' class="danger"':''}>${e(it.label)}</button>`).join('');
  document.body.appendChild(el);
  const r = el.getBoundingClientRect();
  el.style.left = Math.max(8, Math.min(x, window.innerWidth - r.width - 8)) + 'px';
  el.style.top = Math.max(8, Math.min(y, window.innerHeight - r.height - 8)) + 'px';
  el.addEventListener('click', ev => {
    const b = ev.target.closest('[data-i]');
    if (!b) return;
    closeMessageMenu();
    const item = items[Number(b.dataset.i)];
    if (item) item.run();
  });
  menuEl = el;
}

// 会话列表项的上下文菜单：复用 wx-menu 视觉，按钮/位置和消息右键一致。
// 入口的 dataset：
//   data-id        会话 id
//   data-room-kind 'private' / 'general' / 'college' / 'support'
//   data-blocked   '1' / '0'：当前是否已屏蔽（仅私聊有意义）
//   data-pinned    '1' / '0'：当前是否已置顶
//   data-peer-id   私聊对方的 user_id
// 菜单项按 room.kind 过滤：群聊/总聊/客服都没有「屏蔽」入口；通知是「通知」而不是会话，不进这个菜单。
function openRoomMenu(anchor, ev){
  const id = Number(anchor.dataset.id);
  const kind = anchor.dataset.roomKind;
  const blocked = anchor.dataset.blocked === '1';
  const pinned = anchor.dataset.pinned === '1';
  const peer = Number(anchor.dataset.peerId || 0);
  const items = [];
  items.push({ label: pinned ? '取消置顶' : '置顶会话', run: () => roomAction('pin', id, !pinned) });
  items.push({ label: '删除聊天记录', danger: true, run: () => roomAction('clear', id) });
  if (kind === 'private' && peer){
    items.push({ label: blocked ? '取消屏蔽' : '屏蔽对方', run: () => roomAction('block', id, peer, !blocked) });
  }
  // 弹在按钮下方，右侧对齐——与微信长按会话一致。
  const rect = anchor.getBoundingClientRect();
  openMessageMenu(rect.right - 132, rect.bottom + 4, items);
  if (ev) ev.preventDefault();
}

// 把会话级操作的请求集中在一处：成功后再调 render() 把列表/会话本身刷新。
// 用 try/catch 兜住网络错误，失败提示但不破坏当前页面。
async function roomAction(kind, id, ...args){
  try{
    if (kind === 'pin'){
      await api('/rooms/pin', {room_id: id, pinned: args[0]});
      toast(args[0] ? '已置顶' : '已取消置顶');
    }else if (kind === 'clear'){
      if (!confirm('删除与该会话的全部聊天记录？\n\n仅自己这边看不见，对方不受影响。')) return;
      await api('/rooms/clear', {room_id: id});
      toast('已清空聊天记录');
    }else if (kind === 'block'){
      const peer = args[0]; const enabled = args[1];
      await api('/block', {target: peer, enabled});
      toast(enabled ? '已屏蔽，对方不能继续发消息' : '已取消屏蔽');
    }
    // 主动刷新一次会话列表，让置顶顺序、屏蔽标记立刻生效（不靠 8s 轮询）。
    const rooms = await api('/rooms');
    state.rooms = rooms;
    const list = $('#wx-list');
    if (list){
      // 复用 chats() 里的渲染路径：
      const activeId = Number(location.hash.split('/').pop()) || null;
      const notices = state.notices || {unread: 0, items: []};
      renderRoomList(rooms, notices, activeId);
    }
    // 屏蔽 toggle 后可能影响当前聊天窗的头部按钮与底部提示条——
    // 如果当前打开的就是这个房间，整页重画一次。
    const cur = Number(location.hash.split('/').pop());
    if (cur === id) go('messages/' + id);
  }catch(err){
    toast(err.message || '操作失败');
  }
}

// --- 聊天页事件（经 actions 委托分派，见 actions/social.js 的合并） -------
export const chatClicks = {
  'toggle-members': (b, id) => toggleMembers(id),

  'wx-emoji': () => {
    const p = $('#wx-emoji');
    if (p) p.hidden = !p.hidden;
  },

  // 结束客服会话：用户聊完就走，客服下班前收尾。结束即归档消息，
  // 双方会话列表都不再显示这条记录，下次咨询开新会话。
  'close-support': async (b, id) => {
    if (!confirm('结束本次客服会话？\n\n结束后这段聊天记录会从会话列表消失，下次咨询会开启新的会话。')) return;
    try{
      await api('/support/close', {room_id:Number(id)});
      toast('会话已结束');
      go('messages');
    }catch(err){ toast(err.message || '结束失败'); }
  },

  // 撤回后的「重新编辑」：把当时缓存的原文填回输入框，光标放末尾。
  reedit: (b, id) => {
    const text = recalledDrafts.get(id);
    const editor = $('#wx-editor');
    if (text === undefined || !editor){ toast('原文已不可用，请重新输入'); return; }
    editor.value = text;
    editor.focus();
    editor.setSelectionRange(text.length, text.length);
    editor.dispatchEvent(new Event('input'));
  },

  'mute-member': async (b, id) => {
    await api('/moderate', {room_id:Number(b.dataset.room), action:'mute', target:id, muted:!!Number(b.dataset.muted)});
    toast(Number(b.dataset.muted) ? '已禁言' : '已解除禁言');
    await toggleMembers(Number(b.dataset.room)); // 关闭
    await toggleMembers(Number(b.dataset.room)); // 再打开，重拉数据
  },

  // 会话列表项上的「…」：弹上下文菜单（置顶/取消置顶、删除聊天记录、屏蔽切换）。
  // 真正的处理器在 actions/social.js 里（合并进 clicks 之前先铺开 chatClicks），
  // 这里也兜一份防止 social.js 哪天把名字改了。
  'room-menu': (b, ev) => {
    openRoomMenu(b, ev);
  },

  // 底部「已屏蔽，对方不能继续发消息」行内的「取消屏蔽」按钮。
  'unblock-here': async () => {
    if (!state._chatRoom) return;
    const r = state._chatRoom;
    if (!r.peer_id) return;
    try{
      await api('/block', {target: r.peer_id, enabled: false});
      toast('已取消屏蔽');
      go('messages/' + r.id);
    }catch(err){ toast(err.message || '操作失败'); }
  }
};

// --- 页面入口 ------------------------------------------------------------
export async function chats(roomId){
  if (!needLogin()) return;
  const [rooms, notices] = await Promise.all([api('/rooms'), api('/notifications')]);
  // 把 rooms/notices 暂存到 state，下面的「room-menu / block-room / unblock-here」
  // 三个处理器需要拿当前房间 / 最新列表来刷新。
  state.rooms = rooms; state.notices = notices;
  const noticeView = String(roomId) === 'notice';
  const room = noticeView ? null : rooms.joined.find(r => r.id === Number(roomId));
  // rooms 里的 role 是我在这群的群角色，补进 room 供「移除消息」判断。
  if (room){
    room.myRole = room.role;
    // 聊天窗 head / 底部条幅 / 屏蔽按钮都靠这个值判断，避免重复查 /api/rooms。
    state._chatRoom = { id: room.id, kind: room.kind, peer_id: room.peer_id || 0, blocked: !!room.blocked, name: room.name };
  }else{
    state._chatRoom = null;
  }
  const activeId = noticeView ? 'notice' : (room?.id ?? null);

  const side = `<aside class="wx-side">`+
    `<div class="wx-search">${icon('search')}<input id="wx-search-input" type="search" placeholder="搜索会话" value="${e(searchWord)}"></div>`+
    `<div class="wx-list" id="wx-list"></div>`+
    `<div class="wx-side-foot"><button class="text-button" data-go="community">去社区找同学 →</button></div></aside>`;

// 通知类型 → 图标与配色：一眼分清是订单节点、售后还是社区的回复/@。
const NOTE_META = {
  post_reply: ['message', 'info'], mention: ['message', 'violet'],
  order_created: ['bag', 'info'], order_paid: ['wallet', 'ok'],
  order_completed: ['check', 'ok'], order_cancelled: ['close', 'mute'],
  order_delivered: ['truck', 'info'], refund: ['refresh', 'warn'],
  refund_approved: ['check', 'ok'], refund_rejected: ['close', 'danger'],
  ticket: ['shield', 'warn'], content_removed: ['alert', 'danger'],
  ticket_filed: ['shield', 'warn'], ticket_refund: ['shield', 'warn'],
  ticket_reply: ['shield', 'warn'], ticket_resolved: ['shield', 'ok'],
  refund_done: ['refresh', 'ok'], credit: ['chart', 'warn'],
  order_updated: ['bag', 'info'], order_change_result: ['refresh', 'info'],
  order_reschedule: ['refresh', 'info'], order_handover: ['check', 'info'],
  order_timeout: ['close', 'mute'],
  product_moderate: ['alert', 'danger'], product_review: ['check', 'ok']
};

// 每条通知点进去该落到哪。按「引用越精确越优先」：
// 工单 → 工单详情；商品 → 商品详情；帖子 → 社区并展开该帖评论；
// 订单 → 订单列表；其余按类型给最相关页面（信誉变动去诚信页，
// 售后结论去客服中心，整店下架这类没有单件引用的去在售管理）。
// 没有任何引用的（如纯文本信誉通报）返回 null，条目就保持不可点。
function noticeTarget(n){
  if (n.ticket_id) return { go: 'ticket/' + n.ticket_id };
  if (n.product_id) return { go: 'product/' + n.product_id };
  if (n.post_id) return { post: n.post_id, go: 'community' };
  if (n.order_id) return { go: 'orders' };
  if (n.kind === 'credit') return { go: 'credit' };
  if (['product_moderate', 'product_review'].includes(n.kind)) return { go: 'listings' };
  if (['refund', 'refund_approved', 'refund_rejected', 'refund_done',
       'ticket_filed', 'ticket_refund', 'ticket_resolved'].includes(n.kind)) return { go: 'support' };
  return null;
}

// 等社区页把帖子卡渲染出来。列表一页只有 20 条，旧帖子可能不在首屏，
// 轮询到超时为止（约 3 秒），由调用方决定给什么提示。
function waitForPostCard(id, timeout = 3000){
  return new Promise(resolve => {
    const t0 = Date.now();
    (function poll(){
      const card = document.querySelector('.post-card[data-post="' + id + '"]');
      if (card) return resolve(card);
      if (Date.now() - t0 > timeout) return resolve(null);
      setTimeout(poll, 100);
    })();
  });
}

// 通知中心：沿用原来的数据，套微信聊天窗的壳。
  const noticePanel = noticeView ? `
    <header class="wx-chat-head"><div class="wx-head-title"><h3>订单与售后通知</h3><small>打开本页即视为已读；下单、付款、交付、售后、社区的回复与@都会提醒你</small></div></header>
    <div class="wx-stream notice-stream">${notices.items.map(n => {
      const [ic, tone] = NOTE_META[n.kind] || ['bell', 'mute'];
      const link = n.order_id ? `订单 #${n.order_id}` : n.ticket_id ? `工单 #${n.ticket_id}` : n.post_id ? `帖子 #${n.post_id}` : n.product_id ? `商品 #${n.product_id}` : '';
      // 打开通知页即视为已读（下方会自动标记并清角标），所以这里一律渲染成
      // 已读样式——不再保留黄色高亮。之前「保留高亮到下次打开」的设计
      // 被用户反馈为困惑：点开看到了黄色，点它又没反应，像坏了。
      // 现在每条带目标的通知都是可点的整行：有 data-go 的走路由（工单/商品/
      // 订单/客服/诚信页），帖子类留 data-post 由本页监听转社区并展开评论。
      const t = noticeTarget(n);
      const jump = t ? (t.post ? ` data-post="${t.post}"` : ` data-go="${t.go}"`) : '';
      return `<div class="notice-item${t?' can-jump':''}"${jump}${t?' role="link" tabindex="0"':''}><span class="notice-ic" data-tone="${tone}">${icon(ic)}</span><div><p>${e(n.body)}</p><small>${date(n.created)}${link?' · '+e(link):''}</small></div>${t?`<span class="notice-jump">${icon('arrow')}</span>`:''}</div>`;
    }).join('')
      || '<div class="wx-sys">暂无通知</div>'}</div>` : '';

  const chatPanel = room ? `
    <header class="wx-chat-head">
      <button class="wx-back" data-go="messages">${icon('arrow')}</button>
      <div class="wx-head-title"><h3>${e(room.name)}</h3><small>${room.support
        ? `<span class="wx-online ${supportOnDuty()?'on':'off'}">${supportOnDuty()?'客服在线':'客服已下班'}</span>${room.ticket_id?` · <span class="wx-ticket-link" data-go="ticket/${room.ticket_id}">工单 #${room.ticket_id}</span>`:''}`
        : (room.kind==='private'?'私聊':room.count+' 位成员')}</small></div>
      <div class="wx-head-actions">
        ${room.support
          ? `<button class="text-button" data-action="close-support" data-id="${room.id}">${['support','admin','developer'].includes(state.me?.role)?'结束会话':'结束咨询'}</button>`
          : room.kind!=='private'
            ? `<button class="text-button" data-action="toggle-members" data-id="${room.id}">成员</button>
        <button class="text-button" data-action="nominate" data-id="${room.id}">申请管理员</button>`
            : `<button class="text-button" data-action="block-room" data-id="${room.id}">${room.blocked?'取消屏蔽':'屏蔽对方'}</button>`}
      </div>
    </header>
    <div class="wx-chat-body">
      <div class="wx-stream" id="chat-stream"></div>
      <aside class="wx-members" id="wx-members" hidden></aside>
    </div>
    ${room.kind==='private' && room.blocked
      ? `<div class="wx-blocked-banner" role="status"><span>已屏蔽对方，对方不能继续发消息</span><button type="button" class="text-button" data-action="unblock-here">取消屏蔽</button></div>`
      : ''}
    <footer class="wx-input">
      <div class="wx-toolbar">
        <button type="button" class="wx-tool" data-action="wx-emoji" title="表情">😊</button>
        ${room.support
          ? (['support','admin','developer'].includes(state.me?.role)
              ? `<div class="wx-quick" id="wx-quick">${QUICK_REPLIES.map(t=>`<button type="button" class="wx-quick-chip" data-quick="${e(t)}">${e(t)}</button>`).join('')}</div>`
              : `<div class="wx-quick" id="wx-quick" hidden><span class="wx-quick-label">猜你想问</span>${SUPPORT_FAQS.map(t=>`<button type="button" class="wx-quick-chip" data-quick="${e(t)}">${e(t)}</button>`).join('')}</div>`)
          : ''}
        <span class="wx-count" id="wx-count"></span>
      </div>
      <div class="wx-composer" id="wx-composer" data-room="${room.id}">
        <textarea id="wx-editor" name="message" maxlength="2000" rows="1" placeholder="${room.support?(['support','admin','developer'].includes(state.me?.role)?'输入回复，Enter 发送':'描述你的问题，客服会尽快回复'):'输入消息，Enter 发送，Shift+Enter 换行'}"></textarea>
        <div class="wx-send-row"><span class="muted">${room.support?'客服在线时间 08:00–20:00 · 30 分钟无新消息会话自动结束':'消息会经过平台自动审核'}</span><button class="btn primary sm" type="button" id="wx-send">发送</button></div>
      </div>
      <div class="wx-emoji-panel" id="wx-emoji" hidden></div>
    </footer>` : (noticeView ? noticePanel : empty('选择一个会话','可以在商品页联系卖家，或去社区加入群聊。'));

  shell(`<div class="wx-app">${side}<section class="wx-chat">${chatPanel}</section></div>`, 'messages');

  renderRoomList(rooms, notices, activeId);

  // 通知中心的未读是「打开即已读」：点开就自动全部标记已读并清掉顶栏与
  // 「我的」页角标。列表本身直接渲染成已读样式——曾试过「保留高亮到下次
  // 打开让用户知道刚才哪些没读」，被用户反馈为困惑：看到黄色去点又没反应。
  if (noticeView && notices.unread > 0){
    api('/notifications', {}).then(() => {
      notices.unread = 0;
      notices.items.forEach(n => { n.read_at = n.read_at || 1; });
      renderRoomList(rooms, notices, activeId);
      refreshBadges(true);
    }).catch(() => {});
  }

  // 帖子类通知：跳到社区页并就地展开那条帖子的评论区（手风琴逻辑复用
  // actions/social 的 comments 处理器）。帖子不在最新 20 条时列表里找不到卡，
  // 给一句提示，别让用户以为点了没反应。
  if (noticeView){
    document.querySelectorAll('.notice-item[data-post]').forEach(el => el.addEventListener('click', async () => {
      const pid = Number(el.dataset.post);
      go('community');
      const card = await waitForPostCard(pid);
      if (!card){ toast('该帖子不在最新列表，请到社区页查看'); return; }
      card.querySelector('.post-action[data-action="comments"]')?.click();
    }));
  }

  // 搜索会话（客户端过滤，不整页重绘）。
  $('#wx-search-input')?.addEventListener('input', ev => {
    searchWord = ev.target.value;
    renderRoomList(rooms, notices, activeId);
  });

  // 长按 / 右键会话列表项：弹出同样的上下文菜单（手机没 hover 看不到「…」）。
  // 触发后 preventDefault 阻止长按选中文字。
  const list = $('#wx-list');
  if (list){
    let pressTimer = null, pressRow = null;
    const start = (el, clientX, clientY) => {
      if (!el) return;
      clearTimeout(pressTimer);
      pressRow = el;
      pressTimer = setTimeout(() => {
        if (pressRow) openRoomMenu(pressRow);
        pressRow = null;
      }, 500);
    };
    const cancel = () => { clearTimeout(pressTimer); pressRow = null; };
    list.addEventListener('contextmenu', ev => {
      const row = ev.target.closest('.wx-room');
      if (!row) return;
      ev.preventDefault();
      openRoomMenu(row);
    });
    list.addEventListener('touchstart', ev => {
      const row = ev.target.closest('.wx-room');
      if (!row) return;
      const t = ev.touches[0];
      start(row, t.clientX, t.clientY);
    }, {passive:true});
    list.addEventListener('touchend', cancel);
    list.addEventListener('touchmove', cancel);
    list.addEventListener('touchcancel', cancel);
  }

  if (!room) return;

  // 客服会话认领：进入时先认领（await），认领成功才成为成员、才能拉消息。
  // 已被别人认领则只提示、不抢单——这是「两个客服不回同一个用户」的闸门。
  if (room.support && ['support','admin','developer'].includes(state.me?.role)){
    try{
      const claim = await api('/support/claim', {room_id:room.id});
      if (claim.ok) room.assignee = claim.assignee;
      else if (claim.assignee_name) toast(`该会话已由 ${claim.assignee_name} 认领`);
    }catch{ /* 认领失败不阻断查看，服务端仍会按成员校验放行与否 */ }
  }

  // --- 快捷回复 / 猜你想问 ------------------------------------------------
  // 点一下把话填进输入框（不直接发）：客服可以改两个字再发，
  // 用户也能先看一眼再确认，避免「点错就发出去」。
  $('#wx-quick')?.addEventListener('click', ev => {
    const b = ev.target.closest('[data-quick]');
    if (!b) return;
    const editor = $('#wx-editor');
    const text = b.dataset.quick;
    const glue = editor.value && !editor.value.endsWith('\n') ? '\n' : '';
    editor.value = editor.value ? editor.value + glue + text : text;
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
    editor.dispatchEvent(new Event('input'));
    const q = $('#wx-quick');
    if (q) q.hidden = q.hidden; // 保持原状，不在这里折叠
  });

  // --- 表情面板 ----------------------------------------------------------
  const EMOJIS = ['😀','😁','😂','🤣','😊','😍','😘','😜','🤔','😅','😭','😤','😡','🥺','😱','🤗','🤩','😴','🤝','👍','👎','👏','🙏','💪','🎉','🔥','❤️','💔','💯','⚡','🌹','🌈','☀️','🌙','⭐','📚','✏️','🎓','🏀','⚽','🍜','🍵','💰','🎁','📦','🛒','✅','❌'];
  const emojiPanel = $('#wx-emoji');
  emojiPanel.innerHTML = EMOJIS.map(x => `<button type="button" data-emoji="${x}">${x}</button>`).join('');
  emojiPanel.addEventListener('click', ev => {
    const b = ev.target.closest('[data-emoji]');
    if (!b) return;
    const editor = $('#wx-editor');
    // 插到光标处，没有选区时也能正常工作；插完收起面板、焦点回输入框。
    editor.setRangeText(b.dataset.emoji, editor.selectionStart, editor.selectionEnd, 'end');
    editor.focus();
    emojiPanel.hidden = true;
  });

  // --- 发送与输入 --------------------------------------------------------
  // 输入区刻意不用 <form>：没有 form 就不会出现「原生提交 → 整页跳到 /?message=…」，
  // 发送只走下面的显式调用。发送中锁住按钮、复用同一个幂等键，
  // 连点/连按回车只会产生一条消息（服务端 request_key 唯一约束兜底）。
  const stream = $('#chat-stream');
  const editor = $('#wx-editor');
  const sendBtn = $('#wx-send');
  let sending = false;

  // 乐观气泡：真实消息回来后由 pullNew 摘掉，网络再慢也先看到自己的消息。
  const appendPending = (body, key) => {
    const el = document.createElement('div');
    el.className = 'wx-msg mine wx-pending';
    el.dataset.tmp = key;
    el.dataset.body = body;
    el.innerHTML = `<span class="wx-avatar-link">${avatar(state.me.nickname, state.me.id)}</span>`+
      `<div class="wx-bubble-wrap"><p class="wx-bubble">${e(body)}</p><span class="wx-receipt">发送中…</span></div>`+
      // 失败才显示的红色感叹号。.mine 是 row-reverse，所以它在气泡左侧——
      // 与微信一致：自己的消息发送失败时，感叹号挂在气泡左边。
      `<button class="wx-retry" type="button" aria-label="重新发送" hidden>!</button>`;
    stream.appendChild(el);
    stream.scrollTop = stream.scrollHeight;
    return el;
  };

  const send = async () => {
    if (sending) return;
    const body = editor.value.trim();
    if (!body) return;
    sending = true;
    sendBtn.disabled = true;
    const key = uid();
    const pending = appendPending(body, key);
    editor.value = '';
    editor.style.height = 'auto';
    updateCount();
    try{
      await api('/messages', {room_id: room.id, body, key});
      // 请求成功了但真实消息可能还在路上（慢网络下轮询可能先返回旧批次），
      // 先标「已发送」，等真实消息到达时整个乐观气泡会被替换掉。
      pending.querySelector('.wx-receipt').textContent = '已发送';
      await pullNew();
    }catch(err){
      // 失败：气泡标红并挂红色感叹号，点它重发**同一条**。
      // 关键：绝不把正文塞回输入框——那会让「按回车重试」变成「再发一条新消息」，
      // 用户连按几次回车就会看到一串重复气泡（真实踩过的 bug）。
      pending.classList.add('failed');
      pending.querySelector('.wx-receipt').textContent = '发送失败';
      pending.querySelector('.wx-retry').hidden = false;
      toast(err.message);
    }finally{
      sending = false;
      sendBtn.disabled = false;
      editor.focus();
    }
  };

  // 重发失败的那条：复用原幂等键——上一次可能已经到达服务端、只是响应丢了，
  // 同一个 key 重发不会在库里产生第二条。
  const resend = async el => {
    if (!el || sending) return;
    sending = true;
    sendBtn.disabled = true;
    el.classList.remove('failed');
    el.querySelector('.wx-receipt').textContent = '重新发送…';
    el.querySelector('.wx-retry').hidden = true;
    try{
      await api('/messages', {room_id: room.id, body: el.dataset.body, key: el.dataset.tmp});
      el.querySelector('.wx-receipt').textContent = '已发送';
      await pullNew();
    }catch(err){
      el.classList.add('failed');
      el.querySelector('.wx-receipt').textContent = '发送失败';
      el.querySelector('.wx-retry').hidden = false;
      toast(err.message);
    }finally{
      sending = false;
      sendBtn.disabled = false;
      editor.focus();
    }
  };
  stream.addEventListener('click', ev => {
    const btn = ev.target.closest('.wx-retry');
    if (btn) resend(btn.closest('.wx-pending'));
  });
  sendBtn.addEventListener('click', send);
  // Enter 发送、Shift+Enter 换行、输入时自动加高。
  editor.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey){ ev.preventDefault(); send(); }
  });
  editor.addEventListener('input', () => {
    editor.style.height = 'auto';
    editor.style.height = Math.min(editor.scrollHeight, 140)+'px';
    updateCount();
  });
  function updateCount(){ $('#wx-count').textContent = editor.value.length ? editor.value.length+'/2000' : ''; }

  // --- 消息拉取（首次全量最近 200 条，之后增量轮询） ----------------------
  state.messageCursor = 0;
  const seen = new Set();
  let pulling = null;
  const pullNew = () => {
    // 并发合并：3 秒轮询在慢网络下会和上一次请求重叠，两批相同消息各自追加
    // 一次，界面上就会「发一条变三条」。同一时刻只允许一个拉取在跑，
    // 再加 seen 按消息 id 去重兜底。
    if (pulling) return pulling;
    pulling = (async () => {
      const msgs = await api('/messages?room_id='+room.id+'&after='+state.messageCursor);
      const fresh = msgs.filter(m => !seen.has(m.id));
      if (!fresh.length) return;
      fresh.forEach(m => seen.add(m.id));
      const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 80;
      appendMessages(stream, fresh, room);
      state.messageCursor = Math.max(state.messageCursor, ...fresh.map(m => m.id));
      // 真实消息到了：把对应的乐观气泡摘掉，避免同一句出现两次。
      for (const m of fresh){
        if (m.user_id !== state.me.id) continue;
        const el = [...stream.querySelectorAll('.wx-pending')]
          .find(x => x.dataset.body === m.body);
        if (el) el.remove();
      }
      // 用户本来就在底部、或消息是自己发的：自动滚到底；否则保持位置。
      if (atBottom || fresh[fresh.length-1].user_id === state.me.id) stream.scrollTop = stream.scrollHeight;
    })().finally(() => { pulling = null; });
    return pulling;
  };

  // --- 已读回执 ----------------------------------------------------------
  // 服务端只给「其他成员各自的已读位点」，这里按位点给自己每条消息算读数：
  // 群聊「n/总人数」「全部已读」，私聊「已读/未读」。轮询时一起刷新，
  // 所以别人刚读，旧气泡上的回执也会跟着变。
  let receipts = { total: 0, readers: [] };
  const applyReceipts = () => {
    document.querySelectorAll('.wx-receipt[data-receipt-for]').forEach(el => {
      const mid = Number(el.dataset.receiptFor);
      if (!mid) return;
      if (receipts.total <= 0){ el.textContent = ''; return; }
      const read = receipts.readers.filter(x => x.last_read_id >= mid).length;
      el.textContent = room.kind === 'private'
        ? (read ? '已读' : '未读')
        : (read >= receipts.total ? '全部已读' : `${read}/${receipts.total} 已读`);
    });
  };
  const pullReceipts = async () => {
    try{
      receipts = await api('/messages/receipts?room_id='+room.id);
      applyReceipts();
    }catch{ /* 回执拿不到不影响聊天 */ }
  };

  try{ await pullNew(); }catch(err){ toast(err.message); return; }
  stream.scrollTop = stream.scrollHeight;
  pullReceipts();

  // 用户侧的「猜你想问」只在新会话（还没有任何消息）时展示；
  // 一旦聊起来就收起，把输入区还给正常对话。
  const quick = $('#wx-quick');
  if (quick && room.support && !['support','admin','developer'].includes(state.me?.role)){
    quick.hidden = state.messageCursor > 0;
  }

  // --- 右键 / 长按菜单：复制、撤回、删除、移除 --------------------------
  // 三个操作的语义必须分清：
  //   撤回 —— 2 分钟内、只限自己发的，对所有人都生效（后端 removed=2）；
  //   删除 —— 只从我的聊天记录里抹掉，对方不受影响（后端 message_hides）；
  //   移除 —— 群主/管理员在群里处置他人消息（后端 removed=1）。
  const doRecall = async (mid, body) => {
    try{ await api('/messages/recall', {message_id:mid}); }catch(err){ toast(err.message); return; }
    recalledDrafts.set(mid, body);
    const el = document.querySelector(`.wx-msg[data-mid="${mid}"]`);
    if (el) el.outerHTML = `<div class="wx-sys wx-recalled" data-mid="${mid}">你撤回了一条消息 <button type="button" class="wx-reedit" data-action="reedit" data-id="${mid}">重新编辑</button></div>`;
    toast('已撤回，可重新编辑');
  };
  const doHide = async mid => {
    try{ await api('/messages/hide', {message_id:mid}); }catch(err){ toast(err.message); return; }
    document.querySelector(`.wx-msg[data-mid="${mid}"]`)?.remove();
  };
  const doRemove = async mid => {
    try{ await api('/moderate', {room_id:room.id, action:'remove_message', message_id:mid}); }catch(err){ toast(err.message); return; }
    const el = document.querySelector(`.wx-msg[data-mid="${mid}"]`);
    if (el) el.outerHTML = `<div class="wx-sys" data-mid="${mid}">消息已被移除</div>`;
    toast('已移除该消息');
  };
  const messageMenu = (msgEl, x, y) => {
    const mid = Number(msgEl.dataset.mid);
    const mine = msgEl.dataset.mine === '1';
    const created = Number(msgEl.dataset.created);
    const body = msgEl.querySelector('.wx-bubble')?.textContent || '';
    const items = [{
      label: '复制',
      run: () => navigator.clipboard.writeText(body).then(() => toast('已复制')).catch(() => toast('复制失败'))
    }];
    if (mine && Date.now()/1000 - created <= 120) items.push({ label: '撤回', run: () => doRecall(mid, body) });
    items.push({ label: '删除', danger: true, run: () => doHide(mid) });
    if (room.kind !== 'private' && (['owner','moderator'].includes(room.myRole||'') || isAdmin(state.me)))
      items.push({ label: '移除', danger: true, run: () => doRemove(mid) });
    openMessageMenu(x, y, items);
  };

  stream.addEventListener('contextmenu', ev => {
    const msgEl = ev.target.closest('.wx-msg');
    if (!msgEl) return;
    ev.preventDefault();
    messageMenu(msgEl, ev.clientX, ev.clientY);
  });
  // 手机没有右键：长按 500ms 打开同一个菜单；手指移动或抬起就取消，
  // 避免用户只是在滚动列表时误触。
  let pressTimer = null, pressEl = null;
  stream.addEventListener('touchstart', ev => {
    pressEl = ev.target.closest('.wx-msg');
    if (!pressEl) return;
    const t = ev.touches[0];
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => { if (pressEl) messageMenu(pressEl, t.clientX, t.clientY); pressEl = null; }, 500);
  }, {passive:true});
  const cancelPress = () => { clearTimeout(pressTimer); pressEl = null; };
  stream.addEventListener('touchend', cancelPress);
  stream.addEventListener('touchmove', cancelPress);
  stream.addEventListener('touchcancel', cancelPress);

  // 轮询：页面在后台时不发请求（省流量，也不和其它页面的接口抢带宽）；
  // 回执比消息低频——消息 3 秒一次，回执 9 秒一次就够，别人刚读的延迟可以接受。
  let tick = 0;
  state.poll = setInterval(async () => {
    if (document.hidden) return;
    try{ await pullNew(); }catch{ /* 轮询失败静默，下个周期再试 */ }
    if (tick++ % 3 === 0) pullReceipts();
  }, 3000);
  // 会话列表的摘要与角标低频刷新（不重绘页面，搜索词不丢）。
  state.poll2 = setInterval(async () => {
    if (document.hidden) return;
    try{
      Object.assign(rooms, await api('/rooms'));
      renderRoomList(rooms, notices, activeId);
    }catch{ /* 同上 */ }
  }, 8000);
}
