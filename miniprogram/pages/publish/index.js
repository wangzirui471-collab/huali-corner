const app = getApp();
const UNKNOWN = '未核对，交付时检查';
const DEFAULTS = {
  title: '', category: 'books', price: '', delivery: 'pickup', delivery_fee: '0',
  region: '', description: '', publisher: '', author: '', isbn: '', bought: '',
  edition: '版本待确认', notes: UNKNOWN, missing: UNKNOWN, accessories: UNKNOWN,
  condition: '成色待核对，见实拍', original_price: '',
};
const newId = () => Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('');

Page({
  data: {
    fields: { ...DEFAULTS }, photos: {}, uploaded: {}, extraPhotos: [], drafts: [],
    draftId: '', version: 0, saveStatus: '填写后自动保存', conflict: false,
    busy: false, showExtra: false, showDrafts: false, sourceProductId: null,
    editions: ['版本待确认', '第一版', '第二版', '第三版', '第四版', '第五版', '第六版', '第七版', '第八版', '第九版'],
    noteOptions: [UNKNOWN, '无笔记', '少量笔记', '大量笔记'],
    missingOptions: [UNKNOWN, '无缺页', '有缺页，见介绍'],
    accessoryOptions: [UNKNOWN, '原无附件', '无附件', '附件齐全', '附件缺失，见介绍'],
    conditions: ['成色待核对，见实拍', '近乎全新', '正常使用痕迹', '明显磨损，已说明'],
    categories: ['二手书', '宿舍生活', '运动闲置'], deliveries: ['自提', '校内送货', '自提或送货'],
  },

  current(stamp = this._stamp) {
    return !this._disposed && stamp === this._stamp && app.globalData.user &&
      app.globalData.user.id === this._owner && app.globalData.sessionVersion === this._epoch;
  },

  async onLoad(options = {}) {
    clearTimeout(this._timer);
    this.options = options;
    this._disposed = false;
    this._owner = app.globalData.user?.id;
    this._epoch = app.globalData.sessionVersion;
    this._stamp = newId();
    this._queue = Promise.resolve();
    this._uploads = new Set();
    this._generations = {};
    this._failed = new Set();
    this._dirty = false;
    this._copyFrom = null;
    this._lastSaved = '';
    this.setData({ fields: { ...DEFAULTS }, photos: {}, uploaded: {}, extraPhotos: [], drafts: [],
      draftId: newId(), version: 0, conflict: false, busy: false, sourceProductId: null, saveStatus: '填写后自动保存' });
    if (!this._owner) { this.error(new Error('请先在我的页面登录')); return; }
    this._cacheKey = 'zj-native-draft-' + this._owner;
    const stamp = this._stamp;
    let cached = wx.getStorageSync(this._cacheKey);
    if (!cached || typeof cached !== 'object') cached = null;
    const wanted = options.id || (!options.fresh ? cached?.id : null);
    if (!wanted) { if (options.drafts) await this.listDrafts(); return; }
    try {
      let draft;
      try { draft = await app.request('/draft?id=' + wanted); }
      catch (error) {
        if (!cached || cached.id !== wanted || cached.version !== 0) throw error;
        draft = { id: cached.id, version: 0, fields: cached.fields, photos: cached.photos || [] };
      }
      if (!this.current(stamp)) return;
      let dirty = false;
      let conflict = false;
      if (cached?.id === draft.id && cached.dirty) {
        conflict = cached.version !== draft.version;
        if (conflict) draft.version = cached.version;
        draft.fields = cached.fields;
        draft.photos = cached.photos || draft.photos;
        dirty = true;
      }
      this._failed = new Set(cached?.id === draft.id ? cached.failed_angles || [] : []);
      const uploaded = {}, extraPhotos = [];
      for (const photo of draft.photos || []) {
        if (photo.angle === 'extra') extraPhotos.push(photo);
        else uploaded[photo.angle] = photo;
      }
      this._copyFrom = !draft.version ? cached?.copy_from_id : null;
      this.setData({ fields: { ...DEFAULTS, ...draft.fields }, uploaded, extraPhotos,
        draftId: draft.id, version: draft.version, sourceProductId: draft.source_product_id || null,
        conflict,
        saveStatus: conflict ? '版本冲突，已保留本机修改；可读取新版或另存一份' : this._failed.size ? '有照片未上传完成，请重新选择' : dirty ? '已恢复本机内容，等待同步' : '已恢复已保存草稿' });
      this._dirty = dirty;
      this._lastSaved = dirty ? '' : JSON.stringify(this.snapshot());
      this.restorePhotos(stamp);
      if (dirty && !conflict) await this.saveDraft();
      if (options.drafts) await this.listDrafts();
    } catch (error) {
      if (this.current(stamp)) this.error(error);
    }
  },

  async onShow() {
    if (this._owner && !this.current()) {
      try { wx.removeStorageSync(this._cacheKey); } catch {}
      await this.onLoad({ fresh: true });
    }
  },

  snapshot() {
    return { ...this.data.fields, photos: [...Object.values(this.data.uploaded), ...this.data.extraPhotos].map(photo => photo.id) };
  },

  cache() {
    if (!this.current() || (!this._dirty && !this.data.version)) return;
    try {
      wx.setStorageSync(this._cacheKey, { id: this.data.draftId, version: this.data.version,
        fields: this.snapshot(), photos: [...Object.values(this.data.uploaded), ...this.data.extraPhotos],
        dirty: JSON.stringify(this.snapshot()) !== this._lastSaved, copy_from_id: this._copyFrom, failed_angles: [...this._failed] });
    } catch {
      this.setData({ saveStatus: '本机未能保存，正在尝试同步服务器' });
    }
  },

  input(event) {
    if (!this.current()) return;
    const field = event.currentTarget.dataset.field;
    this.setData({ fields: { ...this.data.fields, [field]: String(event.detail.value) } });
    this.changed();
  },

  choose(event) {
    const field = event.currentTarget.dataset.field;
    let value;
    if (field === 'category') value = ['books', 'living', 'sports'][Number(event.detail.value)];
    else if (field === 'delivery') value = ['pickup', 'delivery', 'both'][Number(event.detail.value)];
    else value = this.data[event.currentTarget.dataset.list][Number(event.detail.value)];
    this.setData({ fields: { ...this.data.fields, [field]: value } });
    this.changed();
  },

  changed() {
    this._dirty = true;
    this.cache();
    if (!this.data.conflict) this.setData({ saveStatus: '本机已保存，等待同步…' });
    if (this.data.fields.missing.includes('有缺页') || this.data.fields.accessories.includes('附件缺失')) {
      this.setData({ showExtra: true });
    }
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this.saveDraft(), 2000);
  },

  persist() {
    clearTimeout(this._timer);
    const stamp = this._stamp;
    this._queue = this._queue.catch(() => {}).then(async () => {
      if (!this.current(stamp) || (!this._dirty && !this.data.version)) return;
      if (this.data.conflict) throw new Error('草稿版本冲突，请读取新版或另存一份');
      const fields = this.snapshot();
      const serialized = JSON.stringify(fields);
      if (serialized === this._lastSaved && this.data.version) return;
      this.setData({ saveStatus: '保存中…' });
      const result = await app.request('/draft', { id: this.data.draftId, version: this.data.version, fields,
        ...(this._copyFrom && !this.data.version ? { copy_from_id: this._copyFrom } : {}) });
      if (!this.current(stamp)) return;
      this._copyFrom = null;
      this._lastSaved = serialized;
      this.setData({ version: result.version, saveStatus: this._failed.size ? '有照片未上传完成，请重新选择' : this._uploads.size ? '图片上传中，请勿关闭' : '已保存到服务器' });
      this.cache();
      return result;
    });
    return this._queue;
  },

  async saveDraft() {
    try { await this.persist(); }
    catch (error) {
      if (!this.current()) return;
      const conflict = /另一窗口|版本|新版/.test(error.message);
      this.setData({ conflict, saveStatus: conflict ? '版本冲突，未覆盖服务器新版' : '同步失败，本机内容保留；请重试' });
    }
  },

  async copyDraft() {
    if (!this.current()) return;
    this._copyFrom = this.data.draftId;
    this._lastSaved = '';
    this._dirty = true;
    this.setData({ draftId: newId(), version: 0, conflict: false });
    await this.saveDraft();
  },

  async reloadDraft() {
    try { wx.removeStorageSync(this._cacheKey); } catch {}
    await this.onLoad({ id: this.data.draftId });
  },

  restorePhotos(stamp) {
    const token = wx.getStorageSync('hc-token') || '';
    for (const [angle, photo] of Object.entries(this.data.uploaded)) {
      wx.downloadFile({ url: app.globalData.baseURL + photo.url, header: { Authorization: 'Bearer ' + token },
        success: response => {
          if (!this.current(stamp)) return;
          if (response.statusCode !== 200) { this.error(new Error('已保存图片暂时无法读取，请重试')); return; }
          this.setData({ photos: { ...this.data.photos, [angle]: response.tempFilePath } });
        }, fail: () => { if (this.current(stamp)) this.error(new Error('图片加载失败，可重新打开草稿')); } });
    }
  },

  async pick(event) {
    if (!this.current()) return;
    const angle = event.currentTarget.dataset.angle;
    const stamp = this._stamp;
    const generation = (this._generations[angle] || 0) + 1;
    this._generations[angle] = generation;
    try {
      const media = await new Promise((resolve, reject) => wx.chooseMedia({ count: 1, mediaType: ['image'],
        sourceType: ['camera', 'album'], success: resolve, fail: reject }));
      if (!this.current(stamp) || generation !== this._generations[angle]) return;
      const file = media.tempFiles[0];
      this._dirty = true;
      this._failed.add(angle);
      this.cache();
      if (file.size > 5 * 1024 * 1024) throw new Error('单张图片不能超过5MB，请重新选择');
      this.setData({ photos: { ...this.data.photos, [angle]: file.tempFilePath }, saveStatus: '图片上传中，请勿关闭' });
      const content = wx.getFileSystemManager().readFileSync(file.tempFilePath, 'base64');
      const task = app.request('/upload', { content, angle });
      this._uploads.add(task);
      let photo;
      try { photo = await task; } finally { this._uploads.delete(task); }
      if (!this.current(stamp) || generation !== this._generations[angle]) return;
      this._failed.delete(angle);
      this.setData({ uploaded: { ...this.data.uploaded, [angle]: photo } });
      this.cache();
      await this.saveDraft();
    } catch (error) {
      if (this.current(stamp) && generation === this._generations[angle] && !String(error.errMsg || '').includes('cancel')) this.error(error);
    }
  },

  toggleExtra(event) { this.setData({ showExtra: event.detail.value }); },

  async listDrafts() {
    if (!this.current()) return;
    try { await this.persist(); } catch {}
    try {
      const stamp = this._stamp;
      const drafts = await app.request('/drafts');
      if (this.current(stamp)) this.setData({ drafts, showDrafts: true });
    } catch (error) { this.error(error); }
  },

  async openDraft(event) { await this.onLoad({ id: event.currentTarget.dataset.id }); },
  async newDraft() { try { await this.persist(); } catch {} await this.onLoad({ fresh: true }); },

  async submit() {
    if (!this.current()) { wx.navigateTo({ url: '/pages/hub/index?tab=me' }); return; }
    if (this.data.busy) return;
    const stamp = this._stamp;
    this.setData({ busy: true });
    try {
      await Promise.allSettled([...this._uploads]);
      if (!this.current(stamp)) return;
      if (this._failed.size) throw new Error('有照片未上传成功，请重新选择');
      this._dirty = true;
      await this.persist();
      if (!this.current(stamp)) return;
      const result = await app.request('/draft/publish', { id: this.data.draftId, version: this.data.version });
      if (!this.current(stamp)) return;
      wx.removeStorageSync(this._cacheKey);
      this._dirty = false;
      this._lastSaved = JSON.stringify(this.snapshot());
      this._disposed = true;
      wx.redirectTo({ url: '/pages/detail/index?id=' + result.id });
    } catch (error) { if (this.current(stamp)) this.error(error); }
    finally { if (this.current(stamp)) this.setData({ busy: false }); }
  },

  onHide() { clearTimeout(this._timer); this.cache(); this.saveDraft(); },
  onUnload() { this.onHide(); this._disposed = true; },
  error(error) {
    if (this._disposed) return;
    const message = error.message || error.errMsg || '操作失败，请重试';
    this.setData({ saveStatus: message });
    wx.showToast({ title: message, icon: 'none', duration: 3000 });
  },
});
