'use strict';
// 事件层 · 工单、信誉审核、资金对账、备份

import { $, toast } from '../core/dom.js';
import { money } from '../core/format.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { ticketModal } from '../pages/support.js';
import { uploadEvidenceFiles, creditDialog } from './support-operations.js';
import { context } from '../core/context.js';

export const clicks = {
  'new-ticket': () => ticketModal('other'),
  appeal: () => ticketModal('appeal'),
  report: (b, id) => ticketModal('report', null, id),
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
  credit:(b,id)=>creditDialog(context(),id)
};

export const submits = {
  'ticket-form': async ({ form, d }) => {
    const r = await api('/tickets', {
      ...d,
      evidence:await uploadEvidenceFiles(form,context()),
      type:form.dataset.type,
      order_id:Number(form.dataset.order) || null,
      product_id:Number(form.dataset.product) || null,
      related_ticket_id:Number(form.dataset.related) || null
    });
    closeModal();
    go('ticket/'+r.id);
    toast('工单已提交');
  },

  'ticket-reply-form': async ({ form, d, fd }) => {
    await api('/ticket/reply', {id:Number(form.dataset.id), body:d.body, internal:fd.has('internal')});
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
    await api('/credit', {
      target:Number(form.dataset.target),
      ticket_id:Number(d.ticket_id),
      delta:Number(d.delta),
      reason:d.reason
    });
    closeModal();
    toast('信誉变动已审计记录');
    await render();
  }
};
