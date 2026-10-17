'use strict';
// 页面层 · 微信风格聊天室（私聊 / 学院群 / 总聊 / 订单通知）
// 布局：左侧会话列表（搜索、摘要、未读角标），右侧聊天窗
//（标题栏、成员抽屉、头像气泡、日期分隔、表情面板、撤回）。
import { $, e, icon, toast, uid } from '../core/dom.js';
import { date } from '../core/format.js';
import { state, clearPoll } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, empty } from '../core/shell.js';
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
export function renderMessage(m, room){
  if (m.removed === 2) return `<div class="wx-sys" data-mid="${m.id}">${m.user_id===state.me.id?'你撤回了一条消息':e(m.nickname)+' 撤回了一条消息'}</div>`;
  if (m.removed === 1) return `<div class="wx-sys" data-mid="${m.id}">${e(m.body)}</div>`;
  const mine = m.user_id === state.me.id;
  const showNick = room.kind !== 'private' && !mine;
  // 撤回按钮：自己的、两分钟内、还没被处理过的消息，悬浮时显示。
  const recallable = mine && (Date.now()/1000 - m.created) <= 120;
  // 移除按钮：群主/管理员在群里可移除任何人的消息；私聊不开放。
  const canModerate = room.kind !== 'private' &&
    (['owner','moderator'].includes(room.myRole||'') || state.me.role === 'admin');
  const acts = `<span class="wx-msg-acts">`+
    (recallable?`<button type="button" data-action="recall" data-id="${m.id}">撤回</button>`:'')+
    (canModerate?`<button type="button" data-action="remove-msg" data-id="${m.id}">移除</button>`:'')+
    `</span>`;
  return `<div class="wx-msg ${mine?'mine':''}" data-mid="${m.id}">${mine?acts:''}`+
    `<span class="wx-avatar-link" data-go="profile/${m.user_id}">${avatar(m.nickname, m.user_id)}</span>`+
    `<div class="wx-bubble-wrap">${showNick?`<span class="wx-nick">${e(m.nickname)}</span>`:''}`+
    `<p class="wx-bubble">${e(m.body)}</p></div>${mine?'':acts}</div>`;
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
  return `<button class="wx-room ${r.id===activeId?'sel':''}" data-go="messages/${r.id}" data-name="${e(r.name)}">`+
    avatar(r.name, r.id)+
    `<span class="wx-room-main"><span class="wx-room-top"><b>${e(r.name)}</b>`+
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
  const canMute = (iAm && ['owner','moderator'].includes(iAm.role)) || state.me.role === 'admin';
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

// --- 聊天页事件（经 actions 委托分派，见 actions/social.js 的合并） -------
export const chatClicks = {
  'toggle-members': (b, id) => toggleMembers(id),

  'wx-emoji': () => {
    const p = $('#wx-emoji');
    if (p) p.hidden = !p.hidden;
  },

  recall: async (b, id) => {
    await api('/messages/recall', {message_id:id});
    const el = document.querySelector(`.wx-msg[data-mid="${id}"]`);
    if (el) el.outerHTML = '<div class="wx-sys">你撤回了一条消息</div>';
    toast('已撤回');
  },

  'remove-msg': async (b, id) => {
    const roomId = Number(document.querySelector('#wx-form')?.dataset.room);
    await api('/moderate', {room_id:roomId, action:'remove_message', message_id:id});
    const el = document.querySelector(`.wx-msg[data-mid="${id}"]`);
    if (el) el.outerHTML = '<div class="wx-sys">消息已被移除</div>';
    toast('已移除该消息');
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
    <header class="wx-chat-head"><div class="wx-head-title"><h3>订单与售后通知</h3><small>下单、付款、交付、售后、社区的回复与@都会提醒你</small></div>
    ${notices.items.some(n=>!n.read_at)?'<button class="text-button" data-action="read-notices">全部标记已读</button>':''}</header>
    <div class="wx-stream notice-stream">${notices.items.map(n => {
      const [ic, tone] = NOTE_META[n.kind] || ['bell', 'mute'];
      const link = n.order_id ? `订单 #${n.order_id}` : n.ticket_id ? `工单 #${n.ticket_id}` : n.post_id ? `帖子 #${n.post_id}` : '';
      // 未读的通知整条可点：点了标记已读（actions/social.js 的 read-notice）。
      // 已读的不再挂 data-action——重复点击不该发重复请求。
      const attrs = n.read_at ? '' : ` data-action="read-notice" data-id="${n.id}"`;
      return `<div class="notice-item ${n.read_at?'':'unread'}"${attrs}><span class="notice-ic" data-tone="${tone}">${icon(ic)}</span><div><p>${e(n.body)}</p><small>${date(n.created)}${link?' · '+e(link):''}</small></div></div>`;
    }).join('')
      || '<div class="wx-sys">暂无通知</div>'}</div>` : '';

  const chatPanel = room ? `
    <header class="wx-chat-head">
      <button class="wx-back" data-go="messages">${icon('arrow')}</button>
      <div class="wx-head-title"><h3>${e(room.name)}</h3><small>${room.kind==='private'?'私聊':room.count+' 位成员'}</small></div>
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
    <footer class="wx-input">
      <div class="wx-toolbar">
        <button type="button" class="wx-tool" data-action="wx-emoji" title="表情">😊</button>
        <span class="wx-count" id="wx-count"></span>
      </div>
      <form id="wx-form" data-room="${room.id}">
        <textarea id="wx-editor" name="message" maxlength="2000" rows="1" placeholder="输入消息，Enter 发送，Shift+Enter 换行"></textarea>
        <div class="wx-send-row"><span class="muted">消息会经过平台自动审核</span><button class="btn primary sm" type="submit">发送</button></div>
      </form>
      <div class="wx-emoji-panel" id="wx-emoji" hidden></div>
    </footer>` : (noticeView ? noticePanel : empty('选择一个会话','可以在商品页联系卖家，或去社区加入群聊。'));

  shell(`<div class="wx-app">${side}<section class="wx-chat">${chatPanel}</section></div>`, 'messages');

  renderRoomList(rooms, notices, activeId);

  // 通知中心的未读是「浏览后消失」：点开就自动全部标记已读。
  // 本次渲染仍按未读高亮显示（用户能看到刚才有哪些没读），后台立即清掉，
  // 顶栏与「我的」页角标同步归零——不需要用户再找「全部标记已读」按钮。
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
  // 表单不走全站 submits 委托（避免双发）：发送后立即增量拉取，输入框清空。
  const form = $('#wx-form');
  const editor = $('#wx-editor');
  form.addEventListener('submit', async ev => {
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
  editor.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey){ ev.preventDefault(); form.requestSubmit(); }
  });
  editor.addEventListener('input', () => {
    editor.style.height = 'auto';
    editor.style.height = Math.min(editor.scrollHeight, 140)+'px';
    updateCount();
  });
  function updateCount(){ $('#wx-count').textContent = editor.value.length ? editor.value.length+'/2000' : ''; }

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
