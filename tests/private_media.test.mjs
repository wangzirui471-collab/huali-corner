/** 旧客户端私密媒体兼容测试；全部响应、用户和图片都是合成数据。 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { installAuthenticatedMedia } from '../web 7M/src/core/authenticated-media.js';

/** 建立最小图片节点，不启动浏览器或执行图片网络请求。 */
function image(src = '/media/synthetic-photo') {
  return {
    nodeName: 'IMG', src, isConnected: true, attributes: {},
    /** 模拟图片读取原始路径，避免使用会自动展开的 src 属性。 */
    getAttribute(name) { return name === 'src' ? this.src : this.attributes[name]; },
    /** 保存媒体状态，模拟真实图片节点的属性写入。 */
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

/** 为每项场景建立独立兼容器，记录请求与 Blob 供断言核对。 */
function fixture(fetcher) {
  let session = {token: 'synthetic-session', epoch: 1};
  const requests = [], urls = [];
  const root = {
    /** 夹具只直接触发公共读取接口，不启动浏览器事件循环。 */
    addEventListener() {},
    /** 对应卸载接口，夹具没有外部资源需要回收。 */
    removeEventListener() {},
  };
  const loader = installAuthenticatedMedia({
    root,
    getSession: () => session,
    registerURL: url => urls.push(url),
    fetcher: (...args) => { requests.push(args); return fetcher(...args); },
    urlAPI: {createObjectURL: () => 'blob:synthetic-private-image'},
  });
  return {loader, requests, urls,
    /** 模拟登录上下文变化，不改动任何真实存储。 */
    changeAccount() { session = {token: 'another-session', epoch: 2}; },
  };
}

/** 核对合法私密图携带认证读取，同时不在 URL 中暴露令牌。 */
{
  const test = fixture(async () => new Response(new Blob(['image']), {headers: {'Content-Type': 'image/webp'}}));
  const target = image();
  assert.equal(await test.loader.load(target), true);
  assert.equal(target.src, 'blob:synthetic-private-image');
  assert.equal(test.requests[0][0], '/media/synthetic-photo');
  assert.equal(test.requests[0][1].headers.Authorization, 'Bearer synthetic-session');
  assert.equal(test.requests[0][1].cache, 'no-store');
  assert.deepEqual(test.urls, ['blob:synthetic-private-image']);
  test.loader.dispose();
}

/** 第三方 URL、伪装路径和旧静态资源不能收到 Authorization。 */
{
  const test = fixture(async () => { throw new Error('不应请求'); });
  for (const path of ['https://elsewhere.invalid/media/photo', '//elsewhere.invalid/media/photo', '/media/../api/me', '/assets/item0.svg']) {
    assert.equal(await test.loader.load(image(path)), false);
  }
  assert.equal(test.requests.length, 0);
  test.loader.dispose();
}

/** 即使网络层忽略取消，切换账号后也不能将旧图交给新账号。 */
{
  let complete;
  const test = fixture(() => new Promise(resolve => { complete = resolve; }));
  const target = image();
  const pending = test.loader.load(target);
  test.changeAccount();
  complete(new Response(new Blob(['image']), {headers: {'Content-Type': 'image/webp'}}));
  assert.equal(await pending, false);
  assert.equal(target.src, '/media/synthetic-photo');
  assert.equal(test.urls.length, 0);
  test.loader.dispose();
}

/** 403/代理 HTML 不产生可展示 Blob，也不会不断重试同一图片。 */
{
  const test = fixture(async () => new Response('<html>proxy</html>', {status: 403, headers: {'Content-Type': 'text/html'}}));
  const target = image();
  assert.equal(await test.loader.load(target), false);
  assert.equal(await test.loader.load(target), false);
  assert.equal(test.requests.length, 1);
  assert.equal(test.urls.length, 0);
  test.loader.dispose();
}

console.log('Private media: authorized Blob, same-origin restriction, account isolation and failure checks passed.');

/** 在微信平台边界使用合成响应，执行真实 app 和详情生命周期代码。 */
function nativeFixture() {
  let app, page, download;
  let token = 'synthetic-native-token';
  const deleted = [];
  const wx = {
    /** 只提供合成令牌，其余存储在本场景中为空。 */
    getStorageSync(key) { return key === 'hc-token' ? token : ''; },
    /** 商品响应是合成最小 DTO，不访问真实服务器。 */
    request(options) {
      options.success({ statusCode: 200, data: { id: 1, title: '合成教材', photos: [{angle: 'front', url: '/media/synthetic-native'}], price: 1800, delivery_fee: 0 } });
    },
    /** 暂存微信下载回调，测试可复现页面离开与网络响应的先后顺序。 */
    downloadFile(options) { download = options; },
    /** 临时文件操作只记录路径，绝不删除磁盘文件。 */
    getFileSystemManager() { return {
      /** 只登记待清理的合成路径，不调用真实文件系统。 */
      unlink(options) { deleted.push(options.filePath); },
    }; },
    /** 错误提示不依赖真正的小程序 UI。 */
    showToast() {},
  };
  vm.runInNewContext(readFileSync(new URL('../web 7M/miniprogram/app.js', import.meta.url), 'utf8'), {
    wx, App: definition => { app = definition; }, require: () => ({baseURL: 'https://synthetic.invalid'}),
  });
  vm.runInNewContext(readFileSync(new URL('../web 7M/miniprogram/pages/detail/index.js', import.meta.url), 'utf8'), {
    wx, getApp: () => app, Page: definition => { page = definition; }, require: () => ({demoCover: () => ''}),
  });
  /** 用真实页面的数据更新入口记录可展示结果。 */
  page.setData = function (data) { Object.assign(this.data, data); };
  page.onLoad({id: '1'});
  return {app, page, deleted,
    /** 读取平台收到的下载请求供核对认证头和目标地址。 */
    download() { return download; },
    /** 模拟另一账号替换本机令牌和会话代次。 */
    changeAccount() { token = 'another-native-token'; app.globalData.sessionVersion += 1; },
  };
}

/** 合法详情显示认证下载结果；离开后清空内容并只清理登记过的临时文件。 */
{
  const native = nativeFixture();
  const pending = native.page.onShow();
  await new Promise(setImmediate);
  assert.equal(native.download().url, 'https://synthetic.invalid/media/synthetic-native');
  assert.equal(native.download().header.Authorization, 'Bearer synthetic-native-token');
  native.download().success({statusCode: 200, tempFilePath: 'wxfile://synthetic-private'});
  await pending;
  assert.equal(native.page.data.p.photos[0].url, 'wxfile://synthetic-private');
  native.page.onHide();
  assert.equal(native.page.data.p, null);
  native.app.releaseMedia(['wxfile://unrelated-file']);
  assert.deepEqual(native.deleted, ['wxfile://synthetic-private']);
}

/** 退出页面或更换账号后，迟到的下载都不能重新显示旧账号图片。 */
for (const leave of ['hide', 'switch-account']) {
  const native = nativeFixture();
  const pending = native.page.onShow();
  await new Promise(setImmediate);
  if (leave === 'hide') native.page.onHide();
  else native.changeAccount();
  native.download().success({statusCode: 200, tempFilePath: 'wxfile://synthetic-late'});
  await pending;
  assert.equal(native.page.data.p, null);
  assert.deepEqual(native.deleted, ['wxfile://synthetic-late']);
}

/** 无权下载得到明确的图片失败状态，不展示服务器错误文件或随机演示图。 */
{
  const native = nativeFixture();
  const pending = native.page.onShow();
  await new Promise(setImmediate);
  native.download().success({statusCode: 403, tempFilePath: 'wxfile://synthetic-error'});
  await pending;
  assert.equal(native.page.data.p.photos[0].unavailable, true);
  assert.equal(native.page.data.p.photos[0].url, '');
  assert.deepEqual(native.deleted, ['wxfile://synthetic-error']);
}
console.log('Native private media: authenticated display, cleanup, page/account isolation and forbidden checks passed.');
