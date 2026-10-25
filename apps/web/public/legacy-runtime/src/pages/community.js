'use strict';
// 页面层 · 校园社区
import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell } from '../core/shell.js';
import { selectField } from '../components/forms.js';
import { isStaff } from '../core/roles.js';

// 分区配色与图标：和工单的 type-chip 同一套 tone。
// 「求购」已统一到论坛（#forum/wants），这里保留映射只为兼容历史帖子渲染。
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
  // 处置入口：客服/管理员/开发者能看到「删除」，但自己的帖子不出现
  // （后端也拦「不能处置自己发布的内容」）。
  const canRemove = isStaff(state.me) && p.user_id !== state.me?.id;
  return `<article class="panel post-card" data-post="${p.id}">
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
      ${canRemove ? `<button class="post-action danger" data-action="remove-post" data-id="${p.id}">
        ${icon('trash')}删除帖子
      </button>` : ''}
    </footer>
  </article>`;
}

// 社区首页。
// 求购已统一到论坛（#forum/wants），这里不再重复展示求购面板——避免同一批求购
// 在「社区」和「论坛」各出现一次。社区只负责自由交流：发帖、动态、社群入口，
// 并在首屏给出「去论坛求购」的明确入口，功能不丢、只是不再重复。
export async function community(){
  const posts = await api('/posts?limit=20');
  state.postsFeed = posts;
  shell(`
    <div class="community-hub">
      <section class="community-hero">
        <div class="community-hero-copy">
          <span class="community-eyebrow">CAMPUS COMMUNITY</span>
          <h1>校园社区</h1>
          <p>自由交流，分享日常，也聊聊校园生活。</p>
        </div>
        <div class="community-hero-actions">
          <a class="community-cta primary" href="#forum/wants">${icon('search')}去论坛求购</a>
          <a class="community-cta ghost" href="#forum">${icon('book')}逛论坛</a>
        </div>
      </section>

      <div class="community-grid">
        <section class="community-main">
          <form id="post-form" class="composer-card">
            <div class="composer-head">
              <div class="composer-title">
                <h2>跟同学说点什么</h2>
                <p>分享一个小发现，或者说说你最近在忙什么。</p>
              </div>
              ${selectField('分区','topic',['交流','毕业季','互助'])}
            </div>
            <textarea name="body" required maxlength="2000" placeholder="想找一本书，或者分享一个小发现…"></textarea>
            <div class="composer-foot">
              <small>不自动拉群 · 请勿泄露个人资料</small>
              <button class="btn primary">${icon('edit')}发布帖子</button>
            </div>
          </form>

          <div class="community-feed-head">
            <h2>最新动态</h2>
            <span>和同学聊聊校园里的事</span>
          </div>
          <div class="community-feed" id="post-list">${posts.length ? posts.map(postCard).join('') : `<div class="community-empty">${icon('message')}<b>还没有人发帖</b><p>来说第一句吧，让社区热闹起来。</p></div>`}</div>
          ${posts.length>=20?`<button class="btn secondary full load-more" id="post-more" data-action="load-more-posts">${icon('plus')}加载更多</button>`:''}
        </section>

        <aside class="community-side">
          <section class="group-card">
            <span class="community-eyebrow">FIND YOUR PEOPLE</span>
            <h2>在校园，找到同频的人</h2>
            <div class="group-art">${icon('community')}</div>
            <div class="group-item">
              <div class="group-item-head"><b>广州校区总聊</b><span class="group-badge">全员</span></div>
              <p>全员公共频道，自愿加入。</p>
              <button class="btn primary full" data-action="join" data-value="general">加入总聊</button>
            </div>
            <div class="group-item">
              <div class="group-item-head"><b>计算机工程学院交流群</b><span class="group-badge">500 人/群</span></div>
              <p>每群最多 500 人，满员自动新增下一群。</p>
              <button class="btn secondary full" data-action="join" data-value="college">加入学院群</button>
            </div>
            <p class="group-note">群主与管理员可自愿申请，平台审核授权；群权限不包含资金与退款。</p>
          </section>

          <section class="side-forum-card">
            <div class="side-forum-head"><h3>校园论坛</h3><a href="#forum">全部 ${icon('arrow')}</a></div>
            <a class="side-forum-link" href="#forum/wants"><span>${icon('search')}求购</span><small>想买什么直接喊</small></a>
            <a class="side-forum-link" href="#forum/exchange"><span>${icon('refresh')}交换人生</span><small>技能与时间互换</small></a>
            <a class="side-forum-link" href="#forum/errand"><span>${icon('truck')}代拿快递</span><small>跑腿与代取</small></a>
          </section>
        </aside>
      </div>
    </div>
  `,'community');
}
