import { context } from '../core/context.js';
import { escape } from '../components/publish-fields.js';
export async function drafts() {
    const deps=context();
    const rows = await deps.request('/drafts');
    deps.shell(`<div class="publish-heading"><div><h1>我的草稿</h1><p class="muted">仅自己可见，未填完也可保存。建议保留30天。</p></div><button class="btn primary" data-go="publish/new">新建发布</button></div><div class="draft-list">${rows.map(draft => `<section class="panel"><h2>${escape(draft.fields.title || '未命名草稿')}</h2><p class="muted">${new Date(draft.updated_at * 1000).toLocaleString()} · ${draft.photos.length}张已上传图片${draft.source_product_id ? ' · 退货重售草稿' : ''}</p><button class="btn primary" data-go="publish/${draft.id}">继续编辑</button> <button class="btn secondary" data-action="delete-draft" data-draft-id="${draft.id}">删除草稿</button></section>`).join('') || '<div class="panel">还没有草稿，填写发布页后会自动保存。</div>'}</div>`);
}

