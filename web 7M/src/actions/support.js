'use strict';
// 事件层 · 工单、信誉审核、资金对账、备份

import { $, toast, e } from '../core/dom.js';
import { money } from '../core/format.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { state, statusNames } from '../core/state.js';
import { field } from '../components/forms.js';
import { ticketModal } from '../pages/support.js';
import { setPetState, togglePetPanel, paintDuty } from '../components/ai-pet.js';

// --- AI 宠物对话 ---------------------------------------------------------
function petText(text){ return e(text).replace(/\n/g,'<br>'); }

function petAppend(html, who='bot'){
  const log=$('#ai-pet-log'); if(!log) return null;
  const el=document.createElement('div');
  el.className='ai-pet-msg '+who;
  el.innerHTML=html;
  log.appendChild(el); log.scrollTop=log.scrollHeight;
  return el;
}

// 最近几轮对话：只用于让 AI 理解追问（例如「那退款呢」），不落库。
let petHistory = [];
// 所有者面板的「客服问答 / 办公」模式；普通用户固定走客服问答。
let petMode = 'chat';
// 演示商品预览：先生成、等 L1 确认后才入库。
let pendingProducts = [];

async function petAsk(q, extra){
  const text=String(q||'').trim();
  const log=$('#ai-pet-log'); if(!text||!log) return;
  const form=$('#ai-pet-form'), area=form?.querySelector('textarea[name=q]'), send=form?.querySelector('button[type=submit]');
  if(area) area.value='';
  petAppend(petText(text),'user');
  const wait=petAppend('<span class="ai-pet-typing">正在想…</span>','bot');
  if(send) send.disabled=true;
  setPetState('review');                  // 「专注工作」＝思考中：小转动手翻资料，等接口回来
  try{
    const r=await api('/ai/chat',{question:text,history:petHistory.slice(-4),...(extra||{})},{global:true,timeout:45000});
    const src=(r.sources||[]).slice(0,3).map((s,i)=>`[${i+1}] ${e(s.title||s.source)}`).join(' · ');
    const links=(r.links||[]).map(l=>l.action
      ? `<button type="button" class="ai-pet-link" data-action="${e(l.action)}" data-q="${e(l.q||'')}">${e(l.label)} →</button>`
      : `<a class="ai-pet-link" href="${e(l.href)}">${e(l.label)} →</a>`).join('');
    const prods=(r.products||[]).map(p=>`<a class="ai-pet-prod" href="#product/${p.id}"><span class="ai-pet-prod-img" style="background-image:url('${e(p.url||'')}')"></span><span class="ai-pet-prod-txt"><b>${e(p.title)}</b><small>¥${money(p.price)}${p.nickname?' · '+e(p.nickname):''}</small></span></a>`).join('');
    // 售后：让用户从自己的订单里选一笔；常见服务做成可点的推荐问句。
    const orders=(r.orders||[]).map(o=>`<button type="button" class="ai-pet-order" data-action="ai-pick-order" data-id="${o.id}"><b>${e(o.title)}</b><small>¥${money(o.total)} · ${e(o.status_label)}</small></button>`).join('');
    const sug=(r.suggestions||[]).map(s=>`<button type="button" class="ai-pet-sug" data-action="ai-suggest" data-q="${e(s)}">${e(s)}</button>`).join('');
    const transfer=r.action==='transfer';        // 客户明说要人工，且客服在线
    const offline=r.action==='leave_message';    // 客户明说要人工，但客服已下班
    const st=r.support||{};
    const hours=st.hours||'08:00–20:00';
    let card='';
    if(transfer){
      card=`<div class="ai-pet-transfer"><b>要人工处理？</b><p>先提交一张工单说明情况，再从工单页点「联系在线客服」，客服就知道在聊哪件事。</p><button type="button" class="btn primary" data-action="new-ticket">提交工单</button></div>`;
    }else if(offline){
      // 已下班：留言排队，不给「联系在线客服」——点了也没人接。
      card=`<div class="ai-pet-offline"><b>客服已下班（每天 ${hours}）</b><p>留言和工单会按提交顺序排着，${e(st.next_open||'明天 08:00')}上班后处理。你现在写下来，明天不用重新说一遍。</p><button type="button" class="btn primary" data-action="new-ticket">提交工单留言</button></div>`;
    }
    wait.innerHTML=`<div>${petText(r.answer)}</div>
      ${orders?`<div class="ai-pet-orders">${orders}</div>`:''}
      ${links?`<div class="ai-pet-links">${links}</div>`:''}
      ${prods?`<div class="ai-pet-prods">${prods}</div>`:''}
      ${card}
      ${sug?`<div class="ai-pet-sugs">${sug}</div>`:''}
      ${src?`<div class="ai-pet-src">来源：${src}</div>`:''}
      ${r.notice?`<div class="ai-pet-src">${e(r.notice)}</div>`:''}`;
    paintDuty(r.support);          // 状态灯以服务端为准，避免和回答内容打架
    // 历史只留 role/content：情绪分桶已经删掉，没有需要跨轮继承的标签了。
    petHistory.push(
      {role:'user',content:text},
      {role:'assistant',content:String(r.answer||'')});
    petHistory=petHistory.slice(-4);
    if(transfer) setPetState('wave',1800); else setPetState('idle');   // 要转人工就招手喊客服
  }catch(err){
    // 别再把所有错误盖成同一句：500 那次前端只显示「AI 暂时不可用」，
    // 排查时看不到真因。带出状态码，控制台也留一条。
    if(console && console.warn) console.warn('[ai]', err && err.status, err && err.message);
    const msg=err && err.message ? err.message : 'AI 暂时不可用，请稍后再试。';
    wait.innerHTML=`<div>${petText(msg)}</div>`;
    setPetState('fail',1600);             // 出错时小转晃一下，不用再额外弹提示
  }finally{
    if(send) send.disabled=false;
    log.scrollTop=log.scrollHeight;
  }
}


