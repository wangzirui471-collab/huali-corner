'use strict';
import { $, e, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { needLogin } from '../auth/login.js';
import { forumState,boardOf,postsURL,wantsURL,FORUM_PAGE,refreshForumReplies } from '../pages/forum.js';
import { postRow,replyRow } from '../components/forum.js';

function focusReply(){
  const area=$('#forum-reply-body');
  if(area){area.focus({preventScroll:true});$('#forum-reply-editor').scrollIntoView({block:'center',behavior:'auto'});}
}
function cancelTarget(){
  const form=$('#forum-reply-form');if(!form)return;
  form.dataset.parent='0';$('#forum-reply-target').textContent='回复楼主 · '+forumState.post.nickname;$('#forum-cancel-target').hidden=true;
}
export const clicks={
  'forum-retry':()=>render(),
  'forum-sort':async b=>{forumState.sort=b.dataset.value==='hot'?'hot':'latest';await render();},
  'forum-clear-search':async()=>{forumState.q='';await render();},
  'forum-layout':b=>{
    forumState.layout=b.dataset.value==='cards'?'cards':'list';
    const feed=$('#forum-feed');if(feed)feed.dataset.layout=forumState.layout;
    document.querySelectorAll('[data-action="forum-layout"]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.value===forumState.layout)));
    try{localStorage.setItem('hc-forum-layout',forumState.layout);}catch{}
  },
  'forum-more':async b=>{
    b.disabled=true;const rid=state.renderId,url=forumState.board==='wants'?wantsURL(forumState.rows.length):postsURL(forumState.rows.length),more=await api(url);
    if(rid!==state.renderId||!$('#forum-feed'))return;
    const seen=new Set(forumState.rows.map(p=>p.id)),rows=more.filter(p=>!seen.has(p.id));
    forumState.rows.push(...rows);$('#forum-feed').insertAdjacentHTML('beforeend',rows.map(postRow).join(''));
    if(more.length<FORUM_PAGE)b.parentElement.innerHTML='<span>已显示全部讨论</span>';
  },
  'forum-focus-reply':focusReply,
  'forum-target-reply':(b,id)=>{
    const form=$('#forum-reply-form');if(!form)return;
    form.dataset.parent=String(id);$('#forum-reply-target').textContent='回复 '+b.dataset.name;$('#forum-cancel-target').hidden=false;focusReply();
  },
  'forum-cancel-target':cancelTarget,
  'forum-first-replies':()=>refreshForumReplies(false),
  'forum-more-replies':async b=>{
    b.disabled=true;const rid=state.renderId,post=forumState.post,after=forumState.replies.at(-1)?.id||0;
    const rows=await api('/comments?id='+post.id+'&limit=20&order=asc&after='+after);
    if(rid!==state.renderId||!$('#forum-replies'))return;
    const seen=new Set(forumState.replies.map(c=>c.id)),more=rows.filter(c=>!seen.has(c.id)),start=forumState.replies.length;
    forumState.replies.push(...more);$('#forum-replies').insertAdjacentHTML('beforeend',more.map((c,i)=>replyRow(c,start+i+1)).join(''));
    if(rows.length<FORUM_PAGE)b.remove();
  },
  'forum-share':async()=>{await navigator.clipboard.writeText(location.href);toast('帖子链接已复制');}
};
async function search({d}){
  forumState.q=String(d.q||'').trim().slice(0,100);
  const route=location.hash.slice(1).split('/');
  if(route[0]==='forum'&&route[1])await render();else go('forum/latest');
}
export const submits={
  'forum-search-form':search,
  'forum-mobile-search-form':search,
  'forum-post-form':async({d})=>{
    if(!needLogin())return;
    const board=boardOf(d.board);if(!board?.topic)throw Error('请选择发帖板块');
    const title=String(d.title||'').trim(),text=String(d.body||'').trim();
    if(!title||!text)throw Error('请填写标题和正文');
    const body=title+'\n'+text;if(body.length>2000)throw Error('标题和正文合计最多2000字');
    const p=await api('/posts',{topic:board.topic,body});toast('帖子已发布');go('forum-post/'+p.id);
  },
  'forum-want-form':async({d})=>{
    if(!needLogin())return;
    // 后端 /wants 的 budget 是整数分；表单拿到的是元字符串，必须在这里换算，
    // 否则 cents() 的类型校验会直接 400（社区页的发布框一直是对的）。
    const yuan=Number(d.budget);
    if(!Number.isFinite(yuan)||yuan<=0)throw Error('请输入有效预算');
    const w=await api('/wants',{keyword:d.title,budget:Math.round(yuan*100),description:d.body});
    toast('求购已发布');go('forum-want/'+w.id);
  },
  'forum-reply-form':async({form,d})=>{
    if(!needLogin())return;
    const id=Number(form.dataset.post),rid=state.renderId;
    await api('/comments',{post_id:id,parent_id:Number(form.dataset.parent)||0,body:d.body});
    if(rid!==state.renderId)return;
    form.reset();cancelTarget();toast('回复已发布');
    const posts=await api('/posts?id='+id);
    if(rid!==state.renderId)return;
    if(posts[0])forumState.post=posts[0];
    $('#forum-reply-count').textContent=String(forumState.post.replies||0);
    await refreshForumReplies(true,rid);
  }
};
