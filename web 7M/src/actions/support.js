'use strict';
// 事件层 · 工单、信誉审核、资金对账、备份

import { $, toast } from '../core/dom.js';
import { money } from '../core/format.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';
import { ticketModal } from '../pages/support.js';

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
  credit(b, id){
    modal(`<h2>信誉审核调整</h2><p class="muted">必须关联已核实工单，填写理由。举报不自动扣分，用户可申诉。</p><form id="credit-form" data-target="${id}">${field('关联工单编号','ticket_id','number','','required min="1"')}${field('调整分值（如 -10 或 +10）','delta','number','','required min="-100" max="100"')}<label class="field"><span>审核理由</span><textarea name="reason" required></textarea></label><button class="btn primary">确认调整并记录</button></form>`);
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
      order_id:Number(form.dataset.order) || null,
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
