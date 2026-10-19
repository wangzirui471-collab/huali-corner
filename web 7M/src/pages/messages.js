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
    `<p class="wx-bubble">${e(m.body)}</p></div></div>`;
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

function roomPreview(r){
  if (r.last_body) return (r.last_nick && r.kind!=='private' ? r.last_nick+'：' : '') + r.last_body;
  return '暂无消息';
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
  return `<button class="wx-room ${r.id===activeId?'sel':''}" data-go="messages/${r.id}" data-name="${e(r.name)}">`+
    avatar(isSupport && !isStaff ? (r.assignee_name||'客服') : r.name, r.id, isSupport?'support':'')+
    `<span class="wx-room-main"><span class="wx-room-top"><b>${e(title)}</b>${tag}`+
    `<small class="wx-room-time">${r.last_at?e(hhmm(r.last_at)):''}</small></span>`+
    `<span class="wx-room-preview">${e(roomPreview(r))}${r.muted?icon('bell','wx-mute-ic'):''}</span></span>`+
    (r.unread?`<i class="wx-badge">${r.unread>99?'99+':r.unread}</i>`:'')+
    `</button>`;
}

function renderRoomList(rooms, notices, activeId){
  const list = $('#wx-list');
  if (!list) return;
  const kw = searchWord.trim().toLowerCase();
  const joined = rooms.joined
    .filter(r => !kw || String(r.name).toLowerCase().includes(kw))
    .sort((a,b) => (b.last_at||0) - (a.last_at||0));
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

// --- 聊天页事件（经 actions 委托分派，见 actions/social.js 的合并） -------
export const chatClicks = {
  'toggle-members': (b, id) => toggleMembers(id),

  'wx-emoji': () => {
    const p = $('#wx-emoji');
    if (p) p.hidden = !p.hidden;
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
  }
};

// --- 页面入口 ------------------------------------------------------------
export async function chats(roomId){
  if (!needLogin()) return;
  const [rooms, notices] = await Promise.all([api('/rooms'), api('/notifications')]);
  const noticeView = String(roomId) === 'notice';
  const room = noticeView ? null : rooms.joined.find(r => r.id === Number(roomId));
  // rooms 里的 role 是我在这群的群角色，补进 room 供「移除消息」判断。
  if (room) room.myRole = room.role;
  // 好友门槛（2026-10）：普通私聊只有互为好友才能发消息，客服会话豁免。
  // 历史会话保留可读，但输入区换成「还不是好友」的说明，避免发送后才报错。
  let gate = null;
  if (room && room.kind === 'private' && !room.support) {
    try {
      const mem = await api('/room/members?room_id=' + room.id);
      const peer = (mem.members || []).find(m => m.user_id !== state.me.id);
      if (peer) {
        const st = await api('/friend/state?user_id=' + peer.user_id);
        if (st.state !== 'accepted') gate = { peer, state: st.state };
      }
    } catch { /* 拿不到成员就不拦，交给服务端 */ }
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
  ticket: ['shield', 'warn'], content_removed: ['alert', 'danger']
};

// 通知中心：沿用原来的数据，套微信聊天窗的壳。
  const noticePanel = noticeView ? `
    <header class="wx-chat-head"><div class="wx-head-title"><h3>订单与售后通知</h3><small>打开本页即视为已读；下单、付款、交付、售后、社区的回复与@都会提醒你</small></div></header>
    <div class="wx-stream notice-stream">${notices.items.map(n => {
      const [ic, tone] = NOTE_META[n.kind] || ['bell', 'mute'];
      const link = n.order_id ? `订单 #${n.order_id}` : n.ticket_id ? `工单 #${n.ticket_id}` : n.post_id ? `帖子 #${n.post_id}` : '';
      // 打开通知页即视为已读（下方会自动标记并清角标），所以这里一律渲染成
      // 已读样式——不再保留黄色高亮。之前「保留高亮到下次打开」的设计
      // 被用户反馈为困惑：点开看到了黄色，点它又没反应，像坏了。
      return `<div class="notice-item"><span class="notice-ic" data-tone="${tone}">${icon(ic)}</span><div><p>${e(n.body)}</p><small>${date(n.created)}${link?' · '+e(link):''}</small></div></div>`;
    }).join('')
      || '<div class="wx-sys">暂无通知</div>'}</div>` : '';

  const chatPanel = room ? `
    <header class="wx-chat-head">
      <button class="wx-back" data-go="messages">${icon('arrow')}</button>
      <div class="wx-head-title"><h3>${e(room.name)}</h3><small>${room.support?`客服会话${room.ticket_id?` · <span class="wx-ticket-link" data-go="ticket/${room.ticket_id}">工单 #${room.ticket_id}</span>`:''}`:(room.kind==='private'?'私聊':room.count+' 位成员')}</small></div>
      <div class="wx-head-actions">
        ${room.kind!=='private'?`<button class="text-button" data-action="toggle-members" data-id="${room.id}">成员</button>
        <button class="text-button" data-action="nominate" data-id="${room.id}">申请管理员</button>`
        :`<button class="text-button" data-action="block-room" data-id="${room.id}">屏蔽对方</button>`}
      </div>
    </header>
    <div class="wx-chat-body">
      <div class="wx-stream" id="chat-stream"></div>
      <aside class="wx-members" id="wx-members" hidden></aside>
    </div>
    ${gate ? `<footer class="wx-gate">
      <b>还不是好友，暂时不能发消息</b>
      <p>对方同意好友申请后才能聊天；申请附言最多 15 个字，不能发图片。</p>
      ${gate.state === 'pending_out'
        ? '<span class="tag">已发送申请，等对方处理</span>'
        : `<button class="btn primary sm" data-action="add-friend" data-id="${gate.peer.user_id}" data-name="${e(gate.peer.nickname || '')}">加好友</button>`}
    </footer>` : `<footer class="wx-input">
      <div class="wx-toolbar">
        <button type="button" class="wx-tool" data-action="wx-emoji" title="表情">😊</button>
        <span class="wx-count" id="wx-count"></span>
      </div>
      <form id="wx-form" data-room="${room.id}">
        <textarea id="wx-editor" name="message" maxlength="2000" rows="1" placeholder="输入消息，Enter 发送，Shift+Enter 换行"></textarea>
        <div class="wx-send-row"><span class="muted">消息会经过平台自动审核</span><button class="btn primary sm" type="submit">发送</button></div>
      </form>
      <div class="wx-emoji-panel" id="wx-emoji" hidden></div>
    </footer>`}` : (noticeView ? noticePanel : empty('选择一个会话','可以在商品页联系卖家，或去社区加入群聊。'));

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

  // 搜索会话（客户端过滤，不整页重绘）。
  $('#wx-search-input')?.addEventListener('input', ev => {
    searchWord = ev.target.value;
    renderRoomList(rooms, notices, activeId);
  });

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

  // --- 表情面板 ----------------------------------------------------------
  const EMOJIS = ['😀','😁','😂','🤣','😊','😍','😘','😜','🤔','😅','😭','😤','😡','🥺','😱','🤗','🤩','😴','🤝','👍','👎','👏','🙏','💪','🎉','🔥','❤️','💔','💯','⚡','🌹','🌈','☀️','🌙','⭐','📚','✏️','🎓','🏀','⚽','🍜','🍵','💰','🎁','📦','🛒','✅','❌'];
  const emojiPanel = $('#wx-emoji');
  // 非好友（gate）分支没有输入区，表情面板也不存在——存在才初始化。
  if (emojiPanel){
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
  }

  // --- 发送与输入 --------------------------------------------------------
  // 表单不走全站 submits 委托（避免双发）：发送后立即增量拉取，输入框清空。
  const form = $('#wx-form');
  const editor = $('#wx-editor');
  // gate 分支（还不是好友）只有说明，没有表单；历史消息仍可读。
  form?.addEventListener('submit', async ev => {
    ev.preventDefault();
    const body = editor.value.trim();
    if (!body) return;
    try{
      await api('/messages', {room_id:room.id, body, key:uid()});
    }catch(err){ toast(err.message); return; }
    editor.value = '';
    editor.style.height = 'auto';
    updateCount();
    await pullNew();
  });
  // Enter 发送、Shift+Enter 换行、输入时自动加高。
  editor?.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey){ ev.preventDefault(); form.requestSubmit(); }
  });
  editor?.addEventListener('input', () => {
    editor.style.height = 'auto';
    editor.style.height = Math.min(editor.scrollHeight, 140)+'px';
    updateCount();
  });
  function updateCount(){ const c=$('#wx-count'); if (c && editor) c.textContent = editor.value.length ? editor.value.length+'/2000' : ''; }

  // --- 消息拉取（首次全量最近 200 条，之后增量轮询） ----------------------
  const stream = $('#chat-stream');
  state.messageCursor = 0;
  const pullNew = async () => {
    const msgs = await api('/messages?room_id='+room.id+'&after='+state.messageCursor);
    if (!msgs.length) return;
    const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 80;
    const id = appendMessages(stream, msgs, room);
    if (id && id > state.messageCursor) state.messageCursor = id;
    // 用户本来就在底部、或消息是自己发的：自动滚到底；否则保持位置并提示有新消息。
    if (atBottom || msgs[msgs.length-1].user_id === state.me.id) stream.scrollTop = stream.scrollHeight;
  };
  try{ await pullNew(); }catch(err){ toast(err.message); return; }
  stream.scrollTop = stream.scrollHeight;

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

  state.poll = setInterval(async () => {
    try{ await pullNew(); }catch{ /* 轮询失败静默，下个周期再试 */ }
  }, 3000);
  // 会话列表的摘要与角标低频刷新（不重绘页面，搜索词不丢）。
  state.poll2 = setInterval(async () => {
    try{
      Object.assign(rooms, await api('/rooms'));
      renderRoomList(rooms, notices, activeId);
    }catch{ /* 同上 */ }
  }, 8000);
}
