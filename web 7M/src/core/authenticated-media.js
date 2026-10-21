/** 旧 Bearer 客户端的图片兼容层；私密媒体不通过 URL 携带口令或令牌。 */

const MEDIA_PATH = /^\/media\/[A-Za-z0-9_-]+(?:\?ticket_id=[1-9]\d*)?$/;
const MAX_MEDIA_BYTES = 8 * 1024 * 1024;

/**
 * 安装图片失败后的认证读取：公开图照常加载，受保护图片通过同源 fetch 转 Blob。
 * getSession 提供当前 token/epoch；registerURL 将 Blob URL 纳入现有换页回收。
 * 所有依赖可注入，测试不会访问真实账号或浏览器存储。
 */
export function installAuthenticatedMedia({
  root, getSession, registerURL, fetcher = fetch, urlAPI = URL,
}) {
  const requests = new Set();
  const attempted = new WeakMap();
  let generation = 0;

  /**
   * 读取一个同源媒体图片；失败返回 false，不清登录、不泄漏令牌到其他域名。
   * 账号、渲染或图片地址变化后丢弃迟到响应，避免串号或覆盖用户新选择的照片。
   */
  async function load(image) {
    const path = image?.getAttribute?.('src');
    const session = getSession();
    if (image?.nodeName !== 'IMG' || !MEDIA_PATH.test(path || '') || !session.token) return false;
    const previous = attempted.get(image);
    if (previous?.path === path && previous.token === session.token && previous.epoch === session.epoch) return false;
    attempted.set(image, {path, ...session});
    const controller = new AbortController();
    requests.add(controller);
    const started = generation;
    /** 判断异步结果是否仍属于同一账号、页面和图片节点。 */
    const current = () => {
      const latest = getSession();
      return started === generation && latest.token === session.token
        && latest.epoch === session.epoch && image.isConnected
        && image.getAttribute('src') === path;
    };
    try {
      const response = await fetcher(path, {
        headers: {Authorization: 'Bearer ' + session.token},
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/')) return false;
      if (Number(response.headers.get('Content-Length')) > MAX_MEDIA_BYTES) return false;
      const blob = await response.blob();
      if (!current() || !blob.size || blob.size > MAX_MEDIA_BYTES) return false;
      const url = urlAPI.createObjectURL(blob);
      registerURL(url);
      image.src = url;
      image.setAttribute('data-media-state', 'ready');
      return true;
    } catch {
      if (current()) image.setAttribute('data-media-state', 'unavailable');
      return false;
    } finally {
      requests.delete(controller);
    }
  }

  /** 以捕获方式接收 img 的 error；只有受限同源路径会发带认证的重试。 */
  function onImageError(event) {
    void load(event.target);
  }

  /** 换页或换账号时取消请求，并使忽略取消信号的迟到响应失效。 */
  function cancel() {
    generation += 1;
    for (const controller of requests) controller.abort();
    requests.clear();
  }

  /** 卸载全局事件监听并释放请求；已经登记的 Blob 由现有路由统一回收。 */
  function dispose() {
    cancel();
    root.removeEventListener('error', onImageError, true);
  }

  root.addEventListener('error', onImageError, true);
  return {load, cancel, dispose};
}
