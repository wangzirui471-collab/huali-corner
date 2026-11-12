/** 使用固定合成数据对照原网页与 Vue 构建，验证路由、Pinia、AI 及页面外观。 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.HUALI_PLAYWRIGHT_MODULE || 'playwright-core');
const root = path.resolve(__dirname, '..');
const audit = path.resolve(process.env.HUALI_AUDIT_DIR || path.join(root, 'artifacts/vue3-refactor-20261112'));
const baseline = process.env.HUALI_BASELINE_WEB || path.join(audit, 'baseline-web');
const candidate = path.join(root, 'web 7M/dist');
const user = {id: 42, nickname: '合成同学', role: 'user', score: 100, college: '计算机工程学院', major: '软件工程', education: '本科', status: 'active'};
const product = {id: 101, title: '合成数据结构教材', nickname: '合成卖家', seller_id: 9, seller_college: '计算机工程学院', score: 100, category: 'books', price: 1200, delivery_fee: 0, region: '广州校区', status: 'available', condition: '九成新', description: '仅供本机验收的合成教材。', photos: [], simulation: true, created: 1794400000, delivery: 'pickup'};
const requests = [];
let delayProducts = 0;
let failProducts = false;

/** 业务 API 完全合成，不代理生产、不发送模型请求，不读真实数据库。 */
function payload(url) {
  if (url.pathname === '/api/config') return {name: '华立转角', trial: true, ai: true, auth_mode: 'client_kdf', colleges: ['计算机工程学院'], grades: ['2026'], categories: [['books', '教材书籍']], regions: ['广州校区']};
  if (url.pathname === '/api/me') return user;
  if (url.pathname === '/api/products') return url.searchParams.get('category') && url.searchParams.get('category') !== 'books' ? [] : [product];
  if (url.pathname === '/api/product') return product;
  if (url.pathname === '/api/profile') return {user: {...user, id: 9, nickname: '合成卖家'}, products: [product]};
  if (url.pathname === '/api/friend/state') return {state: 'none'};
  if (url.pathname === '/api/notifications') return {unread: 0, items: []};
  if (url.pathname === '/api/chats') return {rooms: [], unread: 0};
  if (url.pathname === '/api/pet/prefs') return {synced: false};
  if (url.pathname === '/api/admin') return {users: [], audit: []};
  return [];
}

