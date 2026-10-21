'use strict';
// 页面层 · 帮助与客服、客服工作台、工单详情
import { isStaff, isAdmin } from '../core/roles.js';
import { $, e, icon } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { state, statusNames } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty, modal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { needLogin } from '../auth/login.js';

export function ticketModal(type,orderId,productId){
  if(!needLogin())return;
  // appeal 弹窗有两种来路：信誉申诉（无商品）、重新上架复核（关联商品）。
  // 标题随场景变，避免卖家想恢复商品却点进一个叫「信誉申诉」的表单犯嘀咕。
  const titles={refund:'申请售后',report:'提交举报',appeal:productId?'申请重新上架复核':'信誉申诉',other:'联系客服'};
  // 举报从商品页发起，用户手上通常只有商品、不一定记得订单号。
  // 后端会按「提交人 + 该商品」自动匹配最近一笔订单；这里把规则讲明白，
  // 免得用户以为不填订单号就没人管，也免得客服收到一张无凭证的工单。
  const hint=type==='report'
    ? '举报会记录涉事商品与卖家。若你与卖家就该商品有过交易，提交后系统会自动关联最近一笔订单，客服据此核对交付与款项；也可以手动填写订单编号。'
    : productId
      ? '客服复核通过后商品会立即恢复上架，结果会以站内通知告诉你。'
      : '客服每天08:00—20:00处理。平台不承诺先行赔付，双方可提交材料协商。';
  const orderLabel=type==='refund'?'关联订单编号（必填）':'关联订单编号（选填，填写后客服能直接核对交易）';
  modal(`<h2>${titles[type]||'提交问题'}</h2><p class="muted">${hint}</p><form id="ticket-form" data-type="${type}" data-order="${orderId||''}" data-product="${productId||''}">${field('问题标题','subject','text','','required maxlength="80"')}${field(orderLabel,'order_id','number',orderId||'','min="1"')}<label class="field"><span>问题描述 / 证据说明</span><textarea name="body" required maxlength="3000" placeholder="请描述实际问题、证据和希望的处理方式"></textarea></label><button class="btn primary full">提交工单</button></form>`);
}

