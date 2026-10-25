'use strict';
import { $, e, icon } from '../core/dom.js';
import { date, money } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell } from '../core/shell.js';
import { BOARDS,postParts,postRow,wantRow,replyRow,avatar,forumEmpty,forumNotice } from '../components/forum.js';

let savedLayout='list';try{savedLayout=localStorage.getItem('hc-forum-layout')==='cards'?'cards':'list';}catch{}
export const forumState={q:'',sort:'latest',layout:savedLayout,board:'',rows:[],hasMore:false,post:null,replies:[],latest:false};
export const FORUM_PAGE=20;
const PAGE=FORUM_PAGE;
export const boardOf=key=>BOARDS.find(b=>b.key===key);

function nav(active=''){
  return `<nav class="forum-navigation" aria-label="论坛板块"><a href="#forum" ${!active?'aria-current="page"':''}>论坛首页</a>${BOARDS.map(b=>`<a href="#forum/${b.key}" ${active===b.key?'aria-current="page"':''}>${b.short}</a>`).join('')}<a href="#forum/account" ${active==='account'?'aria-current="page"':''}>我的帖子</a></nav>`;
}
function frame(content,active=''){
  shell(`<div class="forum-surface">${nav(active)}${content}</div>`,'forum');
  const search=$('.market-search');
  if(search){search.id='forum-search-form';const input=search.querySelector('input');input.name='q';input.value=forumState.q;input.placeholder='搜索论坛帖子、技能或需求';input.setAttribute('aria-label','搜索论坛帖子');}
}
function aside(){
  return `<aside class="forum-sidebar"><section class="forum-side-card"><h2>我的论坛</h2><a href="#forum/account">${icon('user')}我的帖子${icon('arrow')}</a><a href="#messages/notice">${icon('bell')}回复与通知${icon('arrow')}</a><a href="#me">${icon('user')}个人中心${icon('arrow')}</a></section><section class="forum-side-card forum-guidelines"><h2>交流之前</h2><p>把需求说清楚，让沟通更简单。</p><ul><li>尊重彼此，友善交流</li><li>公开内容中保护个人隐私</li><li>时间、地点和费用先沟通确认</li><li>遇到问题，可举报或联系平台</li></ul><a href="#support">社区帮助 ${icon('arrow')}</a></section></aside>`;
}
function heading(title,description,board='exchange'){
  return `<header class="forum-heading"><div><h1>${e(title)}</h1><p>${e(description)}</p></div><a class="forum-button primary" href="#forum-compose/${board}">${icon('plus')}${board==='wants'?'发布求购':'发布帖子'}</a></header>`;
}
export function postsURL(offset=0){
  const q=new URLSearchParams({limit:String(PAGE),offset:String(offset),sort:forumState.sort,q:forumState.q});
  const board=boardOf(forumState.board);
  if(board?.topic)q.set('topic',board.topic);else q.set('forum','1');
  if(forumState.board==='account')q.set('author',String(state.me.id));
  return '/posts?'+q;
}
export function wantsURL(offset=0){
  const q=new URLSearchParams({limit:String(PAGE),offset:String(offset),q:forumState.q});
  return '/wants?'+q;
}
function toolbar(wants=false){
  return `<div class="forum-toolbar"><div class="forum-sort" aria-label="帖子排序"><button data-action="forum-sort" data-value="latest" aria-pressed="${forumState.sort==='latest'}">最新</button><button data-action="forum-sort" data-value="hot" aria-pressed="${forumState.sort==='hot'}">${wants?'匹配最多':'热门'}</button></div><div class="forum-toolbar-end">${forumState.q?`<span class="forum-search-label">搜索：${e(forumState.q)}</span><button class="forum-clear-search" data-action="forum-clear-search" aria-label="清除搜索">${icon('close')}</button>`:''}<div class="forum-view-switch" aria-label="列表显示方式"><button data-action="forum-layout" data-value="list" aria-pressed="${forumState.layout==='list'}" aria-label="列表布局">${icon('list')}</button><button data-action="forum-layout" data-value="cards" aria-pressed="${forumState.layout==='cards'}" aria-label="卡片布局">${icon('device')}</button></div></div></div>`;
}
export async function forum(key=''){
  const rid=state.renderId;
  if(!key){
    const results=await Promise.allSettled([api('/wants'),api('/posts?topic=交换人生&limit=3'),api('/posts?topic=代拿快递&limit=3'),api('/posts?forum=1&limit=6')]);
    if(rid!==state.renderId)return;
    const cards=BOARDS.map((b,i)=>{
      const r=results[i],rows=r.status==='fulfilled'?r.value:[];
      const preview=r.status==='rejected'?'<span class="forum-small-error">暂时未能加载最新内容</span>':rows.length?rows.slice(0,2).map(p=>`<a href="#${i?'forum-post':'forum-want'}/${Number(p.id)}">${e(i?postParts(p.body).title:'求购 '+p.keyword)}<small>${e(p.nickname)}</small></a>`).join(''):'<span class="forum-small-empty">等待第一条分享</span>';
      return `<section class="forum-board-card"><div class="forum-board-heading"><span class="forum-board-icon">${icon(b.icon)}</span><a href="#forum/${b.key}"><h2>${b.name}</h2></a>${icon('arrow')}</div><p>${b.description}</p><div class="forum-board-preview">${preview}</div><a class="forum-board-link" href="#forum/${b.key}">浏览板块 ${icon('arrow')}</a></section>`;
    }).join('');
    const latest=results[3];
    frame(`${heading('校园论坛','把需要说清楚，把经验分享给同学。')}<div class="forum-board-grid">${cards}</div><div class="forum-columns"><section class="forum-content-card"><div class="forum-section-heading"><h2>最新讨论</h2><a href="#forum/latest">查看全部 ${icon('arrow')}</a></div><div class="forum-feed" data-layout="list">${latest.status==='rejected'?forumNotice('帖子暂时无法加载，请稍后重试。'):latest.value.length?latest.value.map(postRow).join(''):forumEmpty('这里，等你开启一段交流')}</div></section>${aside()}</div>`);
    return;
  }
  forumState.board=key;let rows;
  if(key==='wants'){
    rows=await api(wantsURL());
    if(forumState.sort==='hot')rows.sort((a,b)=>(b.matches||[]).length-(a.matches||[]).length||b.id-a.id);
    forumState.hasMore=rows.length===PAGE;
  }else{rows=await api(postsURL());forumState.hasMore=rows.length===PAGE;}
  if(rid!==state.renderId)return;
  forumState.rows=rows;const board=boardOf(key),title=key==='account'?'我的帖子':board?.name||'全部讨论';
  frame(`<div class="forum-breadcrumb"><a href="#forum">校园论坛</a><span>/</span><span>${title}</span></div>${heading(title,key==='account'?'你发布过的分享，都在这里。':board?.description||'看看同学最近在聊什么。',key==='wants'?'wants':board?.key||'exchange')}<div class="forum-columns"><section class="forum-content-card">${toolbar(key==='wants')}<div class="forum-feed" id="forum-feed" data-layout="${forumState.layout}">${rows.length?rows.map(p=>key==='wants'?wantRow(p,state.me?.id):postRow(p)).join(''):forumEmpty(forumState.q?'没有找到相关内容':'还没有帖子')}</div><div class="forum-load-row">${forumState.hasMore?'<button class="forum-button secondary" data-action="forum-more">加载更多帖子</button>':`<span>${rows.length?'已显示当前内容':'你可以切换板块，或发布第一条分享。'}</span>`}</div></section>${aside()}</div>`,key);
}
export async function forumPost(id){
  const rid=state.renderId;id=Number(id);const posts=await api('/posts?id='+id);
  if(rid!==state.renderId)return;
  const post=posts[0];
  if(!post){frame(`<a class="forum-back" href="#forum">返回论坛</a>${forumEmpty('帖子不存在或已被删除','可以返回论坛看看其他同学的分享。')}`);return;}
  forumState.post=post;forumState.latest=false;forumState.replies=[];
  const {title,body}=postParts(post.body),board=BOARDS.find(b=>b.topic===post.topic);
  frame(`<div class="forum-breadcrumb"><a href="#forum">校园论坛</a><span>/</span><a href="#forum/${board?.key||'latest'}">${e(post.topic)}</a><span>/</span><span>帖子详情</span></div><div class="forum-columns forum-detail-columns"><div class="forum-reading-column"><article class="forum-original"><div class="forum-article-topic">${e(post.topic)}</div><h1>${e(title)}</h1><div class="forum-author-line"><a href="#profile/${Number(post.user_id)}">${avatar(post.nickname,'large')}</a><div><a href="#profile/${Number(post.user_id)}"><b>${e(post.nickname)}</b></a><p><time>${date(post.created)}</time><span>楼主</span></p></div></div><div class="forum-prose forum-original-body">${e(body)}</div><footer class="forum-article-actions"><button class="forum-button primary" data-action="forum-focus-reply">${icon('edit')}参与讨论</button><button data-action="forum-share">${icon('share')}分享</button><button data-action="report-community" data-id="${id}">举报</button></footer></article><section class="forum-replies-section" aria-labelledby="forum-replies-title"><div class="forum-section-heading"><h2 id="forum-replies-title">全部回复 <span id="forum-reply-count">${Number(post.replies)||0}</span></h2><span>按时间顺序</span></div><div id="forum-replies"><p class="forum-loading">正在加载回复…</p></div><div id="forum-replies-more" class="forum-load-row"></div></section><section class="forum-composer-card" id="forum-reply-editor"><h2>参与讨论</h2><p class="forum-editor-context" id="forum-reply-target">回复楼主 · ${e(post.nickname)}</p><form id="forum-reply-form" data-post="${id}" data-parent="0"><label class="forum-sr-only" for="forum-reply-body">回复内容</label><textarea id="forum-reply-body" name="body" required maxlength="1000" rows="4" placeholder="写下你的想法，友善交流，让讨论更有帮助。"></textarea><div class="forum-editor-footer"><small>友善表达，保护彼此隐私。</small><div><button type="button" class="forum-button secondary" data-action="forum-cancel-target" hidden id="forum-cancel-target">取消引用</button><button class="forum-button primary" type="submit">发布回复</button></div></div></form></section></div><aside class="forum-sidebar"><section class="forum-side-card"><h2>关于作者</h2><a class="forum-author-side" href="#profile/${Number(post.user_id)}">${avatar(post.nickname,'large')}<b>${e(post.nickname)}</b></a>${post.college?`<p>${e(post.college)}</p>`:''}<a href="#profile/${Number(post.user_id)}">查看个人主页 ${icon('arrow')}</a></section><section class="forum-side-card"><h2>继续浏览</h2>${BOARDS.map(b=>`<a href="#forum/${b.key}">${b.name}${icon('arrow')}</a>`).join('')}</section></aside></div>`,board?.key);
  try{await refreshForumReplies(false,rid);}catch(err){if(rid===state.renderId&&$('#forum-replies'))$('#forum-replies').innerHTML=forumNotice('回复暂时无法加载，主帖仍可正常阅读。');}
}
let repliesSeq=0;
export async function refreshForumReplies(latest=false,rid=state.renderId){
  const post=forumState.post;if(!post)return;
  const seq=++repliesSeq;
  const rows=await api('/comments?id='+post.id+'&limit='+PAGE+(latest?'':'&order=asc&after=0'));
  if(rid!==state.renderId||seq!==repliesSeq||!$('#forum-replies'))return;
  // 合并而不是整体替换：并发两条回复时，后到的旧响应可能少一条，
  // 直接替换会把先到的那条盖掉（就是「回复被覆盖」）。
  const byId=new Map();
  (forumState.replies||[]).forEach(c=>byId.set(c.id,c));
  rows.forEach(c=>byId.set(c.id,c));
  let merged=[...byId.values()].sort((a,b)=>a.id-b.id);
  if(latest)merged=merged.slice(-PAGE);
  forumState.replies=merged;forumState.latest=latest;
  const start=latest?Math.max(0,Number(post.replies)-merged.length):0;
  $('#forum-replies').innerHTML=merged.length?merged.map((c,i)=>replyRow(c,start+i+1)).join(''):forumEmpty('还没有回复','写下你的想法，让讨论开始。');
  $('#forum-replies-more').innerHTML=latest&&start?'<button class="forum-button secondary" data-action="forum-first-replies">从第一楼开始阅读</button>':rows.length===PAGE?'<button class="forum-button secondary" data-action="forum-more-replies">加载更多回复</button>':'';
}
export async function forumWant(id){
  const rid=state.renderId,w=await api('/want?id='+Number(id));if(rid!==state.renderId)return;
  frame(`<div class="forum-breadcrumb"><a href="#forum">校园论坛</a><span>/</span><a href="#forum/wants">校园求购</a><span>/</span><span>需求详情</span></div><div class="forum-columns"><article class="forum-original"><div class="forum-article-topic">校园求购 · ${w.status==='matched'?'已成交':'寻找中'}</div><h1>求购 ${e(w.keyword)}</h1><div class="forum-author-line">${avatar(w.nickname,'large')}<div><a href="#profile/${Number(w.user_id)}"><b>${e(w.nickname)}</b></a><p>${date(w.created)}</p></div></div><p class="forum-detail-budget">预算 ¥${money(w.budget)}</p><div class="forum-prose forum-original-body">${e(w.description||'这位同学暂未补充物品要求，可以先查看匹配商品或通过好友申请沟通。')}</div><div class="forum-article-actions"><button class="forum-button primary" data-action="want-matches" data-id="${Number(w.id)}">查看 ${(w.matches||[]).length} 件匹配</button>${w.user_id!==state.me?.id&&w.status==='open'?`<button class="forum-button secondary" data-action="want-respond" data-id="${Number(w.id)}" data-user="${Number(w.user_id)}" data-name="${e(w.nickname)}" data-keyword="${e(w.keyword)}">我能卖</button>`:''}</div></article>${aside()}</div>`,'wants');
}
export function forumCompose(key='exchange'){
  const b=boardOf(key)||boardOf('exchange'),want=b.key==='wants';
  frame(`<div class="forum-breadcrumb"><a href="#forum">校园论坛</a><span>/</span><a href="#forum/${b.key}">${b.name}</a><span>/</span><span>发布</span></div><div class="forum-editor-page"><header><h1>${want?'发布求购':'发布帖子'}</h1><p>一个清楚的标题，让需要的同学更容易找到你。</p></header><form id="${want?'forum-want-form':'forum-post-form'}"><label>发布板块<select name="board">${BOARDS.filter(x=>want?x.key==='wants':x.topic).map(x=>`<option value="${x.key}" ${x.key===b.key?'selected':''}>${x.name}</option>`).join('')}</select></label><label>${want?'想买什么':'帖子标题'}<input name="title" required maxlength="${want?40:80}" placeholder="${want?'例如：数据结构教材，第二版':'用一句话说明你想分享或寻找什么'}"></label>${want?'<label>预算（元）<input type="number" name="budget" required min="0.01" max="10000" step="0.01" placeholder="请输入预算"></label>':''}<label>${want?'补充要求':'正文'}<textarea name="body" rows="10" ${want?'':'required'} maxlength="${want?1000:1900}" placeholder="${want?'物品版本、成色和希望的交接方式…':'你能提供什么、希望获得什么，或者分享一段实用的经验…'}"></textarea></label><div class="forum-editor-footer"><small>请勿公开手机号、宿舍房号或其他个人隐私。</small><div><a class="forum-button secondary" href="#forum/${b.key}">返回板块</a><button class="forum-button primary" type="submit">${want?'发布求购':'发布帖子'}</button></div></div></form></div>`,b.key);
}
