import { context } from '../core/context.js';
import { e } from '../core/dom.js';
import { staffFrame, caseRow, pageControls } from '../components/staff-layout.js';
import { types, names } from '../components/support-fields.js';

const titles = {overview:'工作概览',queue:'工单中心',content:'内容管理',users:'用户与信誉',team:'客服管理',operations:'账务与设置',audit:'操作审计'};
const scopes = [['all','全部工单'],['unassigned','待认领'],['mine','我负责'],['review','待复核'],['new','有新通知'],['overdue','超过24小时未更新']];
const roles = {admin:'管理员',support:'客服',user:'普通用户'};
const auditLabels = {product_delist:'商品下架',ticket_claim:'认领工单',ticket_review:'提交复核',ticket_refund:'批准模拟退款',ticket_request_refund:'退款建议',ticket_reject:'不支持申请并结案',ticket_resolved:'协商结案',ticket_assignment:'指派／转派',ticket_handoff:'客服工单交接',support_provision:'创建客服账号',support_active:'变更客服状态',credit:'信誉处罚',credit_warning:'违规提醒',credit_reversal:'冲回处罚',credit_recovery:'整改恢复',appointment:'群管理员任命',moderation:'群聊管理'};

function options(items, value) {
  return items.map(([key,label])=>`<option value="${e(key)}" ${value===key?'selected':''}>${e(label)}</option>`).join('');
}

function stats(summary) {
  return `<div class="staff-stats">${[['unassigned','待认领'],['mine','我负责'],['review','待复核'],['new','有新通知'],['overdue','超过24小时未更新']].map(([key,label])=>`<button class="panel" data-go="staff/queue?scope=${key}"><span>${label}</span><strong>${summary[key]}</strong></button>`).join('')}</div>`;
}

async function queueView(owner, section, params) {
  const filters = Object.fromEntries(params);
  if (section==='content' && !filters.type) filters.type='report';
  const result = await owner.request('/staff/queue?'+new URLSearchParams(filters));
  const extra = new URLSearchParams({...filters});extra.delete('page');
  return `${stats(result.summary)}<section class="panel"><div class="section-heading"><h2>${section==='content'?'内容举报队列':'工单队列'}</h2><button class="btn secondary" data-action="staff-refresh">刷新列表</button></div>${section==='content'?'<p class="muted">可从商品详情直接下架在售商品，也可在下方认领举报、核对原内容。下架不会自动扣分。</p><button class="btn secondary" data-go="home">浏览商品并管理</button>':''}<form id="staff-queue-form" data-section="${section}" class="staff-filter"><label class="field"><span>搜索标题／编号／负责人</span><input name="q" value="${e(filters.q||'')}" maxlength="100"></label><label class="field"><span>待办范围</span><select name="scope">${options(scopes,filters.scope||'all')}</select></label><label class="field"><span>类型</span><select name="type">${options([['','全部'],...Object.entries(types)],filters.type||'')}</select></label><label class="field"><span>状态</span><select name="status">${options([['','全部'],...['open','processing','review','resolved'].map(k=>[k,names[k]])],filters.status||'')}</select></label><button class="btn primary">筛选工单</button></form><p class="muted">优先显示超过24小时未更新的工单，同组按最早更新时间排列。新通知以消息中心未读状态为准。</p><div class="ticket-list">${result.items.map(t=>caseRow(t,owner.date)).join('')||'<p class="muted">此条件下暂无工单。</p>'}</div>${pageControls('staff/'+section,result,extra.size?'&'+extra.toString():'')}</section>`;
}

async function overview(owner) {
  const result = await owner.request('/staff/queue?page_size=5');
  return `${stats(result.summary)}<section class="panel"><div class="section-heading"><h2>优先处理</h2><button class="btn primary" data-go="staff/queue">查看全部工单</button></div><div class="ticket-list">${result.items.map(t=>caseRow(t,owner.date)).join('')||'<p class="muted">当前没有工单。</p>'}</div></section><section class="panel"><h2>工作说明</h2><p>客服服务时段：08:00—20:00。客服认领、回复和提交建议；退款批准、信誉处理与人员授权由管理员处理。</p><p class="muted">状态为“启用”表示账号可使用，不代表本人在线。交易资金全部为模拟。</p></section>`;
}

async function users(owner, params) {
  const data=await owner.request('/admin');
  const q=(params.get('q')||'').trim().toLowerCase();
  const all=data.users.filter(u=>(u.nickname+' '+u.id+' '+u.college).toLowerCase().includes(q));
  const page=Math.max(1,Number(params.get('page'))||1), items=all.slice((page-1)*20,page*20);
  return `<section class="panel"><h2>用户与信誉</h2><form id="staff-user-form" class="staff-search"><input name="q" value="${e(q)}" placeholder="昵称、编号或学院" aria-label="搜索用户"><button class="btn secondary">搜索用户</button></form><p class="muted">处罚只针对已核实并结束的关联工单；退款、举报、点赞本身不会自动扣分。</p><div class="user-table">${items.map(u=>`<div><span><b>${e(u.nickname)}</b><small>#${u.id} · ${e(roles[u.role]||u.role)} · ${e(u.college)}</small></span><b>${u.score}/100</b>${u.id!==owner.user.id?`<button class="text-button" data-credit-user="${u.id}">信誉处理</button>`:''}</div>`).join('')||'<p>没有符合条件的用户。</p>'}</div>${pageControls('staff/users',{total:all.length,page,page_size:20},'&q='+encodeURIComponent(q))}</section>`;
}

