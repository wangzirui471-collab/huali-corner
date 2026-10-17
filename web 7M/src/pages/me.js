'use strict';
// User-domain pages only. A registers actions, image/file events and stylesheet.
import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { card } from '../components/product-card.js';
import { needLogin } from '../auth/login.js';
import { userProfileForm, userAvatarForm, userProfileSummary } from '../components/user-profile.js';

function pageScope(){
  const owner = state.me?.id, token = state.token, epoch = state.renderId, route = location.hash;
  return {owner,current:()=>state.me?.id===owner && state.token===token
    && state.renderId===epoch && location.hash===route};
}

export async function profile(id){
  const target = Number(id);
  if (!Number.isSafeInteger(target) || target <= 0) throw new Error('用户不存在');
  const scope = pageScope();
  const result = await api('/profile?id='+encodeURIComponent(target));
  if (!scope.current()) return;
  if (result?.user?.id !== target || !Array.isArray(result.products)) {
    throw new Error('公开资料响应不完整，请稍后重试');
  }
  const user = result.user, products = result.products.filter(product=>product.status==='available');
  const own = state.me?.id === user.id;
  const contact = own
    ? '<button class="btn secondary" data-go="me">编辑我的资料</button>'
    : `<button class="btn primary" data-action="chat" data-id="${target}">发私信</button>`;
  shell(`<div class="user-center user-public-profile">${heading('NICE TO MEET YOU','同学的转角','这里展示自填资料，不代表学生、学校或实名认证。')}<section class="panel">${userProfileSummary(user)}<div class="user-profile-buttons">${contact}</div></section><section class="user-public-products"><h2>在售商品</h2><div class="product-grid">${products.map(card).join('')}</div>${products.length ? '' : empty('暂时没有在售商品','可以稍后再来看看。')}</section></div>`);
}

function accountButtons(user){
  return `<div class="user-account-buttons">${state.config.trial ? '<button class="btn secondary" data-action="change-password">修改密码</button>' : ''}<button class="btn secondary" data-action="logout">退出登录</button></div>${['admin','support'].includes(user.role) ? '<section class="panel staff-entry"><div><h2>管理与客服</h2><p>待办工单、举报和管理操作</p></div><button class="btn primary" data-go="staff">进入管理工作台</button></section>' : ''}`;
}

function shortcuts(user,counts){
  const stats = [['我的订单',counts.orders],['我的收藏',counts.favorites],['在售商品',counts.listings],['信誉分',user.score]];
  const links = [['orders','bag','我的订单','购买与出售'],['listings','tag','我发布的','商品管理'],
    ['favorites','heart','我的收藏','想要的好物'],['profile/'+user.id,'user','公开主页','别人看到的你']];
  return `<div class="mine-stats">${stats.map(([label,value])=>`<div class="stat-cell"><b>${e(value)}</b><span>${label}</span></div>`).join('')}</div><nav class="mine-actions" aria-label="我的功能">${links.map(([route,art,label,desc])=>`<button data-go="${route}">${icon(art)}<b>${label}</b><small>${desc}</small></button>`).join('')}</nav>`;
}

function creditHistory(history){
  const records = history.map(item=>`<div class="case-message"><b>${item.delta>0?'+':''}${e(item.delta)}分 · 工单 #${e(item.ticket_id)}</b><p>${e(item.reason)}</p><small>${e(date(item.created))}</small></div>`).join('');
  return `<section class="panel user-credit"><h2>信誉记录与申诉</h2><p>初始100分，低于60分暂停发布。举报和点赞不会自动改变信誉；处罚必须有审核理由。信誉不是交易担保。</p>${records || '<p class="muted">暂无信誉变更记录。</p>'}<button class="btn secondary" data-action="appeal">申请信誉申诉</button></section>`;
}

export async function mine(){
  if (!needLogin()) return;
  const scope = pageScope();
  const [user,history,listings,favorites,orders] = await Promise.all([
    api('/user/profile'),api('/credit/history'),api('/my-products'),
    api('/products?favorite=1'),api('/orders')
  ]);
  if (!scope.current()) return;
  if (user?.id !== scope.owner || !Number.isSafeInteger(user.profile_version)
      || user.profile_version < 0 || ![history,listings,favorites,orders].every(Array.isArray)) {
    throw new Error('用户中心响应不完整，请确认资料接口已接入');
  }
  state.me = user;
  const counts = {orders:orders.length,favorites:favorites.length,
    listings:listings.filter(product=>product.status==='available').length};
  shell(`<div class="user-center" data-user-center data-user-owner="${user.id}">${heading('YOUR CORNER','我的转角','不必证明学生身份，毕业后也可以继续分享闲置。')}<section class="panel" data-user-summary>${userProfileSummary(user)}</section>${accountButtons(user)}${shortcuts(user,counts)}<div class="user-center-editor">${userProfileForm(user)}${userAvatarForm(user)}</div>${creditHistory(history)}</div>`,'me');
}
