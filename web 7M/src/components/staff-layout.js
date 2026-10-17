import { e } from '../core/dom.js';

const sections = [['overview','工作概览'],['queue','工单中心'],['content','内容管理'],['users','用户与信誉'],['team','客服管理'],['operations','账务与设置'],['audit','操作审计']];

export function staffFrame(context, active, content) {
  const admin = context.user.role === 'admin';
  const visible = admin ? sections : sections.filter(([key])=>['overview','queue','content'].includes(key));
  return `<div class="staff-layout"><nav class="staff-navigation panel" data-staff-navigation aria-label="管理工作台导航"><strong>${admin?'平台管理':'客服工作'}台</strong>${visible.map(([key,title])=>`<button class="${active===key?'selected':''}" data-go="staff/${key}" ${active===key?'aria-current="page"':''}>${title}</button>`).join('')}<button data-go="me">账号与密码</button><button data-go="home">返回交易首页</button></nav><div class="staff-content">${content}</div></div>`;
}

export function caseRow(ticket, date) {
  const labels = {open:'待认领',processing:'处理中',review:'待复核',resolved:'已解决'};
  const types = {refund:'售后',report:'举报',appeal:'申诉',other:'咨询',reschedule:'改约'};
  const elapsed = Math.max(0, Math.floor((Date.now()/1000-ticket.updated_at)/3600));
  return `<button class="ticket-row" data-go="ticket/${ticket.id}"><span class="ticket-type">${e(types[ticket.type]||ticket.type)}</span><span><b>${e(ticket.subject)}</b><small>#${ticket.id} · ${e(ticket.nickname)} · ${ticket.assignee_name?'负责人：'+e(ticket.assignee_name):'未分配'}<br>最后更新 ${e(date(ticket.updated_at))} · ${elapsed<1?'不足1小时':elapsed+'小时'}${ticket.status==='resolved'?'前更新':'未更新'}</small></span><span class="case-row-status">${ticket.has_unread?'<span class="tag">新通知</span>':''}${ticket.overdue?'<span class="tag danger">超过24小时未更新</span>':''}<span class="tag">${labels[ticket.status]||e(ticket.status)}</span></span></button>`;
}

export function pageControls(route, result, extra='') {
  const pages = Math.max(1, Math.ceil(result.total/result.page_size));
  return `<div class="staff-pagination"><button class="btn secondary" data-go="${route}?page=${result.page-1}${extra}" ${result.page<=1?'disabled':''}>上一页</button><span>第 ${result.page} / ${pages} 页 · ${result.total} 条</span><button class="btn secondary" data-go="${route}?page=${result.page+1}${extra}" ${result.page>=pages?'disabled':''}>下一页</button></div>`;
}
