'use strict';
// 页面层 · 我的转角 与 同学公开主页
//
// 「我的」页参考主流二手 App 的信息架构重排（2026-10-17）：
//   头像卡 → 通知条 → 五格数据 → 购买/出售宫格 → 发布横幅 → 服务宫格 → 资料与信誉。
// 没有的功能（红包、足迹、钱包、分期）一律不放占位——空格子比没有格子更糟。
// 所有数字都来自已有接口，不为此新增后端。
//
// 分工提示：本文件属协作者领地（见 docs/前端协作规范.md），
// 本轮由平台端侧代为重构，协作者后续在此文件内继续迭代即可。

import { $, e, icon } from '../core/dom.js';
import { date, money } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { card } from '../components/product-card.js';
import { needLogin } from '../auth/login.js';

// 公开主页。看别人的时候是只读的；看自己的时候，资料编辑表单就在这里——
// 「我的」页改版后不再放表单，编辑资料回到它归属的地方：主页。
export async function profile(id){
  const r=await api('/profile?id='+id),u=r.user;
  const own=state.me&&state.me.id===u.id;
  // 试用版学院是固定目录（state.config.colleges）；演示版与公开页允许自填，留空即可。
  const collegeOptions=(state.config.colleges||[]).map(c=>`<option ${state.me&&state.me.college===c.source_name?'selected':''}>${e(c.source_name)}</option>`).join('');
  shell(`${heading('NICE TO MEET YOU','同学的转角','看看这位同学的公开信息和在售好物。')}
  <section class="panel profile-card">
    <span class="avatar jumbo">${e(u.nickname[0])}</span>
    <div><h2>${e(u.nickname)}${u.trusted?'<span class="trusted-pill">诚信客户</span>':''}</h2><p>${e(u.college)} · ${e(u.major)} · ${e(u.education)}</p><p>${e(u.bio||'让闲置遇到真正需要它的人。')}</p><span class="tag">信誉 ${u.score}/100 · 不是交易担保</span></div>
    ${!own?`<button class="btn primary" data-action="chat" data-id="${u.id}">发私信</button>`:''}
  </section>
  <h2>在售商品</h2>
  <div class="product-grid">${r.products.filter(p=>p.status==='available').map(card).join('')}</div>
  ${own?`<form id="profile-form" class="panel">
    <h2>编辑我的资料</h2>
    <div class="form-grid">
      ${field('昵称','nickname','text',state.me.nickname,'required maxlength="24"')}
      ${selectField('当前状态','education',['本科','专科','已毕业','其他'])}
      <label class="field"><span>学院（自填，非认证）</span><select name="college">${collegeOptions}<option value="">暂不填写</option></select></label>
      ${field('专业（可选）','major','text',state.me.major)}
    </div>
    <label class="field"><span>简介</span><textarea name="bio" maxlength="300">${e(state.me.bio)}</textarea></label>
    <button class="btn primary">保存资料</button>
    <p class="muted">学院目录来自用户提供文件，部分名称可能为旧称；不展示实名或学生认证徽章。</p>
  </form>`:''}`,'me');
  if(own)$('[name=education]').value=state.me.education;
}

// --- 「我的」页 ------------------------------------------------------------

// 宫格小方块。count>0 时出红点数字，0 时安静——满屏的 0 会把真正的待办淹没。
// 红点只给「待办」：看完或处理完就该消失。收藏数、在售数这类存量不是消息，
// 传 alert=false 只留安静的小入口，否则红点永远亮着，把真正的待办淹没。
// go 为空时用 extra 提供行为（data-action="..."），这类方块不带跳转。
// tone='danger' 用于注销/退出这类不可逆操作，文字转红以示区别。
function tile(go, ic, label, count, extra = '', tone = '', alert = true) {
  const badge = alert && count > 0 ? `<i class="me-badge">${count > 99 ? '99+' : count}</i>` : '';
  const attrs = go ? `data-go="${go}"` : extra;
  return `<button class="me-tile ${tone}" ${attrs}>
    <span class="me-tile-icon">${icon(ic)}</span><small>${e(label)}</small>${badge}</button>`;
}

// 内容分区标题：左侧标题、右侧「查看全部」。空数据时不出「查看全部」——
// 指向一个空列表的链接是负体验。
const secHead = (title, go, label = '查看全部') =>
  `<header class="me-sec-head"><h3>${e(title)}</h3>${go ? `<button class="text-button" data-go="${go}">${e(label)}${icon('arrow')}</button>` : ''}</header>`;

const meEmpty = text => `<p class="me-empty">${e(text)}</p>`;

// 最近订单预览行。整行可点进订单页；缩略图取第一件商品，多件时标「等 N 件」。
function orderRow(o) {
  const first = o.items && o.items[0] ? o.items[0] : {};
  const more = o.items && o.items.length > 1 ? ` 等${o.items.length}件` : '';
  const role = o.buyer_id === state.me.id ? '我买到的' : '我卖出的';
  return `<div class="me-order-row" data-go="orders">
    <img src="${e(first.photo || '')}" alt="" loading="lazy">
    <div class="me-order-main"><b>${e(first.title || '订单 #'+o.id)}${more}</b>
      <small>${e(statusNames[o.status] || o.status)} · ${role} · ${date(o.created)}</small></div>
    <b class="me-order-amount">¥${money(o.total)}</b></div>`;
}

