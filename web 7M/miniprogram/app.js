App({
  globalData: {baseURL:'http://127.0.0.1:8080', user:null, sessionVersion:0, notificationCount:0},
  onLaunch() { this.globalData.user = wx.getStorageSync('hc-user') || null; },
  onShow() { this.startNotifications(); },
  onHide() { this.stopNotifications(); },
  request(path, data) {
    const version = this.globalData.sessionVersion;
    return new Promise((resolve, reject) => wx.request({
      url:this.globalData.baseURL + '/api' + path, method:data === undefined ? 'GET' : 'POST',
      header:{'Content-Type':'application/json', Authorization:'Bearer ' + (wx.getStorageSync('hc-token') || '')}, data,
      success: response => {
        if (version !== this.globalData.sessionVersion) { reject(new Error('账号已切换，请重新打开页面')); return; }
        if (response.statusCode >= 200 && response.statusCode < 300) resolve(response.data);
        else reject(new Error(response.data.error || '请求失败'));
      },
      fail: () => reject(new Error('无法连接后端，请检查地址和开发者工具设置')),
    }));
  },
  watchNotifications(listener) {
    if (!this._noticeListeners) this._noticeListeners = new Set();
    this._noticeListeners.add(listener);
    listener(this.globalData.notificationCount || 0);
    return () => this._noticeListeners.delete(listener);
  },
  _noticeCount(value) {
    this.globalData.notificationCount = value;
    for (const listener of this._noticeListeners || []) listener(value);
  },
  startNotifications() {
    const user = this.globalData.user;
    if (!user) { this.stopNotifications(); return; }
    const epoch = this.globalData.sessionVersion;
    if (this._notices?.userId === user.id && this._notices.epoch === epoch) return;
    this.stopNotifications();
    const state = {userId:user.id, epoch, busy:false};
    this._notices = state;
    const refresh = async () => {
      if (state.busy || this._notices !== state) return;
      state.busy = true;
      try {
        const result = await this.request('/notifications');
        if (this._notices === state && this.globalData.user?.id === state.userId && this.globalData.sessionVersion === state.epoch) {
          this._noticeCount(result.unread_count);
        }
      } catch { /* Offline alerts remain on the server; foreground retries continue. */ }
      finally { state.busy = false; }
    };
    state.refresh = refresh;
    state.timer = setInterval(refresh, 5000);
    refresh();
  },
  refreshNotifications() { return this._notices?.refresh(); },
  stopNotifications() {
    if (this._notices) clearInterval(this._notices.timer);
    this._notices = null;
    this._noticeCount(0);
  },
  async demoLogin(phone) {
    const code = await this.request('/auth/code', {phone});
    const result = await this.request('/auth/login', {phone, code:code.demo_code});
    this.globalData.sessionVersion++;
    wx.setStorageSync('hc-token', result.token);
    wx.setStorageSync('hc-user', result.user);
    this.globalData.user = result.user;
    this.startNotifications();
    return result;
  },
  absolute(url) { return this.globalData.baseURL + url; },
});
