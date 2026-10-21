/** 账号或查询切换后，旧请求即使忽略 AbortSignal，也不能返回旧身份的数据。 */
export class StaleResponseError extends Error {
  /** 使用稳定类别让页面忽略已失效请求，不将其显示成业务失败。 */
  constructor() {
    super('请求所属上下文已失效');
    this.name = 'StaleResponseError';
  }
}

export class RequestScope {
  epoch = 0;
  /** @type {Set<AbortController>} 当前上下文尚未释放的请求。 */
  controllers = new Set();

  /** 账号切换或页面销毁时取消请求，并让已在解析正文的响应失效。 */
  reset() {
    this.epoch += 1;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
  }

  /**
   * 在当前上下文执行操作；只返回仍属于当前上下文的结果。
   * @template T
   * @param {(signal: AbortSignal) => Promise<T>} operation 要执行的异步请求。
   * @returns {Promise<T>} 未失效的响应数据。
   */
  async run(operation) {
    const startedAt = this.epoch;
    const controller = new AbortController();
    this.controllers.add(controller);
    try {
      const result = await operation(controller.signal);
      if (startedAt !== this.epoch) throw new StaleResponseError();
      return result;
    } catch (error) {
      if (startedAt !== this.epoch) throw new StaleResponseError();
      throw error;
    } finally {
      this.controllers.delete(controller);
    }
  }
}