/** 提供原文件或构建文件并限制路径在各自静态目录内。 */
async function serve(dir) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://synthetic.invalid');
    if (url.pathname.startsWith('/api/')) {
      requests.push(url.pathname + url.search);
      res.setHeader('Content-Type', 'application/json');
      if (url.pathname === '/api/products' && failProducts) {
        res.statusCode = 503;
        return res.end('{"error":"合成商品服务暂不可用"}');
      }
      const body = JSON.stringify(payload(url));
      if (url.pathname === '/api/products' && delayProducts) return setTimeout(() => res.end(body), delayProducts);
      return res.end(body);
    }
    const filename = path.resolve(dir, decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname).slice(1));
    if (!filename.startsWith(path.resolve(dir) + path.sep) || !fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
      res.statusCode = 404;
      return res.end('missing');
    }
    res.setHeader('Content-Type', {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.jpg': 'image/jpeg'}[path.extname(filename)] || 'application/octet-stream');
    fs.createReadStream(filename).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {server, origin: 'http://127.0.0.1:' + server.address().port};
}

/** 只比较原页面内容和布局；排除 Vue 容器属性与页面外的宠物动画。 */
async function snapshot(page) {
  await page.locator('.market-main').waitFor();
  await page.locator('[data-home-catalog][aria-busy="true"]').waitFor({state: 'detached'});
  await page.evaluate(() => document.fonts.ready);
  return page.evaluate(() => {
    const app = document.querySelector('#app');
    const main = document.querySelector('.market-main');
    const header = document.querySelector('.market-header');
    const h = header.getBoundingClientRect();
    const m = main.getBoundingClientRect();
    return {
      html: app.innerHTML,
      text: main.innerText,
      boxes: [h.x, h.y, h.width, h.height, m.x, m.y, m.width, m.height],
      css: [getComputedStyle(main).backgroundColor, getComputedStyle(header).fontFamily, getComputedStyle(main).padding],
    };
  });
}

/** 登录态由合成 storage 预置；固定时钟和已读提示，避免视觉对照被问候动画干扰。 */
async function contextFor(browser, width) {
  const context = await browser.newContext({viewport: {width, height: 900}, reducedMotion: 'reduce', timezoneId: 'Asia/Shanghai'});
  await context.addInitScript(() => {
    Date.now = () => 1794441600000;
    localStorage.setItem('hc-token', 'synthetic-framework-session');
    localStorage.setItem('hc-token-expires', String(1894441600000));
    localStorage.setItem('hc-pet-hint-seen', '1');
  });
  return context;
}

/** 对照全部无副作用页面后，检查 Vue Router 单一导航源及 Pinia 实例。 */
async function main() {
  fs.mkdirSync(audit, {recursive: true});
  if (!process.env.HUALI_BASELINE_WEB && !fs.existsSync(path.join(baseline, 'index.html'))) {
    // 从只读历史提交恢复对照样本，不切换分支、不覆盖当前源文件。
    const ref = 'a36cead19ba6ce5548a6fb6d8e6ed8a748da2e8d';
    const names = execFileSync('git', ['ls-tree', '-r', '-z', '--name-only', ref, '--', 'web 7M'], {cwd: root, encoding: 'utf8'}).split('\0').filter(Boolean);
    for (const name of names) {
      const target = path.join(baseline, name.slice('web 7M/'.length));
      fs.mkdirSync(path.dirname(target), {recursive: true});
      fs.writeFileSync(target, execFileSync('git', ['show', ref + ':' + name], {cwd: root, maxBuffer: 64 * 1024 * 1024}));
    }
  }
  assert.ok(fs.existsSync(path.join(baseline, 'index.html')), '请先保存重构前网页供对照');
  const before = await serve(baseline);
  const after = await serve(candidate);
  const browser = await chromium.launch({headless: true, executablePath: process.env.HUALI_BROWSER_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const rows = [];
  const errors = [];
  try {
    for (const width of process.env.HUALI_FAILURE_ONLY ? [] : [390, 1440]) {
      const context = await contextFor(browser, width);
      const old = await context.newPage();
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      for (const route of ['home', 'home/books', 'home/free', 'community', 'forum/latest', 'product/101', 'profile/9', 'orders', 'listings', 'cart', 'me', 'support', 'staff', 'admin']) {
        await Promise.all([
          old.goto(before.origin + '/#' + route, {waitUntil: 'networkidle'}),
          page.goto(after.origin + '/#' + route, {waitUntil: 'networkidle'}),
        ]);
        const [a, b] = await Promise.all([snapshot(old), snapshot(page)]);
        assert.equal(b.html, a.html, width + ' ' + route + ' 页面 HTML 被改变');
        assert.deepEqual(b.boxes, a.boxes, width + ' ' + route + ' 布局被改变');
        assert.deepEqual(b.css, a.css, width + ' ' + route + ' 样式被改变');
        assert.doesNotMatch(b.text, /暂时无法打开|服务暂不可用/, '合成数据不应导致页面故障 ' + route);
        if (route === 'home') {
          await old.locator('.market-app').screenshot({path: path.join(audit, 'before-' + width + '.png'), animations: 'disabled'});
          await page.locator('.market-app').screenshot({path: path.join(audit, 'after-' + width + '.png'), animations: 'disabled'});
        }
        rows.push({width, route, identicalHtml: true, identicalLayout: true, identicalStyles: true});
      }
      await page.goto(after.origin + '/#home', {waitUntil: 'networkidle'});
      const appState = await page.evaluate(() => {
        const app = document.querySelector('#huali-root').__vue_app__;
        const store = app.config.globalProperties.$pinia._s.get('site');
        return {vue: app.version, store: store.$id, user: store.me.id, route: app.config.globalProperties.$router.currentRoute.value.name};
      });
      assert.match(appState.vue, /^3\./);
      assert.equal(appState.store, 'site');
      assert.equal(appState.user, 42);
      assert.equal(appState.route, 'home');
      const homeHtml = await page.locator('#app').innerHTML();
      const beforeEpoch = await page.evaluate(() => document.querySelector('#huali-root').__vue_app__.config.globalProperties.$pinia._s.get('site').renderId);
      await page.locator('[data-go="home"]').first().click();
      await page.waitForFunction(epoch => document.querySelector('#huali-root').__vue_app__.config.globalProperties.$pinia._s.get('site').renderId > epoch, beforeEpoch);
      await page.locator('[data-home-catalog][aria-busy="true"]').waitFor({state: 'detached'});
      assert.equal(await page.locator('#app').innerHTML(), homeHtml, '同路由刷新改变页面');
      await page.locator('[data-action="feed-sort"][data-value="price"]').click();
      await page.waitForFunction(() => document.querySelector('#huali-root').__vue_app__.config.globalProperties.$pinia._s.get('site').filter.sort === 'price');
      await page.locator('[data-go="community"]:visible').first().click();
      await page.waitForURL('**/#/community');
      await page.locator('.community-hub').waitFor();
      await page.goBack();
      await page.waitForURL('**/#/home');
      await page.goForward();
      await page.waitForURL('**/#/community');
      await page.evaluate(() => {location.hash = '#home/books';});
      await page.waitForFunction(() => document.querySelector('[data-action="home-channel"][data-value="books"]')?.getAttribute('aria-pressed') === 'true');
      // AI 输入框必须保留在 body 上，页面路由切换不可重建实例。
      await page.locator('#ai-pet-body').click();
      await page.locator('#ai-pet-q').fill('跨页合成草稿');
      await page.evaluate(() => {location.hash = '#community';});
      await page.locator('.community-hub').waitFor();
      assert.equal(await page.locator('#ai-pet-q').inputValue(), '跨页合成草稿');
      assert.equal(await page.locator('#ai-pet-panel').count(), 1);
      await page.evaluate(() => {location.hash = '#not-a-real-route';});
      await page.waitForURL('**/#/home');
      rows.push({width, oldLinks: true, history: true, sameRouteRefresh: true, pinia: true, aiAcrossRoutes: true, unknownRoute: true});
      user.role = 'owner';
      await Promise.all([old.reload({waitUntil: 'networkidle'}), page.reload({waitUntil: 'networkidle'})]);
      for (const route of ['admin/people?scope=all&q=%E4%B9%A6', 'staff/users']) {
        await Promise.all([
          old.goto(before.origin + '/#' + route, {waitUntil: 'networkidle'}),
          page.goto(after.origin + '/#' + route, {waitUntil: 'networkidle'}),
        ]);
        const [a, b] = await Promise.all([snapshot(old), snapshot(page)]);
        assert.equal(b.html, a.html, '所有者工作台或查询参数改变 ' + route);
        assert.deepEqual(b.boxes, a.boxes);
        assert.doesNotMatch(b.text, /暂时无法打开|服务暂不可用/);
        rows.push({width, route, ownerDesk: true, identicalHtml: true, identicalLayout: true});
      }
      assert.ok(requests.some(request => request.startsWith('/api/admin/accounts?') && new URL(request, 'http://synthetic.invalid').searchParams.get('q') === '书'), JSON.stringify(requests.filter(request => request.includes('/admin'))));
      user.role = 'user';
      // 卸载应用后，原事件委托不能继续弹窗或执行页面操作。
      await page.evaluate(() => {
        document.querySelector('#overlay').innerHTML = '';
        document.querySelector('#huali-root').__vue_app__.unmount();
        const button = document.createElement('button');
        button.dataset.action = 'login';
        document.body.appendChild(button);
        button.click();
        button.remove();
      });
      assert.equal(await page.locator('#overlay').innerHTML(), '');
      await context.close();
    }
    // 回包已过期的商品请求不能覆盖刚打开的社区。
    const context = await contextFor(browser, 390);
    const page = await context.newPage();
    delayProducts = 300;
    await page.goto(after.origin + '/#home', {waitUntil: 'domcontentloaded'});
    await page.locator('.market-header').waitFor();
    await page.evaluate(() => {location.hash = '#community';});
    await page.locator('.community-hub').waitFor();
    await page.waitForTimeout(450);
    assert.match(await page.locator('.market-main').innerText(), /社区/);
    await context.close();
    assert.deepEqual(errors, []);
    failProducts = true;
    delayProducts = 0;
    const failureContext = await contextFor(browser, 390);
    const failurePage = await failureContext.newPage();
    await failurePage.goto(after.origin + '/#home/books', {waitUntil: 'networkidle'});
    assert.match(await failurePage.locator('.market-main').innerText(), /商品暂时无法加载/);
    assert.equal(await failurePage.getByRole('button', {name: '重新加载商品'}).getAttribute('data-go'), 'home/books');
    failProducts = false;
    await failurePage.getByRole('button', {name: '重新加载商品'}).click();
    await failurePage.locator('[data-home-catalog][aria-busy="true"]').waitFor({state: 'detached'});
    assert.match(await failurePage.locator('.market-main').innerText(), /合成数据结构教材/);
    await failureContext.close();
    failProducts = false;
    if (process.env.HUALI_DEV_ORIGIN) {
      const context = await contextFor(browser, 390);
      const page = await context.newPage();
      const devErrors = [];
      page.on('pageerror', error => devErrors.push(error.message));
      await page.route('**/api/**', route => route.fulfill({contentType: 'application/json', body: JSON.stringify(payload(new URL(route.request().url())))}));
      const cssResponse = await page.request.get(process.env.HUALI_DEV_ORIGIN + '/market.css?v=20261021-ui-integrated');
      assert.equal(cssResponse.status(), 200, '开发服务必须原样提供原站 CSS');
      assert.equal(await cssResponse.text(), fs.readFileSync(path.join(root, 'web 7M/market.css'), 'utf8'));
      await page.goto(process.env.HUALI_DEV_ORIGIN + '/#home/books', {waitUntil: 'networkidle'});
      await page.locator('[data-home-catalog][aria-busy="true"]').waitFor({state: 'detached'});
      assert.equal(await page.locator('[data-action="home-channel"][data-value="books"]').getAttribute('aria-pressed'), 'true');
      await page.locator('[data-go="community"]:visible').first().click();
      await page.waitForURL('**/#/community');
      assert.deepEqual(devErrors, []);
      await context.close();
      rows.push({viteDevelopment: true, originalCssBytes: true, oldLinks: true, navigation: true});
    }
    const result = {ok: true, comparisons: rows, sortAndManualRetry: true, slowResponseGuard: true, pageErrors: errors, productionWrites: false};
    fs.writeFileSync(path.join(audit, 'framework-browser-result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
    await Promise.all([new Promise(resolve => before.server.close(resolve)), new Promise(resolve => after.server.close(resolve))]);
  }
}

main().catch(error => {console.error(error); process.exitCode = 1;});
