'use strict';
// 页面层 · 信誉与申诉：星级、分数、完整规则与变动记录
import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { api } from '../core/http.js';
import { state } from '../core/state.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const STAR_MAX = 7;

export async function credit(){
  if (!needLogin()) return;
  const [me, history] = await Promise.all([api('/me'), api('/credit/history')]);
  state.me = me;
  const filled = '★'.repeat(me.stars), hollow = '☆'.repeat(STAR_MAX - me.stars);
  const total = me.good_reviews + (me.next_star_need || 0);
  const progress = me.next_star ? Math.min(100, Math.round(me.good_reviews / Math.max(1, total) * 100)) : 100;
  const nextTitle = (me.star_tiers || []).find(t => t.star === me.next_star)?.title || '';

  shell(`${heading('TRUST & APPEAL', '信誉与申诉', '信誉分决定你能不能发布，星级决定同学怎么看你。')}

<section class="panel credit-hero">
  <div class="credit-stars" aria-label="${me.stars} 星">${filled}<span class="credit-stars-empty">${hollow}</span></div>
  <h2>${me.stars} 星 · ${e(me.star_title)}</h2>
  <p class="muted">信誉分 ${me.score}/100${me.score < 60 ? ' · 已暂停发布，申诉通过后恢复' : ''}</p>
  ${me.next_star
    ? `<div class="credit-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><i style="width:${progress}%"></i></div>
       <p class="muted">已获 ${me.good_reviews} 个好评，再得 <b>${me.next_star_need}</b> 个升到 ${me.next_star} 星「${e(nextTitle)}」</p>`
    : '<p class="muted">已达最高星级</p>'}
</section>

<section class="panel">
  <h2>星级怎么定</h2>
  <div class="credit-tiers">
    <div class="credit-tier base ${me.stars === 4 ? 'current' : ''}"><span>★★★★</span><b>4 星 · 新手卖家</b><small>注册即得</small></div>
    ${(me.star_tiers || []).map(t => `<div class="credit-tier ${me.stars === t.star ? 'current' : ''}"><span>${'★'.repeat(t.star)}</span><b>${t.star} 星 · ${e(t.title)}</b><small>累计 ${t.need} 个好评</small></div>`).join('')}
  </div>
  <p class="muted">4 星起步、7 星封顶。好评 = 买家完成订单后给你打的 4–5 星；差评不会直接掉星，但会进入售后核实。</p>
</section>

<section class="panel">
  <h2>怎么加分</h2>
  <ul class="credit-rules">
    <li><b>收到 4–5 星好评</b><span>+1 分 · 每天最多 3 分、每月最多 10 分</span></li>
    <li><b>申诉成功</b><span>客服核实属于误判后，恢复被扣的分值</span></li>
    <li><b>主动配合处理纠纷</b><span>客服核实后可酌情加分</span></li>
  </ul>
  <p class="muted">信誉分上限 100；分数满了也不会溢出，加分不会让你越过真实经营记录拿标签。</p>
</section>

<section class="panel">
  <h2>怎么扣分</h2>
  <ul class="credit-rules">
    <li><b>轻微违规</b><span>-3 分起</span></li>
    <li><b>中度违规</b><span>-8 分起</span></li>
    <li><b>严重违规（售假、引导站外交易等）</b><span>-15 分起 · 掉 1 颗星</span></li>
  </ul>
  <p class="muted">金额越大扣得越多：订单 &lt;30 元 +0；30–100 元 +1；100–300 元 +3；&gt;300 元 +6。所有扣分必须由客服关联工单、写明证据和理由后才能执行，不能凭举报直接扣。</p>
</section>

<section class="panel">
  <h2>红线与后果</h2>
  <ul class="credit-rules">
    <li><b>低于 60 分</b><span>暂停发布与重新上架</span></li>
    <li><b>低于 40 分</b><span>星级最高 2 星，限制交易</span></li>
    <li><b>低于 20 分</b><span>降到 1 星，仅可浏览</span></li>
  </ul>
</section>

<section class="panel">
  <h2>我的信誉记录</h2>
  ${history.length
    ? history.map(h => `<div class="case-message"><b>${h.delta > 0 ? '+' : ''}${h.delta} 分</b><p>${e(h.reason)}</p><small>${date(h.created)}${h.ticket_id ? ' · 工单 #' + h.ticket_id : ''}</small></div>`).join('')
    : '<p class="muted">还没有信誉变动记录。保持真实描述、按时交付，分数和星级会稳步涨。</p>'}
  <button class="btn secondary" data-action="appeal">${icon('message')}申请信誉申诉</button>
</section>`, 'me');
}
