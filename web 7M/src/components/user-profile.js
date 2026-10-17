'use strict';

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

function versionField(user){
  const version = Number.isSafeInteger(user.profile_version) && user.profile_version >= 0
    ? String(user.profile_version) : '';
  return `<input type="hidden" name="profile_version" value="${version}">`;
}

function optionField(label,name,options,value){
  return `<label class="field" for="user-${name}"><span>${label}</span><select data-user-control id="user-${name}" name="${name}">${options.map(([key,text])=>`<option value="${key}"${value===key?' selected':''}>${text}</option>`).join('')}</select></label>`;
}

export function userProfileSummary(user={}){
  const values = userProfileValues(user);
  const degree = degreeOptions.find(([key])=>key===values.degree_level)[1];
  const status = studyOptions.find(([key])=>key===values.study_status)[1];
  const score = Number.isFinite(user.score) ? user.score : '—';
  return `<div class="user-profile-heading">${userAvatar(user)}<div class="user-profile-identity"><h2>${e(user.nickname || '同学')}</h2><p>${e(user.college || '学院暂未填写')} · ${e(user.major || '专业暂未填写')}</p><div class="user-profile-options"><span>学历：${degree}</span><span>状态：${status}</span></div><p class="user-profile-bio">${e(user.bio || '简介暂未填写')}</p><span class="tag">信誉 ${e(score)}/100 · 不是交易担保</span></div></div>`;
}

export function userProfileForm(user){
  const values = userProfileValues(user);
  return `<form id="user-profile-form" class="panel user-profile-form" aria-labelledby="user-profile-title">${versionField(user)}<h2 id="user-profile-title">个人资料</h2><p class="muted">学历与在读状态可以分别填写，也可以暂不填写；这些信息均为自填。</p><div class="user-profile-fields"><label class="field" for="user-nickname"><span>昵称 *</span><input data-user-control id="user-nickname" name="nickname" value="${e(user.nickname)}" required maxlength="24" autocomplete="nickname"></label><label class="field" for="user-major"><span>专业（可选）</span><input data-user-control id="user-major" name="major" value="${e(user.major)}" maxlength="80"></label>${optionField('学历层次','degree_level',degreeOptions,values.degree_level)}${optionField('在读 / 毕业状态','study_status',studyOptions,values.study_status)}<label class="field user-profile-wide" for="user-college"><span>学院</span><input id="user-college" value="${e(user.college || '暂未填写')}" readonly aria-describedby="user-college-note"><small id="user-college-note">${user.college==='计算机工程学院'?'计算机工程学院试点，不代表学校或学籍认证。':'学院沿用现有账号资料，本页不开放校区变更。'}</small></label><label class="field user-profile-wide" for="user-bio"><span>简介（可选）</span><textarea data-user-control id="user-bio" name="bio" maxlength="300" rows="4">${e(user.bio)}</textarea></label></div><div class="user-profile-buttons"><button data-user-control class="btn primary" type="submit">保存资料</button><button data-user-control class="btn secondary" type="button" data-action="user-profile-reset">重新载入资料</button></div><div data-user-profile-feedback class="user-feedback" role="status" aria-live="polite" tabindex="-1"></div><section data-user-comparison class="user-comparison" aria-label="服务器资料对照" hidden></section></form>`;
}

export function userAvatarForm(user){
  return `<form id="user-avatar-form" class="panel user-avatar-form" aria-labelledby="user-avatar-title">${versionField(user)}<input type="hidden" name="upload_id" value=""><h2 id="user-avatar-title">我的头像</h2><p class="muted">上传后先由你预览，确认设为头像才会公开。</p><div data-user-avatar-preview class="user-avatar-preview">${userAvatar(user)}</div><label class="field" for="user-avatar-file"><span>选择图片</span><input data-user-control id="user-avatar-file" name="avatarfile" type="file" accept="image/jpeg,image/png,image/webp" aria-describedby="user-avatar-note"></label><p id="user-avatar-note" class="muted">支持 JPEG、PNG、WebP，原文件不超过 2 MiB；不支持动画。</p><div class="user-profile-buttons"><button data-user-control class="btn secondary" type="button" data-action="user-avatar-preview">本地预览</button><button data-user-control class="btn primary" type="submit">上传并预览</button><button data-user-control class="btn primary" type="button" data-action="user-avatar-confirm" hidden>确认设为头像</button><button data-user-control class="btn secondary" type="button" data-action="user-avatar-cancel">取消本次选择</button><button data-user-control class="text-button" type="button" data-action="user-avatar-remove">移除当前头像</button></div><div data-user-avatar-feedback class="user-feedback" role="status" aria-live="polite" tabindex="-1"></div></form>`;
}

export function userProfileComparison(user){
  const version = Number.isSafeInteger(user.profile_version) ? user.profile_version : '';
  return `<h3>服务器上的资料</h3><p>当前版本 ${e(version)}。你的表单输入仍保留，请先核对差异。</p>${userProfileSummary(user)}<div class="user-profile-buttons"><button data-user-control type="button" class="btn secondary" data-action="user-profile-keep-input" data-profile-version="${e(version)}">保留我的输入，采用此版本继续编辑</button><button data-user-control type="button" class="btn secondary" data-action="user-profile-reset">用服务器资料替换表单</button></div>`;
}
