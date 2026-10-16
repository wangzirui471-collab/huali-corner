/* Account-owned drafts. The server is authoritative for publication and prices. */
(() => {
  'use strict';
  let active = null;
  const unknown = '未核对，交付时检查';
  const cacheKey = userId => `zj-draft-${userId}`;
  const defaults = {
    title: '', category: 'books', price: '', delivery: 'pickup', delivery_fee: '0',
    description: '', edition: '版本待确认', publisher: '', notes: unknown,
    missing: unknown, accessories: unknown, condition: '成色待核对，见实拍',
    bought: '', author: '', isbn: '', original_price: '', point: '楼下公共入口',
  };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const uid = () => crypto.randomUUID();
  const input = (label, name, value = '', attributes = '') => `<label class="field"><span>${label}</span><input name="${name}" value="${escape(value)}" ${attributes}></label>`;
  const select = (label, name, options, value) => `<label class="field"><span>${label}</span><select name="${name}">${options.map(option => {
    const [key, text] = Array.isArray(option) ? option : [option, option];
    return `<option value="${escape(key)}" ${key === value ? 'selected' : ''}>${escape(text)}</option>`;
  }).join('')}</select></label>`;

  function fields(state) {
    const result = { ...state.fields };
    if (state.form) {
      for (const [name, value] of new FormData(state.form)) {
        if (typeof value === 'string') result[name] = value;
      }
    }
    result.photos = state.photos.map(photo => photo.id);
    return result;
  }

  function status(state, message, conflict = false) {
    if (state.form) {
      state.form.querySelector('[data-testid=draft-status]').textContent = message + (state.failed?.size ? '；有照片未上传完成，请重新选择：' + [...state.failed].map(angle => ({front:'正面',side:'侧面',top:'顶部',extra:'补图'}[angle] || angle)).join('、') : '');
      state.form.querySelector('.draft-conflict').hidden = !conflict;
    }
  }

  function cache(state) {
    if (!state.touched || !state.deps.isCurrent() || (active && active !== state)) return;
    try {
      localStorage.setItem(cacheKey(state.deps.user.id), JSON.stringify({
        id: state.id, version: state.version, fields: fields(state),
        photos: state.photos.map(photo => ({ id: photo.id, angle: photo.angle, url: photo.url })),
        copy_from_id: state.copyFrom || null,
        failed_angles: [...state.failed],
        updated_at: Date.now(), dirty: state.lastSaved !== JSON.stringify(fields(state)),
      }));
      state.localOK = true;
    } catch {
      state.localOK = false;
      status(state, '本机存储不可用，正在尝试保存到服务器');
    }
  }

  function save(state) {
    clearTimeout(state.timer);
    state.queue = state.queue.catch(() => {}).then(async () => {
      if (!state.deps.isCurrent()) return;
      if (!state.touched && !state.version) return;
      if (state.conflict) throw new Error('草稿版本冲突，请读取新版或另存一份');
      const snapshot = fields(state);
      const serialized = JSON.stringify(snapshot);
      if (serialized === state.lastSaved && state.version) return;
      status(state, state.uploads.size ? '图片上传中，文字保存中…' : '保存中…');
      try {
        const result = await state.deps.request('/draft', {
          id: state.id, version: state.version, fields: snapshot,
          ...(state.copyFrom && !state.version ? { copy_from_id: state.copyFrom } : {}),
        });
        if (!state.deps.isCurrent()) return;
        state.version = result.version;
        state.copyFrom = null;
        state.lastSaved = serialized;
        cache(state);
        status(state, state.uploads.size ? '图片上传中，请勿关闭页面' : `已保存于 ${new Date().toLocaleTimeString()}${state.localOK ? '' : '（本机缓存不可用）'}`);
      } catch (error) {
        state.conflict = error.message.includes('另一窗口') || error.message.includes('版本');
        status(state, state.conflict ? '版本冲突：未覆盖服务器新版' : '同步失败；本机保存状态见提示，联网后请重试', state.conflict);
        throw error;
      }
    });
    return state.queue;
  }

  function changed(state) {
    if (!state.deps.isCurrent()) return;
    state.touched = true;
    state.fields = fields(state);
    cache(state);
    if (!state.conflict) status(state, state.localOK ? '已在本机保存，等待同步…' : '本机未能保存，等待服务器同步…');
    clearTimeout(state.timer);
    state.timer = setTimeout(() => { save(state).catch(() => {}); }, 2000);
    const isBook = state.fields.category === 'books';
    state.form.querySelector('.book-fields').hidden = !isBook;
    state.form.querySelector('.delivery-fee').hidden = state.fields.delivery === 'pickup';
    if (state.fields.missing?.includes('有缺页') || state.fields.accessories?.includes('附件缺失')) {
      state.form.querySelector('details').open = true;
      state.form.querySelector('[name=description]').placeholder = '请说明缺页位置或缺失附件';
    }
  }

  async function preview(state, photo) {
    if (photo.preview) return photo.preview;
    const response = await fetch(photo.url, { headers: { Authorization: 'Bearer ' + state.deps.session } });
    if (!response.ok) throw new Error('已保存照片暂时无法读取，请重试');
    const url = URL.createObjectURL(await response.blob());
    state.urls.add(url);
    photo.preview = url;
    return url;
  }

  function drawPhotos(state) {
    for (const angle of ['front', 'side', 'top']) {
      const slot = state.form.querySelector(`[data-preview=${angle}]`);
      const photo = state.photos.find(item => item.angle === angle);
      slot.replaceChildren();
      if (photo) {
        preview(state, photo).then(url => {
          if (!slot.isConnected || !state.deps.isCurrent()) return;
          const image = document.createElement('img');
          image.alt = { front: '正面实拍', side: '侧面实拍', top: '顶部实拍' }[angle];
          image.src = url;
          slot.replaceChildren(image);
        }).catch(error => status(state, error.message));
      }
    }
    state.form.querySelector('.photo-count').textContent = `已保存 ${state.photos.length} 张图片 · 至少正面、侧面、顶部各一张`;
  }

  async function upload(state, file, angle) {
    if (file.size > 5 * 1024 * 1024) throw new Error('单张图片不能超过5MB，请重新选择');
    const generation = (state.generations[angle] || 0) + 1;
    state.generations[angle] = generation;
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('图片读取失败，请重新选择'));
      reader.readAsDataURL(file);
    });
    if (!state.deps.isCurrent()) return;
    const photo = await state.deps.request('/upload', { content, angle });
    if (!state.deps.isCurrent() || state.generations[angle] !== generation) return;
    if (angle !== 'extra') state.photos = state.photos.filter(item => item.angle !== angle);
    state.photos.push(photo);
    state.failed.delete(angle);
    drawPhotos(state);
    cache(state);
  }

  async function render(deps, draftId) {
    let cached = null;
    try { cached = JSON.parse(localStorage.getItem(cacheKey(deps.user.id)) || 'null'); } catch {}
    let draft = null;
    let restoredLocal = false;
    let reopenedConflict = false;
    const requested = draftId && draftId !== 'new' ? draftId : (!draftId ? cached?.id : null);
    if (requested) {
      try { draft = await deps.request('/draft?id=' + encodeURIComponent(requested)); }
      catch (error) {
        if (draftId && draftId !== 'new') throw error;
        if (cached?.version === 0) {
          draft = { id: cached.id, version: 0, fields: cached.fields, photos: cached.photos || [] };
          restoredLocal = true;
        }
      }
    }
    if (draft && cached?.id === draft.id && cached.dirty) {
      reopenedConflict = cached.version !== draft.version;
      if (reopenedConflict) draft.version = cached.version;
      draft.fields = cached.fields;
      draft.photos = cached.photos || draft.photos;
      restoredLocal = true;
    }
    const state = {
      deps, id: draft?.id || uid(), version: draft?.version || 0,
      fields: { ...defaults, ...(draft?.fields || {}) }, photos: draft?.photos || [],
      source: draft?.source_product_id, queue: Promise.resolve(), uploads: new Set(), urls: new Set(),
      copyFrom: cached?.id === draft?.id && !draft?.version ? cached?.copy_from_id : null,
      failed: new Set(cached?.id === draft?.id ? cached?.failed_angles || [] : []), generations: {}, localOK: true, conflict: reopenedConflict, timer: null,
      touched: !!draft,
    };
    if (draft?.fields?.photos?.length && state.photos.length !== draft.fields.photos.length) {
      state.photos = draft.fields.photos.map(id => state.photos.find(item => item.id === id)).filter(Boolean);
    }
    active = state;
    const value = state.fields;
    const buildings = deps.config.buildings || [];
    if (!value.building) value.building = buildings[0] || '';
    state.lastSaved = draft && !restoredLocal ? JSON.stringify({ ...state.fields, photos: state.photos.map(photo => photo.id) }) : '';
    deps.shell(`<div class="publish-heading"><div><p class="eyebrow">给闲置一个新去处</p><h1>简单选一选，就能发布</h1><p class="muted">未知可以直说，已知缺陷请如实填写。</p></div><div><button class="btn secondary" data-go="drafts">我的草稿</button> <button class="text-button" data-go="publish/new">新建一条</button></div></div>
      <form id="publish-form" class="simple-publish">
        <div class="draft-toolbar"><span data-testid="draft-status">${draft ? (restoredLocal ? '已恢复本机内容，等待同步' : '已恢复已保存草稿') : '填写后自动保存，草稿建议保留30天'}</span><button type="button" class="text-button" data-draft-save>立即保存</button></div>
        <div class="draft-conflict notice" hidden>未覆盖其他窗口的新版。<button type="button" data-draft-reload>读取新版</button><button type="button" data-draft-copy>另存一份</button></div>
        ${state.source ? '<div class="notice">这是退回物品的重新上架草稿。请重新检查当前缺页、笔记、附件和照片，再确认发布。</div>' : ''}
        <section class="panel"><h2><span class="step-number">1</span> 卖什么，选一下</h2><div class="form-grid">
          ${select('物品类别', 'category', [['books', '二手书'], ['living', '宿舍生活'], ['sports', '运动闲置']], value.category)}
          ${input('物品／书名 *', 'title', value.title, 'required maxlength="80" placeholder="例如：数据结构 第二版"')}
          ${select('成色', 'condition', ['成色待核对，见实拍', '近乎全新', '正常使用痕迹', '明显磨损，已说明'], value.condition)}
        </div><div class="book-fields" ${value.category === 'books' ? '' : 'hidden'}><div class="form-grid">
          ${select('版次', 'edition', ['版本待确认', '第一版', '第二版', '第三版', '第四版', '第五版', '第六版', '第七版', '第八版', '第九版', ...(value.edition && !['版本待确认','第一版','第二版','第三版','第四版','第五版','第六版','第七版','第八版','第九版'].includes(value.edition) ? [value.edition] : [])], value.edition)}
          ${select('笔记', 'notes', [unknown, '无笔记', '少量笔记', '大量笔记', ...(value.notes && ![unknown,'无笔记','少量笔记','大量笔记'].includes(value.notes) ? [value.notes] : [])], value.notes)}
          ${select('缺页', 'missing', [unknown, '无缺页', '有缺页，见介绍'], value.missing)}
          ${select('附件', 'accessories', [unknown, '原无附件', '无附件', '附件齐全', '附件缺失，见介绍'], value.accessories)}
        </div></div></section>
        <section class="panel"><h2><span class="step-number">2</span> 实拍三张，自动上传</h2><p class="muted photo-count"></p><div class="photo-inputs">
          ${[['front', '正面', '书籍拍封面'], ['side', '侧面', '书籍拍书脊'], ['top', '顶部', '书籍拍书页顶部']].map(([angle, title, tip]) => `<label class="upload-slot"><b>${title}</b><small>${tip}</small><div class="upload-preview" data-preview="${angle}"></div><input type="file" name="${angle}" accept="image/jpeg,image/png,image/webp"></label>`).join('')}
        </div><p class="muted">上传完成后可关窗继续编辑。重复图片不能凑数，图片不代表平台鉴真。</p></section>
        <section class="panel"><h2><span class="step-number">3</span> 定价格，选交付</h2><div class="form-grid">
          ${input('售价（元）*', 'price', value.price, 'type="number" min="0" max="10000" step="0.01" required placeholder="例如12，也可以免费送"')}
          ${select('交付方式', 'delivery', [['pickup', '自提'], ['delivery', '校内送货'], ['both', '自提或送货']], value.delivery)}
          <div class="delivery-fee" ${value.delivery === 'pickup' ? 'hidden' : ''}>${input('送货费（元）', 'delivery_fee', value.delivery_fee, 'type="number" min="0" max="10000" step="0.01"')}</div>
          ${window.ZJLocations.control(deps.config,'region',value.region || value.building + value.point,true,80)}
        </div><p class="muted">地点和费用会展示给买家；具体交付时间在订单中双方确认。</p></section>
        <details class="panel publish-extra"><summary>补充信息与缺陷说明（选填）</summary><label class="field"><span>补充说明／已知缺陷</span><textarea name="description" maxlength="3000" placeholder="不填时只根据已选情况生成介绍，不承诺正版或无瑕疵">${escape(value.description)}</textarea></label><div class="form-grid">
          ${input('出版社（未知可留空）', 'publisher', value.publisher)}${input('作者（可选）', 'author', value.author)}
          ${input('ISBN（可选）', 'isbn', value.isbn)}${input('购买月份（不记得可留空）', 'bought', value.bought)}
          ${input('原价（可选，元）', 'original_price', value.original_price, 'type="number" min="0" max="10000" step="0.01"')}
        </div><label class="field"><span>版权页／内页／缺陷补图（可选，全部最多9张）</span><input type="file" name="extra" multiple accept="image/jpeg,image/png,image/webp"></label></details>
        <div class="publish-submit"><span class="muted">当前信誉 ${deps.user.score}/100 · 交易与付款均为模拟</span><button type="submit" class="btn primary">确认发布</button></div>
      </form>`);
    state.form = document.getElementById('publish-form');
    drawPhotos(state);
    state.form.addEventListener('input', event => { if (event.target.type !== 'file') changed(state); });
    state.form.addEventListener('change', event => {
      if (event.target.type !== 'file') { changed(state); return; }
      state.touched = true;
      for (const file of event.target.files) {
        const angle = event.target.name;
        state.failed.add(angle);
        cache(state);
        const promise = upload(state, file, angle);
        state.uploads.add(promise);
        status(state, '图片上传中，请勿关闭页面');
        promise.catch(error => { state.failed.add(angle); cache(state); status(state, error.message + '；请重新选择该照片'); })
          .finally(() => { state.uploads.delete(promise); if (!state.failed.size) save(state).catch(() => {}); });
      }
    });
    state.form.querySelector('[data-draft-save]').onclick = () => { state.touched = true; save(state).catch(error => deps.toast(error.message)); };
    state.form.querySelector('[data-draft-reload]').onclick = async () => {
      if (!confirm('读取服务器新版会替换当前未同步内容。需要保留时请先选择另存一份。')) return;
      clearLocal(deps.user.id);
      state.conflict = true;
      active = null;
      await render(deps, state.id).catch(error => deps.toast(error.message));
    };
    state.form.querySelector('[data-draft-copy]').onclick = async () => {
      state.copyFrom = state.id; state.id = uid(); state.version = 0; state.conflict = false; state.lastSaved = '';
      await save(state).catch(error => deps.toast(error.message));
    };
    if (restoredLocal) changed(state);
    if (state.conflict) status(state, '版本冲突：已保留本机未同步修改，可读取新版或另存一份', true);
    else if (state.failed.size) status(state, '草稿已恢复');
  }

  async function submit() {
    const state = active;
    if (!state?.deps.isCurrent()) throw new Error('请重新登录后继续');
    state.touched = true;
    await Promise.allSettled([...state.uploads]);
    if (state.failed.size) throw new Error('有照片未上传完成，请重新选择后发布');
    await save(state);
    const product = await state.deps.request('/draft/publish', { id: state.id, version: state.version });
    clearLocal(state.deps.user.id);
    active = null;
    for (const url of state.urls) URL.revokeObjectURL(url);
    state.deps.toast('发布成功，草稿已关闭');
    state.deps.go('product/' + product.id);
  }

  async function drafts(deps) {
    const rows = await deps.request('/drafts');
    deps.shell(`<div class="publish-heading"><div><h1>我的草稿</h1><p class="muted">仅自己可见，未填完也可保存。建议保留30天。</p></div><button class="btn primary" data-go="publish/new">新建发布</button></div><div class="draft-list">${rows.map(draft => `<section class="panel"><h2>${escape(draft.fields.title || '未命名草稿')}</h2><p class="muted">${new Date(draft.updated_at * 1000).toLocaleString()} · ${draft.photos.length}张已上传图片${draft.source_product_id ? ' · 退货重售草稿' : ''}</p><button class="btn primary" data-go="publish/${draft.id}">继续编辑</button> <button class="btn secondary" data-delete-draft="${draft.id}">删除草稿</button></section>`).join('') || '<div class="panel">还没有草稿，填写发布页后会自动保存。</div>'}</div>`);
    document.querySelectorAll('[data-delete-draft]').forEach(button => {
      button.onclick = async () => {
        if (!confirm('确认删除这份草稿？')) return;
        try { await deps.request('/draft/delete', { id: button.dataset.deleteDraft }); }
        catch (error) { deps.toast(error.message); return; }
        try {
          const cached = JSON.parse(localStorage.getItem(cacheKey(deps.user.id)) || 'null');
          if (cached?.id === button.dataset.deleteDraft) clearLocal(deps.user.id);
        } catch {}
        await drafts(deps).catch(error => deps.toast(error.message));
      };
    });
  }

  async function suspend() {
    const state = active;
    if (!state) return;
    clearTimeout(state.timer);
    cache(state);
    if (state.form && state.deps.isCurrent() && !state.conflict) {
      await save(state).catch(() => {});
    }
    if (active === state) active = null;
    for (const url of state.urls) URL.revokeObjectURL(url);
  }

  function clearLocal(userId) {
    try { localStorage.removeItem(cacheKey(userId)); } catch {}
    if (active?.deps.user.id === userId) {
      clearTimeout(active.timer);
      active = null;
    }
  }

  window.addEventListener('pagehide', () => { if (active) cache(active); });
  window.ZJPublisher = { render, submit, drafts, suspend, clearLocal };
})();
