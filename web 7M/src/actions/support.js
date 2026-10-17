'use strict';
// 事件层 · 工单、信誉审核、资金对账、备份

import { $, toast, e } from '../core/dom.js';
import { money } from '../core/format.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { statusNames } from '../core/state.js';
import { field } from '../components/forms.js';
import { ticketModal } from '../pages/support.js';

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

  // 在线客服：建好与「转角客服」的私聊后直接跳进聊天窗，用户在熟悉的消息
  // 界面里实时沟通；工单仍用于需要留痕的售后/举报/申诉。
  'chat-support': async () => {
    const r = await api('/support/room', {});
    go('messages/' + r.id);
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
  }
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
  }
};