async function team(owner) {
  const [workers,data]=await Promise.all([owner.config.trial?owner.request('/admin/support'):[],owner.request('/admin')]);
  return `<section class="panel"><div class="section-heading"><h2>独立客服账号</h2>${owner.config.trial?'<button class="btn primary" data-operation="create-support">创建客服账号</button>':''}</div><p class="muted">每人使用独立账号。停用会撤销登录会话，将未结工单退回待分配队列；待复核状态保留。交接记录可在审计中查看。</p>${workers.map(w=>`<div class="offer-row"><span><b>${e(w.nickname)}</b><br><small>${e(w.phone.replace(/^(\d{3})\d{4}(\d{4})$/,'$1****$2'))} · ${w.is_active?'启用':'停用'} · 未结工单 ${w.pending_count}</small></span><button class="btn secondary" data-operation="support-active" data-id="${w.id}" data-active="${!w.is_active}">${w.is_active?'停用并交接':'启用客服'}</button></div>`).join('')||'<p>暂无独立客服账号。</p>'}</section><section class="panel"><h2>群管理员申请</h2>${data.nominations.map(n=>`<div class="offer-row"><span>${e(n.nickname)} · ${e(n.name)}<br>${e(n.reason)}</span>${n.status==='pending'?`<button class="btn secondary" data-action="appoint" data-id="${n.id}">批准任命</button>`:`<span>${e({approved:'已批准',rejected:'已拒绝'}[n.status]||n.status)}</span>`}</div>`).join('')||'<p class="muted">暂无申请。</p>'}</section>`;
}

async function operations(owner) {
  const [status,records]=await Promise.all([owner.request('/admin/operations'),owner.request('/reconcile')]);
  const inconsistent=records.filter(r=>!r.consistent);
  return `<section class="panel"><h2>模拟账务核对</h2><p>共 ${records.length} 笔订单，需核查 ${inconsistent.length} 笔。</p><p class="muted">支付＝退款＋净结算＋待结算；所有金额均为模拟记录。</p><button class="btn secondary" data-action="reconcile">查看逐笔记录</button>${inconsistent.map(r=>`<p>订单 #${r.id} 需要核查 <button class="text-button" data-go="orders/${r.id}">查看订单</button></p>`).join('')}</section><section class="panel"><h2>备份与恢复</h2>${status.last_backup?`<p>最近成功创建：${e(owner.date(status.last_backup.created))}</p><p class="muted">${e(status.last_backup.file)} · ${(status.last_backup.bytes/1024).toFixed(1)} KB</p>`:'<p>尚无记录到的成功备份，请创建并另存副本。</p>'}${status.last_error?`<p class="tag danger">最近备份失败：${e(status.last_error)}</p>`:''}<button class="btn secondary" data-action="backup">保存完整备份</button><p class="muted">备份保存在服务器数据目录的 backups 文件夹，包含私人数据，不提供公开下载。建议运营者另存副本。</p><details><summary>恢复操作说明</summary><p>先停止服务，将备份解压到新的空数据目录，使用该目录启动。核对订单、图片与账务后再恢复使用，不覆盖原数据。</p><p class="muted">创建成功不等于已经做过恢复演练，请定期按上述步骤验证。</p></details></section><section class="panel"><h2>账号与密码</h2><button class="btn secondary" data-go="me">修改密码／退出登录</button><p class="muted">忘记密码时，在登录窗口使用私密恢复码。管理员没有恢复码时，需由服务器运营者通过本机管理命令重置，不能仅凭手机号找回。</p></section>`;
}

async function audit(owner, params) {
  const result=await owner.request('/admin/audit?'+params);
  return `<section class="panel"><h2>操作审计</h2><form id="staff-audit-form" class="staff-search"><input name="q" value="${e(params.get('q')||'')}" placeholder="操作人、对象、依据或操作类型代码" aria-label="搜索审计记录"><button class="btn secondary">搜索记录</button></form><div data-audit-list>${result.items.map(item=>`<article class="case-message"><b>${e(auditLabels[item.type]||item.type)} · #${item.id}</b><p>${e(item.actor_name||'系统')}（#${item.actor||'—'}） → ${e(item.target_name||'相关流程')}${item.target?'（#'+item.target+'）':''}</p><p>${e(item.reason)}</p><small>${e(owner.date(item.created))}${item.score_before!==null&&item.score_before!==undefined?' · 信誉 '+item.score_before+' → '+item.score_after:''}</small>${item.ticket_id?`<button class="text-button" data-go="ticket/${item.ticket_id}">工单 #${item.ticket_id}</button>`:''}${item.product_id?`<button class="text-button" data-go="product/${item.product_id}">商品 #${item.product_id}</button>`:''}</article>`).join('')||'<p>暂无记录。</p>'}</div>${pageControls('staff/audit',result,'&q='+encodeURIComponent(params.get('q')||''))}</section>`;
}

export async function staffPage(section='overview', query='') {
  const owner=context();
  if (!['admin','support'].includes(owner.user?.role)) throw new Error('没有工作台权限');
  if (!titles[section]) section='overview';
  if (owner.user.role!=='admin'&&!['overview','queue','content'].includes(section)) throw new Error('仅管理员可使用此分区');
  const params=new URLSearchParams(query);
  const content=section==='overview'?await overview(owner):['queue','content'].includes(section)?await queueView(owner,section,params):section==='users'?await users(owner,params):section==='team'?await team(owner):section==='operations'?await operations(owner):await audit(owner,params);
  owner.shell(staffFrame(owner,section,`${owner.heading('STAFF WORKSPACE',titles[section],'客服08:00—20:00 · 所有支付、退款与结算均为模拟')}${content}`),'staff');
}