export async function support(staff=false){if(!needLogin())return;if(staff&&!isStaff(state.me))throw new Error('没有客服权限');const [tickets,credit]=await Promise.all([api('/tickets'),staff?Promise.resolve(null):api('/credit/history')]);const admin=staff?await api('/admin'):null;shell(`${heading(staff?'SUPPORT DESK':'WE ARE HERE TO HELP',staff?'客服工作台':'帮助与售后',staff?'认领、证据、处理与复核，每一步保留记录。':'客服每天08:00—20:00，非工作时间仍可留言。先提交问题，客服受理后可在线沟通。',`<button class="btn primary" data-action="new-ticket">${icon('plus')}提交问题</button>`)}<div class="support-stats">${[['待处理',tickets.filter(t=>t.status==='open').length],['处理中',tickets.filter(t=>['processing','review'].includes(t.status)).length],['已解决',tickets.filter(t=>t.status==='resolved').length]].map(([n,v])=>`<div class="panel"><span>${n}</span><strong>${v}</strong></div>`).join('')}</div><section class="panel"><div class="section-heading"><h2>${staff?'工单队列':'我的反馈'}</h2>${staff?'<div><button class="btn secondary" data-action="reconcile">资金对账</button> <button class="btn secondary" data-action="backup">保存完整备份</button></div>':''}</div><div class="ticket-list">${tickets.map(t=>`<button class="ticket-row" data-go="ticket/${t.id}"><span class="ticket-type">${{refund:'售后',report:'举报',appeal:'申诉',reschedule:'改约',other:'咨询'}[t.type]}</span><span><b>${e(t.subject)}</b><small>#${t.id} · ${e(t.nickname)} · ${date(t.created)}</small></span><span class="tag">${e(statusNames[t.status])}</span>${icon('arrow')}</button>`).join('')||empty('暂无工单','有问题时可以从订单页或这里发起反馈。')}</div></section>${staff?'':`<section class="panel"><h2>信誉规则与申诉</h2><p class="muted">初始100分，低于60分暂停发布。举报和点赞不会自动改变信誉；处罚必须有审核理由，对结论有异议就在这里提交申诉工单。诚信客户标签看经营记录：发布满10件、至少完成1笔交付、全部按时交付且没有退款。</p>${credit.map(h=>`<div class="case-message"><b>${h.delta>0?'+':''}${h.delta}分${h.ticket_id?` · 工单 #${h.ticket_id}`:''}</b><p>${e(h.reason)}</p><small>${date(h.created)}</small></div>`).join('')||'<p class="muted">暂无信誉变动记录。</p>'}<button class="btn secondary" data-action="appeal">申请信誉申诉</button></section>`}${staff?`<section class="panel"><h2>信誉与管理权限</h2><p class="muted">仅平台管理员可调整信誉，必须关联工单并写明证据理由。群管理员没有此权限。</p><div class="user-table">${admin.users.map(u=>`<div><span>${e(u.nickname)} <small>#${u.id} · ${e(u.role)}</small>${u.status==='banned'?' <small>已封禁</small>':''}</span><b>${u.score}/100</b>${u.id!==state.me.id?`<button class="text-button" data-action="credit" data-id="${u.id}">审核调整</button>`:''}${isAdmin(state.me)&&u.id!==state.me.id&&!['admin','developer'].includes(u.role)?`<button class="text-button" data-action="ban" data-id="${u.id}" data-value="${u.status==='banned'?'false':'true'}">${u.status==='banned'?'解封':'封禁'}</button>`:''}</div>`).join('')}</div></section><section class="panel"><h2>群管理员申请</h2>${admin.nominations.map(n=>`<div class="offer-row"><span>${e(n.nickname)} · ${e(n.name)} · ${e(n.reason)}</span>${n.status==='pending'?`<button class="btn secondary" data-action="appoint" data-id="${n.id}">批准任命</button>`:`<span class="tag">${e(n.status)}</span>`}</div>`).join('')||'<p class="muted">暂无申请</p>'}</section><details class="panel"><summary>操作审计记录</summary>${admin.audit.map(a=>`<p>#${a.id} ${e(a.type)} · ${e(a.reason)} · ${date(a.created)}</p>`).join('')||'暂无操作'}</details>`:''}`,staff?'staff':'me');}
export async function ticketPage(id){
  if(!needLogin())return;
  const t=await api('/ticket?id='+id);
  const staff=isStaff(state.me);
  const o=t.order_id?await api('/order?id='+t.order_id):null;
  const prod=t.product_id?await api('/product?id='+t.product_id).catch(()=>null):null;
  // 无订单时不能只甩一句「未关联订单」：处理人需要知道缺了什么、能不能补、
  // 点哪儿补。有商品的工单让客服从当事人订单里补绑；两样都没有的，
  // 直接说清楚「无法核实、无法扣分」，别让人对着一张白纸猜。
  const orderCard=o
    ?`<p>订单 #${o.id} · ${e(statusNames[o.status])}</p><p>买家：${e(o.buyer)}<br>卖家：${e(o.seller)}</p><h2>¥${money(o.total)}</h2><p>交付：${date(o.appointment)}</p><p>${e(o.address||o.items[0].region)}</p><small>模拟资金，不代表真实到账。</small>${staff?`<button class="text-button" data-action="link-order" data-id="${t.id}">改绑订单</button>`:''}`
    :`<div class="notice notice-stack"><b>未关联订单</b><p>${prod
        ? '这张工单由商品举报发起，提交时没带订单号。若举报人买过该商品，可点下面「关联订单」从当事人的订单里补一笔，补齐后金额与双方记录才可核。'
        : '这张工单既没有订单也没有商品，只有文字描述。缺交易凭证，无法核实金额与责任，也无法据此扣信誉分。'}</p></div>${staff
        ?`<button class="btn secondary full" data-action="link-order" data-id="${t.id}">关联订单</button>`
        :'<p class="muted">如涉及具体交易，请在下方回复里写明订单编号，客服会为你补关联。</p>'}`;
  const productCard=prod
    ?`<hr><button class="ticket-row" data-go="product/${prod.id}"><span class="ticket-type">商品</span><span><b>${e(prod.title)}</b><small>#${prod.id} · ¥${money(prod.price)} · ${e(statusNames[prod.status])}</small></span>${icon('arrow')}</button>${staff&&prod.status==='removed'?`<p class="muted">该商品当前处于下架状态${t.type==='appeal'?'，复核申诉成立可在此恢复上架':''}。</p>${t.type==='appeal'?`<button class="btn primary full" data-action="restore-product" data-id="${prod.id}">复核通过，恢复上架</button>`:''}`:''}`
    :(t.product_id?`<hr><p class="muted">工单涉及的商品 #${t.product_id} 已被删除，无法再打开详情。</p>`:'');
  // 在线客服只对「有未结案工单的当事人」开放：先有工单再聊，
  // 客服点开会话就知道在聊哪张单，也避免把客服从售后里抽走去答闲聊。
  const chatBtn=(!staff&&t.user_id===state.me.id&&t.status!=='resolved')
    ?`<hr><button class="btn primary full" data-action="chat-support" data-id="${t.id}">${icon('message')}联系在线客服</button>`
    :'';
  shell(`${heading('CASE #'+t.id,t.subject,'客服服务时间 08:00—20:00 · 所有资金操作为模拟')}<div class="support-case"><section class="panel"><span class="tag">${e(statusNames[t.status])}</span><h3>${e(t.nickname)}的反馈</h3><p class="description">${e(t.body)}</p>${t.reason?`<div class="notice">处理依据：${e(t.reason)}</div>`:''}<div class="case-timeline">${t.messages.map(m=>`<div class="case-message"><b>${e(m.nickname)} ${m.internal?'· 内部备注（不发给用户）':''}</b><p>${e(m.body)}</p><small>${date(m.created)}</small></div>`).join('')}</div><form id="ticket-reply-form" data-id="${t.id}">${staff&&state.config.ai?`<div class="ai-reply" data-ticket="${t.id}">
            <div class="ai-reply-head"><div><b>AI 建议回复</b><small>依据知识库生成 · 需人工确认后发送</small></div><button type="button" class="btn secondary" data-action="ai-reply">生成建议</button></div>
            <div class="ai-reply-body" hidden></div>
          </div>`:''}<label class="field"><span>补充材料 / 回复</span><textarea name="body" required></textarea></label>${staff?'<label class="checkbox"><input name="internal" type="checkbox">仅内部备注</label>':''}<button class="btn primary">发送回复</button></form></section><aside><section class="panel"><h2>关联信息</h2>${orderCard}${productCard}${chatBtn}</section>${staff&&t.status!=='resolved'?`<form id="resolve-form" class="panel" data-id="${t.id}" data-amount="${o?.total||0}"><h2>处理工单</h2><label class="field"><span>处理依据 *</span><textarea name="reason" required placeholder="写明证据、双方意见及处理依据"></textarea></label><div class="stack"><button class="btn secondary" name="outcome" value="claim">认领工单</button><button class="btn secondary" name="outcome" value="review">提交复核</button>${t.type==='refund'?'<button class="btn primary" name="outcome" value="refund">模拟退款</button>':''}<button class="btn secondary" name="outcome" value="reject">不支持退款 / 结案</button><button class="btn secondary" name="outcome" value="resolved">协商完成并结案</button></div></form>`:''}</aside></div>`,'me');
}
