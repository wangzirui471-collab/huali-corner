import { context } from '../core/context.js';
import { e } from '../core/dom.js';
import { state } from '../core/state.js';

export const clicks = {
  'moderate-product': (button, id) => {
    const owner = context();
    if (!owner?.user || !['admin', 'support'].includes(owner.user.role)) throw new Error('仅管理员和客服可下架商品');
    owner.modal(`<h2>下架商品</h2><p>${e(button.dataset.title)}</p><p class="muted">下架后停止展示和新下单，保留商品记录并通知卖家；不会自动扣信誉分。</p><form id="moderate-product-form" data-id="${id}" data-owner="${owner.user.id}" data-epoch="${state.renderId}"><label class="field"><span>下架原因 *</span><textarea name="reason" required maxlength="500" placeholder="例如：实拍与描述不符、重复发布或违规内容"></textarea></label><button class="btn danger" type="submit">确认下架</button><button class="btn secondary" type="button" data-action="close">取消</button></form>`);
  },
};

export const submits = {
  'moderate-product-form': async ({form, d}) => {
    const owner = context();
    if (owner.user?.id !== Number(form.dataset.owner) || state.renderId !== Number(form.dataset.epoch)) throw new Error('页面或账号已切换，请重新打开操作');
    await owner.request('/product/moderation', {id:Number(form.dataset.id), reason:d.reason});
    owner.closeModal();
    owner.toast('商品已下架，已记录原因并通知卖家');
    await owner.render();
  },
};
