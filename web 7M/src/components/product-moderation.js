// Managers use the staff action; owners use their existing voluntary delist action.
export function moderationButton(product, user) {
  if (!user || product.status !== 'available') return '';
  const own = product.seller_id === user.id;
  const management = user.role === 'admin' || (user.role === 'support' && !own);
  if (!management && !own) return '';
  const action = management ? 'moderate-product' : 'delist';
  return `<button class="btn product-delist" data-action="${action}" data-id="${Number(product.id)}">下架商品</button>`;
}
