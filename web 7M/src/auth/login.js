'use strict';
// 账号层 · 登录入口、试用版密码登录、恢复码、退出
// 公开演示版没有账号体系，所有写操作都被这里拦成一段说明而不是表单。

import { e, toast } from '../core/dom.js';
import { state, clearPoll } from '../core/state.js';
import { render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { field } from '../components/forms.js';

export function publicDemoNotice(){
  modal(`<span class="eyebrow">HUALI CORNER PREVIEW</span><h2>先逛逛，看看转角</h2><p>这是公开演示版，不收集手机号、收货地址、照片或聊天内容，也不进行真实交易。</p><p class="muted">可以体验搜索、分类、商品详情、卖家主页和社区样例。其余功能可在本地模拟版体验。</p><button class="btn primary full" data-action="close">继续逛逛</button>`);
}

export function needLogin(){
  if (state.me) return true;
  loginModal();
  return false;
}

export function clearAccount(){
  state.token = ''; state.me = null; state.cart = [];
  clearPoll();
  sessionStorage.removeItem('hc-token');
}

export async function setLogin(r){
  state.token = r.token;
  state.me = r.user;
  sessionStorage.setItem('hc-token', state.token);
  state.cart = JSON.parse(sessionStorage.getItem('hc-cart-'+state.me.id) || '[]');
  closeModal();
  toast('欢迎，'+state.me.nickname+(state.config.trial?' · 订单和付款均为模拟':' · 当前为模拟登录'));
  await render();
}

export function recoveryNotice(code){
  modal(`<span class="eyebrow">KEEP THIS PRIVATE</span><h2>保存你的账号恢复码</h2><p>请复制到自己的密码管理器或私密笔记。不要发到群聊，不要提供给其他人。恢复码可重置密码，仅在本次展示。</p><p><code id="recovery-code" style="overflow-wrap:anywhere;user-select:all">${e(code)}</code></p><p class="muted">修改或找回密码后，旧恢复码和所有已登录会话均会失效。之后请使用新密码重新登录。</p><button class="btn secondary full" data-action="copy-recovery">复制恢复码</button><button class="btn primary full" data-action="close">已保存，继续使用</button>`);
}

function passwordField(name, label, autocomplete){
  // 只有「设置新密码」才加长度下限；登录框不加 ——
  // 否则一旦调整下限，老账号会被自己当年设的旧密码挡在门外。
  const floor = autocomplete === 'new-password' ? ' minlength="6"' : '';
  return `<label class="field"><span>${label}</span><input type="password" name="${name}" required${floor} maxlength="128" autocomplete="${autocomplete}"></label>`;
}

// 试用版：手机号 + 密码，不发短信，手机号也不做实名/学籍认证。
export function trialLoginModal(mode='login'){
  const phone = field('手机号（未验证）','phone','tel','','required pattern="1[3-9][0-9]{9}" autocomplete="username" placeholder="仅作账号使用"');
  const title = mode === 'register' ? '加入华立转角' : mode === 'recover' ? '用恢复码找回账号' : '欢迎回到华立转角';
  modal(`<span class="eyebrow">计算机工程学院 · 小范围试用</span><h2>${title}</h2><p class="muted">手机号未验证，不发送短信，不作为实名、学籍或号码归属认证。交易和付款均为模拟。</p><div class="stack"><button class="btn secondary" data-action="trial-auth-mode" data-value="login">账号登录</button><button class="btn secondary" data-action="trial-auth-mode" data-value="register">注册账号</button></div><form id="${mode==='register'?'register-form':mode==='recover'?'recover-form':'login-form'}">${phone}${mode==='register'?field('昵称','nickname','text','','required maxlength="24" autocomplete="nickname"'):''}${mode==='recover'?field('账号恢复码','recovery_code','password','','required maxlength="128" autocomplete="off"'):''}${mode==='recover'?passwordField('new_password','新密码（6至128个字符）','new-password'):passwordField('password','密码（6至128个字符）',mode==='register'?'new-password':'current-password')}${mode!=='login'?passwordField('password_confirm','再输入一次密码','new-password'):''}${mode==='register'?'<label class="field"><span><input type="checkbox" name="agree" required> 我了解本版为模拟交易，同意保存账号、发布内容和必要订单记录；不填写身份证、宿舍房号或支付信息。</span></label>':''}<button class="btn primary full">${mode==='register'?'注册并登录':mode==='recover'?'重置密码':'登录'}</button></form><button class="text-button" data-action="trial-auth-mode" data-value="recover">使用恢复码找回</button><p class="muted">使用未在其他网站使用过的密码。恢复码只展示一次，请私下保存；无法仅凭手机号找回账号。管理员与客服账号由平台运营者单独建立，登录页不提供任何共享默认口令。</p>`);
}

export function loginModal(){
  if (window.HUALI_STATIC_DEMO){ publicDemoNotice(); return; }
  if (state.config.auth_mode === 'password'){ trialLoginModal(); return; }
  modal(`<span class="eyebrow">WELCOME TO YOUR CORNER</span><h2>在转角，遇见好物</h2><p class="muted">手机号即可注册，毕业生也欢迎。当前是本地模拟验证码，不发送短信。</p><form id="login-form">${field('手机号','phone','tel','','required pattern="1[3-9][0-9]{9}" placeholder="请输入11位手机号"')}<div class="code-field">${field('验证码','code','text','','required maxlength="6"')}<button class="btn secondary" type="button" data-action="code">获取测试验证码</button></div><p id="code-hint" class="muted"></p><button class="btn primary full">登录 / 注册</button></form><div class="demo-logins"><small>快速体验（测试账号）</small><div><button class="btn secondary" data-action="demo-login" data-value="13800000001">卖家体验</button><button class="btn secondary" data-action="demo-login" data-value="13800000002">买家体验</button><button class="btn secondary" data-action="demo-login" data-value="19065322759">管理员登录</button></div></div>`);
}

export function changePasswordModal(){
  modal(`<h2>修改密码</h2><form id="change-password-form">${field('原密码','old_password','password','','required maxlength="128" autocomplete="current-password"')}${field('新密码','new_password','password','','required minlength="6" maxlength="128" autocomplete="new-password"')}${field('再输入一次新密码','password_confirm','password','','required minlength="6" maxlength="128" autocomplete="new-password"')}<p class="muted">修改后所有设备退出登录，并生成新的恢复码。</p><button class="btn primary">确认修改密码</button></form>`);
}
