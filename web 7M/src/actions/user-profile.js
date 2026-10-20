'use strict';

// All shared account data stays in state.me. Per-operation session snapshots
// live only in closures; unsaved inputs and upload selections stay on the form.
import { e, icon } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { modal } from '../core/shell.js';
import { userAvatar } from '../components/user-avatar.js';
import { userProfileSummary, userProfileComparison, userProfileValues } from '../components/user-profile.js';

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;
const AVATAR_ID = /^ua_[0-9a-f]{32}$/;
const CONFLICT_MESSAGE = '资料已更新，请重新载入并核对';

export function isUserProfileConflict(error){
  // Current core/http.js exposes message only; A may add status without
  // breaking existing callers. This exact message is our own domain contract.
  return error?.status === 409 || error?.message === CONFLICT_MESSAGE;
}

function profileVersion(value){
  if (!/^\d+$/.test(String(value))) throw new Error('资料版本不可用，请重新载入资料');
  const version = Number(value);
  if (!Number.isSafeInteger(version)) throw new Error('资料版本不可用，请重新载入资料');
  return version;
}

function scopeFor(element){
  const root = element.closest('[data-user-center]');
  const owner = state.me?.id, token = state.token, epoch = state.renderId, route = location.hash;
  if (!root || !owner || !token || root.dataset.userOwner !== String(owner)) {
    throw new Error('请重新登录后打开个人资料');
  }
  return {root, owner, token, epoch, visible:()=>root.isConnected
    && state.me?.id===owner && state.token===token && state.renderId===epoch && location.hash===route};
}

function lock(scope){
  if (scope.root.dataset.userBusy === '1' || !scope.visible()) return null;
  scope.root.dataset.userBusy = '1';
  const controls = [...scope.root.querySelectorAll('[data-user-control]')]
    .map(control=>[control,control.disabled]);
  for (const [control] of controls) control.disabled = true;
  return ()=>{
    delete scope.root.dataset.userBusy;
    if (scope.visible()) for (const [control,disabled] of controls) control.disabled = disabled;
  };
}

function feedback(scope, area, text){
  const target = scope.root.querySelector(`[data-user-${area}-feedback]`);
  if (target && scope.visible()) { target.innerHTML = ''; target.textContent = text; }
}

function failure(scope, area, error){
  if (!scope.visible()) return;
  const target = scope.root.querySelector(`[data-user-${area}-feedback]`);
  if (!target) return;
  if (isUserProfileConflict(error)) {
    target.innerHTML = '<p>资料已在其他页面更新。你的输入仍保留，请先核对服务器资料。</p><button data-user-control type="button" class="btn secondary" data-action="user-profile-compare">查看服务器资料并核对</button>';
  } else {
    target.textContent = error?.message || '保存失败，请稍后重试；你的输入仍保留。';
  }
  target.focus?.();
}

async function operation(element, area, work){
  const scope = scopeFor(element);
  const release = lock(scope);
  if (!release) return;
  feedback(scope,area,'处理中…');
  try { await work(scope); }
  catch (error) { failure(scope,area,error); }
  finally { release(); }
}

function assertProfile(profile, owner){
  if (profile?.id !== owner || !Number.isSafeInteger(profile.profile_version) || profile.profile_version < 0) {
    throw new Error('资料响应不完整，请联系维护者或重新载入');
  }
  return profile;
}

function syncVersions(root, version){
  for (const input of root.querySelectorAll('[name="profile_version"]')) input.value = String(version);
}

function applyProfile(scope, profile){
  if (!scope.visible()) return false;
  assertProfile(profile,scope.owner);
  state.me = profile;
  syncVersions(scope.root,profile.profile_version);
  const summary = scope.root.querySelector('[data-user-summary]');
  if (summary) summary.innerHTML = userProfileSummary(profile);
  const preview = scope.root.querySelector('[data-user-avatar-preview]');
  if (preview && !preview.dataset.userObjectUrl) preview.innerHTML = userAvatar(profile);
  const comparison = scope.root.querySelector('[data-user-comparison]');
  if (comparison) { comparison.hidden = true; comparison.innerHTML = ''; }
  return true;
}

function field(form,name){
  const control = form.elements.namedItem(name);
  if (!control) throw new Error('资料表单不完整，请重新打开页面');
  return control;
}

async function saveProfile({form}){
  await operation(form,'profile',async scope=>{
    const payload = {profile_version:profileVersion(field(form,'profile_version').value)};
    for (const name of ['nickname','major','bio','degree_level','study_status']) {
      payload[name] = field(form,name).value;
    }
    const result = await api('/user/profile',payload);
    if (applyProfile(scope,result)) feedback(scope,'profile','资料已保存。');
  });
}

async function compareProfile(button){
  await operation(button,'profile',async scope=>{
    const latest = await api('/user/profile');
    if (!scope.visible()) return;
    assertProfile(latest,scope.owner);
    const panel = scope.root.querySelector('[data-user-comparison]');
    panel.innerHTML = userProfileComparison(latest);
    panel.hidden = false;
    feedback(scope,'profile','服务器资料已显示在下方，你的表单输入没有改变。');
    panel.scrollIntoView?.({block:'nearest',behavior:'smooth'});
  });
}

