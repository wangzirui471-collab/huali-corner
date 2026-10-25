'use strict';
// 页面层 · 信誉与申诉：段位卡、成长路径、加减分规则、红线与记录
import { e, icon } from '../core/dom.js';
import { date } from '../core/format.js';
import { api } from '../core/http.js';
import { state } from '../core/state.js';
import { shell, heading } from '../core/shell.js';
import { needLogin } from '../auth/login.js';

const STAR_MAX = 7;

// 当前状态给一句人话提示，比堆规则更让人愿意读。
function tipFor(me){
  if (me.score < 60) return '信誉分已低于 60，发布和上架暂停中。先申诉或完成现有订单，分数会逐步恢复。';
  if (me.stars_adjust && !me.good_reviews) return `当前星级含管理员调整 ${me.stars_adjust > 0 ? '+' : ''}${me.stars_adjust} 星。持续拿到好评，星级才会真正由口碑撑住。`;
  if (!me.good_reviews) return '还没有收到好评。完成第一单、交付时如实描述，买家打出 4–5 星就能起步冲 5 星。';
  if (me.stars >= STAR_MAX) return '已经封顶。保持真实描述和按时交付，就能稳稳守住「优品卖家」。';
  return `再攒 ${me.next_star_need} 个好评，就能升到 ${me.next_star} 星「${me.next_star_title || ''}」。`;
}

