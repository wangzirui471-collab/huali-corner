/** 健康 DTO 来自服务端 OpenAPI；JavaScript 运行时仍需校验真实网络数据。 */
import { isRecord } from './client';

/** @typedef {import('./generated').components['schemas']['HealthData']} HealthData 健康 DTO。 */

/**
 * 将外部数据校验为健康信息；business_ready=false 表示仍为骨架。
 * @param {unknown} value 网络传入的数据。
 * @returns {HealthData} 完整且符合协议的健康信息。
 */
export function decodeHealth(value) {
  if (
    !isRecord(value) ||
    value.status !== 'ok' ||
    (value.environment !== 'local' &&
      value.environment !== 'test' &&
      value.environment !== 'production') ||
    value.business_ready !== false
  ) {
    throw new TypeError('健康数据不符合 v1 契约');
  }
  return {
    status: 'ok',
    environment: value.environment,
    business_ready: false,
  };
}
