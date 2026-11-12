/** 从子目录打开已编译的公开演示，检查原只读功能、图片与无真实 API 请求。 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.HUALI_PLAYWRIGHT_MODULE || 'playwright-core');
const root = path.resolve(process.env.HUALI_DEMO_ROOT || path.join(__dirname, '../artifacts/vue3-refactor-20261112/public-demo'));

/** 仅挂载 /demo/，根 /assets 刻意保持 404，防止子目录路径错误被掩盖。 */
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://local.invalid');
  if (!url.pathname.startsWith('/demo/')) {res.statusCode = 404; return res.end('missing');}
  const file = path.resolve(root, decodeURIComponent(url.pathname.slice('/demo/'.length)) || 'index.html');
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.statusCode = 404; return res.end('missing');}
  res.setHeader('Content-Type', {'.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.json':'application/json', '.png':'image/png', '.svg':'image/svg+xml', '.webp':'image/webp', '.jpg':'image/jpeg'}[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

/** 完整执行编译脚本和只读快照，检查专题图与商品图实际解码成功。 */
async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({headless:true, executablePath: process.env.HUALI_BROWSER_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const errors = [];
  const requests = [];
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({viewport:{width, height:900}, reducedMotion:'reduce'});
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => requests.push(request.url()));
      await page.goto(origin + '/demo/#home', {waitUntil:'networkidle'});
      await page.locator('[data-home-catalog][aria-busy="true"]').waitFor({state:'detached'});
      assert.match(await page.locator('.market-main').innerText(), /在校园，发现好物/);
      const images = await page.locator('.mint-cover').evaluateAll(nodes => nodes.map(img => ({url:img.currentSrc, loaded:img.complete && img.naturalWidth > 0})));
      assert.ok(images.length >= 4 && images.every(img => img.loaded && img.url.includes('/demo/assets/')), JSON.stringify(images));
      await page.locator('[data-action="home-channel"][data-value="books"]').click();
      await page.waitForURL('**/#/home/books');
      await page.locator('[data-home-catalog][aria-busy="true"]').waitFor({state:'detached'});
      await page.evaluate(() => {location.hash = '#support';});
      await page.locator('[data-public-demo-feature]').waitFor();
      assert.equal(await page.locator('form').count(), 1, '只读演示除搜索外不应开放提交表单');
      await page.close();
    }
    assert.deepEqual(errors, []);
    assert.ok(!requests.some(url => new URL(url).pathname.startsWith('/api/')));
    console.log(JSON.stringify({ok:true, widths:[390,1440], subdirectory:true, carouselImagesLoaded:true, readOnlyRoutes:true, apiCalls:0, pageErrors:errors}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {console.error(error); process.exitCode=1;});
