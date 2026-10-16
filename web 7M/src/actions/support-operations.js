import { context as getContext } from '../core/context.js';
import { e, field, evidenceInput, names, types, amountText } from '../components/support-fields.js';
import { support, ticketModal } from '../pages/support.js';
export async function uploadEvidenceFiles(form, context = getContext()) {
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
export async function creditDialog(context, target) {
    const rules = await context.request('/credit/rules');
    context.modal(`<h2>信誉处理 #${target}</h2><p class="muted">必须关联已核实且结束的工单。申诉成功冲回原处罚，整改恢复须满足30天规则。</p><form id="op-credit" data-operation-form="credit" data-target="${target}"><label class="field"><span>处理类型</span><select name="credit_mode"><option value="penalty">核实违规</option><option value="reverse">申诉成立，冲回原处罚</option><option value="recover">整改后人工恢复最多5分</option></select></label>${field('关联工单编号', 'ticket_id', 'number', '', 'required min="1"')}<label class="field" data-credit-rule><span>适用规则</span><select name="rule_key">${rules.map(rule => `<option value="${rule.key}">${e(rule.label)} · ${rule.delta ? rule.delta + '分' : '提醒'}</option>`).join('')}</select></label><div data-credit-original hidden>${field('原处罚记录ID', 'audit_id', 'number', '', 'min="1"')}</div><label class="field"><span>核实／复核依据</span><textarea name="reason" required maxlength="1000"></textarea></label><button class="btn primary">记录信誉处理</button></form>`);
    const form = document.getElementById('op-credit');
    form.querySelector('[name=credit_mode]').onchange = event => {
      form.querySelector('[data-credit-rule]').hidden = event.target.value !== 'penalty';
      form.querySelector('[data-credit-original]').hidden = event.target.value !== 'reverse';
      form.querySelector('[name=audit_id]').required = event.target.value === 'reverse';
    };
  }
export async function operationClick(button){
    if (!button) return;
    const context = getContext();
    if (!context?.isCurrent()) return;
    button.disabled = true;
    try {
      if (button.hasAttribute('data-credit-user')) { await creditDialog(context, Number(button.dataset.creditUser)); return; }
      const action = button.dataset.operation;
      if(action==='appeal-case'){await ticketModal('appeal',null,null,Number(button.dataset.id));return;}
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
  }
export async function operationSubmit({form,button}){
    const context = getContext();
    if (!context?.isCurrent()) return;
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
  }

export function filterCases(){
 const q=document.querySelector('[name=queue_query]');if(!q)return;
 const type=document.querySelector('[name=queue_type]').value,status=document.querySelector('[name=queue_status]').value;
 document.querySelectorAll('.ticket-row').forEach(row=>{row.hidden=!!((q.value && !row.textContent.toLowerCase().includes(q.value.trim().toLowerCase())) || (type && row.dataset.ticketType!==type) || (status && row.dataset.ticketStatus!==status));});
}