// 所有者办公：查询/起草直接答；账号动作返回 proposal，等 L1 二次确认后执行。
async function petOffice(q, mode){
  const text=String(q||'').trim();
  const log=$('#ai-pet-log'); if(!text||!log) return;
  const form=$('#ai-pet-form'), area=form?.querySelector('textarea[name=q]'), send=form?.querySelector('button[type=submit]');
  if(area) area.value='';
  petAppend(petText(text),'user');
  const wait=petAppend('<span class="ai-pet-typing">正在查平台数据…</span>','bot');
  if(send) send.disabled=true;
  setPetState('review');
  try{
    // 办公请求是全局面板发起的，不跟随页面重渲染丢弃；最多等 60 秒。
    const r=await api('/ai/office',{question:text,mode:mode||'query'},{global:true,timeout:60000});
    const p=r.proposal;
    // 数据查询由后端确定性拼好，另带一份 items：列表比一大段文字好扫。
    const rows=(r.items||[]).map(it=>`<div class="ai-pet-row"><b>${e(it.title)}</b>${it.meta?`<small>${e(it.meta)}</small>`:''}</div>`).join('');
    wait.innerHTML=`<div>${petText(r.answer)}</div>
      ${rows?`<div class="ai-pet-rows">${rows}</div>`:''}
      ${p?`<div class="ai-pet-action"><b>待执行</b><p>${e(p.summary)}</p><p class="muted">不可逆操作，需要你再次确认。</p><button type="button" class="btn primary" data-action="ai-office-confirm" data-kind="${e(p.kind)}" data-target="${p.target}" data-role="${e(p.role||'')}" data-name="${e(p.nickname)}">确认执行</button></div>`:''}
      ${r.mode==='mock'?'<div class="ai-pet-src">模型暂不可用，以上为数据快照</div>':''}`;
    setPetState('idle');
  }catch(err){
    wait.innerHTML=`<div>${petText(err.message||'办公助手暂时不可用')}</div>`;
    setPetState('fail',1600);
  }finally{
    if(send) send.disabled=false;
    log.scrollTop=log.scrollHeight;
  }
}


