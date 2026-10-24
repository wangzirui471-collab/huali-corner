/** 转换已有 hash 业务书签；只保留已知查询参数，不执行外站跳转。 @param {string} hash 旧片段。 */
export function legacyDestination(hash) {
  const [fragment, search = ''] = hash.split('?');
  const match = /^#\/?([a-z-]+)(?:\/([a-z0-9_-]+))?$/i.exec(fragment);
  if (!match) return null;
  const [, name, id] = match;
  const query = new URLSearchParams(search);
  if (query.has('next') || query.has('redirect')) return null;
  const keep = new URLSearchParams();
  for (const key of [
    'q',
    'category',
    'sort',
    'free',
    'type',
    'actor',
    'since',
    'until',
    'order',
    'product',
  ])
    if (query.has(key)) keep.set(key, query.get(key) || '');
  const fixed = /** @type {Record<string,string>} */ ({
    home: '/',
    login: '/login',
    publish: '/publish',
    cart: '/cart',
    orders: '/orders',
    me: '/me',
    favorites: '/favorites',
    friends: '/friends',
    community: '/community',
    tickets: '/support',
    admin: '/workspace',
    staff: '/workspace',
    'my-products': '/my-products',
    notifications: '/messages/notice',
  });
  const detail = /** @type {Record<string,string>} */ ({
    product: '/products/',
    post: '/posts/',
    want: '/wants/',
    profile: '/users/',
    ticket: '/support/',
    dossier: '/workspace/users/',
  });
  const desks = /** @type {Record<string,string>} */ ({
    people: 'accounts',
    support: 'tickets',
    desk: 'overview',
    overview: 'overview',
    tickets: 'tickets',
    sessions: 'sessions',
    products: 'products',
    content: 'content',
    sellers: 'sellers',
    accounts: 'accounts',
    staff: 'staff',
    words: 'words',
    audit: 'audit',
    reconcile: 'reconcile',
    backup: 'backup',
  });
  let destination = !id ? fixed[name] || null : null;
  if (detail[name] && /^\d+$/.test(id || '')) destination = detail[name] + id;
  if (name === 'messages' && (!id || /^\d+$/.test(id)))
    destination = '/messages' + (id ? '/' + id : '');
  if (name === 'forum') destination = '/forum' + (id ? '/' + id : '');
  if (['admin', 'staff'].includes(name) && id && desks[id]) destination = '/workspace/' + desks[id];
  if (name === 'me' && id)
    destination =
      {
        favorites: '/favorites',
        products: '/my-products',
        orders: '/orders',
        profile: '/me/profile',
        security: '/me/security',
      }[/** @type {'profile'} */ (id)] || null;
  return destination ? destination + (keep.size ? '?' + keep.toString() : '') : null;
}
/** 开发联调仅允许本机后端，不允许用户信息、子路径或远程主机。 @param {string} address 服务地址。 */
export function localBackend(address) {
  const url = new URL(address);
  if (
    !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
    url.protocol !== 'http:' ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  )
    throw new Error('旧业务代理必须是无凭据的本机 HTTP 服务地址');
  return url.origin;
}
