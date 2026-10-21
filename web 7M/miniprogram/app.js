// 全局数据层：后端地址、会话、请求封装。
// 后端地址默认取 config.js，可在「我的 → 设置后端地址」里运行时覆盖（存本地）。
const config = require('./config');

App({
  globalData: {
    baseURL: wx.getStorageSync('hc-api-base') || config.baseURL,
    user: null,
    sessionVersion: 0
  },

  /** 启动时恢复用户摘要；请求仍由服务端校验令牌。 */
  onLaunch() {
    this.globalData.user = wx.getStorageSync('hc-user') || null;
  },

  /** 切换后端地址并使旧请求失效，适用于本地联调。 */
  setBaseURL(url) {
    const next = String(url || '').trim().replace(/\/+$/, '');
    wx.setStorageSync('hc-api-base', next);
    this.globalData.baseURL = next || config.baseURL;
    this.globalData.sessionVersion++;
    return this.globalData.baseURL;
  },

  /** 统一 JSON 请求；账号或后端地址变化后拒绝旧响应。 */
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
      /** 先检查请求所属会话，再交付业务结果。 */
      success(r) {
        if (version !== app.globalData.sessionVersion) {
          reject(new Error('账号已切换，请重新打开页面'));
          return;
        }
        if (r.statusCode >= 200 && r.statusCode < 300) resolve(r.data);
        else reject(new Error(r.data.error || '请求失败'));
      },
      /** 网络失败保留登录状态，并说明本地联调的排查位置。 */
      fail() {
        reject(new Error('连不上后端 ' + app.globalData.baseURL + '：请确认手机与电脑同一 WiFi、后端用 --host 0.0.0.0 启动、防火墙放行端口'));
      }
    }));
  },

  /** 仅供既有演示模式登录，正式密码登录仍使用原页面流程。 */
  async demoLogin(phone) {
    const code = await this.request('/auth/code', { phone });
    const r = await this.request('/auth/login', { phone, code: code.demo_code });
    this.globalData.sessionVersion++;
    wx.setStorageSync('hc-token', r.token);
    wx.setStorageSync('hc-user', r.user);
    this.globalData.user = r.user;
    return r;
  },

  /** 将后端相对资源路径转换成当前服务的完整地址。 */
  absolute(url) {
    return this.globalData.baseURL + url;
  },

  /** 登录媒体带 Bearer 下载为临时文件，解决 image 控件无法携带请求头的问题。 */
  mediaURL(path) {
    // 严格匹配媒体路径，不能把令牌发送到第三方或写进 URL。
    if (!/^\/media\/[A-Za-z0-9_-]+(?:\?ticket_id=[1-9]\d*)?$/.test(path || '')) {
      return Promise.resolve(this.absolute(path));
    }
    const token = wx.getStorageSync('hc-token') || '';
    if (!token) return Promise.resolve(this.absolute(path));
    const version = this.globalData.sessionVersion;
    const baseURL = this.globalData.baseURL;
    return new Promise((resolve, reject) => wx.downloadFile({
      url: baseURL + path,
      header: { Authorization: 'Bearer ' + token },
      /** 拒绝无权或失效会话的下载，迟到临时文件立即清理。 */
      success: result => {
        if (result.tempFilePath) {
          this.mediaFiles ||= new Set();
          this.mediaFiles.add(result.tempFilePath);
        }
        const current = version === this.globalData.sessionVersion
          && baseURL === this.globalData.baseURL && token === wx.getStorageSync('hc-token');
        if (result.statusCode !== 200 || !result.tempFilePath || !current) {
          this.releaseMedia([result.tempFilePath]);
          reject(new Error(current ? '图片暂时无法读取' : '账号已切换，请重新打开页面'));
          return;
        }
        resolve(result.tempFilePath);
      },
      /** 下载失败只影响图片，不清除账号或商品信息。 */
      fail: () => reject(new Error('图片下载失败，请稍后重试')),
    }));
  },

  /** 只清理本应用登记的临时媒体，不删除其他缓存或用户文件。 */
  releaseMedia(paths) {
    for (const path of paths) {
      if (!this.mediaFiles?.has(path)) continue;
      this.mediaFiles.delete(path);
      wx.getFileSystemManager().unlink({
        filePath: path,
        /** 系统已清理的临时文件无需再报错。 */
        fail() {},
      });
    }
  }
});