export async function credit(){
  if (!needLogin()) return;
  const [me, history] = await Promise.all([api('/me'), api('/credit/history')]);
  state.me = me;

  const filled = '★'.repeat(me.stars);
  const hollow = '☆'.repeat(STAR_MAX - me.stars);
  const need = me.next_star_need || 0;
  const total = me.good_reviews + need;
  const progress = me.next_star ? Math.min(100, Math.round(me.good_reviews / Math.max(1, total) * 100)) : 100;
  const nextTitle = (me.star_tiers || []).find(t => t.star === me.next_star)?.title || '';
  const barWidth = Math.max(4, progress);  // 0 好评时也留一条可见的进度底线
  const tiers = [{ star: 4, title: '新手卖家', need: 0, base: true }, ...(me.star_tiers || [])];
  const low = me.score < 60;

  const step = t => `<li class="credit-step ${me.stars === t.star ? 'is-current' : ''} ${me.stars > t.star ? 'is-past' : ''}">
      <span class="credit-step-dot"><b>${t.star}</b><i>★</i></span>
      <div class="credit-step-body"><b>${e(t.title)}</b><small>${t.base ? '注册即得' : '累计 ' + t.need + ' 个好评'}</small></div>
      ${me.stars === t.star ? '<span class="credit-step-tag">当前</span>' : ''}
      ${me.stars > t.star ? '<span class="credit-step-check">' + icon('check') + '</span>' : ''}
    </li>`;

  shell(`${heading('TRUST & APPEAL', '信誉与申诉', '信誉分决定你能不能发布，星级决定同学怎么看你。')}

<section class="credit-hero ${low ? 'is-low' : ''}">
  <div class="credit-hero-top">
    <span class="credit-eyebrow">当前段位</span>
    <span class="credit-score-pill">信誉分 <b>${me.score}</b><i>/100</i></span>
  </div>
  <div class="credit-badge">
    <div class="credit-badge-stars" aria-label="${me.stars} 星">${filled}<em>${hollow}</em></div>
    <div class="credit-badge-title">${e(me.star_title)}</div>
    <div class="credit-badge-sub">${me.stars} 星 · ${low ? '已触发发布限制' : '正常经营中'}</div>
  </div>
  <div class="credit-meter">
    <div class="credit-meter-head"><span>升星进度</span><b>${me.good_reviews}${me.next_star ? ' / ' + total : ''} 好评</b></div>
    <div class="credit-meter-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><i style="width:${barWidth}%"></i></div>
    <p>${e(tipFor(Object.assign({}, me, { next_star_title: nextTitle })))}</p>
  </div>
</section>

<section class="panel credit-card">
  <div class="credit-head"><h2>段位成长</h2><small>好评 = 买家完成订单后打的 4–5 星</small></div>
  <ol class="credit-ladder">${tiers.map(step).join('')}</ol>
  <p class="credit-note">4 星起步、7 星封顶。好评 = 买家完成订单后给你打的 4–5 星；差评不会直接掉星，但会进入售后核实。管理员可依据核实结果直接调整星级（每次 ±1/±2），调整记录会出现在下方的信誉时间线里。</p>
</section>

<section class="panel credit-card">
  <div class="credit-head"><h2>怎么加分</h2><span class="credit-chip up">正向</span></div>
  <ul class="credit-feed">
    <li class="up"><span class="credit-delta">+1</span><div><b>收到 4–5 星好评</b><small>每天最多 3 分 · 每月最多 10 分</small></div><span class="credit-feed-ic">${icon('heart')}</span></li>
    <li class="up"><span class="credit-delta">恢复</span><div><b>申诉成功</b><small>客服核实属于误判，返还被扣的分值</small></div><span class="credit-feed-ic">${icon('shield')}</span></li>
    <li class="up"><span class="credit-delta">+</span><div><b>主动配合处理纠纷</b><small>客服核实后酌情加分</small></div><span class="credit-feed-ic">${icon('message')}</span></li>
  </ul>
  <p class="credit-note">信誉分上限 100，加满为止；加分不会替你跳过真实经营记录。</p>
</section>

<section class="panel credit-card">
  <div class="credit-head"><h2>怎么扣分</h2><span class="credit-chip down">违规</span></div>
  <ul class="credit-feed">
    <li class="down"><span class="credit-delta">−3</span><div><b>轻微违规</b><small>描述轻微不符、沟通不当</small></div></li>
    <li class="down"><span class="credit-delta">−8</span><div><b>中度违规</b><small>逾期不交付、拒不配合售后</small></div></li>
    <li class="down"><span class="credit-delta">−15</span><div><b>严重违规</b><small>售假、引导站外交易 · 掉 1 颗星</small></div></li>
  </ul>
  <div class="credit-price">
    <b>金额越大扣得越多</b>
    <div class="credit-steps"><span>&lt;30 元 <i>+0</i></span><span>30–100 <i>+1</i></span><span>100–300 <i>+3</i></span><span>&gt;300 <i>+6</i></span></div>
  </div>
  <p class="credit-note">所有扣分必须由客服关联工单、写明证据理由后才能执行；举报不会自动扣分。</p>
</section>

<section class="panel credit-card">
  <div class="credit-head"><h2>红线与后果</h2><small>分越低，限制越硬</small></div>
  <div class="credit-redlines">
    <div><b>60</b><span>低于此分<br>暂停发布</span></div>
    <div><b>40</b><span>星级封顶<br>2 星</span></div>
    <div><b>20</b><span>降到 1 星<br>仅可浏览</span></div>
  </div>
</section>

<section class="panel credit-card">
  <div class="credit-head"><h2>我的信誉记录</h2>${history.length ? '<small>近 ' + history.length + ' 条</small>' : ''}</div>
  ${history.length
    ? `<ul class="credit-timeline">${history.map(h => `<li class="${h.delta > 0 ? 'up' : 'down'}"><span class="credit-tl-dot"></span><div><b>${h.delta > 0 ? '+' : ''}${h.delta} ${h.kind === 'stars' ? '星' : '分'}</b><p>${e(h.reason)}</p><small>${date(h.created)}${h.ticket_id ? ' · 工单 #' + h.ticket_id : ''}</small></div></li>`).join('')}</ul>`
    : '<p class="credit-empty">还没有信誉变动记录。保持真实描述、按时交付，分数和星级会稳步涨。</p>'}
  <button class="btn secondary full" data-action="appeal">${icon('message')}申请信誉申诉</button>
</section>`, 'me');
}
