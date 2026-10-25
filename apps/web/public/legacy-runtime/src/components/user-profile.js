'use strict';
// 用户中心的展示层：资料预览、资料编辑（设置行）、头像上传（左右分栏）。
//
// 与事件层的契约（改结构时不能动，否则 actions/user-profile.js 会断）：
//   · 根节点 [data-user-center] + data-user-owner = 当前用户 id
//   · 预览区 [data-user-summary]（applyProfile 会整块替换 innerHTML）
//   · 表单 #user-profile-form / #user-avatar-form，字段名 nickname/major/bio/
//     degree_level/study_status/profile_version/upload_id/avatarfile 不变
//   · 头像预览容器 [data-user-avatar-preview]
//   · 反馈区 [data-user-profile-feedback] / [data-user-avatar-feedback]
//   · 冲突对照面板 [data-user-comparison]
//   · 所有需要「提交中锁定」的控件带 data-user-control

import { e } from '../core/dom.js';
import { userAvatar } from './user-avatar.js';

export const degreeOptions = [
  ['unspecified','暂不填写'],['bachelor','本科'],['junior_college','专科'],['other','其他']
];
export const studyOptions = [
  ['unspecified','暂不填写'],['studying','在读'],['graduated','已毕业'],['other','其他']
];

export function userProfileValues(user={}){
  // 静态演示版只有旧 education 字段。不从「已毕业」反推学历，也不从学历反推在读状态。
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

// 一行设置：左标签（可带一行小字说明）右控件。is-stacked 用于文本域（整行）。
function row({label, note = '', forId = '', control, stacked = false}){
  const tag = forId ? 'label' : 'span';
  const forAttr = forId ? ` for="${forId}"` : '';
  return `<div class="uc-row${stacked ? ' is-stacked' : ''}">
    <div class="uc-label-wrap"><${tag} class="uc-label"${forAttr}>${label}</${tag}>${note ? `<small class="uc-note">${note}</small>` : ''}</div>
    <div class="uc-ctl">${control}</div>
  </div>`;
}

function optionField(label, name, options, value){
  return row({
    label,
    forId: 'uc-'+name,
    control: `<select data-user-control id="uc-${name}" name="${name}">${options.map(([key,text])=>`<option value="${key}"${value===key?' selected':''}>${text}</option>`).join('')}</select>`
  });
}

/** 预览区：对应抖音个人主页头部。改完立刻看到「别人会看到什么」。 */
export function userProfileSummary(user={}){
  const values = userProfileValues(user);
  const degree = degreeOptions.find(([key])=>key===values.degree_level)[1];
  const status = studyOptions.find(([key])=>key===values.study_status)[1];
  const score = Number.isFinite(user.score) ? user.score : '—';
  return `<div class="uc-preview">${userAvatar(user,'large')}<div class="uc-preview-who"><b class="uc-preview-name">${e(user.nickname || '同学')}</b><p class="uc-preview-meta">${e(user.college || '学院暂未填写')} · 学历：${degree} · 在读状态：${status}</p><span class="uc-chip">信誉 ${e(score)} / 100 · 不是交易担保</span></div></div>`;
}

/** 资料编辑：设置行结构，一行一项。 */
export function userProfileForm(user){
  const values = userProfileValues(user);
  const collegeNote = user.college === '计算机工程学院'
    ? '由平台统一维护，不可自行修改；不代表学校或学籍认证。'
    : '学院沿用现有账号资料，本页不开放修改。';
  return `<form id="user-profile-form" class="uc-form">${versionField(user)}
    <div class="uc-rows">
      ${row({label:'昵称 *', note:'展示在帖子和订单里', forId:'uc-nickname',
        control:`<input data-user-control id="uc-nickname" name="nickname" value="${e(user.nickname)}" required maxlength="24" autocomplete="nickname">`})}
      ${row({label:'专业', note:'选填', forId:'uc-major',
        control:`<input data-user-control id="uc-major" name="major" value="${e(user.major)}" maxlength="80" placeholder="例如：软件工程">`})}
      ${optionField('学历层次','degree_level',degreeOptions,values.degree_level)}
      ${optionField('在读 / 毕业状态','study_status',studyOptions,values.study_status)}
      ${row({label:'学院', control:`<span class="uc-readonly">${e(user.college || '暂未填写')}</span><small class="uc-note uc-readonly-note">${e(collegeNote)}</small>`})}
      ${row({label:'个人简介', note:'选填，最多 300 字', forId:'uc-bio', stacked:true,
        control:`<textarea data-user-control id="uc-bio" name="bio" maxlength="300" rows="4" placeholder="介绍一下你自己，或者写下你希望交易时对方注意的事。">${e(user.bio)}</textarea>`})}
    </div>
    <div data-user-profile-feedback class="uc-feedback" role="status" aria-live="polite" tabindex="-1"></div>
    <section data-user-comparison class="uc-compare" aria-label="服务器资料对照" hidden></section>
  </form>`;
}

/** 头像：左预览 右操作，独立分组。三阶段按钮显隐顺序与旧版完全一致。 */
export function userAvatarForm(user){
  return `<form id="user-avatar-form" class="uc-avatar-form">${versionField(user)}
    <input type="hidden" name="upload_id" value="">
    <div class="uc-avatar-body">
      <div class="uc-avatar-left">
        <div data-user-avatar-preview class="uc-avatar-slot">${userAvatar(user,'large')}</div>
        <small class="uc-note">当前头像</small>
      </div>
      <div class="uc-avatar-right">
        <input data-user-control id="uc-avatar-file" name="avatarfile" type="file" class="uc-file-native" accept="image/jpeg,image/png,image/webp" aria-describedby="uc-avatar-note">
        <div class="uc-file-row">
          <label class="uc-btn uc-file-btn" for="uc-avatar-file">选择图片</label>
          <span class="uc-file-name" data-user-file-name>未选择图片</span>
        </div>
        <p id="uc-avatar-note" class="uc-note">支持 JPEG、PNG、WebP，原文件不超过 2 MiB；不支持动画与多帧图片。</p>
        <div class="uc-ops">
          <button data-user-control class="uc-btn is-primary" type="submit">上传并预览</button>
          <button data-user-control class="uc-btn" type="button" data-action="user-avatar-preview">本地预览</button>
          <button data-user-control class="uc-btn" type="button" data-action="user-avatar-cancel">取消本次选择</button>
          <button data-user-control class="uc-btn is-primary" type="button" data-action="user-avatar-confirm" hidden>确认设为头像</button>
          <button data-user-control class="uc-link uc-ops-end" type="button" data-action="user-avatar-remove">移除当前头像</button>
        </div>
        <div data-user-avatar-feedback class="uc-feedback" role="status" aria-live="polite" tabindex="-1"></div>
      </div>
    </div>
  </form>`;
}

/** 409 冲突时的对照面板。 */
export function userProfileComparison(user){
  const version = Number.isSafeInteger(user.profile_version) ? user.profile_version : '';
  return `<h3 class="uc-compare-title">服务器上的资料</h3><p class="uc-note">当前版本 ${e(version)}。你的表单输入仍保留，请先核对差异。</p>${userProfileSummary(user)}<div class="uc-ops"><button data-user-control type="button" class="uc-btn" data-action="user-profile-keep-input" data-profile-version="${e(version)}">保留我的输入，采用此版本继续编辑</button><button data-user-control type="button" class="uc-btn" data-action="user-profile-reset">用服务器资料替换表单</button></div>`;
}
