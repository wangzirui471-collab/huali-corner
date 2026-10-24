import { onMounted, onScopeDispose, ref, shallowRef } from 'vue';
import { ApiError } from '../http/client.js';
import { api, session } from './session.js';

/** 绑定页面身份和生命周期，阻止离开后恢复的文件读取或 KDF 继续借新身份写入。 */
export function useLegacyApi() {
  const token = session.token,
    epoch = session.epoch,
    controller = new AbortController();
  onScopeDispose(() => controller.abort());
  /** 每次请求前后都核对身份；查询重试信号与页面取消共同生效。 @param {string} path 旧业务路径。 @param {import('./client.js').LegacyOptions} [options] 请求选项。 */
  return async function request(path, options = {}) {
    if (controller.signal.aborted || token !== session.token || epoch !== session.epoch)
      throw new DOMException('页面或账号已切换', 'AbortError');
    const result = await api(path, {
      ...options,
      signal: options.signal
        ? AbortSignal.any([controller.signal, options.signal])
        : controller.signal,
    });
    if (controller.signal.aborted || token !== session.token || epoch !== session.epoch)
      throw new DOMException('页面或账号已切换', 'AbortError');
    return result;
  };
}

/**
 * 页面查询具有独立取消与版本门槛；重试和卸载都会使旧响应失效。
 * @template T
 * @param {(signal: AbortSignal) => Promise<T>} loader 查询。
 */
export function useLoad(loader) {
  const data = shallowRef(/** @type {T|null} */ (null));
  const loading = ref(false),
    error = ref(''),
    forbidden = ref(false);
  let controller = new AbortController(),
    generation = 0,
    disposed = false;
  /** 重新查询保留已有可见内容；先取消上一轮，防止搜索竞态覆盖。 */
  async function reload() {
    controller.abort();
    controller = new AbortController();
    const current = ++generation;
    loading.value = true;
    error.value = '';
    forbidden.value = false;
    try {
      const result = await loader(controller.signal);
      if (!disposed && current === generation) data.value = result;
    } catch (failure) {
      if (
        !disposed &&
        current === generation &&
        !(failure instanceof Error && failure.name === 'AbortError')
      ) {
        error.value = failure instanceof Error ? failure.message : '读取失败';
        forbidden.value = failure instanceof ApiError && failure.status === 403;
      }
    } finally {
      if (!disposed && current === generation) loading.value = false;
    }
  }
  onMounted(reload);
  onScopeDispose(() => {
    disposed = true;
    generation++;
    controller.abort();
    data.value = null;
  });
  return { data, loading, error, forbidden, reload };
}
/** 提交错误持久显示；输入只由成功回调清理，不会在 catch 中丢弃。 */
export function useAction() {
  const busy = ref(false),
    error = ref(''),
    notice = ref('');
  let active = true;
  onScopeDispose(() => {
    active = false;
  });
  /** 串行执行一次用户动作；结果未知明确显示，调用者保留原请求。 @param {() => Promise<unknown>} job 业务动作。 @param {string} [message] 成功提示。 */
  async function run(job, message = '已保存') {
    if (busy.value) return false;
    busy.value = true;
    error.value = '';
    notice.value = '';
    try {
      await job();
      if (active) notice.value = message;
      return active;
    } catch (failure) {
      if (active) error.value = failure instanceof Error ? failure.message : '操作失败，请重试';
      return false;
    } finally {
      if (active) busy.value = false;
    }
  }
  return { busy, error, notice, run };
}