function keepInputs(button){
  const scope = scopeFor(button);
  if (!scope.visible() || scope.root.dataset.userBusy === '1') return;
  const version = profileVersion(button.dataset.profileVersion);
  syncVersions(scope.root,version);
  feedback(scope,'profile','已采用核对后的版本，输入仍保留；请确认内容后再次点击保存。');
}

async function resetProfile(button){
  await operation(button,'profile',async scope=>{
    if (!confirm('重新载入会替换尚未保存的资料输入，是否继续？')) {
      feedback(scope,'profile','已保留当前输入。');
      return;
    }
    const latest = await api('/user/profile');
    if (!scope.visible()) return;
    assertProfile(latest,scope.owner);
    const form = scope.root.querySelector('#user-profile-form');
    const values = userProfileValues(latest);
    for (const name of ['nickname','major','bio']) field(form,name).value = latest[name] ?? '';
    for (const name of ['degree_level','study_status']) field(form,name).value = values[name];
    applyProfile(scope,latest);
    feedback(scope,'profile','已载入服务器资料。');
  });
}

function avatarForm(root){
  const form = root.querySelector('#user-avatar-form');
  if (!form) throw new Error('头像表单不完整，请重新打开页面');
  return form;
}

function selectedFile(form){
  const file = field(form,'avatarfile').files?.[0];
  if (!file || !file.size) throw new Error('请先选择一张头像图片');
  if (file.size > MAX_AVATAR_BYTES) throw new Error('头像原文件不能超过2 MiB');
  if (file.type && !['image/jpeg','image/png','image/webp'].includes(file.type)) {
    throw new Error('头像仅支持JPEG、PNG或WebP图片');
  }
  return file;
}

function releasePreview(preview){
  const previous = preview?.dataset.userObjectUrl;
  if (previous && state.mediaURLs.has(previous)) {
    URL.revokeObjectURL(previous);
    state.mediaURLs.delete(previous);
  }
  if (preview) delete preview.dataset.userObjectUrl;
}

function putPreview(scope, blob){
  if (!scope.visible()) return;
  const preview = scope.root.querySelector('[data-user-avatar-preview]');
  releasePreview(preview);
  const url = URL.createObjectURL(blob);
  state.mediaURLs.add(url);
  preview.dataset.userObjectUrl = url;
  // This blob URL is created here, never taken from user JSON or HTML.
  preview.innerHTML = `<span class="user-avatar user-avatar-large" role="img" aria-label="待确认的头像预览"><span class="user-avatar-fallback" aria-hidden="true">预览</span><img data-user-avatar-image src="${e(url)}" alt="待确认的头像预览"></span>`;
}

function clearSelection(scope){
  const form = avatarForm(scope.root);
  field(form,'upload_id').value = '';
  field(form,'avatarfile').value = '';
  showFileName(scope.root,'');
  const preview = scope.root.querySelector('[data-user-avatar-preview]');
  releasePreview(preview);
  preview.innerHTML = userAvatar(state.me);
  scope.root.querySelector('[data-action="user-avatar-confirm"]').hidden = true;
}

// 文件名回显：自定义按钮替代了原生 input 的「未选择任何文件」文案，
// 选了没选、选的是哪张，用户得能一眼看到，否则会重复点「选择图片」。
function showFileName(root, name){
  const target = root.querySelector('[data-user-file-name]');
  if (!target) return;
  const picked = typeof name === 'string' && name.trim();
  target.textContent = picked ? name : '未选择任何文件';
  target.classList.toggle('is-picked', Boolean(picked));
}

function localPreview(button){
  const scope = scopeFor(button);
  if (!scope.visible() || scope.root.dataset.userBusy === '1') return;
  try {
    const form = avatarForm(scope.root);
    // A preview of a newly selected file invalidates the previous upload's
    // confirm button, even if that older resource remains privately stored.
    field(form,'upload_id').value = '';
    scope.root.querySelector('[data-action="user-avatar-confirm"]').hidden = true;
    const file = selectedFile(form);
    showFileName(scope.root,file.name);
    putPreview(scope,file);
    feedback(scope,'avatar','这是本地预览，尚未上传。点击“上传并预览”后再确认公开。');
  } catch (error) { failure(scope,'avatar',error); }
}

function fileContent(file){
  return new Promise((resolve,reject)=>{
    const reader = new FileReader();
    reader.onload = ()=>{
      const content = String(reader.result).split(',')[1];
      if (content) resolve(content); else reject(new Error('图片读取失败，请重新选择'));
    };
    reader.onerror = ()=>reject(new Error('图片读取失败，请重新选择'));
    reader.readAsDataURL(file);
  });
}

