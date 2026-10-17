import { staffFrame } from '../components/staff-layout.js';
import { caseSources, refundContext } from '../components/case-context.js';
import { context as getContext } from '../core/context.js';
import { e, toast } from '../core/dom.js';
import { modal } from '../core/shell.js';
import { names, types, field, evidenceInput, amountText } from '../components/support-fields.js';
export async function support(context, staff = false) {

    if (staff && !['support', 'admin'].includes(context.user.role)) throw new Error('没有客服权限');
    const admin = staff && context.user.role === 'admin';
    const [tickets, management, workers] = await Promise.all([
      context.request('/tickets'), admin ? context.request('/admin') : Promise.resolve(null),
      admin && context.config.trial ? context.request('/admin/support') : Promise.resolve([]),
    ]);
    const pending = tickets.filter(ticket => ticket.status === 'open').length;
    const working = tickets.filter(ticket => ['processing', 'review'].includes(ticket.status)).length;
    context.shell(`${context.heading(staff ? 'SUPPORT DESK' : 'SUPPORT', staff ? '客服工作台' : '帮助与售后', '每天08:00—20:00处理，非工作时间可提交。本站所有退款为模拟。', '<button class="btn primary" data-action="new-ticket">提交问题</button>')}
      <div class="support-stats">${[['待处理', pending], ['处理中／复核', working], ['已解决', tickets.length - pending - working]].map(([name, count]) => `<div class="panel"><span>${name}</span><strong>${count}</strong></div>`).join('')}</div>
      <section class="panel"><div class="section-heading"><h2>${staff ? '工单队列' : '我的反馈'}</h2><button class="btn secondary" data-operation="refresh-cases" data-staff="${staff}">刷新列表</button></div>
      <div class="form-grid">${field('搜索标题／编号', 'queue_query')}
      <label class="field"><span>类型</span><select name="queue_type"><option value="">全部</option>${Object.entries(types).map(([key, label]) => `<option value="${key}">${label}</option>`).join('')}</select></label>
      <label class="field"><span>状态</span><select name="queue_status"><option value="">全部</option>${['open', 'processing', 'review', 'resolved'].map(key => `<option value="${key}">${names[key]}</option>`).join('')}</select></label></div>
      <div class="ticket-list">${tickets.map(ticket => `<button class="ticket-row" data-go="ticket/${ticket.id}" data-ticket-type="${ticket.type}" data-ticket-status="${ticket.status}"><span class="ticket-type">${e(types[ticket.type] || ticket.type)}</span><span><b>${e(ticket.subject)}</b><small>#${ticket.id} · ${e(ticket.nickname)} · ${context.date(ticket.created)} · ${ticket.assignee ? '已认领 #' + ticket.assignee : '未认领'}</small></span><span class="tag">${e(names[ticket.status])}</span></button>`).join('') || context.empty('暂无工单')}</div></section>
      ${admin ? `<section class="panel"><div class="section-heading"><h2>独立客服账号</h2>${context.config.trial ? '<button class="btn primary" data-operation="create-support">创建客服账号</button>' : '<span class="muted">密码试用版支持建立独立客服</span>'}</div><p class="muted">每人一个账号，客服负责受理与建议；退款批准、扣分和人员授权由平台管理员处理。</p>${workers.map(worker => `<div class="offer-row" data-support-account="${worker.id}"><span><b>${e(worker.nickname)}</b> · ${e(worker.phone)} · ${worker.is_active ? '启用' : '停用'}</span><button class="btn secondary" data-operation="support-active" data-id="${worker.id}" data-active="${!worker.is_active}">${worker.is_active ? '停用客服' : '启用客服'}</button></div>`).join('')}</section>
      <section class="panel"><h2>信誉与申诉处理</h2><p class="muted">只处理已核实的关联工单，不因退款、举报或差评自动扣分。</p><div class="user-table">${management.users.map(user => `<div data-credit-row="${user.id}"><span>${e(user.nickname)} <small>#${user.id} · ${e(user.role)}</small></span><b>${user.score}/100</b>${user.id !== context.user.id ? `<button class="text-button" data-credit-user="${user.id}">信誉处理</button>` : ''}</div>`).join('')}</div></section>
      <section class="panel"><h2>群管理员申请</h2>${management.nominations.map(item => `<div class="offer-row"><span>${e(item.nickname)} · ${e(item.name)} · ${e(item.reason)}</span>${item.status === 'pending' ? `<button class="btn secondary" data-action="appoint" data-id="${item.id}">批准任命</button>` : `<span>${e(item.status)}</span>`}</div>`).join('') || '<p class="muted">暂无申请</p>'}</section>
      <section class="panel"><button class="btn secondary" data-action="reconcile">模拟账务核对</button> <button class="btn secondary" data-action="backup">保存完整备份</button></section><details class="panel"><summary>操作审计记录</summary>${management.audit.map(item => `<p>#${item.id} · ${e(item.type)} · ${e(item.reason)} · ${context.date(item.created)}</p>`).join('')}</details>` : ''}`, 'me');
}
export async function ticket(context, id) {

    const data = await context.request('/ticket?id=' + id);
    if(data.restricted){
      const restrictedContent=`${context.heading('CASE #'+data.id,data.subject,'工单队列摘要')}<section class="panel"><span class="tag">${e(names[data.status])}</span><p>为保护隐私，未分配给你的工单不展示正文、地址、证据或内部备注。</p>${!data.assignee&&data.status!=='resolved'?`<form id="resolve-form" data-operation-form="resolve" data-id="${data.id}">${field('认领依据','reason','text','','required maxlength="1000"')}<button class="btn primary" name="outcome" value="claim">认领后查看详情</button></form>`:'<p>请由管理员按职责转派，或查看自己认领的工单。</p>'}</section>`;
      const staffView=['admin','support'].includes(context.user.role);
      context.shell(staffView?staffFrame(context,'queue',restrictedContent):restrictedContent,staffView?'staff':'me');
      return;
    }
    const order = data.order_id ? await context.request('/order?id=' + data.order_id) : null;
    const participant = data.user_id === context.user.id || (order && [order.buyer_id, order.seller_id].includes(context.user.id));
    const staff = ['support', 'admin'].includes(context.user.role) && !participant;
    const admin = staff && context.user.role === 'admin';
    const workers = admin && context.config.trial && data.status !== 'resolved' ? await context.request('/admin/support') : [];
    const live = data.status !== 'resolved';
    const returned = data.refund_mode === 'return_refund';
    const content=`${context.heading('CASE #' + data.id, data.subject, '客服08:00—20:00 · 处理进度与实际退款成功分开记录')}<div class="support-case"><section class="panel"><span class="tag">${e(names[data.status])}</span><h3>${e(data.nickname)}的反馈</h3><p class="description">${e(data.body)}</p>${data.reason ? `<div class="notice">处理依据：${e(data.reason)}</div>` : ''}
      ${data.type === 'refund' ? `<div class="notice">${returned ? '退货退款：需确认实物退回后批准退款' : '仅退款：不因此恢复卖家库存'}${data.requested_amount ? '<p>建议退款 ¥' + amountText(data.requested_amount) + '</p>' : ''}</div>` : ''}
      ${(data.evidence || []).length ? `<h3>私密图片证据</h3><div class="case-evidence-buttons">${data.evidence.map((photo, index) => `<button class="btn secondary" data-operation="evidence" data-id="${photo.id}">证据图片${index + 1}${photo.internal ? '（内部）' : ''}</button>`).join('')}</div>` : ''}
      <div class="case-timeline">${data.messages.map(message => `<div class="case-message ${message.internal?'internal-note':''}"><b>${e(message.nickname)} ${message.internal ? '· 内部备注' : ''}</b><p>${e(message.body)}</p><small>${context.date(message.created)}</small></div>`).join('')}</div>
      ${live ? `<form id="op-case-reply" data-operation-form="reply" data-id="${data.id}"><label class="field"><span>补充材料／回复</span><textarea name="body" maxlength="2000"></textarea></label>${evidenceInput}${staff ? '<label class="checkbox internal-note"><input name="internal" type="checkbox">仅内部备注（当事人不可见；勾选后发送按钮会提示内部备注）</label>' : ''}<button class="btn primary" data-case-reply-send>发送给当事人</button></form>` : `<div class="notice">原工单已结案，不能继续向已结案流程提交材料。${participant?`<button class="btn secondary" data-operation="appeal-case" data-id="${data.id}">提交关联申诉／新材料</button>`:'请由当事人提交关联申诉，保留原处理记录。'}</div>`}${data.related_ticket_id?`<p><button class="text-button" data-go="ticket/${data.related_ticket_id}">查看原工单 #${data.related_ticket_id}</button></p>`:''}</section>
      <aside>${caseSources(data,staff,admin)}<section class="panel"><h2>关联信息</h2>${order ? `<p>订单 #${order.id}</p><p>${order.items.map(item=>e(item.title)).join('、')}</p><p>买家：${e(order.buyer)}<br>卖家：${e(order.seller)}</p><h2>¥${amountText(order.total)}</h2><p>${e(order.address || order.items[0]?.region)}</p><small>支付、退款与结算全部为模拟。</small>` : '<p>未关联订单</p>'}</section>
      ${order && returned ? `<section class="panel"><h2>实物退回</h2><p>${data.return_received_at ? '卖家已确认收到退回实物' : data.return_sent_at ? '买家已退回，等待卖家确认实物' : '尚未记录实物退回'}</p>${live && order.delivered_at && context.user.id === order.buyer_id && !data.return_sent_at ? `<button class="btn secondary" data-operation="return" data-id="${data.id}" data-action-value="return_sent">已退回实物</button>` : ''}${live && context.user.id === order.seller_id && data.return_sent_at && !data.return_received_at ? `<button class="btn primary" data-operation="return" data-id="${data.id}" data-action-value="confirm_return">确认收到退货</button>` : ''}${!live && data.return_received_at && context.user.id === order.seller_id ? '<button class="btn secondary" data-go="selling">去我的发布重新上架</button>' : ''}</section>` : ''}
      ${staff && live ? `<form id="resolve-form" data-operation-form="resolve" class="panel" data-id="${data.id}" data-total="${order?.total||0}"><h2>处理工单</h2>${refundContext(data,order)}<label class="field"><span>处理依据 *</span><textarea name="reason" required maxlength="1000" placeholder="说明证据、双方意见和处理依据"></textarea></label>${data.type === 'refund' ? field('退款／建议金额（元）', 'amount_yuan', 'number', amountText(data.requested_amount || order.total), 'min="0.01" step="0.01" max="' + order.total / 100 + '"') : ''}<div class="stack">${!data.assignee?'<button class="btn secondary" name="outcome" value="claim">认领工单</button>':''}<button class="btn secondary" name="outcome" value="review">提交复核</button>${data.type === 'refund' ? `<button class="btn secondary" name="outcome" value="request_refund">提交退款建议</button>${admin ? `<button class="btn primary" name="outcome" value="refund" ${returned && order.delivered_at && !data.return_received_at ? 'disabled' : ''}>模拟退款</button>` : ''}` : ''}${admin || data.type !== 'refund' ? `<button class="btn secondary" name="outcome" value="reject">${data.type==='refund'?'不支持退款并结案':'不支持申请并结案'}</button><button class="btn secondary" name="outcome" value="resolved">协商完成并结案</button>` : ''}</div></form>` : ''}
      ${workers.some(worker => worker.is_active) ? `<form id="op-assign" class="panel" data-operation-form="assign" data-id="${data.id}"><h2>指派／转派</h2><label class="field"><span>客服</span><select name="support_user_id">${workers.filter(worker => worker.is_active).map(worker => `<option value="${worker.id}">${e(worker.nickname)}</option>`).join('')}</select></label>${field('转派依据', 'assign_reason', 'text', '', 'required maxlength="1000"')}<button class="btn secondary">确认转派</button></form>` : ''}</aside></div>`;
    context.shell(staff?staffFrame(context,'queue',content):content,staff?'staff':'me');
  }
export const supportPage=(staff=false)=>support(getContext(),staff);
export const ticketPage=id=>ticket(getContext(),id);
export async function ticketModal(type,orderId,productId,relatedId){
 const context=getContext();
 const order=type==='refund'&&orderId?await context.request('/order?id='+orderId):null;
 if(!context.isCurrent())return;
 modal(`<h2>${relatedId?'提交关联申诉':'提交反馈与售后'}</h2><p class="muted">客服08:00—20:00；所有退款均为模拟，不承诺先行赔付。</p>${relatedId?`<p>关联原工单 #${Number(relatedId)}；新材料进入独立待处理队列，原结论保留。</p>`:''}<form id="ticket-form" data-type="${type}" data-order="${orderId||''}" data-product="${productId||''}" data-related="${relatedId||''}">${field('问题标题','subject','text','','required maxlength="80"')}<label class="field"><span>问题说明</span><textarea name="body" required maxlength="3000"></textarea></label>${type==='refund'?`<label class="field"><span>退款方式</span><select name="refund_mode"><option value="refund_only">仅退款，不恢复卖家库存</option>${order?.delivered_at?'<option value="return_refund">退货退款，需确认实物退回</option>':''}</select></label>${!order?.delivered_at?'<p class="muted">订单尚未交付，无需退回实物。</p>':''}`:''}${evidenceInput}<button class="btn primary">提交反馈</button></form>`);
}
