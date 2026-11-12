/** 用当前网页原文件和本机合成API检查启动会话、手机登录错误及首页，绝不连接生产登录或数据库。 */
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const assert = require("node:assert/strict");
const { chromium } = require(
  process.env.HUALI_PLAYWRIGHT_MODULE || "playwright-core",
);
const ROOT = path.resolve(process.env.HUALI_WEB_ROOT || path.join(__dirname, "../web 7M/dist"));
const results = [];
let mode = "html401";
/** 原网页静态资源原样提供；身份、登录和商品全部合成，不代理真实API。 */
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://local.invalid");
  if (url.pathname.startsWith("/api/")) {
    res.setHeader("Content-Type", "application/json");
    if (url.pathname === "/api/config")
      return res.end(
        JSON.stringify({
          name: "华立转角",
          trial: true,
          ai: mode === "pet",
          auth_mode: "client_kdf",
          colleges: [{ name: "计算机工程学院" }],
          grades: ["2026"],
        }),
      );
    if (url.pathname === "/api/me") {
      if (mode === "html401") {
        res.statusCode = 401;
        res.setHeader("Content-Type", "text/html");
        return res.end("<!DOCTYPE html><h1>Proxy access</h1>");
      }
      if (mode === "json401") {
        res.statusCode = 401;
        return res.end(JSON.stringify({ error: "请先登录" }));
      }
      return res.end(
        JSON.stringify({
          id: 42,
          nickname: "合成同学",
          role: "user",
          college: "计算机工程学院",
        }),
      );
    }
    if (url.pathname === "/api/auth/salt")
      return res.end(JSON.stringify({ salt: "00".repeat(16), rounds: 600000 }));
    if (["/api/auth/login", "/api/auth/register"].includes(url.pathname)) {
      res.setHeader("Content-Type", "text/html");
      return res.end("<!DOCTYPE html><h1>Proxy page</h1>");
    }
    return res.end("[]");
  }
  const name = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const file = path.resolve(ROOT, name);
  if (
    !file.startsWith(ROOT + path.sep) ||
    !fs.existsSync(file) ||
    !fs.statSync(file).isFile()
  ) {
    res.statusCode = 404;
    return res.end("missing");
  }
  const mime =
    {
      ".js": "application/javascript",
      ".css": "text/css",
      ".html": "text/html",
      ".png": "image/png",
      ".webp": "image/webp",
      ".svg": "image/svg+xml",
      ".jpg": "image/jpeg",
    }[path.extname(file)] || "application/octet-stream";
  res.setHeader("Content-Type", mime);
  fs.createReadStream(file).pipe(res);
});
/** 完整加载真实入口，不抽取或改写启动代码，检查持久会话和真实DOM。 */
async function main() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.HUALI_BROWSER_EXECUTABLE ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  });
  const errors = [];
  try {
    for (const width of [390, 1440]) {
      for (const kind of ["html401", "json401"]) {
        mode = kind;
        const context = await browser.newContext({
          viewport: { width, height: 900 },
        });
        await context.addInitScript(() => {
          localStorage.setItem("hc-token", "synthetic-local-session");
          localStorage.setItem(
            "hc-token-expires",
            String(Date.now() + 86400000),
          );
        });
        const page = await context.newPage();
        await page.goto(origin, { waitUntil: "networkidle" });
        await page.waitForFunction(
          () =>
            !document
              .querySelector("#app")
              ?.textContent.includes("正在打开转角"),
          {},
          { timeout: 10000 },
        );
        const token = await page.evaluate(() =>
          localStorage.getItem("hc-token"),
        );
        try {
          assert.equal(
            token,
            kind === "html401" ? "synthetic-local-session" : null,
            kind + "会话判定错误",
          );
          results.push({ width, kind, pass: true });
        } catch (error) {
          errors.push(error.message);
        }
        await context.close();
      }
      console.log(
        JSON.stringify({ startupResults: results, startupErrors: errors }),
      );
      mode = "guest";
      const context = await browser.newContext({
        viewport: { width, height: 900 },
      });
      const page = await context.newPage();
      const pageErrors = [];
      page.on("console", (m) => {
        if (m.type() === "error") console.log("console " + m.text());
      });
      page.on("requestfailed", (r) => console.log("failed " + r.url()));
      page.on("pageerror", (e) => pageErrors.push(e.message));
      await page.goto(origin, { waitUntil: "networkidle" });
      await page.waitForFunction(
        () =>
          !document.querySelector("#app")?.textContent.includes("正在打开转角"),
        {},
        { timeout: 10000 },
      );
      if (!(await page.locator('[data-action="login"]').count()))
        throw new Error(
          "guest init: " +
            (await page.locator("body").innerText()).slice(0, 400) +
            " errors:" +
            pageErrors.join(";"),
        );
      await page.locator('[data-action="login"]').first().click();
      await page
        .locator('#login-form [name="phone"]')
        .fill("synthetic@invalid.test");
      await page
        .locator('#login-form [name="password"]')
        .fill("Synthetic-Only");
      await page.locator("#login-form button").last().click();
      await page.waitForFunction(() =>
        document.querySelector("#toast")?.textContent.includes("接口响应异常"),
      );
      assert.equal(
        await page.locator('#login-form [name="phone"]').inputValue(),
        "synthetic@invalid.test",
      );
      assert.equal(
        await page.locator('#login-form [name="password"]').inputValue(),
        "Synthetic-Only",
      );
      assert.equal(pageErrors.length, 0);
      results.push({
        width,
        kind: "loginHtmlResponse",
        inputPreserved: true,
        noRawJsonError: true,
      });
      // 注册同样走真实600000轮派生，网络只返回合成HTML，不创建生产账号。
      await page
        .locator('[data-action="trial-auth-mode"][data-value="register"]')
        .click();
      await page
        .locator('#register-form [name="phone"]')
        .fill("synthetic-new@invalid.test");
      await page.locator('#register-form [name="nickname"]').fill("合成同学");
      await page.locator('#register-form [name="grade"]').selectOption("2026");
      await page
        .locator('#register-form [name="password"]')
        .fill("Synthetic-Only");
      await page
        .locator('#register-form [name="password_confirm"]')
        .fill("Synthetic-Only");
      await page.locator('#register-form [name="agree"]').check();
      const registration = page.waitForResponse((response) =>
        response.url().endsWith("/api/auth/register"),
      );
      await page.locator("#register-form button").last().click();
      await registration;
      await page.waitForFunction(
        () => !document.querySelector("#register-form button").disabled,
      );
      assert.equal(
        await page.locator('#register-form [name="phone"]').inputValue(),
        "synthetic-new@invalid.test",
      );
      assert.equal(
        await page.locator('#register-form [name="nickname"]').inputValue(),
        "合成同学",
      );
      assert.equal(pageErrors.length, 0);
      results.push({
        width,
        kind: "registrationHtmlResponse",
        inputPreserved: true,
        noRawJsonError: true,
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
      "../artifacts/current-web-audit-20261112/browser-result.json",
    ),
    JSON.stringify({ localOnly: true, results, errors }, null, 2),
  );
  console.log(JSON.stringify({ results, errors }));
  if (errors.length) process.exitCode = 1;
}
main().catch((error) => {
  console.error(error.stack);
  server.close();
  process.exit(1);
});
