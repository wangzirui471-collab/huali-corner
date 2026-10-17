// Reuse main's registered staff action and /api/product/moderate contract.
export function moderationButton(product, user) {
  if (!user || !['admin', 'support'].includes(user.role)
      || product.status !== 'available' || product.seller_id === user.id) return '';
  return `<button class="btn product-delist" data-action="moderate-product" data-id="${Number(product.id)}">下架商品</button>`;
}
