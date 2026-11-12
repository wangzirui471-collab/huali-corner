/** 当前网页版AI三模式、窗口和失败草稿的合成浏览器验收，不调用真实模型或写生产数据。 */
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const assert = require("node:assert/strict");
const { chromium } = require(
  process.env.HUALI_PLAYWRIGHT_MODULE || "playwright-core",
);
const ROOT = path.resolve(process.env.HUALI_WEB_ROOT || path.join(__dirname, "../web 7M/dist"));
const requests = [];
/** 所有API仅返回合成所有者和空业务数据，AI固定失败以检查输入恢复。 */
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://local.invalid");
  if (u.pathname.startsWith("/api/")) {
    requests.push(u.pathname);
    res.setHeader("Content-Type", "application/json");
    if (u.pathname === "/api/config")
      return res.end(
        JSON.stringify({
          name: "华立转角",
          trial: true,
          ai: true,
          auth_mode: "client_kdf",
          colleges: [],
          grades: [],
        }),
      );
    if (u.pathname === "/api/me")
      return res.end(
        JSON.stringify({ id: 42, nickname: "合成所有者", role: "owner" }),
      );
    if (u.pathname === "/api/pet/prefs") return res.end('{"synced":false}');
    if (u.pathname === "/api/pet/prefs/save") return res.end('{"ok":true}');
    if (u.pathname.startsWith("/api/ai/")) {
      res.statusCode = 503;
      return setTimeout(() => res.end('{"error":"合成AI服务暂不可用"}'), 150);
    }
    return res.end("[]");
  }
  const file = path.resolve(
    ROOT,
    u.pathname === "/" ? "index.html" : u.pathname.slice(1),
  );
  if (
    !file.startsWith(ROOT + path.sep) ||
    !fs.existsSync(file) ||
    !fs.statSync(file).isFile()
  ) {
    res.statusCode = 404;
    return res.end("missing");
  }
  res.setHeader(
    "Content-Type",
    {
      ".js": "application/javascript",
      ".css": "text/css",
      ".html": "text/html",
      ".png": "image/png",
      ".webp": "image/webp",
      ".svg": "image/svg+xml",
      ".jpg": "image/jpeg",
    }[path.extname(file)] || "application/octet-stream",
  );
  fs.createReadStream(file).pipe(res);
});
/** 真实DOM边界断言，拒绝窗口或宠物跑到屏幕外。 */
async function bounds(locator, width, height) {
  const b = await locator.boundingBox();
  assert.ok(
    b &&
      b.x >= -1 &&
      b.y >= -1 &&
      b.x + b.width <= width + 1 &&
      b.y + b.height <= height + 1,
    JSON.stringify(b),
  );
  return b;
}
/** 每屏宽检查已有模式就地切换、不跳旧页、三模式失败保留草稿及最大化还原。 */
async function main() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.HUALI_BROWSER_EXECUTABLE ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  });
  const result = [];
  try {
    for (const width of [360, 390, 768, 1440]) {
      const context = await browser.newContext({
        viewport: { width, height: 900 },
        reducedMotion: "reduce",
      });
      await context.addInitScript(() => {
        localStorage.setItem("hc-token", "synthetic-owner-session");
        localStorage.setItem("hc-token-expires", String(Date.now() + 86400000));
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(origin, { waitUntil: "networkidle" });
      const initialUrl = page.url();
      await page.locator("#ai-pet-body").waitFor({ state: "visible" });
      await page.locator("#ai-pet-body").click();
      await page.locator("#ai-pet-panel").waitFor({ state: "visible" });
      await bounds(page.locator("#ai-pet-panel"), width, 900);
      const initial = await page.locator("#ai-pet-panel").boundingBox();
      await page.locator("#ai-pet-max").click();
      await bounds(page.locator("#ai-pet-panel"), width, 900);
      await page.locator("#ai-pet-max").click();
      const restored = await page.locator("#ai-pet-panel").boundingBox();
      assert.ok(
        Math.abs(initial.x - restored.x) <= 1 &&
          Math.abs(initial.y - restored.y) <= 1,
        "放大还原跳位",
      );
      for (const mode of ["chat", "office", "work"]) {
        await page
          .locator('[data-action="ai-pet-mode"][data-mode="' + mode + '"]')
          .click();
        const question = "合成问题 " + mode;
        await page.locator("#ai-pet-q").fill(question);
        await page.locator('#ai-pet-form button[type="submit"]').click();
        await page.waitForFunction(() =>
          document
            .querySelector("#ai-pet-log")
            .textContent.includes("合成AI服务暂不可用"),
        );
        await page.waitForFunction(
          () =>
            !document.querySelector('#ai-pet-form button[type="submit"]')
              .disabled,
        );
        assert.equal(
          await page.locator("#ai-pet-q").inputValue(),
          question,
          "失败后丢失输入 " + mode,
        );
        assert.equal(page.url(), initialUrl, "模式切换发生跳页");
        // 等待过程中写的新草稿不能被失败恢复覆盖，也不能自动发起第二次模型请求。
        const previousCalls = requests.filter((name) =>
          name.startsWith("/api/ai/"),
        ).length;
        const nextRequest = page.waitForRequest((request) =>
          request.url().includes("/api/ai/"),
        );
        await page.locator("#ai-pet-q").fill("上一轮待失败问题");
        await page.locator('#ai-pet-form button[type="submit"]').click();
        await nextRequest;
        await page.locator("#ai-pet-q").fill("正在编辑的新草稿");
        await page.waitForFunction(
          () =>
            !document.querySelector('#ai-pet-form button[type="submit"]')
              .disabled,
        );
        assert.equal(
          await page.locator("#ai-pet-q").inputValue(),
          "正在编辑的新草稿",
        );
        assert.equal(
          requests.filter((name) => name.startsWith("/api/ai/")).length,
          previousCalls + 1,
        );
      }
      await page.locator("#ai-pet-set").click();
      for (const size of [60, 100, 140, 160]) {
        await page.locator("#ps-scale").evaluate((el, v) => {
          el.value = String(v);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }, size);
        await bounds(page.locator("#ai-pet-body"), width, 900);
      }
      await page.locator('.ps-x[data-ps="close"]').click();
      await page.locator("#ai-pet-close").click();
      await page.locator("#ai-pet-panel").waitFor({ state: "hidden" });
      assert.equal(errors.length, 0);
      result.push({
        width,
        modesInline: true,
        failedInputRetained: true,
        newDraftPreserved: true,
        noAutomaticRetry: true,
        windowBounds: true,
        maxRestore: true,
        scales: [60, 100, 140, 160],
        pageErrors: 0,
      });
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
  fs.writeFileSync(
    path.resolve(
      __dirname,
      "../artifacts/current-web-audit-20261112/pet-result.json",
    ),
    JSON.stringify({ localOnly: true, result, modelCalls: 0 }, null, 2),
  );
  console.log(JSON.stringify(result));
}
main().catch((error) => {
  console.error(error.stack);
  server.close();
  process.exit(1);
});
