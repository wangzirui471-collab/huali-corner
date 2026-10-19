'use strict';
// 用户中心 · 个人资料与头像表单
//
// 2026-10-19 视觉重做（对齐主流二手 App 的个人主页：封面 + 完成度 + 列表行）。
// **契约不可破坏**（actions/user-profile.js 与 tests/user_center.test.mjs 依赖）：
//   · userProfileForm：id=user-profile-form、name=nickname/profile_version/major/
//     degree_level/study_status/bio、id=user-college 且 readonly、version 域在
//     nickname 之前、data-user-profile-feedback、所有控件带 data-user-control
//   · userAvatarForm：id=user-avatar-form、name=upload_id、accept 三类型、
//     confirm 按钮初始 hidden、data-user-avatar-remove/preview/confirm/cancel
//   · userProfileSummary：保存后局部刷新 [data-user-summary]，输出即新封面头部

import { e } from '../core/dom.js';
import { userAvatar } from './user-avatar.js';

export const degreeOptions = [
  ['unspecified','暂不填写'],['bachelor','本科'],['junior_college','专科'],['other','其他']
];
export const studyOptions = [
  ['unspecified','暂不填写'],['studying','在读'],['graduated','已毕业'],['other','其他']
];

export function userProfileValues(user={}){
  // Static public demos still contain legacy education only. Do not infer a
  // degree from graduation, or a study status from a degree.
  const legacyDegree = {'本科':'bachelor','专科':'junior_college'}[user.education] || 'unspecified';
  const legacyStatus = user.education === '已毕业' ? 'graduated' : 'unspecified';
  return {
    degree_level:degreeOptions.some(([key])=>key===user.degree_level) ? user.degree_level : legacyDegree,
    study_status:studyOptions.some(([key])=>key===user.study_status) ? user.study_status : legacyStatus
  };
}

// 资料完成度：昵称/专业/简介/学历/在读状态各 20%。头像走独立表单不计入，
// 避免同一件事在两处催促进度。写 0 也行——完成度只鼓励，不拦截。
function profileProgress(user, values){
  const parts = [
    Boolean((user.nickname||'').trim()),
    Boolean((user.major||'').trim()),
    Boolean((user.bio||'').trim()),
    values.degree_level !== 'unspecified',
    values.study_status !== 'unspecified'
  ];
  return Math.round(parts.filter(Boolean).length / parts.length * 100);
}

function versionField(user){
  const version = Number.isSafeInteger(user.profile_version) && user.profile_version >= 0
    ? String(user.profile_version) : '';
  return `<input type="hidden" name="profile_version" value="${version}">`;
}

function optionField(label,name,options,value){
  return `<label class="field" for="user-${name}"><span>${label}</span><select data-user-control id="user-${name}" name="${name}">${options.map(([key,text])=>`<option value="${key}"${value===key?' selected':''}>${text}</option>`).join('')}</select></label>`;
}

// 资料列表行：标签在左、控件在右（窄屏堆叠）。select 也要 data-user-control。
function rowField(label,name,value,extra=''){
  return `<label class="up-row" for="user-${name}"><span class="up-row-label">${label}</span><input data-user-control id="user-${name}" name="${name}" value="${e(value||'')}" ${extra}></label>`;
}

// 封面头部：公开页（别人的主页）与保存后局部刷新共用这一套 markup。
// 参考图要素：大头像、昵称、学院/在线状态、星级、简介、诚信徽章。
export function userProfileSummary(user={}){
  const values = userProfileValues(user);
  const score = Number.isFinite(user.score) ? user.score : null;
  const stars = score===null ? '' : `<span class="ph-stars" aria-label="信誉 ${score} 分">${'★'.repeat(Math.max(1,Math.round(score/20)))}${'☆'.repeat(5-Math.max(1,Math.round(score/20)))}</span>`;
  return `<div class="profile-hero">
  <div class="profile-cover" aria-hidden="true"></div>
  <div class="profile-hero-body">
    ${userAvatar(user,'large')}
    <div class="profile-hero-main">
      <div class="profile-hero-name"><h2>${e(user.nickname || '同学')}</h2>${user.trusted?'<span class="profile-pill trusted">诚信客户</span>':''}</div>
      <p class="profile-hero-sub">${e(user.college || '学院暂未填写')} · ${e(user.major || '专业暂未填写')} · ${values.degree_level==='unspecified'?'':degreeOptions.find(([k])=>k===values.degree_level)[1]}</p>
      <div class="profile-hero-meta">${stars?`<span class="profile-hero-score">${score} 分 ${stars}</span>`:'<span class="profile-hero-score muted">暂无信誉分</span>'}<span class="profile-hero-online">当前在线</span></div>
      <p class="profile-hero-bio">${e(user.bio || '这位同学还没有写简介。')}</p>
    </div>
  </div>
</div>`;
}

