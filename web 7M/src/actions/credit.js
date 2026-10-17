import { e } from '../core/dom.js';

export async function creditDialog(context, target, preferredCase) {
  const [rules, options]=await Promise.all([context.request('/credit/rules'),context.request('/credit/options?target_user_id='+target)]);
  if(!context.isCurrent())return;
  context.modal(`<h2>信誉处理 · ${e(options.user.nickname)}</h2><p class="muted">只可选择已核实、已结束且与该用户关联的工单。每项处理需填写依据，保留申诉入口。</p><form id="op-credit" data-operation-form="credit" data-target="${target}" data-owner="${context.user.id}"><label class="field"><span>处理类型</span><select name="credit_mode"><option value="penalty">核实违规</option><option value="reverse">申诉成立，冲回原处罚</option><option value="recover">整改后人工恢复最多5分</option></select></label><label class="field"><span>已核实的关联工单</span><select name="ticket_id" required></select></label><label class="field" data-credit-rule><span>适用规则</span><select name="rule_key">${rules.map(r=>`<option value="${r.key}">${e(r.label)} · ${r.delta?r.delta+'分':'提醒'}</option>`).join('')}</select></label><label class="field" data-credit-original hidden><span>待冲回的原处罚</span><select name="audit_id">${options.penalties.map(r=>`<option value="${r.id}">记录 #${r.id} · ${r.delta||0}分 · ${e(r.reason)}</option>`).join('')}</select></label><div class="notice" data-credit-preview></div><p class="muted">以上为按当前记录计算的预计结果，提交时服务端会重新核验关联、重复处罚、申诉和恢复资格。</p><label class="field"><span>核实／复核依据</span><textarea name="reason" required maxlength="1000"></textarea></label><button class="btn primary">记录信誉处理</button></form>`);
  const form=document.getElementById('op-credit');
  function updateCases() {
    const mode=form.elements.credit_mode.value;
    const cases=mode==='penalty'?options.penalty_cases:options.appeal_cases;
    const selected=form.elements.ticket_id.value||String(preferredCase||'');
    form.elements.ticket_id.innerHTML=cases.map(t=>`<option value="${t.id}" ${String(t.id)===selected?'selected':''}>#${t.id} · ${e(t.subject)}</option>`).join('')||'<option value="">暂无符合条件的工单，请先核实并结案</option>';
    form.querySelector('[data-credit-rule]').hidden=mode!=='penalty';
    form.querySelector('[data-credit-original]').hidden=mode!=='reverse';
    form.elements.audit_id.required=mode==='reverse';
    updatePreview();
  }
  function updatePreview() {
    const mode=form.elements.credit_mode.value, before=options.user.score;
    const rule=rules.find(r=>r.key===form.elements.rule_key.value);
    const original=options.penalties.find(r=>String(r.id)===form.elements.audit_id.value);
    let delta=mode==='recover'?5:mode==='reverse'?-(original?.delta||0):rule?.delta||0;
    if(mode==='penalty'&&rule?.key==='no_show'&&!options.recent_no_show)delta=0;
    const after=Math.max(0,Math.min(100,before+delta));
    const summary=`预计信誉 ${before} → ${after}${after<60?'；低于60分，暂停新发布':''}${mode==='penalty'&&rule?.key==='fraud'?'；严重欺诈将限制新交易并下架在售商品':''}`;
    form.querySelector('[data-credit-preview]').textContent=summary;
    form.dataset.preview=summary;
    form.querySelector('button[type=submit],button.btn.primary').disabled=!form.elements.ticket_id.value||(mode==='reverse'&&!original);
  }
  form.elements.credit_mode.onchange=updateCases;
  form.elements.rule_key.onchange=updatePreview;
  form.elements.audit_id.onchange=updatePreview;
  updateCases();
}
