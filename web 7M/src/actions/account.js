'use strict';
// 事件层 · 登录、注册、恢复码、改密码、退出、个人资料

import { $, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { loginModal, trialLoginModal, changePasswordModal, recoveryNotice, setLogin, clearAccount } from '../auth/login.js';

export const clicks = {
  login: () => loginModal(),
  'trial-auth-mode': b => trialLoginModal(b.dataset.value),
  'change-password': () => changePasswordModal(),

  // 本地模拟验证码：直接回填到输入框，不发送短信。
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
    await api('/auth/logout', {});
    state.token = ''; state.me = null; state.cart = [];
    sessionStorage.removeItem('hc-token');
    go('home');
  },

  deactivate: async () => {
    if (!confirm('注销后账号立即下线、在售商品全部下架、无法再登录；订单、工单与信誉记录会保留以便追溯。有未完成订单或未结案工单时无法注销。确认注销账号？')) return;
    await api('/auth/deactivate', {});
    state.token = ''; state.me = null; state.cart = [];
    sessionStorage.removeItem('hc-token');
    toast('账号已注销');
    go('home');
  },

  'copy-recovery': async () => {
    await navigator.clipboard.writeText($('#recovery-code').textContent);
    toast('已复制，请私下保存');
  }
};

export const submits = {
  'login-form': async ({ d }) => { await setLogin(await api('/auth/login', d)); },

  'register-form': async ({ d, fd }) => {
    if (!fd.has('agree')) throw new Error('请先阅读并确认试用说明');
    if (d.password !== d.password_confirm) throw new Error('两次输入的密码不一致');
    const r = await api('/auth/register', {phone:d.phone, password:d.password, nickname:d.nickname,
      college:d.college, major:d.major, grade:d.grade});
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
  const r = await api(formId === 'recover-form' ? '/auth/recover' : '/auth/password', {
    phone:d.phone,
    recovery_code:d.recovery_code,
    old_password:d.old_password,
    new_password:d.new_password
  });
  clearAccount();
  go('home');
  await render();
  recoveryNotice(r.recovery_code);
}