export function userProfileForm(user){
  const values = userProfileValues(user);
  const progress = profileProgress(user, values);
  return `<form id="user-profile-form" class="panel user-profile-form" aria-labelledby="user-profile-title">
  ${versionField(user)}
  <header class="up-head">
    <div><h2 id="user-profile-title">个人资料</h2><p class="muted">学历与在读状态可以分别填写，也可以暂不填写；这些信息均为自填。</p></div>
    <div class="up-progress" aria-label="资料完成度">
      <div class="up-progress-bar"><span style="width:${progress}%"></span></div>
      <small>完成 ${progress}%${progress<100?' · 填得越全，同学越敢直接下单':' · 已经很完整了'}</small>
    </div>
  </header>
  <div class="up-rows">
    ${rowField('昵称 *','nickname',user.nickname,'required maxlength="24" autocomplete="nickname"')}
    ${rowField('专业（可选）','major',user.major,'maxlength="80"')}
    <label class="up-row" for="user-degree_level"><span class="up-row-label">学历层次</span><select data-user-control id="user-degree_level" name="degree_level">${degreeOptions.map(([key,text])=>`<option value="${key}"${values.degree_level===key?' selected':''}>${text}</option>`).join('')}</select></label>
    <label class="up-row" for="user-study_status"><span class="up-row-label">在读状态</span><select data-user-control id="user-study_status" name="study_status">${studyOptions.map(([key,text])=>`<option value="${key}"${values.study_status===key?' selected':''}>${text}</option>`).join('')}</select></label>
    <div class="up-row up-row-readonly"><span class="up-row-label">学院</span><input class="up-row-static" id="user-college" value="${e(user.college || '暂未填写')}" readonly aria-describedby="user-college-note"><small id="user-college-note">${user.college==='计算机工程学院'?'计算机工程学院试点，不代表学校或学籍认证。':'学院沿用现有账号资料，本页不开放校区变更。'}</small></div>
    <label class="up-row up-row-block" for="user-bio"><span class="up-row-label">个人简介（可选）</span><textarea data-user-control id="user-bio" name="bio" rows="3" maxlength="300" placeholder="比如：只出专业书，支持校内自提。">${e(user.bio)}</textarea></label>
  </div>
  <div class="user-profile-buttons"><button data-user-control class="btn primary" type="submit">保存资料</button><button data-user-control class="btn secondary" type="button" data-action="user-profile-reset">重新载入资料</button></div>
  <div data-user-profile-feedback class="user-feedback" role="status" aria-live="polite" tabindex="-1"></div>
  <section data-user-comparison class="user-comparison" aria-label="服务器资料对照" hidden></section>
</form>`;
}

export function userAvatarForm(user){
  return `<form id="user-avatar-form" class="panel user-avatar-form" aria-labelledby="user-avatar-title">
  ${versionField(user)}<input type="hidden" name="upload_id" value="">
  <header class="up-head"><h2 id="user-avatar-title">我的头像</h2><p class="muted">上传后先由你预览，确认设为头像才会公开。</p></header>
  <div class="avatar-stage">
    <div data-user-avatar-preview class="user-avatar-preview">${userAvatar(user)}</div>
    <label class="avatar-picker" for="user-avatar-file"><span class="avatar-picker-icon" aria-hidden="true">＋</span><b>选择图片</b><small>JPEG / PNG / WebP，不超过 2 MiB</small><input data-user-control id="user-avatar-file" name="avatarfile" type="file" accept="image/jpeg,image/png,image/webp" aria-describedby="user-avatar-note"></label>
  </div>
  <p id="user-avatar-note" class="muted">原图仅在预览时存在于本页面；确认前任何人看不到。不支持动画。</p>
  <div class="user-profile-buttons">
    <button data-user-control class="btn secondary" type="button" data-action="user-avatar-preview">本地预览</button>
    <button data-user-control class="btn primary" type="submit">上传并预览</button>
    <button data-user-control class="btn primary" type="button" data-action="user-avatar-confirm" hidden>确认设为头像</button>
    <button data-user-control class="btn secondary" type="button" data-action="user-avatar-cancel">取消本次选择</button>
    <button data-user-control class="text-button" type="button" data-action="user-avatar-remove">移除当前头像</button>
  </div>
  <div data-user-avatar-feedback class="user-feedback" role="status" aria-live="polite" tabindex="-1"></div>
</form>`;
}

export function userProfileComparison(user){
  const version = Number.isSafeInteger(user.profile_version) ? user.profile_version : '';
  return `<h3>服务器上的资料</h3><p>当前版本 ${e(version)}。你的表单输入仍保留，请先核对差异。</p>${userProfileSummary(user)}<div class="user-profile-buttons"><button data-user-control type="button" class="btn secondary" data-action="user-profile-keep-input" data-profile-version="${e(version)}">保留我的输入，采用此版本继续编辑</button><button data-user-control type="button" class="btn secondary" data-action="user-profile-reset">用服务器资料替换表单</button></div>`;
}
