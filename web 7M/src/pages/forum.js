'use strict';
// 页面层 · 论坛（2026-10 从原「校园社区」拆出）
//
// 三个板块，各自独立：
//   求购 —— 发求购、看别人的求购、点「我能卖」向求购者发起好友申请；
//   交换人生 —— 技能与时间互换（教吉他换修电脑、拍照换家教…）；
//   代拿快递 —— 代取快递、带饭、搬运等跑腿信息。
//
// 边界：代考、代课签到一类违反学术诚信的内容不设分区，服务端词库也会拦截。
// 聊天与好友不在这里，在「社区」页。
import { $, e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { postCard } from './community.js';

const TABS = [
  ['wants', '求购', '想买什么直接喊，匹配在售卖家', 'search'],
  ['exchange', '交换人生', '技能、时间、经验互换', 'refresh'],
  ['errand', '代拿快递', '代取快递、带饭、搬运', 'truck']
];

// 发帖表单：topic 用隐藏域锁定，不给用户改——分区是页面定的。
function postComposer(topic, placeholder){
  return `<form id="post-form" class="panel forum-composer">
    <input type="hidden" name="topic" value="${e(topic)}">
    <textarea name="body" required maxlength="2000" rows="3" placeholder="${e(placeholder)}"></textarea>
    <div class="submit-row"><small>不自动拉群 · 请勿泄露个人资料</small><button class="btn primary">发布</button></div>
  </form>`;
}

function wantRow(w){
  const mine = state.me && w.user_id === state.me.id;
  const matched = w.status === 'matched';
  return `<div class="want-row">
    <div class="want-head"><b>求购 ${e(w.keyword)}</b><span class="tag">预算 ¥${money(w.budget)}</span>${matched ? '<span class="tag muted-tag">已成交</span>' : ''}</div>
    <small>${e(w.nickname)} · ${w.matches.length} 件匹配 · ${date(w.created)}</small>
    ${w.description ? `<p class="want-desc">${e(w.description)}</p>` : ''}
    <div class="want-actions">
      ${w.status === 'open' ? `<button class="text-button" data-action="want-matches" data-id="${w.id}">查看匹配</button>` : ''}
      ${!mine && w.status === 'open' ? `<button class="btn primary sm" data-action="want-respond" data-id="${w.id}" data-user="${w.user_id}" data-name="${e(w.nickname)}" data-keyword="${e(w.keyword)}">我能卖</button>` : ''}
      ${mine ? '<span class="tag">这是我发布的</span>' : ''}
    </div>
  </div>`;
}

export async function forum(){
  const [wants, exchange, errand] = await Promise.all([
    api('/wants'), api('/posts?topic=交换人生&limit=20'), api('/posts?topic=代拿快递&limit=20')
  ]);
  state.postsFeed = exchange;

  shell(`${heading('SAME CAMPUS, MORE CONNECTIONS', '校园论坛', '求购、交换、跑腿，先说清楚需求再私聊。')}
  <div class="forum-page">
    <div class="forum-tabs" role="tablist">
      ${TABS.map(([key, label, hint, ic], i) => `<button class="forum-tab${i === 0 ? ' active' : ''}" role="tab" data-forum-tab="${key}" aria-selected="${i === 0}">
        <span class="forum-tab-icon">${icon(ic)}</span><b>${label}</b><small>${hint}</small></button>`).join('')}
    </div>

    <section class="forum-panel" data-forum-tab="wants">
      <div class="forum-panel-head"><div><h2>校园求购</h2><p class="muted">看到想卖的就点「我能卖」，对方同意好友后即可私聊协商。</p></div>
        <button class="btn primary" data-action="open-want">${icon('plus')}发布求购</button></div>
      ${wants.length ? `<div class="want-list">${wants.map(wantRow).join('')}</div>` : '<div class="forum-empty"><b>还没有求购</b><p>来发第一条，让有货的同学看到你。</p></div>'}
    </section>

    <section class="forum-panel" data-forum-tab="exchange" hidden>
      <div class="forum-panel-head"><div><h2>交换人生</h2><p class="muted">我会什么、想换什么，写清楚就能找到同频的人。不涉及代考、代课签到等违规内容。</p></div></div>
      ${postComposer('交换人生', '比如：会剪视频，想换吉他入门教学；或者周末可以帮拍毕业照，换一顿饭。')}
      <div class="post-list">${exchange.length ? exchange.map(postCard).join('') : '<div class="forum-empty"><b>还没有交换帖</b><p>写下你能提供的技能或时间，第一条就从你开始。</p></div>'}</div>
    </section>

    <section class="forum-panel" data-forum-tab="errand" hidden>
      <div class="forum-panel-head"><div><h2>代拿快递</h2><p class="muted">代取快递、带饭、搬运，写清地点和酬谢，私聊确认后再行动。</p></div></div>
      ${postComposer('代拿快递', '比如：明天下午去菜鸟驿站，可帮带 2 件到 A1 楼下，酬谢 2 元/件。')}
      <div class="post-list">${errand.length ? errand.map(postCard).join('') : '<div class="forum-empty"><b>还没有跑腿信息</b><p>发一条你顺路能带的，或者你需要人带的。</p></div>'}</div>
    </section>
  </div>`, 'forum');

  document.querySelectorAll('[data-forum-tab]').forEach(tab => {
    tab.onclick = () => {
      document.querySelectorAll('[data-forum-tab]').forEach(t => {
        t.classList.toggle('active', t === tab);
        t.setAttribute('aria-selected', String(t === tab));
      });
      document.querySelectorAll('.forum-panel').forEach(panel => {
        panel.hidden = panel.dataset.forumTab !== tab.dataset.forumTab;
      });
    };
  });
}
