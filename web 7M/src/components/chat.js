import { e, icon } from '../core/dom.js';

export function roomButtons(rooms,activeId){
 return rooms.map(room=>`<button class="room ${room.id===activeId?'selected':''}" data-go="messages/${room.id}">${icon(room.kind==='private'?'user':'community')}<span>${e(room.name)}${room.unread_count?`<b class="tag">${room.unread_count>99?'99+':room.unread_count}条未读</b>`:''}<small>${room.last_message?e(room.last_message.body.slice(0,36)):room.kind==='private'?'私聊':room.count+'位成员'}</small></span></button>`).join('')||'<p class="muted">还没有会话，去社区主动加入群聊。</p>';
}
