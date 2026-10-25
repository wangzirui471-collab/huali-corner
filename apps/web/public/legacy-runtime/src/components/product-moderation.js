// Managers use the staff action; owners use their existing voluntary delist action.
import { isAdmin, isStaff } from '../core/roles.js';

export function moderationButton(product, user) {
  if (!user || product.status !== 'available') return '';
  const own = product.seller_id === user.id;
  // 开发者与管理员同级：都能处置任何人的商品。客服只能处置别人的，
  // 自己的商品走卖家自己的「下架」，避免客服误用平台处置绕过正常流程。
  const management = isAdmin(user) || (isStaff(user) && !own);
  if (!management && !own) return '';
  const action = management ? 'moderate-product' : 'delist';
  return `<button class="btn product-delist" data-action="${action}" data-id="${Number(product.id)}">下架商品</button>`;
}
