'use strict';
// 事件层 · 登录、注册、恢复码、改密码、退出、个人资料
//
// 派生路径（按 `state.config.auth_mode` 决定）
// -----------------------------------------
//   'demo'        — 公开演示版，无登录态；本文件不参与。
//   'password'    — 旧路径：把 password 直接 POST 给服务端，服务端
//                   用 CPython 的 hashlib.pbkdf2_hmac 派生。
//                   仅本地 8081（server.py）使用。
//   'client_kdf'  — 浏览器先用 SubtleCrypto 算出 600k 轮 PBKDF2
//                   digest，再把 {phone, salt, rounds, digest} 提交；
//                   让 Workers 免费计划 10ms CPU 也能扛。
//                   何时走这条：state.config.auth_mode === 'client_kdf'。
// 详见 `core/pbkdf2.js` 顶部注释。

import { $, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { loginModal, trialLoginModal, changePasswordModal, recoveryNotice, setLogin, clearAccount } from '../auth/login.js';
import { pbkdf2Hex, randomSaltHex } from '../core/pbkdf2.js';

async function digestWith(password, saltHex, rounds){
  // 把派生失败（浏览器不支持 / 轮数超限等）翻译成中文，避免堆栈吓到试用用户。
  try {
    return await pbkdf2Hex(password, saltHex, rounds);
  } catch (err) {
    throw new Error('口令派生失败：' + (err && err.message ? err.message : '请刷新页面或换浏览器重试'));
  }
}

export const clicks = {
  login: () => loginModal(),
  'trial-auth-mode': b => trialLoginModal(b.dataset.value),
  'change-password': () => changePasswordModal(),

  // 本地模拟验证码：直接回填到输入框，不发送短信。
  // 仅 'password' 模式用得到；'client_kdf' 模式没有验证码流程。
  code: async () => {
    const phone = $('[name=phone]').value, c = await api('/auth/code', {phone});
    $('[name=code]').value = c.demo_code;
    $('#code-hint').textContent = '本地测试验证码：'+c.demo_code+'（不会发短信）';
  },

  'demo-login': async b => {
    b.disabled = true;
    const phone = b.dataset.value, c = await api('/auth/code', {phone});
    await setLogin(await api('/auth/login', {phone, code:c.demo_code}));
  },

  // 管理员/客服账号由运营者单独建立（manage_trial.py 或 HUALI_ADMIN_* 环境变量），
  // 登录页不再提供固定号码 + 固定口令的一键入口——仓库是公开的，
  // 那等于对外发布一个可用的管理员密码。

  logout: async () => {
    try { await api('/auth/logout', {}); }
    finally { clearAccount(); go('home'); }
  },

  deactivate: async () => {
    if (!confirm('注销后账号立即下线、在售商品全部下架、无法再登录；订单、工单与信誉记录会保留以便追溯。有未完成订单或未结案工单时无法注销。确认注销账号？')) return;
    await api('/auth/deactivate', {});
    clearAccount();
    toast('账号已注销');
    go('home');
  },

  'copy-recovery': async () => {
    await navigator.clipboard.writeText($('#recovery-code').textContent);
    toast('已复制，请私下保存');
  }
};

function roundsFromConfig(){
  // 新凭据固定使用平台规范；旧凭据登录仍使用服务端返回的历史轮数。
  return 600000;
}

export const submits = {
  'login-form': async ({ d }) => {
    if (state.config.auth_mode === 'client_kdf'){
      const { salt, rounds } = await api('/auth/salt?phone=' + encodeURIComponent(d.phone));
      const digest = await digestWith(d.password, salt, rounds);
      await setLogin(await api('/auth/login', { phone: d.phone, digest }));
      return;
    }
    await setLogin(await api('/auth/login', d));
  },

  'register-form': async ({ d, fd }) => {
    if (!fd.has('agree')) throw new Error('请先阅读并确认试用说明');
    if (d.password !== d.password_confirm) throw new Error('两次输入的密码不一致');
    if (state.config.auth_mode === 'client_kdf'){
      const salt = randomSaltHex();
      const rounds = roundsFromConfig();
      const digest = await digestWith(d.password, salt, rounds);
      const r = await api('/auth/register', { phone: d.phone, nickname: d.nickname, college: d.college, grade: d.grade, major: d.major || '', salt, rounds, digest });
      await setLogin(r);
      recoveryNotice(r.recovery_code);
      return;
    }
    const r = await api('/auth/register', { phone: d.phone, password: d.password, nickname: d.nickname, college: d.college, grade: d.grade, major: d.major || '' });
    await setLogin(r);
    recoveryNotice(r.recovery_code);
  },

  // 找回密码与主动改密码共用一段：都是「改完就全部下线，并发一张新恢复码」。
  'recover-form': ({ form, d }) => resetPassword('recover-form', form, d),
  'change-password-form': ({ form, d }) => resetPassword('change-password-form', form, d),

  'profile-form': async ({ d }) => {
    state.me = await api('/me', d);
    toast('资料已保存');
    await render();
  }
};

async function resetPassword(formId, form, d){
  if (d.new_password !== d.password_confirm) throw new Error('两次输入的密码不一致');
  if (state.config.auth_mode === 'client_kdf'){
    const salt = randomSaltHex();
    const rounds = roundsFromConfig();
    const new_digest = await digestWith(d.new_password, salt, rounds);
    let body;
    if (formId === 'recover-form'){
      body = { phone: d.phone, salt, rounds, digest: new_digest, recovery_code: d.recovery_code };
    } else {
      const current = await api('/auth/salt');
      const old_digest = await digestWith(d.old_password, current.salt, current.rounds);
      body = { salt, rounds, digest: new_digest, old_digest };
    }
    const r = await api(formId === 'recover-form' ? '/auth/recover' : '/auth/password', body);
    clearAccount();
    go('home');
    await render();
    recoveryNotice(r.recovery_code);
    return;
  }
  const r = await api(formId === 'recover-form' ? '/auth/recover' : '/auth/password', {
    phone: d.phone,
    recovery_code: d.recovery_code,
    old_password: d.old_password,
    new_password: d.new_password
  });
  clearAccount();
  go('home');
  await render();
  recoveryNotice(r.recovery_code);
}