export async function mine(){
  if(!needLogin())return;
  state.me=await api('/me');
  const [myList,favList,myOrders,notices]=await Promise.all([
    api('/my-products'),api('/products?favorite=1'),api('/orders'),api('/notifications')
  ]);
  const me=state.me.id;
  // 按「我是买家还是卖家 + 订单状态」计数。口径与订单页一致：
  //   待收货 = 已付款未确认收货；售后 = 争议或已退款；待发货 = 卖家已收款未交付。
  const countBy=(role,statuses)=>myOrders.filter(o=>o[role+'_id']===me&&statuses.includes(o.status)).length;
  const listingCount=myList.filter(x=>x.status==='available').length;
  const favoriteCount=favList.length;
  const cells=[
    ['收藏',favoriteCount,'favorites'],
    ['取货清单',state.cart.length,'cart'],
    ['通知',notices.unread,'messages/notice'],
    ['在售',listingCount,'listings']
  ];

  // 购买 / 出售宫格。每个格子通到订单页的一个**预筛视图**（orders.js 的
  // 查询参数），而不是一律甩到全部订单列表——「退款/售后 1」点进去就该
  // 只看到那一单。口径必须与 orders.js 的 ORDER_GROUPS 完全一致。
  // 红点口径 = 「需要我动作的」：
  //   待付款/待收货/待发货 跟订单状态走，处理完自动消失；
  //   售后只数进行中的争议（disputed）——refunded 是已处理完的终态，
  //   钱都退完了还亮红点，用户会以为还有事没办完。
  //   我卖出的/我发布的 是存量不是待办，不配红点。
  const buy=[
    ['待付款',countBy('buyer',['awaiting_payment']),'wallet','orders/?role=buy&f=to_pay'],
    ['待收货',countBy('buyer',['paid','awaiting_handover','awaiting_receipt']),'truck','orders/?role=buy&f=receiving'],
    ['退款/售后',countBy('buyer',['disputed']),'refresh','orders/?role=buy&f=aftersale']
  ];
  const sell=[
    ['待发货',countBy('seller',['paid','awaiting_handover']),'bag','orders/?role=sell&f=to_ship'],
    ['我卖出的',myOrders.filter(o=>o.seller_id===me).length,'tag','orders/?role=sell',false],
    ['我发布的',myList.length,'plus','listings',false]
  ];
  const tileOf=([label,n,ic,go,alert])=>tile(go,ic,label,n,'','',alert!==false);

  // 刻意不放 heading：参考的二手 App「我的」页没有大标题，头像卡就是页首。
  shell(`
  <div class="me-page">
    <section class="me-card me-hero">
      <span class="avatar jumbo">${e(state.me.nickname[0])}</span>
      <div class="me-hero-main">
        <h2>${e(state.me.nickname)}</h2>
        <p>${e(state.me.college||'学院未填写')}${state.me.education?` · ${e(state.me.education)}`:''}</p>
        <span class="tag ${state.me.score<60?'danger':''}">信誉 ${state.me.score}/100${state.me.score<60?' · 暂不能发布':''}</span>
      </div>
      <div class="me-hero-side">
        <button class="me-round" data-go="messages/notice" aria-label="订单与售后通知">${icon('bell')}</button>
        ${state.config.trial?`<button class="me-round" data-action="change-password" aria-label="修改密码">${icon('shield')}</button>`:''}
      </div>
    </section>

    ${notices.unread
      ? `<button class="me-notice alert" data-go="messages/notice">${icon('bell')}你有 <b>${notices.unread}</b> 条未读订单通知，点击查看</button>`
      : `<div class="me-notice">${icon('shield')}模拟交易试用 · 不扣真实款项 · 平台依据规则保障双方权益</div>`}

    <section class="me-card me-stats">
      ${cells.map(([label,n,go])=>`<button data-go="${go}"><small>${label}</small><b>${n}</b></button>`).join('')}
      <div><small>信誉分</small><b>${state.me.score}</b></div>
    </section>

    <section class="me-card me-orders">
      <div class="me-orders-head"><b>购买</b><span class="me-vline"></span><b>出售</b><button class="text-button me-orders-all" data-go="orders">全部订单${icon('arrow')}</button></div>
      <div class="me-orders-body">
        <div class="me-half">${buy.map(tileOf).join('')}</div>
        <span class="me-vline"></span>
        <div class="me-half">${sell.map(tileOf).join('')}</div>
      </div>
      <div class="me-orders-more">
        ${tile('favorites','heart','我的收藏',favoriteCount,'','',false)}
        ${tile('listings','tag','在售商品',listingCount,'','',false)}
        ${tile('messages/notice','bell','消息通知',notices.unread)}
      </div>
    </section>

    <section class="me-banner">
      <span class="me-banner-icon">${icon('plus')}</span>
      <div><b>有闲置要出？</b><small>拍三张照片，一分钟挂上转角</small></div>
      <button class="btn primary" data-go="publish">去发布</button>
    </section>

    <section class="me-card me-sec">
      ${secHead('最近订单', myOrders.length ? 'orders' : '')}
      ${myOrders.length ? myOrders.slice(0,3).map(orderRow).join('') : meEmpty('还没有订单。逛逛首页，看中的直接下单一分钟搞定。')}
    </section>

    <section class="me-card me-tools">
      ${tile('profile/'+state.me.id,'user','公开主页',0)}
      ${state.config.trial?tile('','shield','账号与安全',0,'data-action="change-password"'):''}
      ${tile('support','message','帮助与客服',0)}
      ${tile('','chart','信誉与申诉',0,'data-action="appeal"')}
      ${tile('','close','退出登录',0,'data-action="logout"','danger')}
      ${tile('','trash','注销账号',0,'data-action="deactivate"','danger')}
    </section>
  </div>`,'me');}
