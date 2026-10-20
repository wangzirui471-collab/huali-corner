'use strict';
import { e, icon } from '../core/dom.js';
import { date, money } from '../core/format.js';
export const BOARDS = [
  {key:'wants',name:'校园求购',short:'求购',description:'让需要的好物，找到有它的同学。',icon:'search'},
  {key:'exchange',name:'交换人生',short:'交换人生',topic:'交换人生',description:'分享你的技能，交换时间与经验。',icon:'refresh'},
  {key:'errand',name:'代拿快递',short:'代拿快递',topic:'代拿快递',description:'顺路帮一点忙，让校园生活更方便。',icon:'bag'}
];
export function postParts(value){
  const text=String(value||'').trim(),lines=text.split(/\r?\n/),first=lines[0]||'未命名帖子';
  return {title:first.length>72?first.slice(0,72)+'…':first,body:lines.length>1&&first.length<=72?lines.slice(1).join('\n').trim():text};
}
export function avatar(name,size=''){
  return `<span class="forum-avatar ${size}" aria-hidden="true">${e([...String(name||'同学')][0])}</span>`;
}
export function postRow(p){
  const {title,body}=postParts(p.body);
  return `<article class="forum-post-row" data-forum-post="${Number(p.id)}"><div class="forum-post-main"><div class="forum-row-heading">${p.pinned?'<span class="forum-pin">置顶</span>':''}<a class="forum-post-title" href="#forum-post/${Number(p.id)}">${e(title)}</a></div><p class="forum-excerpt">${e(body)}</p><div class="forum-post-meta"><span>${e(p.topic)}</span><span class="forum-meta-author">${avatar(p.nickname)}<a href="#profile/${Number(p.user_id)}">${e(p.nickname)}</a></span><time>${date(p.created)}</time></div></div><div class="forum-post-stats"><a href="#forum-post/${Number(p.id)}">${icon('message')}<span>${Number(p.replies)||0} 回复</span></a>${Number.isFinite(p.views)?`<span>${p.views} 浏览</span>`:''}</div></article>`;
}
export function wantRow(w,viewer){
  const mine=Number(w.user_id)===Number(viewer),matched=w.status==='matched';
  return `<article class="forum-post-row forum-want-row"><div class="forum-post-main"><div class="forum-row-heading"><a class="forum-post-title" href="#forum-want/${Number(w.id)}">求购 ${e(w.keyword)}</a>${matched?'<span class="forum-pin">已成交</span>':''}</div><p class="forum-excerpt">${e(w.description||'查看详情，与同学沟通物品和交接方式。')}</p><div class="forum-post-meta"><span class="forum-meta-author">${avatar(w.nickname)}<a href="#profile/${Number(w.user_id)}">${e(w.nickname)}</a></span><time>${date(w.created)}</time><span>${(w.matches||[]).length} 件匹配</span></div></div><div class="forum-want-aside"><span class="forum-budget"><small>预算</small> ¥${money(w.budget)}</span>${!mine&&!matched?`<button class="forum-button secondary" data-action="want-respond" data-id="${Number(w.id)}" data-user="${Number(w.user_id)}" data-name="${e(w.nickname)}" data-keyword="${e(w.keyword)}">我能卖</button>`:''}</div></article>`;
}
export function replyRow(c,floor){
  return `<details class="forum-reply" id="forum-reply-${Number(c.id)}" open><summary>${avatar(c.nickname)}<span class="forum-reply-who"><b>${e(c.nickname)}</b><time>${date(c.created)}</time></span><span class="forum-floor">${floor} 楼</span><span class="forum-fold">${icon('down')}</span></summary><div class="forum-reply-content">${c.parent_nickname?`<p class="forum-quote">回复 ${e(c.parent_nickname)}</p>`:''}<div class="forum-prose">${e(c.body)}</div><div class="forum-reply-actions"><a href="#profile/${Number(c.user_id)}">查看主页</a><button data-action="forum-target-reply" data-id="${Number(c.id)}" data-name="${e(c.nickname)}">回复</button></div></div></details>`;
}
export function forumEmpty(title,body='换个关键词，或分享你的第一条帖子。'){
  return `<div class="forum-empty-state">${icon('message')}<h3>${e(title)}</h3><p>${e(body)}</p></div>`;
}
export function forumNotice(message){
  return `<div class="forum-inline-error" role="status"><p>${e(message)}</p><button class="forum-button secondary" data-action="forum-retry">重新加载</button></div>`;
}
