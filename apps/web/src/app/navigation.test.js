import { describe, it, expect } from 'vitest';
import { legacyDestination, localBackend } from './navigation.js';
describe('隔离入口与旧链接兼容', () => {
  /** 旧详情、会话和工作台链接保留编号；未知 hash 不形成外站跳转。 */
  it('转换已有业务书签并拒绝外站路径', () => {
    expect(legacyDestination('#product/18')).toBe('/products/18');
    expect(legacyDestination('#messages/9')).toBe('/messages/9');
    expect(legacyDestination('#staff/tickets')).toBe('/workspace/tickets');
    expect(legacyDestination('#admin/people?scope=all&q=zhang')).toBe(
      '/workspace/accounts?q=zhang',
    );
    expect(legacyDestination('#home?category=books')).toBe('/?category=books');
    expect(legacyDestination('#me/favorites')).toBe('/favorites');
    expect(legacyDestination('#https://evil.example')).toBe(null);
    expect(legacyDestination('#/login?next=//evil.example')).toBe(null);
  });
  /** 开发代理仅允许明确的本机服务，配置错误必须在启动前停止。 */
  it('拒绝远程业务代理与含凭据地址', () => {
    expect(localBackend('http://127.0.0.1:8081')).toBe('http://127.0.0.1:8081');
    expect(() => localBackend('https://production.example')).toThrow();
    expect(() => localBackend('http://user:password@localhost:8081')).toThrow();
    expect(() => localBackend('http://localhost:8081/path')).toThrow();
  });
});
