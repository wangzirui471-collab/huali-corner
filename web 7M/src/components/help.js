import { e } from '../core/dom.js';
import { money, date } from '../core/format.js';
import { field, selectField } from './forms.js';

export const helpTypes=[['parcel','快递代取'],['documents','资料代交'],['moving','搬运帮忙'],['study','学习辅导／笔记整理'],['other','其他互助']];
export function helpForm(){
 return `<form id="help-post-form" data-key="${crypto.randomUUID()}"><div class="form-grid">${selectField('发布方向','kind',[['need','我需要帮助'],['offer','我提供服务']])}${selectField('服务类别','service_type',helpTypes)}${field('标题','title','text','','required maxlength="80" placeholder="例如：今晚帮取一件小快递"')}${field('意向报酬（元，留空面议）','reward_yuan','number','','min="0" max="10000" step="0.01" placeholder="可填0表示无偿"')}${field('公共地点','place','text','','required maxlength="120" placeholder="如 C1楼下公共入口"')}${field('截止时间','deadline','datetime-local','','required')}</div><label class="field"><span>需求说明</span><textarea name="body" required maxlength="2000" placeholder="说明物品大小、时间要求等；取件码和个人联系方式请私聊提供。"></textarea></label><p class="muted">这是信息发布与私聊协商，不创建服务订单、不收款、不承诺服务担保。</p><button class="btn primary full">发布互助信息</button></form>`;
}

export function helpCard(post){
 const active=post.status==='open';
 return `<article class="panel help-card" data-help-post="${post.id}"><div class="section-heading"><span class="tag">${e(post.service_label)} · ${post.kind==='need'?'需要帮助':'提供服务'}</span><span class="tag">${{open:'招募中',closed:'已关闭',expired:'已过期'}[post.status]}</span></div><h2><button class="text-button" data-go="help/${post.id}">${e(post.title)}</button></h2><p class="post-body">${e(post.body)}</p><p><b>${post.reward===null?'报酬面议':post.reward===0?'无偿互助':'意向报酬 ¥'+money(post.reward)}</b></p><p class="muted">${e(post.place)} · 截止 ${date(post.deadline)}</p><button class="text-button" data-go="profile/${post.user_id}">${e(post.nickname)} · ${e(post.college)}</button><div class="stack">${post.is_owner?`<button class="btn secondary" data-action="help-status" data-id="${post.id}" data-value="${active?'closed':'open'}" ${post.status==='expired'?'disabled':''}>${active?'关闭需求':'重新开放'}</button>`:active?`<button class="btn primary" data-action="chat" data-id="${post.user_id}">私聊协商</button>`:'<span class="muted">已停止招募</span>'}<button class="text-button" data-action="comments" data-id="${post.id}">公开留言</button><button class="text-button" data-action="help-feedback" data-id="${post.id}">客服反馈</button><button class="text-button" data-action="help-report" data-id="${post.id}">举报</button></div></article>`;
}
