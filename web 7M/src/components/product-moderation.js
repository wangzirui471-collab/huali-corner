import { e } from '../core/dom.js';

export function moderationButton(product, user) {
  return user && ['admin', 'support'].includes(user.role) && product.status === 'available'
    ? `<button class="btn danger" data-action="moderate-product" data-id="${product.id}" data-title="${e(product.title)}">下架商品</button>` : '';
}