export const clicks = {
  'new-ticket': () => ticketModal('other'),
  appeal: () => ticketModal('appeal'),

  // 给历史工单补交易凭证：只列当事人或涉事商品相关的订单，避免客服在
  // 全平台订单里翻找，也避免把无关订单错绑进来。
  'link-order': async (b, id) => {
    const rows = await api('/ticket/candidates?id='+id);
    if (!rows.length){ toast('该工单当事人没有可关联的订单，可让对方补充订单号'); return; }
    modal(`<h2>关联订单</h2><p class="muted">只列出与工单当事人或涉事商品有关的订单。关联后金额、买卖双方与交付记录会出现在工单右侧，处理依据才能写实。</p><form id="link-order-form" data-id="${id}"><label class="field"><span>选择订单</span><select name="order_id" required>${rows.map(o=>`<option value="${o.id}">#${o.id} · ${e((o.titles||[]).join('、').slice(0,36))} · ¥${money(o.total)} · ${e(statusNames[o.status]||o.status)} · 买 ${e(o.buyer)} / 卖 ${e(o.seller)}${o.matched_product?' · 含涉事商品':''}</option>`).join('')}</select></label><button class="btn primary full">确认关联</button></form>`);
  },
  report: (b, id) => ticketModal('report', null, id),

  // 在线客服：先有工单才放行（后端同样会拦）。从工单页进来时带 ticket_id，
  // 会话就绑定到那张单，客服打开就知道在聊哪件事。
  'chat-support': async (b, id) => {
    try{
      const r = await api('/support/room', id ? {ticket_id:id} : {});
      go('messages/' + r.id);
    }catch(err){
      toast(err.message);
      // 被门槛拦下时直接把「提交问题」表单递到面前，别让用户自己找入口。
      if (/先提交问题/.test(err.message)) ticketModal('other');
    }
  },

  // 商品被平台处置或卷入退款/争议后，「我发布的」里给卖家的复核入口。
  // 直接开一张关联该商品的申诉工单——卖家不需要自己去客服页找表单，
  // 也不需要知道「申诉」和「联系客服」是两条什么流程。
  'relist-appeal': (b, id) => {
    ticketModal('appeal', null, id);
    const s = document.querySelector('[name=subject]');
    if (s) s.value = `商品 #${id} 重新上架复核申请`;
  },
  'report-community': (b, id) => {
    ticketModal('report');
    $('[name=subject]').value = '社区帖子 #'+id+' 举报';
  },

  // 对账：支付 = 退款 + 净结算 + 待结算，任何一笔对不上都要列出来。
  reconcile: async () => {
    const rows = await api('/reconcile');
    modal(`<h2>模拟资金对账</h2><p class="muted">支付＝退款＋净结算＋待结算。所有金额为模拟记录。</p>${rows.map(r=>`<div class="case-message"><b>订单 #${r.id} · ${r.consistent?'账目一致':'需要核查'}</b><p>支付 ¥${money(r.payment)} / 退款 ¥${money(r.refund)} / 净结算 ¥${money(r.net_settlement)} / 待结算 ¥${money(r.held)}</p></div>`).join('')||'暂无资金记录'}`);
  },

  backup: async () => {
    if (state.config.auth_mode === 'client_kdf') {
      const response = await fetch('/api/backup', { method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + state.token }, body: '{}' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || '备份下载失败');
      }
      const link = document.createElement('a');
      link.href = URL.createObjectURL(await response.blob());
      link.download = `转角私密备份-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
      toast('私密备份已下载，请妥善保管');
      return;
    }
    await api('/backup', {});
    toast('数据库一致性备份已保存到本地数据目录');
  },

  // 信誉分只能由平台管理员、且必须挂在一张已核实的工单上调整。
  // 选违规类型按「基础分＋金额阶梯」自动算（方案 A）；留空则手填分值。
  credit(b, id){
    modal(`<h2>信誉审核调整</h2><p class="muted">必须关联已核实工单并填写理由。选违规类型按「基础分＋金额阶梯」自动算分，也可留空手填。</p>
      <form id="credit-form" data-target="${id}">
        ${field('关联工单编号','ticket_id','number','','required min="1"')}
        <label class="field"><span>违规类型（选填）</span><select name="violation">
          <option value="">手填分值，不自动算</option>
          <option value="minor">轻微违规 · 基础 3 分</option>
          <option value="moderate">中度违规 · 基础 8 分</option>
          <option value="severe">严重违规 · 基础 15 分</option>
        </select></label>
        ${field('调整分值（扣分为负，如 -10；选类型后可留空）','delta','number','','min="-100" max="100"')}
        <label class="field"><span>审核理由</span><textarea name="reason" required></textarea></label>
        <p class="muted" id="credit-hint">金额阶梯：&lt;30 元 +0 · 30–100 +1 · 100–300 +3 · &gt;300 +6</p>
        <div class="stack">
          <button type="button" class="btn secondary" data-action="credit-preview">按价格计算建议分</button>
          <button class="btn primary">确认调整并记录</button>
        </div>
      </form>`);
  },

  // 预览建议分：只读 dry_run，把「基础分 + 金额档」拆开给人看，并预填分值。
  'credit-preview': async () => {
    const form = $('#credit-form'); if (!form) return;
    const violation = form.querySelector('[name=violation]').value;
    const ticketId = form.querySelector('[name=ticket_id]').value;
    if (!violation){ toast('请先选择违规类型'); return; }
    if (!ticketId){ toast('请先填写关联工单编号'); return; }
    const r = await api('/credit', {
      target:Number(form.dataset.target), ticket_id:Number(ticketId),
      violation, dry_run:true, reason:'预览'
    });
    const hint = $('#credit-hint');
    if (hint) hint.innerHTML = `建议扣 <b>${r.suggested}</b> 分（${r.label}基础 ${r.base} ＋ 金额档 ${r.extra}；订单金额 ¥${money(r.amount)}）。可在此基础上手改分值。`;
    const delta = form.querySelector('[name=delta]');
    if (delta && !delta.value) delta.value = -r.suggested;
  },

  // 封禁 / 解封：比扣信誉分更硬的约束，仅管理员对非管理员账号操作。
  // 星级调整：管理员对非管理员账号 ±1/±2 星，写审计并在用户信誉页可见。
  stars(b, id){
    modal(`<h2>调整信誉星级</h2>
      <p class="muted">星级 = 好评成长 + 管理员调整。每次最多 ±2 星，理由会展示在用户的「信誉与申诉」页。</p>
      <form id="stars-form" data-target="${id}">
        <label class="field"><span>调整幅度</span><select name="delta">
          <option value="1">+1 星</option><option value="2">+2 星</option>
          <option value="-1">−1 星</option><option value="-2">−2 星</option>
        </select></label>
        <label class="field"><span>调整理由（用户可见）</span><textarea name="reason" required maxlength="500" placeholder="例如：误判纠正 / 严重违规降级 / 毕业季优质卖家奖励"></textarea></label>
        <button class="btn primary full">确认调整</button>
      </form>`);
  },

  ban: async (b, id) => {
    const banning = b.dataset.value === 'true';
    if (!confirm(banning ? `确认封禁用户 #${id}？封禁后立即下线、在售商品下架、无法登录。` : `确认解封用户 #${id}？`)) return;
    let reason = '';
    if (banning){
      reason = (prompt('封禁理由（会写入审计记录）：') || '').trim();
      if (!reason){ toast('需要填写封禁理由'); return; }
    }else{
      reason = '解封';
    }
    await api('/admin/ban', {target:id, banned:banning, reason});
    toast(banning ? '已封禁' : '已解封');
    await render();
  },
  // 本地 AI 客服：只生成建议，绝不自动发给客户；客服核对后手动插入回复框。
  'ai-reply': async b => {
    const box = b.closest('.ai-reply');
    if (!box) return;
    const out = box.querySelector('.ai-reply-body');
    const ticket = Number(box.dataset.ticket);
    b.disabled = true;
    out.hidden = false;
    out.innerHTML = '<p class="ai-reply-loading">正在检索知识库并生成建议…</p>';
    try {
      const r = await api('/ai/reply', {ticket_id: ticket});
      const sources = (r.sources || []).map((s, i) => `<li><b>[${i + 1}]</b> ${e(s.title || s.source)}</li>`).join('');
      const transfer = r.action === 'transfer';
      out.innerHTML = `<div class="ai-reply-badge ${transfer ? 'is-transfer' : ''}">${transfer ? '建议转人工' : 'AI 建议'}</div>
        <div class="ai-reply-text">${e(r.answer).replace(/\n/g, '<br>')}</div>
        ${r.notice ? `<p class="ai-reply-notice">${e(r.notice)}</p>` : ''}
        <div class="ai-reply-meta">${r.mode === 'rule' ? '规则回复' : r.mode === 'guard' ? '未命中资料' : r.mode === 'mock' ? '知识库摘录' : '模型生成'}${r.latency_ms ? ` · ${Math.round(r.latency_ms)} ms` : ''}</div>
        ${sources ? `<details class="ai-reply-sources"><summary>参考 ${r.sources.length} 条资料</summary><ol>${sources}</ol></details>` : ''}
        <div class="ai-reply-actions"><button type="button" class="btn primary" data-action="ai-insert">插入回复框</button><button type="button" class="btn secondary" data-action="ai-reply">重新生成</button></div>`;
    } catch (err) {
      out.innerHTML = `<p class="ai-reply-error">${e(err.message)}</p>`;
    } finally {
      b.disabled = false;
    }
  },

  'ai-insert': b => {
    const box = b.closest('.ai-reply');
    const text = box?.querySelector('.ai-reply-text')?.innerText || '';
    const area = $('#ticket-reply-form')?.querySelector('textarea[name=body]');
    if (!area || !text) return;
    area.value = text;
    area.focus();
    area.scrollIntoView({block: 'center', behavior: 'smooth'});
    toast('已插入回复框，请核对后发送');
  },
  'ai-pet-toggle': () => togglePetPanel(),
  'ai-pet-chip': b => petAsk(b.dataset.q),
  // 售后：选中订单后把 order_id 一起带给后端，按订单状态回答。
  'ai-pick-order': b => petAsk('订单 #' + b.dataset.id + ' 的售后怎么处理？', {order_id: Number(b.dataset.id)}),
  // 常见服务推荐：点一下就是一句完整问题。
  'ai-suggest': b => petAsk(b.dataset.q),
  'ai-office': b => { petMode = 'office'; petOffice(b.dataset.q, b.dataset.mode || 'query'); },
  'ai-pet-mode': b => {
    petMode = b.dataset.mode === 'office' ? 'office' : 'chat';
    document.querySelectorAll('.ai-pet-mode button').forEach(x => x.classList.toggle('active', x.dataset.mode === petMode));
    const area = $('#ai-pet-q');
    if (area) area.placeholder = petMode === 'office' ? '问用户/订单/商品/工单，或说「把某某降为管理员」…' : '问问小转，例如：怎么发布？';
  },
  // 不可逆动作：L1 在浏览器里再确认一次，确认后才调用执行端点（后端仍校验身份并写审计）。
  'ai-office-confirm': async b => {
    const kind=b.dataset.kind, target=Number(b.dataset.target), role=b.dataset.role||'', name=b.dataset.name||'该账号';
    const verb = kind==='disable' ? '注销' : kind==='revoke' ? '强制下线' : '调整角色';
    if (!window.confirm(`再次确认：${verb}「${name}」？\n此操作会撤销其登录会话，不可逆。`)) return;
    b.disabled=true; b.textContent='执行中…';
    try{
      const r=await api('/ai/office/confirm',{kind,target,role});
      toast(r.message||'已执行');
      b.textContent='已执行';
    }catch(err){ toast(err.message||'执行失败'); b.disabled=false; b.textContent='确认执行'; }
  },
  // 生成演示商品：只生成预览，L1 确认后才入库。
  'ai-office-gen': async b => {
    const log=$('#ai-pet-log'); if(!log) return;
    const topic = window.prompt('生成什么主题的演示商品？（例如：宿舍好物、二手书、运动器材）', b.dataset.q || '宿舍好物');
    if (!topic) return;
    petAppend(petText('生成演示商品：' + topic), 'user');
    const wait=petAppend('<span class="ai-pet-typing">正在生成预览…</span>','bot');
    setPetState('review');
    try{
      const r = await api('/ai/office/generate', {prompt: topic, count: 5});
      pendingProducts = r.items || [];
      if (!pendingProducts.length){
        wait.innerHTML = '<div>没生成出可用的商品，换个主题再试。</div>';
        setPetState('fail',1600);
        return;
      }
      const rows = pendingProducts.map((p,i)=>`<div class="ai-pet-prod" style="cursor:default"><span class="ai-pet-prod-img" style="background-image:url('${e(p.photo||'')}')"></span><span class="ai-pet-prod-txt"><b>${i+1}. ${e(p.title)}</b><small>¥${money(p.price)} · ${e(p.condition)}</small></span></div>`).join('');
      wait.innerHTML = `<div>已生成 ${pendingProducts.length} 件预览（尚未入库）：</div>
        <div class="ai-pet-prods">${rows}</div>
        <div class="ai-pet-action"><b>确认入库</b><p>会以你的账号发布为演示商品（标记 virtual），出现在首页。</p><button type="button" class="btn primary" data-action="ai-office-publish">确认入库（${pendingProducts.length} 件）</button></div>`;
      setPetState('idle');
    }catch(err){
      wait.innerHTML = `<div>${petText(err.message || '生成失败')}</div>`;
      setPetState('fail',1600);
    }
  },
  'ai-office-publish': async b => {
    if (!pendingProducts.length) return;
    if (!window.confirm(`确认把这 ${pendingProducts.length} 件演示商品入库？会出现在首页商品列表。`)) return;
    b.disabled=true; b.textContent='入库中…';
    try{
      const r = await api('/ai/office/publish', {items: pendingProducts});
      toast(`已入库 ${r.count} 件演示商品`);
      b.textContent = `已入库 ${r.count} 件`;
      pendingProducts = [];
    }catch(err){ toast(err.message || '入库失败'); b.disabled=false; b.textContent='重试'; }
  },
  // 小转给了「去首页搜索」：把关键词塞进搜索框并跳到首页。
  'pet-search': b => {
    const q=b.dataset.q||'';
    state.filter.q=q; state.filter.category=''; state.freeShelf=false; state.homeLimit=40;
    togglePetPanel(false);
    go('home');
  },
};

export const submits = {
  'ticket-form': async ({ form, d }) => {
    const r = await api('/tickets', {
      ...d,
      type:form.dataset.type,
      order_id:Number(form.dataset.order) || (d.order_id?Number(d.order_id):null),
      product_id:Number(form.dataset.product) || null
    });
    closeModal();
    go('ticket/'+r.id);
    toast('工单已提交');
  },

  'stars-form': async ({ form, d }) => {
    const r = await api('/admin/stars', {target:Number(form.dataset.target), delta:Number(d.delta), reason:d.reason});
    closeModal();
    toast(`已调整：${r.stars} 星 · ${r.star_title}`);
    await render();
  },

  'ticket-reply-form': async ({ form, d, fd }) => {
    await api('/ticket/reply', {id:Number(form.dataset.id), body:d.body, internal:fd.has('internal')});
    await render();
  },

  'link-order-form': async ({ form, d }) => {
    await api('/ticket/link-order', {id:Number(form.dataset.id), order_id:Number(d.order_id)});
    closeModal();
    toast('已关联订单，处理依据可引用交易记录');
    await render();
  },

  // outcome 由被点下的那个 submit 按钮的 value 决定（认领 / 复核 / 退款 / 结案）。
  'resolve-form': async ({ form, d, button }) => {
    await api('/ticket/resolve', {
      id:Number(form.dataset.id),
      reason:d.reason,
      outcome:button.value,
      amount:Number(form.dataset.amount)
    });
    toast('处理结果已记录，资金均为模拟');
    await render();
  },

  'credit-form': async ({ form, d }) => {
    const violation = d.violation || null;
    const delta = d.delta === '' ? null : Number(d.delta);
    if (!violation && delta === null){ toast('请填写调整分值，或选择违规类型自动计算'); return; }
    const r = await api('/credit', {
      target:Number(form.dataset.target),
      ticket_id:Number(d.ticket_id),
      delta,
      violation,
      reason:d.reason
    });
    closeModal();
    toast(delta !== null ? '信誉变动已审计记录' : `已按价格计算并扣分（现信誉 ${r.score}/100）`);
    await render();
  },
  'ai-pet-form': async ({d}) => { await (petMode === 'office' ? petOffice(d.q) : petAsk(d.q)); },
};
