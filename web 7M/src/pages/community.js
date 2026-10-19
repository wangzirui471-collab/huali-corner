'use strict';
// 页面层 · 社区（2026-10 拆分后：好友与聊天中心）
//
// 论坛负责「发信息」（求购/交换人生/代拿快递），社区负责「找到人」：
//   新的朋友 —— 收到的申请（同意/拒绝）、发出的申请（等待中）；
//   好友 —— 已成为好友的人，点「发消息」进聊天；
//   会话 —— 已有的私聊/群聊，点进微信风格聊天页。
//
// 私聊门槛：只有互为好友才能聊天（服务端 send_message 会拦，客服会话豁免）。
// 申请附言最多 15 字、不能发图片——这是产品规则，不是前端装饰。
import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

// 帖子卡仍由本模块导出：论坛页与动作层都复用它。
const TOPICS = {
  '交流':   { tone: 'info',   icon: 'message' },
  '求购':   { tone: 'warn',   icon: 'search' },
  '毕业季': { tone: 'violet', icon: 'heart' },
  '互助':   { tone: 'ok',     icon: 'check' },
  '交换人生': { tone: 'violet', icon: 'refresh' },
  '代拿快递': { tone: 'ok',     icon: 'truck' }
};

export function postCard(p) {
  const topic = TOPICS[p.topic] || { tone: 'mute', icon: 'message' };
  const replies = Number(p.replies) || 0;
  return `<article class="panel post-card">
    <header class="post-head">
      <button class="post-author" data-go="profile/${p.user_id}" aria-label="查看 ${e(p.nickname)} 的主页">
        <span class="avatar post-avatar">${e((p.nickname || '?')[0])}</span>
        <span class="post-who"><b>${e(p.nickname)}</b><small>${date(p.created)}</small></span>
      </button>
      <span class="type-chip" data-tone="${topic.tone}">${icon(topic.icon)}${e(p.topic)}</span>
    </header>
    <p class="post-body">${e(p.body)}</p>
    <footer class="post-actions">
      <button class="post-action" data-action="comments" data-id="${p.id}">
        ${icon('message')}评论 / 回复${replies ? `<span class="reply-count">${replies}</span>` : ''}
      </button>
      <button class="post-action quiet" data-action="report-community" data-id="${p.id}">
        ${icon('alert')}举报
      </button>
    </footer>
  </article>`;
}

function friendRow(f) {
  const meta = [f.college, f.grade].filter(Boolean).join(' · ') || '学院未填写';
  return `<div class="friend-row">
    <span class="avatar friend-avatar">${e((f.nickname || '?')[0])}</span>
    <div class="friend-main"><b>${e(f.nickname)}</b><small>${e(meta)} · 信誉 ${f.score}</small></div>
    <button class="btn secondary sm" data-action="friend-message" data-id="${f.user_id}">${icon('message')}发消息</button>
  </div>`;
}

function requestRow(f, incoming) {
  const meta = [f.college, f.grade].filter(Boolean).join(' · ');
  return `<div class="friend-request-row">
    <span class="avatar friend-avatar">${e((f.nickname || '?')[0])}</span>
    <div class="friend-main">
      <b>${e(f.nickname)}</b><small>${e(meta || '学院未填写')} · ${date(f.created)}</small>
      ${f.message ? `<p class="friend-note">「${e(f.message)}」</p>` : ''}
      ${f.want_id ? '<small class="friend-want">回应了你的求购</small>' : ''}
    </div>
    ${incoming
      ? `<div class="friend-request-actions"><button class="btn primary sm" data-action="friend-accept" data-id="${f.id}">同意</button><button class="btn secondary sm" data-action="friend-reject" data-id="${f.id}">拒绝</button></div>`
      : '<span class="tag">等待对方处理</span>'}
  </div>`;
}

export async function community() {
  if (!needLogin()) return;
  const [box, rooms] = await Promise.all([api('/friends'), api('/rooms')]);
  const incoming = box.incoming || [];
  const joined = (rooms.joined || []);
  // 群入口：/api/rooms 返回的是 general（总聊房间）与 college（我的学院名），
  // 不是 available 列表。已加入的群不重复出现在「加入群聊」里。
  const joinedKinds = new Set(joined.map(r => r.kind));
  const groups = [];
  if (rooms.general && !joinedKinds.has('general')) {
    groups.push({ kind: 'general', name: rooms.general.name || '广州校区总聊', count: rooms.general.count });
  }
  if (rooms.college && !joinedKinds.has('college')) {
    groups.push({ kind: 'college', name: rooms.college + '交流群', count: null });
  }

  shell(`${heading('FIND YOUR PEOPLE', '社区', '先加好友，再慢慢聊。')}
  <div class="community-page">
    <section class="panel friends-panel">
      <div class="friends-head">
        <div><h2>好友</h2><p class="muted">${box.friends.length} 位好友 · 只有好友之间才能私聊</p></div>
        <span class="friends-count">${box.friends.length}</span>
      </div>
      ${incoming.length ? `<div class="friends-block"><h3>新的朋友 <i class="me-badge inline">${incoming.length}</i></h3>${incoming.map(f => requestRow(f, true)).join('')}</div>` : ''}
      ${box.outgoing.length ? `<div class="friends-block"><h3>等待验证</h3>${box.outgoing.map(f => requestRow(f, false)).join('')}</div>` : ''}
      <div class="friends-block">
        <h3>我的好友</h3>
        ${box.friends.length ? box.friends.map(friendRow).join('') : '<div class="forum-empty small"><b>还没有好友</b><p>去商品页或论坛点「加好友」，对方同意后就能聊天。</p></div>'}
      </div>
    </section>

    <section class="panel rooms-panel">
      <div class="friends-head"><div><h2>会话</h2><p class="muted">私聊与群聊都在这里</p></div></div>
      ${joined.length ? `<div class="room-list">${joined.map(r => `<button class="room-row" data-go="messages/${r.id}">
        <span class="avatar room-avatar">${e((r.name || '群')[0])}</span>
        <span class="room-main"><b>${e(r.name || '会话')}</b><small>${e(r.last_body || '还没有消息')}</small></span>
        ${r.unread ? `<i class="me-badge">${r.unread}</i>` : ''}
      </button>`).join('')}</div>` : '<div class="forum-empty small"><b>还没有会话</b><p>加了好友之后，从好友列表点「发消息」开始。</p></div>'}
      <div class="friends-block">
        <h3>加入群聊</h3>
        ${groups.length ? groups.map(r => `<button class="room-row" data-action="join" data-value="${r.kind}">
          <span class="avatar room-avatar">${icon('community')}</span>
          <span class="room-main"><b>${e(r.name)}</b><small>${r.count != null ? r.count + ' 人在群' : '点击加入'}</small></span>
        </button>`).join('') : '<p class="muted">已加入全部群聊。</p>'}
      </div>
    </section>
  </div>`, 'community');
}
