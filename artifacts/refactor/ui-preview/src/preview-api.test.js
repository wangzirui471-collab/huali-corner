import { afterEach, expect, it, vi } from "vitest";
import { installPreviewApi } from "./preview-api.js";
const originalFetch = globalThis.fetch;
/** 还原预览专用网络边界，测试不修改业务源码的客户端。 */
afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

/** 主要导航需要合法的旧 DTO，而不是落到首页占位或未实现响应。 */
it("社区、论坛、消息、订单与工单均提供可读的演示内容", async () => {
  installPreviewApi();
  for (const path of ["/posts", "/wants", "/orders", "/tickets"]) {
    const response = await fetch("/api" + path);
    expect(response.status, path).toBe(200);
    const data = await response.json();
    expect(Array.isArray(data), path).toBe(true);
    expect(data.length, path).toBeGreaterThan(0);
  }
  const rooms = await (await fetch("/api/rooms")).json();
  expect(rooms.joined.length).toBeGreaterThan(0);
  const messages = await (await fetch("/api/messages?room_id=9")).json();
  expect(messages.length).toBeGreaterThan(0);
});

/** 只读预览拒绝业务写入，既不能假报成功，也不能穿透到原 fetch。 */
it("演示页面的发送与交易不会调用真实网络", async () => {
  const upstream = vi.fn();
  globalThis.fetch = upstream;
  installPreviewApi();
  const response = await fetch("/api/messages", {
    method: "POST",
    body: JSON.stringify({ body: "演示消息", room_id: 9 }),
  });
  expect(response.status).toBe(403);
  expect((await response.json()).error).toContain("预览");
  expect(upstream).not.toHaveBeenCalled();
});
