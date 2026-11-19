/** 在已构建的首页比对地图点位、试读翻页和窄屏，不访问生产接口。 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.HUALI_PLAYWRIGHT_MODULE || 'playwright-core');

const candidate = path.resolve(__dirname, '../web 7M/dist');
const baseline = process.env.HUALI_CAMPUS_BASELINE;
const review = process.env.HUALI_CAMPUS_REVIEW;
const mime = {'.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.jpg':'image/jpeg', '.webp':'image/webp', '.png':'image/png', '.svg':'image/svg+xml'};
const exampleProducts = [{id:101,title:'合成数据结构教材',category:'books',nickname:'合成卖家',seller_id:9,price:1200,region:'广州校区',status:'available',photos:[]}];
const testApi = {'/api/config':{name:'华立转角',trial:true,ai:false,categories:[['books','教材书籍']],regions:['广州校区']},'/api/products':exampleProducts};

/** 提供构建资源与最小合成接口，拒绝离开静态文件根目录。 */
async function serve(dir) {
  const server = http.createServer((req, res) => {
    const {pathname} = new URL(req.url, 'http://127.0.0.1');
    if (pathname.startsWith('/api/')) {
      res.setHeader('Content-Type','application/json');
      return res.end(JSON.stringify(testApi[pathname] ?? []));
    }
    const file = path.resolve(dir,'.' + decodeURIComponent(pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(path.resolve(dir) + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.statusCode = 404;
      return res.end('missing');
    }
    res.setHeader('Content-Type',mime[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  return {server,origin:`http://127.0.0.1:${server.address().port}`};
}

/** 从可见的轮播入口打开真实专题弹窗。 */
async function openTopic(page, index, topic) {
  await page.locator(`[data-slide-index="${index}"]`).click();
  await page.locator(`[data-campus-open="${topic}"]`).click();
  return page.locator('dialog.campus-dialog[open]');
}

/** 有验收目录时，记录同尺寸的页面表现。 */
async function screenshot(dialog, name) {
  if (review) await dialog.screenshot({path:path.join(review, name + '.png')});
}

/** 对照原图检查代表点位的像素，并实际点击全部地点、实景及缩放控制。 */
async function checkMap(dialog) {
  const map = dialog.locator('[data-campus-model]');
  const img = map.locator('img');
  await img.evaluate(node => node.decode());
  assert.deepEqual(await img.evaluate(node => [node.naturalWidth,node.naturalHeight]), [1080,540]);
  const pointPixels = await map.evaluate(node => {
    const rect = node.querySelector('img').getBoundingClientRect();
    return [...node.querySelectorAll('[data-campus-point]')].map(pin => {
      const {x,y,width,height} = pin.getBoundingClientRect();
      return [Math.round((x + width/2 - rect.x) * 1080/rect.width),Math.round((y + height/2 - rect.y) * 540/rect.height)];
    });
  });
  assert.equal(pointPixels.length,15);
  assert.deepEqual(pointPixels[4],[872,74],'D1 在原图的右上角');
  assert.deepEqual(pointPixels[5],[222,181],'D2/D5/D6 在原图的左侧');
  assert.deepEqual(pointPixels[11],[755,275],'图书馆位置对齐原图');
  const choices = await dialog.locator('[data-campus-list]').all();
  for (const [i,choice] of choices.entries()) {
    await choice.click();
    assert.equal(await dialog.locator(`[data-campus-point="${i}"]`).getAttribute('aria-pressed'),'true');
    assert.match(await dialog.locator('[data-map-selection]').innerText(),new RegExp('^' + (i + 1) + ' · '));
  }
  await map.locator('[data-campus-point="11"]').click();
  assert.match(await dialog.locator('[data-map-selection]').innerText(),/本科图书馆/);
  await dialog.locator('[data-map-tilt]').click();
  assert.notEqual(await map.locator('[data-map-plane]').evaluate(node => getComputedStyle(node).transform),'none');
  await dialog.getByRole('button',{name:'放大地图'}).click();
  assert.ok(await map.evaluate(node => node.scrollWidth > node.clientWidth));
  await dialog.locator('[data-map-reset]').click();
  assert.equal(await dialog.locator('[data-map-tilt]').getAttribute('aria-pressed'),'false');
  assert.equal(await map.evaluate(node => node.scrollLeft),0);
  await dialog.locator('[data-campus-teaching-photo]').click();
  await dialog.locator('[data-campus-photo]').evaluate(node => node.decode());
  assert.match(await dialog.locator('[data-campus-caption]').innerText(),/图书馆正面/);
  await dialog.locator('[data-campus-mode="reference"]').click();
  assert.equal(await dialog.locator('[data-reference-map]').getAttribute('src'),await img.getAttribute('src'));
  await dialog.locator('[data-campus-mode="map"]').click();
  assert.match(await dialog.locator('[data-map-selection]').innerText(),/本科图书馆/);
}

/** 逐章翻过七章，检查公式、例题、展开答案，最后用目录和键盘定位。 */
async function checkBook(dialog) {
  const picker = dialog.locator('[data-book-chapter]');
  assert.equal(await picker.locator('option').count(),7);
  const prev = dialog.getByRole('button',{name:'上一页'});
  const next = dialog.getByRole('button',{name:'翻到下一页'});
  assert.ok(await prev.isDisabled());
  for (let i = 0; i < 7; i++) {
    const paper = dialog.locator('[data-campus-book] > article');
    assert.equal(await dialog.locator('[data-book-position]').innerText(),`${i + 1} / 7`);
    assert.equal(await paper.locator('.campus-book-formulas li').count(),3);
    assert.equal(await paper.locator('.campus-book-example li').count(),3);
    const summary = paper.locator('summary');
    await summary.click();
    assert.ok(await paper.locator('details p').isVisible());
    await summary.click();
    if (i < 6) await next.click();
  }
  assert.ok(await next.isDisabled());
  await picker.selectOption('5');
  assert.equal(await dialog.locator('h3').innerText(),'定积分的应用');
  await prev.press('ArrowLeft');
  assert.equal(await picker.inputValue(),'4');
  assert.match(await dialog.getByRole('link',{name:/出版社目录/}).getAttribute('href'),/^https:\/\/xuanshu\.hep\.com\.cn/);
}

/** 验证两张高清快照、原卡片的路由及页面可返回。 */
async function checkSideCards(page, width) {
  const side = page.locator('.mint-side');
  const cards = [['books','reading-room.jpg'],['free','dorm-room.jpg']];
  for (const [channel, file] of cards) {
    const image = side.locator(`[data-go="home/${channel}"] img`);
    await image.evaluate(node => node.decode());
    assert.ok((await image.getAttribute('src')).endsWith('/' + file));
    assert.equal(await image.evaluate(node => node.naturalWidth),1080);
  }
  await screenshot(side,`side-cards-${width}`);
  for (const [channel] of cards) {
    await side.locator(`[data-go="home/${channel}"]`).click();
    await page.waitForURL('**/#/home/' + channel);
    await page.goBack();
    await page.waitForURL(url => ['#home','#/home'].includes(url.hash));
  }
}

/** 两种视口逐项验证，旧版只用于同尺寸截图。 */
async function main() {
  const sites = [];
  let browser;
  try {
    sites.push(await serve(candidate));
    if (baseline) sites.push(await serve(baseline));
    browser = await chromium.launch({headless:true, executablePath:process.env.HUALI_BROWSER_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
    for (const [{origin}, before] of sites.map((site,i) => [site,i === 1])) {
      for (const width of [1440,390]) {
        const page = await browser.newPage({viewport:{width,height:900},isMobile:width===390,hasTouch:width===390,reducedMotion:'reduce'});
        const errors = [];
        page.on('pageerror',error => errors.push(error.message));
        await page.goto(origin + '/#home');
        await page.locator('.mint-hero').waitFor();
        await page.locator('[data-home-catalog][aria-busy="false"]').waitFor();
        const map = await openTopic(page,2,'dorm');
        if (!before) await checkMap(map);
        await screenshot(map,`${before?'before':'after'}-map-${width}`);
        if (!before && width === 1440) {
          await map.locator('[data-map-tilt]').click();
          await screenshot(map,'after-map-tilt-1440');
        }
        await map.getByRole('button',{name:'关闭专题'}).click();
        const book = await openTopic(page,1,'books');
        if (!before) {
          await checkBook(book);
          await book.locator('[data-book-chapter]').selectOption('1');
          await book.locator('[data-campus-book] > article summary').click();
          assert.ok(await book.evaluate(node => node.scrollWidth <= node.clientWidth + 1));
          await book.evaluate(node => node.scrollTo(0,0));
        }
        await screenshot(book,`${before?'before':'after'}-book-${width}`);
        await book.getByRole('button',{name:'关闭专题'}).click();
        if (!before) {
          const tour = await openTopic(page,0,'tour');
          assert.ok(await tour.locator('[data-campus-model]').isVisible());
          await tour.getByRole('button',{name:'关闭专题'}).click();
          const trade = await openTopic(page,3,'swap');
          await trade.locator('[data-trade-step="2"]').click();
          assert.match(await trade.locator('[data-trade-caption]').innerText(),/交接/);
          await trade.getByRole('button',{name:'关闭专题'}).click();
          await checkSideCards(page,width);
        }
        assert.deepEqual(errors,[]);
        await page.close();
        console.log(`${before?'改前取证':'功能通过'} · ${width}px`);
      }
    }
  } finally {
    await browser?.close();
    await Promise.all(sites.map(({server}) => new Promise(resolve => server.close(resolve))));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
