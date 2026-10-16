// Draft identity and immutable defaults, shared independently of HTML.
export const unknown = '未核对，交付时检查';
export const cacheKey = (userId,productId) => productId?`zj-edit-${userId}-${productId}`:`zj-draft-${userId}`;
export const defaults = {
    title: '', category: 'books', price: '', delivery: 'pickup', delivery_fee: '0',
    description: '', edition: '版本待确认', publisher: '', notes: unknown,
    missing: unknown, accessories: unknown, condition: '成色待核对，见实拍',
    bought: '', author: '', isbn: '', original_price: '', point: '楼下公共入口',
  };

export const uid = () => crypto.randomUUID();
