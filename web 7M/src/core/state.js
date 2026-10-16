'use strict';
// 基础设施层 · 会话与全局状态
// 这是唯一持有可变全局状态的地方。其他模块只读写 state，不自己另建副本。

export const state = {
  // 公开演示版没有登录态，token 恒为空。
  token: window.HUALI_STATIC_DEMO ? '' : sessionStorage.getItem('hc-token') || '',
  logoutSession:null,
  me: null,
  draftEditor: null,
  draftGeneration:0,
  inbox: null,
  feed: null,
  mediaURLs:new Set(),
  config: {},
  filter: {category:'', q:'', sort:''},
  poll: null,
  renderId: 0,
  cart: [],
  // 逛逛页的「免费送」货架开关与频道筛选并列存在。
  freeShelf: false,
  // 消息页的增量拉取游标，提交消息后需要接着它继续追加。
  messageCursor: 0
};

export const statusNames = {
  available:'在售', reserved:'已预留', sold:'已售出', removed:'已下架',
  awaiting_payment:'待付款', paid:'待交付', awaiting_handover:'待核对交接',
  awaiting_receipt:'待确认收货', completed:'已完成', cancelled:'已取消',
  disputed:'售后处理中', refunded:'已退款',
  open:'待处理', processing:'处理中', review:'待复核', resolved:'已解决',
  pending:'待接受', accepted:'已接受', rejected:'已拒绝'
};

// 公开演示版：这些路由不开放，点进去只给说明，不给表单。
export const demoFeatures = {
  help:['校园互助','可登录试用版支持发布需求与私聊协商；公开演示不接收发布、取件码或服务报酬。'],
  publish:['发布闲置','本地模拟版支持正面、侧面、顶部三张实拍，以及书籍版次、笔记、缺页和附件说明。'],
  orders:['订单与售后','本地模拟版可体验合并同卖家取货、模拟付款、交接确认与售后处理。'],
  messages:['校园聊天','本地模拟版包含私聊、学院群和总聊；公开演示不接收或发送消息。'],
  me:['个人中心','本地模拟版支持个人资料、订单和信誉记录；本演示无需注册。'],
  support:['帮助与客服','计划客服时段为08:00—20:00，工单与售后流程可在本地模拟版体验；此页面不提供真人在线客服。'],
  staff:['客服工作台','客服工单、退款审核与对账仅在本地模拟版展示，公开网站没有后台登录入口。'],
  cart:['合并取货','同一卖家的商品可合并取货，送货费按所选商品的最高送货费收取一次。'],
  favorites:['我的收藏','本地模拟版包含收藏功能；公开演示暂不保存收藏。'],
  ticket:['售后反馈','本地模拟版可体验提交工单、补充说明与处理结果；公开演示不接收工单。']
};

export function bumpRenderId(){ return ++state.renderId; }

export function clearPoll(){ clearInterval(state.poll); state.poll = null; }

export function saveCart(){
  sessionStorage.setItem('hc-cart-'+state.me.id, JSON.stringify(state.cart));
}

export function loadCart(){
  state.cart = JSON.parse(sessionStorage.getItem('hc-cart-'+state.me.id) || '[]');
}
