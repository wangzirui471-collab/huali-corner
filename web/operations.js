/* Staff accounts, case handling, physical returns and credit. No push service. */
(() => {
  'use strict';
  let deps = null;
  const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const names = { open: '待处理', processing: '处理中', review: '待复核', resolved: '已解决', available: '在售', reserved: '已预留', sold: '已售出', removed: '已下架' };
  const types = { refund: '售后', report: '举报', appeal: '申诉', other: '咨询', reschedule: '改约' };
  const field = (label, name, type = 'text', value = '', extra = '') => `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${e(value)}" ${extra}></label>`;
  const evidenceInput = '<label class="field"><span>图片证据（选填，每次最多6张）</span><input name="evidence" type="file" multiple accept="image/jpeg,image/png,image/webp"><small>请先遮挡手机号、证件等无关隐私，证据不会公开展示。</small></label>';
  const amountText = cents => (cents / 100).toFixed(2);

  function configure(value) { deps = value; }

  async function uploadEvidenceFiles(form, context = deps) {
    const input = form.querySelector('input[name=evidence]');
    const files = [...(input?.files || [])];
    if (files.length > 6) throw new Error('每次最多上传6张证据图');
    const result = [];
    for (const file of files) {
      if (file.size > 5 * 1024 * 1024) throw new Error('证据图片不能超过5MB');
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('证据图片读取失败'));
        reader.readAsDataURL(file);
      });
      if (!context.isCurrent()) throw new Error('账号已切换');
      const upload = await context.request('/upload', { content, angle: 'proof', private: true });
      result.push(upload.id);
    }
    return result;
  }

  async function selling(context) {
    configure(context);
    const products = await context.request('/seller/products');
    context.shell(`${context.heading('MY LISTINGS', '我的发布', '售后后先核对实物去向，符合条件再从预填草稿重新发布。')}<div class="panel"><button class="btn secondary" data-go="drafts">我的草稿</button> <button class="btn primary" data-go="publish/new">发布新物品</button></div>${products.map(product => `<section class="panel"><div class="section-heading"><h2>${e(product.title)}</h2><span class="tag">${e(names[product.status] || product.status)}</span></div><p>¥${amountText(product.price)} · ${e(product.region)}</p><button class="btn secondary" data-go="product/${product.id}">查看详情</button> ${product.can_relist ? `<button class="btn primary" data-operation="relist" data-id="${product.id}">重新上架</button>` : ''}${product.relist_reason ? `<p class="muted">${e(product.relist_reason)}</p>` : ''}</section>`).join('') || context.empty('还没有发布物品')}`, 'me');
  }

  async function support(context, staff = false) {
    configure(context);
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
    const filter = () => {
      const query = document.querySelector('[name=queue_query]').value.trim().toLowerCase();
      const type = document.querySelector('[name=queue_type]').value;
      const state = document.querySelector('[name=queue_status]').value;
      document.querySelectorAll('.ticket-row').forEach(row => {
        row.hidden = !!((query && !row.textContent.toLowerCase().includes(query)) || (type && row.dataset.ticketType !== type) || (state && row.dataset.ticketStatus !== state));
      });
    };
    for (const name of ['queue_query', 'queue_type', 'queue_status']) {
      document.querySelector(`[name=${name}]`).addEventListener('input', filter);
      document.querySelector(`[name=${name}]`).addEventListener('change', filter);
    }
  }

  async function ticket(context, id) {
    configure(context);
    const data = await context.request('/ticket?id=' + id);
    const order = data.order_id ? await context.request('/order?id=' + data.order_id) : null;
    const participant = data.user_id === context.user.id || (order && [order.buyer_id, order.seller_id].includes(context.user.id));
    const staff = ['support', 'admin'].includes(context.user.role) && !participant;
    const admin = staff && context.user.role === 'admin';
    const workers = admin && context.config.trial && data.status !== 'resolved' ? await context.request('/admin/support') : [];
    const live = data.status !== 'resolved';
    const returned = data.refund_mode === 'return_refund';
    context.shell(`${context.heading('CASE #' + data.id, data.subject, '客服08:00—20:00 · 处理进度与实际退款成功分开记录')}<div class="support-case"><section class="panel"><span class="tag">${e(names[data.status])}</span><h3>${e(data.nickname)}的反馈</h3><p class="description">${e(data.body)}</p>${data.reason ? `<div class="notice">处理依据：${e(data.reason)}</div>` : ''}
      ${data.type === 'refund' ? `<div class="notice">${returned ? '退货退款：需确认实物退回后批准退款' : '仅退款：不因此恢复卖家库存'}${data.requested_amount ? '<p>建议退款 ¥' + amountText(data.requested_amount) + '</p>' : ''}</div>` : ''}
      ${(data.evidence || []).length ? `<h3>私密图片证据</h3>${data.evidence.map((photo, index) => `<button class="btn secondary" data-operation="evidence" data-id="${photo.id}">证据图片${index + 1}${photo.internal ? '（内部）' : ''}</button>`).join('')}` : ''}
      <div class="case-timeline">${data.messages.map(message => `<div class="case-message"><b>${e(message.nickname)} ${message.internal ? '· 内部备注' : ''}</b><p>${e(message.body)}</p><small>${context.date(message.created)}</small></div>`).join('')}</div>
      <form id="op-case-reply" data-operation-form="reply" data-id="${data.id}"><label class="field"><span>补充材料／回复</span><textarea name="body" maxlength="2000"></textarea></label>${evidenceInput}${staff ? '<label class="checkbox"><input name="internal" type="checkbox">仅内部备注</label>' : ''}<button class="btn primary">发送回复</button></form></section>
      <aside><section class="panel"><h2>关联信息</h2>${order ? `<p>订单 #${order.id}</p><p>买家：${e(order.buyer)}<br>卖家：${e(order.seller)}</p><h2>¥${amountText(order.total)}</h2><p>${e(order.address || order.items[0]?.region)}</p><small>支付、退款与结算全部为模拟。</small>` : '<p>未关联订单</p>'}</section>
      ${order && returned ? `<section class="panel"><h2>实物退回</h2><p>${data.return_received_at ? '卖家已确认收到退回实物' : data.return_sent_at ? '买家已退回，等待卖家确认实物' : '尚未记录实物退回'}</p>${live && order.delivered_at && context.user.id === order.buyer_id && !data.return_sent_at ? `<button class="btn secondary" data-operation="return" data-id="${data.id}" data-action-value="return_sent">已退回实物</button>` : ''}${live && context.user.id === order.seller_id && data.return_sent_at && !data.return_received_at ? `<button class="btn primary" data-operation="return" data-id="${data.id}" data-action-value="confirm_return">确认收到退货</button>` : ''}${!live && data.return_received_at && context.user.id === order.seller_id ? '<button class="btn secondary" data-go="selling">去我的发布重新上架</button>' : ''}</section>` : ''}
      ${staff && live ? `<form id="resolve-form" data-operation-form="resolve" class="panel" data-id="${data.id}"><h2>处理工单</h2><label class="field"><span>处理依据 *</span><textarea name="reason" required maxlength="1000" placeholder="说明证据、双方意见和处理依据"></textarea></label>${data.type === 'refund' ? field('退款／建议金额（元）', 'amount_yuan', 'number', amountText(data.requested_amount || order.total), 'min="0.01" step="0.01" max="' + order.total / 100 + '"') : ''}<div class="stack"><button class="btn secondary" name="outcome" value="claim">认领工单</button><button class="btn secondary" name="outcome" value="review">提交复核</button>${data.type === 'refund' ? `<button class="btn secondary" name="outcome" value="request_refund">提交退款建议</button>${admin ? `<button class="btn primary" name="outcome" value="refund" ${returned && !data.return_received_at ? 'disabled' : ''}>模拟退款</button>` : ''}` : ''}${admin || data.type !== 'refund' ? '<button class="btn secondary" name="outcome" value="reject">不支持退款／结案</button><button class="btn secondary" name="outcome" value="resolved">协商完成并结案</button>' : ''}</div></form>` : ''}
      ${workers.some(worker => worker.is_active) ? `<form id="op-assign" class="panel" data-operation-form="assign" data-id="${data.id}"><h2>指派／转派</h2><label class="field"><span>客服</span><select name="support_user_id">${workers.filter(worker => worker.is_active).map(worker => `<option value="${worker.id}">${e(worker.nickname)}</option>`).join('')}</select></label>${field('转派依据', 'assign_reason', 'text', '', 'required maxlength="1000"')}<button class="btn secondary">确认转派</button></form>` : ''}</aside></div>`, 'me');
  }

  async function creditDialog(context, target) {
    const rules = await context.request('/credit/rules');
    context.modal(`<h2>信誉处理 #${target}</h2><p class="muted">必须关联已核实且结束的工单。申诉成功冲回原处罚，整改恢复须满足30天规则。</p><form id="op-credit" data-operation-form="credit" data-target="${target}"><label class="field"><span>处理类型</span><select name="credit_mode"><option value="penalty">核实违规</option><option value="reverse">申诉成立，冲回原处罚</option><option value="recover">整改后人工恢复最多5分</option></select></label>${field('关联工单编号', 'ticket_id', 'number', '', 'required min="1"')}<label class="field" data-credit-rule><span>适用规则</span><select name="rule_key">${rules.map(rule => `<option value="${rule.key}">${e(rule.label)} · ${rule.delta ? rule.delta + '分' : '提醒'}</option>`).join('')}</select></label><div data-credit-original hidden>${field('原处罚记录ID', 'audit_id', 'number', '', 'min="1"')}</div><label class="field"><span>核实／复核依据</span><textarea name="reason" required maxlength="1000"></textarea></label><button class="btn primary">记录信誉处理</button></form>`);
    const form = document.getElementById('op-credit');
    form.querySelector('[name=credit_mode]').onchange = event => {
      form.querySelector('[data-credit-rule]').hidden = event.target.value !== 'penalty';
      form.querySelector('[data-credit-original]').hidden = event.target.value !== 'reverse';
      form.querySelector('[name=audit_id]').required = event.target.value === 'reverse';
    };
  }

  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-operation],[data-credit-user]');
    if (!button) return;
    const context = deps;
    if (!context?.isCurrent()) return;
    button.disabled = true;
    try {
      if (button.hasAttribute('data-credit-user')) { await creditDialog(context, Number(button.dataset.creditUser)); return; }
      const action = button.dataset.operation;
      const id = button.dataset.id;
      if (action === 'refresh-cases') await support(context, button.dataset.staff === 'true');
      else if (action === 'credit-rules') {
        const rules = await context.request('/credit/rules');
        context.modal(`<h2>信誉处理规则</h2><p class="muted">初始100分，低于60分不能新发布。举报、差评、退款本身不自动扣分，须核实后人工处理，可申诉。</p>${rules.map(rule => `<p><b>${e(rule.label)}</b>：${rule.delta ? rule.delta + '分' : '提醒、不扣分'}</p>`).join('')}<p class="muted">非欺诈整改后30天无新增核实违规，可申请人工恢复最多5分，每30天一次。</p>`);
      }
      else if (action === 'relist') { const draft = await context.request('/relist', { product_id: Number(id) }); context.go('publish/' + draft.id); }
      else if (action === 'return') { if (!confirm('请确认实物操作确实已完成。')) return; await context.request('/ticket/return', { id: Number(id), action: button.dataset.actionValue }); await context.render(); }
      else if (action === 'support-active') { if (!confirm('确认变更此客服账号？停用会撤销已登录会话。')) return; await context.request('/admin/support/active', { user_id: Number(id), is_active: button.dataset.active === 'true' }); await support(context, true); }
      else if (action === 'create-support') context.modal(`<h2>创建独立客服账号</h2><p class="muted">只给客服受理权限，不共享管理员账号。密码请私下交给本人，已存在的账号不会覆盖原密码。</p><form id="op-create-support" data-operation-form="create-support">${field('手机号（未验证归属）', 'support_phone', 'tel', '', 'required pattern="1[3-9][0-9]{9}" maxlength="11"')}${field('客服昵称', 'support_nickname', 'text', '', 'required maxlength="24"')}${field('初始独立密码', 'support_password', 'password', '', 'required minlength="12" maxlength="128" autocomplete="new-password"')}<button class="btn primary">建立客服账号</button></form>`);
      else if (action === 'evidence') {
        const response = await fetch('/media/' + encodeURIComponent(id), { headers: { Authorization: 'Bearer ' + context.session } });
        if (!response.ok) throw new Error('不能读取该证据；客服请先认领工单，或检查账号权限');
        const url = URL.createObjectURL(await response.blob());
        if (!context.isCurrent()) { URL.revokeObjectURL(url); return; }
        context.modal('<h2>私密工单证据</h2><img class="evidence-view" alt="工单证据">');
        const image = document.querySelector('.evidence-view');
        image.onload = () => URL.revokeObjectURL(url);
        image.style.width = '100%'; image.src = url;
      }
    } catch (error) { context.toast(error.message); }
    finally { button.disabled = false; }
  });

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('[data-operation-form]')) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const context = deps;
    if (!context?.isCurrent()) return;
    const button = event.submitter;
    const data = Object.fromEntries(new FormData(form));
    if (button) button.disabled = true;
    try {
      const operation = form.dataset.operationForm;
      if (operation === 'create-support') {
        await context.request('/admin/support', { phone: data.support_phone, nickname: data.support_nickname, password: data.support_password });
        form.reset(); context.closeModal(); context.toast('客服账号已配置，请私下交付密码'); await support(context, true);
      } else if (operation === 'reply') {
        const evidence = await uploadEvidenceFiles(form, context);
        await context.request('/ticket/reply', { id: Number(form.dataset.id), body: data.body, internal: new FormData(form).has('internal'), evidence });
        await context.render();
      } else if (operation === 'resolve') {
        await context.request('/ticket/resolve', { id: Number(form.dataset.id), outcome: button.value, reason: data.reason, ...(data.amount_yuan ? { amount_yuan: data.amount_yuan } : {}) });
        context.toast('处理记录已保存，资金均为模拟'); await context.render();
      } else if (operation === 'assign') {
        await context.request('/ticket/assign', { id: Number(form.dataset.id), support_user_id: Number(data.support_user_id), reason: data.assign_reason });
        await context.render();
      } else if (operation === 'credit') {
        const mode = data.credit_mode;
        const payload = { ticket_id: Number(data.ticket_id), reason: data.reason };
        const endpoint = mode === 'reverse' ? 'reverse' : mode === 'recover' ? 'recover' : 'penalty';
        if (mode === 'reverse') payload.audit_id = Number(data.audit_id);
        else payload.target_user_id = Number(form.dataset.target);
        if (mode === 'penalty') payload.rule_key = data.rule_key;
        await context.request('/credit/' + endpoint, payload);
        context.closeModal(); context.toast('信誉处理已记录，可通过申诉复核'); await context.render();
      }
    } catch (error) { context.toast(error.message); }
    finally { if (button) button.disabled = false; }
  });

  window.ZJOperations = { configure, selling, support, ticket, evidenceInput, uploadEvidenceFiles, creditDialog };
})();
