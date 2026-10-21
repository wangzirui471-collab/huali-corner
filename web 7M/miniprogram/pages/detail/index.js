/** 商品详情沿用旧接口；认证图片适配不改变交易规则。 */
const app = getApp();
const { demoCover } = require('../../utils');

Page({
  data: { p: null },

  /** 记录商品编号，进入前台时统一加载，避免重复请求。 */
  onLoad(options) { this.id = options.id; },
  /** 返回详情时重新校验权限，不恢复上一账号的图片。 */
  onShow() { this.hidden = false; return this.load(); },
  /** 隐藏时清除私密内容，并使迟到响应失效。 */
  onHide() { this.clearMedia(); },
  /** 直接退出页面时同样清理临时媒体。 */
  onUnload() { this.clearMedia(); },

  /** 只释放此页面用过且由应用登记的临时文件。 */
  clearMedia() {
    this.hidden = true;
    this.loadVersion = (this.loadVersion || 0) + 1;
    app.releaseMedia((this.data.p?.photos || []).map(photo => photo.url));
    this.setData({ p: null });
  },

  /** 加载商品与合法图片；换页、换账号或新刷新后丢弃旧结果。 */
  async load() {
    if (this.hidden) return;
    const loadVersion = this.loadVersion = (this.loadVersion || 0) + 1;
    const sessionVersion = app.globalData.sessionVersion;
    try {
      const product = await app.request('/product?id=' + this.id);
      const originals = product.simulation ? product.photos.slice(0, 1) : product.photos;
      const photos = await Promise.all(originals.map(async photo => {
        const isPhoto = !photo.url.endsWith('.svg');
        try {
          return { ...photo, isPhoto, url: await app.mediaURL(photo.url) };
        } catch {
          return { ...photo, isPhoto, url: '', unavailable: true };
        }
      }));
      if (this.hidden || loadVersion !== this.loadVersion
        || sessionVersion !== app.globalData.sessionVersion) {
        app.releaseMedia(photos.map(photo => photo.url));
        return;
      }
      app.releaseMedia((this.data.p?.photos || []).map(photo => photo.url));
      this.setData({ p: {
        ...product, photos, coverStyle: demoCover(product, app.globalData.baseURL),
        priceText: (product.price / 100).toFixed(2),
        delivered: ((product.price + product.delivery_fee) / 100).toFixed(2),
      } });
    } catch (error) {
      if (!this.hidden && loadVersion === this.loadVersion
        && sessionVersion === app.globalData.sessionVersion) {
        wx.showToast({ title: error.message, icon: 'none' });
      }
    }
  },

  /** 未登录时进入原账号页，返回值说明当前操作是否可以继续。 */
  login() {
    if (app.globalData.user) return true;
    wx.navigateTo({ url: '/pages/hub/index?tab=me' });
    return false;
  },

  /** 收藏和点赞仍使用服务端开关语义，成功后刷新详情。 */
  async react(event) {
    if (!this.login()) return;
    const kind = event.currentTarget.dataset.kind;
    try {
      await app.request('/react', { product_id: Number(this.id), kind,
        on: !(kind === 'favorite' ? this.data.p.favorited : this.data.p.liked) });
      await this.load();
    } catch (error) { wx.showToast({ title: error.message, icon: 'none' }); }
  },

  /** 清单按用户编号隔离，只保存商品编号并进入原清单页。 */
  cart() {
    if (!this.login()) return;
    const key = 'hc-cart-' + app.globalData.user.id;
    const ids = wx.getStorageSync(key) || [];
    if (!ids.includes(Number(this.id))) ids.push(Number(this.id));
    wx.setStorageSync(key, ids);
    wx.navigateTo({ url: '/pages/hub/index?tab=cart' });
  },

  /** 私聊权限仍由旧服务端校验，详情只负责进入返回的会话。 */
  async chat() {
    if (!this.login()) return;
    try {
      const room = await app.request('/rooms/private', { peer: this.data.p.seller_id });
      wx.navigateTo({ url: '/pages/hub/index?tab=messages&room=' + room.id });
    } catch (error) { wx.showToast({ title: error.message, icon: 'none' }); }
  },

  /** 打开当前卖家的既有公开主页。 */
  profile() { wx.navigateTo({ url: '/pages/hub/index?tab=profile&user=' + this.data.p.seller_id }); },

  /** 以元输入、以整数分提交报价，保留旧后端金额与交易校验。 */
  offer() {
    if (!this.login()) return;
    wx.showModal({ title: '商品出价（元）', editable: true, placeholderText: '不包含送货费',
      /** 用户确认后才提交，取消弹窗不产生写入。 */
      success: async result => {
        if (!result.confirm) return;
        try {
          await app.request('/offer', { product_id: Number(this.id),
            amount: Math.round(Number(result.content) * 100) });
          wx.showToast({ title: '已提交出价' });
        } catch (error) { wx.showToast({ title: error.message, icon: 'none' }); }
      },
    });
  },

  /** 分享原商品深链，不把令牌或临时图片路径带出页面。 */
  onShareAppMessage() {
    return { title: this.data.p?.title || '华立转角', path: '/pages/detail/index?id=' + this.id };
  },
});
