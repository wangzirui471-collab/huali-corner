'use strict';
// 页面层 · 私聊 / 学院群 / 总聊
import { $, e, icon, toast } from '../core/dom.js';
import { date } from '../core/format.js';
import { state, clearPoll } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { panel } from '../core/inbox.js';
import { context } from '../core/context.js';
import { needLogin } from '../auth/login.js';

export function messageBubble(m){return `<div class="chat-message ${m.user_id===state.me.id?'mine':''}" data-message="${m.id}"><button data-go="profile/${m.user_id}" class="chat-name">${e(m.nickname)}</button><p>${e(m.body)}</p><small>${date(m.created)}</small></div>`;}
export async function chats(roomId){if(!needLogin())return;const rooms=await api('/rooms');const notices=await panel(context());let room=rooms.joined.find(r=>r.id===Number(roomId));shell(`${heading('STAY CONNECTED','消息','私聊、学院群与订单消息，各有自己的位置。')}${notices}<div class="chat-layout"><aside class="panel room-list"><button class="btn secondary full" data-go="orders">查看订单通知</button>${rooms.joined.map(r=>`<button class="room ${room?.id===r.id?'selected':''}" data-go="messages/${r.id}">${icon(r.kind==='private'?'user':'community')}<span>${e(r.name)}<small>${r.kind==='private'?'私聊':r.count+'位成员'}</small></span></button>`).join('')||'<p class="muted">还没有会话，去社区主动加入群聊。</p>'}<button class="text-button" data-go="community">去社区找同学 →</button></aside><section class="panel chat-panel">${room?`<div class="chat-title"><h3>${e(room.name)}</h3>${room.kind!=='private'?`<button class="text-button" data-action="nominate" data-id="${room.id}">申请管理员</button>`:`<button class="text-button" data-action="block-room" data-id="${room.id}">屏蔽对方</button>`}</div><div class="chat-stream" id="chat-stream"></div><form id="message-form" data-room="${room.id}" class="message-form"><input name="message" required maxlength="2000" placeholder="说点什么，友善交流…" autocomplete="off"><button class="btn primary">发送</button></form>`:empty('选择一个会话','可以在商品页联系卖家，或去社区加入群聊。')}</section></div>`,'messages');
 if(room){state.messageCursor=0;const load=async()=>{try{const messages=await api('/messages?room_id='+room.id+'&after='+state.messageCursor);const stream=$('#chat-stream');if(!stream)return;for(const msg of messages){if(msg.id>state.messageCursor){stream.insertAdjacentHTML('beforeend',messageBubble(msg));state.messageCursor=msg.id;}}if(messages.length)stream.scrollTop=stream.scrollHeight;}catch(err){clearPoll();toast(err.message);}};await load();state.poll=setInterval(load,3000);}}
