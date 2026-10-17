// 全局数据层：后端地址、会话、请求封装。
// 后端地址默认取 config.js，可在「我的 → 设置后端地址」里运行时覆盖（存本地）。
const config = require('./config');

App({
  globalData: {
    baseURL: wx.getStorageSync('hc-api-base') || config.baseURL,
    user: null,
    sessionVersion: 0
  },

  onLaunch() {
    this.globalData.user = wx.getStorageSync('hc-user') || null;
  },

  // 运行时切换后端地址：体验版给同学用时直接填电脑局域网 IP，不必改代码重传。
  setBaseURL(url) {
    const next = String(url || '').trim().replace(/\/+$/, '');
    wx.setStorageSync('hc-api-base', next);
    this.globalData.baseURL = next || config.baseURL;
    this.globalData.sessionVersion++;
    return this.globalData.baseURL;
  },

  request(path, data) {
    const app = this;
    const version = this.globalData.sessionVersion;
    return new Promise((resolve, reject) => wx.request({
      url: app.globalData.baseURL + '/api' + path,
      method: data === undefined ? 'GET' : 'POST',
      header: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + (wx.getStorageSync('hc-token') || '')
      },
      data,
      success(r) {
        if (version !== app.globalData.sessionVersion) {
          reject(new Error('账号已切换，请重新打开页面'));
          return;
        }
        if (r.statusCode >= 200 && r.statusCode < 300) resolve(r.data);
        else reject(new Error(r.data.error || '请求失败'));
      },
      fail() {
        reject(new Error('连不上后端 ' + app.globalData.baseURL + '：请确认手机与电脑同一 WiFi、后端用 --host 0.0.0.0 启动、防火墙放行端口'));
      }
    }));
  },

  async demoLogin(phone) {
    const code = await this.request('/auth/code', { phone });
    const r = await this.request('/auth/login', { phone, code: code.demo_code });
    this.globalData.sessionVersion++;
    wx.setStorageSync('hc-token', r.token);
    wx.setStorageSync('hc-user', r.user);
    this.globalData.user = r.user;
    return r;
  },

  absolute(url) {
    return this.globalData.baseURL + url;
  }
});
