/** 验证当前网页请求在正文阶段也能超时，失败后保留会话且不自动重复提交。 */
import assert from "node:assert/strict";
import test from "node:test";

globalThis.window = {};
globalThis.sessionStorage = {
  getItem() {
    return null;
  },
};
const { api } = await import("../web 7M/src/core/http.js");
const { state } = await import("../web 7M/src/core/state.js");

/** 合成JSON头已返回但正文一直等待的响应，Abort后模拟真实fetch正文拒绝。 */
function stalledBody(signal) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: () =>
      new Promise((resolve, reject) => {
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("已取消", "AbortError")),
          { once: true },
        );
        setTimeout(() => resolve({ ok: true }), 120);
      }),
  };
}

/** 登录正文挂起时必须在指定时限内失败并保留账号和可人工重试的状态。 */
test("登录请求的超时覆盖JSON正文读取且不自动重发", async () => {
  state.token = "synthetic-session";
  let calls = 0;
  globalThis.fetch = async (_url, options) => {
    calls++;
    return stalledBody(options.signal);
  };
  await assert.rejects(
    api(
      "/auth/login",
      { phone: "synthetic@invalid.test", digest: "synthetic" },
      { timeout: 25 },
    ),
    (error) => {
      assert.equal(error.status, 504);
      assert.match(error.message, /超时/);
      assert.doesNotMatch(error.message, /AI/);
      return true;
    },
  );
  assert.equal(calls, 1);
  assert.equal(state.token, "synthetic-session");
});

/** 成功及协议失败都必须及时清理定时器，避免稍后误取消已完成请求。 */
test("正常JSON成功后不会触发迟到的取消", async () => {
  let signal;
  globalThis.fetch = async (_url, options) => {
    signal = options.signal;
    return Response.json({ ok: true });
  };
  assert.deepEqual(
    await api("/auth/salt?phone=synthetic", {}, { timeout: 25 }),
    { ok: true },
  );
  await new Promise((resolve) => setTimeout(resolve, 45));
  assert.equal(signal.aborted, false);
});

/** 读请求头一直不返回时，中文错误不应误称正在调用AI。 */
test("普通登录网络超时使用通用提示并保留会话", async () => {
  state.token = "synthetic-session";
  globalThis.fetch = async (_url, options) =>
    new Promise((_resolve, reject) => {
      options.signal.addEventListener(
        "abort",
        () => reject(new DOMException("取消", "AbortError")),
        { once: true },
      );
    });
  await assert.rejects(
    api("/auth/login", { phone: "synthetic@invalid.test" }, { timeout: 20 }),
    (error) => {
      assert.equal(error.status, 504);
      assert.doesNotMatch(error.message, /AI/);
      assert.match(error.message, /结果|确认|重复/);
      return true;
    },
  );
  assert.equal(state.token, "synthetic-session");
});