export function avatarFileChange(event){
  const input = event.target;
  // 两个 id 都认：改版把输入框 id 改成了 uc-avatar-file，旧标记（user-avatar-file）
  // 仍可能在未刷新的页面里存在。这里不做严格单 id 匹配，否则「选了文件没反应」。
  if (!input?.matches?.('#uc-avatar-file, #user-avatar-file')) return;
  const root = input.closest('[data-user-center]');
  if (!root?.isConnected || root.dataset.userOwner !== String(state.me?.id) || !state.token) return;
  localPreview(input);
}

async function privatePreview(scope, result){
  if (!AVATAR_ID.test(result?.upload_id || '') || result.preview_url !== '/media/'+result.upload_id) {
    throw new Error('头像上传响应不完整，请重新上传');
  }
  if (!scope.visible()) return null;
  // Only binary media uses fetch; all JSON operations reuse core/http.js.
  const response = await fetch(result.preview_url,{headers:{Authorization:'Bearer '+scope.token},
    credentials:'same-origin',redirect:'error',cache:'no-store'});
  if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/webp')) {
    throw new Error('头像已上传，但预览读取失败，请重新选择后再试');
  }
  const blob = await response.blob();
  if (!blob.size || blob.size > MAX_AVATAR_BYTES) throw new Error('头像预览无效，请重新上传');
  return scope.visible() ? blob : null;
}

async function uploadAvatar({form}){
  await operation(form,'avatar',async scope=>{
    const file = selectedFile(form);
    field(form,'upload_id').value = '';
    scope.root.querySelector('[data-action="user-avatar-confirm"]').hidden = true;
    const content = await fileContent(file);
    if (!scope.visible()) return;
    const result = await api('/user/avatar/upload',{content});
    const blob = await privatePreview(scope,result);
    if (!blob || !scope.visible()) return;
    field(form,'upload_id').value = result.upload_id;
    putPreview(scope,blob);
    scope.root.querySelector('[data-action="user-avatar-confirm"]').hidden = false;
    feedback(scope,'avatar','已上传，仅你可见。确认设为头像后才会公开。');
  });
}

async function selectAvatar(button, remove=false){
  await operation(button,'avatar',async scope=>{
    const form = avatarForm(scope.root);
    const uploadId = remove ? null : field(form,'upload_id').value;
    if (!remove && !AVATAR_ID.test(uploadId)) throw new Error('请先上传并预览头像');
    if (remove && !confirm('移除当前头像后将显示默认头像，是否继续？')) {
      feedback(scope,'avatar','已保留当前头像。');
      return;
    }
    const result = await api('/user/avatar',{
      upload_id:uploadId,profile_version:profileVersion(field(form,'profile_version').value)
    });
    if (!applyProfile(scope,result)) return;
    clearSelection(scope);
    feedback(scope,'avatar',remove ? '已移除当前头像，恢复默认显示。' : '头像已更新。');
  });
}

function cancelAvatar(button){
  const scope = scopeFor(button);
  if (!scope.visible() || scope.root.dataset.userBusy === '1') return;
  clearSelection(scope);
  feedback(scope,'avatar','已取消本次选择，当前公开头像没有改变。');
}

export function avatarImageError(event){
  const image = event.target;
  if (!image?.matches?.('[data-user-avatar-image]')) return;
  image.hidden = true;
  const wrapper = image.closest('[data-user-avatar]');
  if (wrapper) wrapper.setAttribute('aria-label',wrapper.dataset.userAvatarLabel || '默认头像');
}

// 左侧设置导航：只跳本页分区，不再重复「我的」页已有的帖子/收藏入口。
function scrollToSection(button){
  const target = document.getElementById(button.dataset.target || '');
  if (!target) return;
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  button.closest('.uc-nav-group')?.querySelectorAll('.uc-nav-link')
    .forEach(x => x.classList.toggle('is-active', x === button));
}

// 账号与安全：密码与注销收在一个入口，避免和「我的」页各放一个重复按钮。
function securityModal(){
  modal(`<h2>账号与安全</h2>
    <p class="muted">密码与注销都在这里处理；操作立即生效，请确认后再点。</p>
    <div class="uc-security-list">
      <button type="button" class="uc-security-item" data-action="change-password">
        <span class="uc-security-icon">${icon('shield')}</span>
        <span class="uc-security-main"><b>修改密码</b><small>修改后所有设备退出登录，并生成新的恢复码</small></span>
        ${icon('arrow')}
      </button>
      <button type="button" class="uc-security-item is-danger" data-action="deactivate">
        <span class="uc-security-icon">${icon('trash')}</span>
        <span class="uc-security-main"><b>注销账号</b><small>账号立即下线、在售商品下架；历史订单与工单保留</small></span>
        ${icon('arrow')}
      </button>
    </div>`);
}

export const clicks = {
  'uc-scroll':scrollToSection,
  'uc-security':securityModal,
  'user-profile-compare':compareProfile,
  'user-profile-keep-input':keepInputs,
  'user-profile-reset':resetProfile,
  'user-avatar-preview':localPreview,
  'user-avatar-confirm':button=>selectAvatar(button),
  'user-avatar-remove':button=>selectAvatar(button,true),
  'user-avatar-cancel':cancelAvatar
};

export const submits = {'user-profile-form':saveProfile,'user-avatar-form':uploadAvatar};
