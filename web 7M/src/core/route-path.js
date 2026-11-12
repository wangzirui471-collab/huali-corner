/** 兼容既有 #home 与 Vue Router 的 #/home，保留查询串原有编码。 */
export function routePath(hash = location.hash) {
  return String(hash || '').replace(/^#\/?/, '').replace(/^\//, '') || 'home';
}
