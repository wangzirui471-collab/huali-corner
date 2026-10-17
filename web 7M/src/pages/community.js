'use strict';
// 页面层 · 校园社区
import { $, e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { selectField } from '../components/forms.js';

// 分区配色与图标：和工单的 type-chip 同一套 tone，
// 「求购」偏橙（有交易意图）、「互助」偏绿（纯帮忙）、「毕业季」偏紫。
const TOPICS = {
  '交流':   { tone: 'info',   icon: 'message' },
  '求购':   { tone: 'warn',   icon: 'search' },
  '毕业季': { tone: 'violet', icon: 'heart' },
  '互助':   { tone: 'ok',     icon: 'check' }
};

// 一张帖子卡：作者行（头像 + 名字 + 时间）、正文、底部操作条。
// 正文用 pre-wrap 保留换行——同学发「第一行求、第二行条件」很常见，
// 折成一段就读不懂了。
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

export async function community(){const [posts,wants]=await Promise.all([api('/posts?limit=20'),api('/wants')]);state.postsFeed=posts;shell(`${heading('SAME CAMPUS, MORE CONNECTIONS','校园社区','自由交流，分享求购，也聊聊校园生活。')}<div class="community-layout"><section><section class="panel want-board"><div class="section-heading"><h2>校园求购</h2><button class="btn primary" data-action="open-want">${icon('search')}发布求购</button></div><p class="muted">想买什么直接喊，平台帮你匹配在售卖家；成交收 5% 撮合服务费（模拟）。</p>${wants.length?`<div class="want-list">${wants.map(w=>`<div class="want-row"><div class="want-head"><b>求购 ${e(w.keyword)}</b><span class="tag">预算 ¥${money(w.budget)}</span>${w.status==='matched'?'<span class="tag">已成交</span>':''}</div><small>${e(w.nickname)} · ${w.matches.length} 件匹配 · ${date(w.created)}</small>${w.status==='open'?`<button class="text-button" data-action="want-matches" data-id="${w.id}">查看匹配</button>`:''}</div>`).join('')}</div>`:'<p class="muted">还没有求购，来发第一条。</p>'}</section><form id="post-form" class="panel"><div class="section-heading"><h2>跟同学说点什么</h2>${selectField('分区','topic',['交流','求购','毕业季','互助'])}</div><textarea name="body" required maxlength="2000" placeholder="想找一本书，或者分享一个小发现…"></textarea><div class="submit-row"><small>不自动拉群 · 请勿泄露个人资料</small><button class="btn primary">发布帖子</button></div></form><div id="post-list">${posts.map(postCard).join('')}</div>${posts.length>=20?`<button class="btn secondary full load-more" id="post-more" data-action="load-more-posts">${icon('plus')}加载更多</button>`:''}</section><aside class="panel community-groups"><span class="eyebrow">FIND YOUR PEOPLE</span><h2>在校园，找到同频的人</h2><div class="group-art">${icon('community')}</div><h3>广州校区总聊</h3><p>全员公共频道，自愿加入。</p><button class="btn primary full" data-action="join" data-value="general">加入总聊</button><hr><h3>计算机工程学院交流群</h3><p>每群最多500人，满员自动新增下一群。</p><button class="btn secondary full" data-action="join" data-value="college">加入学院群</button><p class="muted">群主与管理员可自愿申请，平台审核授权；群权限不包含资金与退款。</p></aside></div>`,'community');}
