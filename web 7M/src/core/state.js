'use strict';
// 基础设施层 · 会话与全局状态
// 这是唯一持有可变全局状态的地方。其他模块只读写 state，不自己另建副本。
import { readSessionToken } from './session.js';

export const state = {
  // 公开演示版没有登录态，token 恒为空。
  token: window.HUALI_STATIC_DEMO ? '' : readSessionToken(),
  me: null,
  config: {},
  filter: {category:'', q:'', sort:''},
  poll: null,
  // 聊天页的低频轮询（会话列表摘要刷新），与 poll 一起在路由切换时清掉。
  poll2: null,
  renderId: 0,
  cart: [],
  // 逛逛页的「免费送」货架开关与频道筛选并列存在。
  freeShelf: false,
  // 逛逛商品流的分页：初始 40 件，「加载更多」累加；切换筛选时归位。
  homeLimit: 40,
  // 当前首页的交互句柄，换页时释放观察器、事件与轮播计时器。
  homeView: null,
  // 社区帖子流的分页：初始 20 条，「加载更多」累加。
  // 社区帖子流：offset 分页累积，避免「增大 limit」撞上后端 50 条封顶。
  postsFeed: [],
  // 消息页的增量拉取游标，提交消息后需要接着它继续追加。
  messageCursor: 0,
  // 求购撮合：买家点「我要这个」后暂存 {want, product}，结算时带上以记撮合服务费。
  // 必须记住来源商品：用户中途清空购物车或把该商品移除后，这份关联要同时失效，
  // 否则下一笔无关订单会带着 want_id，把那条求购错标成「已成交」并多记 5% 服务费。
  pendingWant: null,
  // 页面里创建过的 blob: URL（头像本地预览等）。集中登记才能保证换页/换账号时
  // 全部 revoke：漏一个就泄漏一份内存，反复上传头像会持续涨。
  mediaURLs: new Set(),
  // 旧 Bearer 图片兼容器：路由切换时取消尚未结束的私密图片请求。
  mediaLoader: null
};

export const statusNames = {
  available:'在售', reserved:'已预留', sold:'已售出', removed:'已下架',
  awaiting_payment:'待付款', paid:'待交付', awaiting_handover:'待核对交接',
  awaiting_receipt:'待确认收货', completed:'已完成', cancelled:'已取消',
  disputed:'售后处理中', refunded:'已退款', partial_refunded:'部分退款',
  open:'待处理', processing:'处理中', review:'待复核', resolved:'已解决',
  pending:'待接受', accepted:'已接受', rejected:'已拒绝'
};

// 公开演示版：这些路由不开放，点进去只给说明，不给表单。
export const demoFeatures = {
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

export function clearPoll(){
  clearInterval(state.poll); state.poll = null;
  clearInterval(state.poll2); state.poll2 = null;
}

export function saveCart(){
  syncPendingWant();
  sessionStorage.setItem('hc-cart-'+state.me.id, JSON.stringify(state.cart));
}

export function loadCart(){
  state.cart = JSON.parse(sessionStorage.getItem('hc-cart-'+state.me.id) || '[]');
  state.pendingWant = null;
}

// 求购关联只对「来源商品仍在清单里」有效；商品被移除或清空清单后自动作废。
export function syncPendingWant(){
  if (state.pendingWant && !state.cart.includes(state.pendingWant.product)) state.pendingWant = null;
}

export function clearPendingWant(){ state.pendingWant = null; }
