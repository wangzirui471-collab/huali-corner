'use strict';
// 基础设施层 · 页面骨架、区块标题、弹窗
// 每个页面都先拼好 HTML 字符串交给 shell()，由它套上统一头部、导航和页脚。

import { $, e, icon } from './dom.js';
import { state } from './state.js';
import { isStaff, isAdmin } from './roles.js';
import { asset } from './asset.js';

function navItem(route, label, ic, active){
  // 角标数字由 core/badges.js 在每次渲染后填充；hidden 初始，避免闪一个空的。
  // 「我的」聚合通知+聊天；「消息」只看聊天未读。同一属性可以出现在多处，set 是全量填充。
  const badge = route === 'me' ? '<i class="nav-badge" data-nav-badge="me" hidden></i>'
    : route === 'messages' ? '<i class="nav-badge" data-nav-badge="messages" hidden></i>' : '';
  return `<button class="nav-item ${active===route?'active':''}" data-go="${route}">${icon(ic)}<span>${label}</span>${badge}</button>`;
}

export function heading(kicker, title, desc, action=''){
  return `<div class="page-heading"><div><div class="eyebrow">${e(kicker)}</div><h1>${e(title)}</h1>${desc?`<p>${e(desc)}</p>`:''}</div>${action}</div>`;
}

export function empty(title, desc='换个条件试试，或者成为第一个发布的人。'){
  return `<div class="empty">${icon('book')}<h3>${e(title)}</h3><p>${e(desc)}</p><button class="btn secondary" data-go="home">去逛逛</button></div>`;
}

export function modal(html){
  $('#overlay').innerHTML = `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true"><button class="modal-close" data-action="close" aria-label="关闭">${icon('close')}</button>${html}</section></div>`;
  setTimeout(() => $('#overlay input')?.focus(), 20);
}

export function closeModal(){ $('#overlay').innerHTML = ''; }

export function shell(content, active='home'){
  $('#app').innerHTML = `<div class="market-app"><header class="market-header" data-market-header><div class="header-inner"><button class="brand" data-go="home"><img class="brand-mark" src="${asset('/assets/logo-mark.png')}" width="46" height="46" alt="华立转角"><span class="brand-text">华立转角<small>校园里的二手好物集</small></span></button><button class="campus-switch" data-go="community">${icon('pin')}<span>广州校区<small>计算机工程学院试点</small></span></button><form id="search-form" class="market-search" role="search">${icon('search')}<input type="search" name="q" aria-label="搜索商品" placeholder="搜教材、球拍、耳机、宿舍好物" value="${e(state.filter.q)}"><button type="submit">搜索</button></form><div class="header-actions"><button class="header-message" data-go="messages" aria-label="查看消息">${icon('message')}<i class="nav-badge on-icon" data-nav-badge="messages" hidden></i></button><button class="cart-button" data-go="cart">${icon('bag')}<span>取货清单${state.cart.length?' · '+state.cart.length:''}</span></button><button class="account-button" ${state.me?'data-go="me"':'data-action="login"'}>${state.me?`<span class="avatar tiny">${e(state.me.nickname[0])}</span>${e(state.me.nickname)}`:'登录 / 注册'}</button></div></div><nav class="desktop-navigation"><div>${navItem('home','逛逛','home',active)}${navItem('community','社区','community',active)+navItem('forum','论坛','book',active)}${navItem('me','我的','user',active)}<button class="nav-service" data-go="support">帮助与客服</button>${isStaff(state.me)?`<button class="nav-service ${active==='staff'?'active':''}" data-go="staff">客服工作台</button>`:''}${isAdmin(state.me)?`<button class="nav-service ${active==='admin'?'active':''}" data-go="admin">管理员工作台</button>`:''}<button class="btn primary" data-go="publish">${icon('plus')}发布闲置</button></div></nav></header><div class="simulation-bar">本地模拟交易试用 · 不扣真实款项 · 示例商品均已标注</div><main class="market-main ${active==='home'?'market-main-home':''}">${content}</main><footer class="site-footer"><span><b>华立转角</b> · 闲置有去处，同学有照应。<small class="footer-note">演示商品配图来自维基共享资源，依知识共享授权使用，仅作试用演示。</small></span><button data-go="support">客服 08:00—20:00 · 帮助与售后</button></footer></div><nav class="mobile-nav">${navItem('home','逛逛','home',active)}${navItem('community','社区','community',active)+navItem('forum','论坛','book',active)}<button class="mobile-publish ${active==='publish'?'active':''}" data-go="publish" aria-label="发布闲置">${icon('plus')}<span>发布</span></button>${navItem('messages','消息','message',active)}${navItem('me','我的','user',active)}</nav></div>`;
  // 顶部是 sticky 的，高度随断点变化，CSS 的 --header-h 只能运行时量出来。
  const _mh = document.querySelector('.market-header');
  if (_mh) document.documentElement.style.setProperty('--header-h', _mh.offsetHeight+'px');
  if (state.config.trial) $('.simulation-bar').textContent = '计算机工程学院试用 · 手机号未验证 · 订单和付款均为模拟';
  if (window.HUALI_STATIC_DEMO){
    $('.simulation-bar').textContent = '公开演示 · 虚构商品与社区样例 · 不收集个人信息 · 不进行真实交易';
    const postForm = $('#post-form');
    if (postForm){
      const notice = document.createElement('section');
      notice.className = 'panel';
      notice.innerHTML = '<h2>校园社区样例</h2><p>看看求购和毕业季的交流方式。公开演示不接收帖子或聊天内容。</p>';
      postForm.replaceWith(notice);
    }
  }
}
