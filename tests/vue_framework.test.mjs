/** 检查框架接入后的共享状态、运行时句柄及旧链接协议，不请求真实 API。 */
import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = {};
globalThis.sessionStorage = {getItem: () => null};

/** 旧模块与 Pinia 必须持有同一个 store，不能复制第二份账号或购物车。 */
test('Pinia 为唯一业务状态且仍兼容原 state 写法', async () => {
  const {state} = await import('../web 7M/src/core/state.js');
  const {pinia, useSiteStore} = await import('../web 7M/src/framework/store.js');
  assert.equal(state, useSiteStore(pinia));
  assert.equal(state.$id, 'site');
  state.me = {id: 42};
  state.cart = [7];
  assert.deepEqual(useSiteStore(pinia).cart, [7]);
  state.filter.q = '教材';
  assert.equal(useSiteStore(pinia).filter.q, '教材');
  const handle = {dispose() {}};
  state.homeView = handle;
  assert.equal(state.homeView, handle);
});

/** 旧分享链接与官方 hash history 格式必须解析成同一路由。 */
test('路由兼容旧 hash、规范 hash、ID 和查询参数', async () => {
  const {routePath} = await import('../web 7M/src/core/route-path.js');
  assert.equal(routePath('#home/books'), 'home/books');
  assert.equal(routePath('#/home/books'), 'home/books');
  assert.equal(routePath('#/admin/people?scope=all&q=%E4%B9%A6'), 'admin/people?scope=all&q=%E4%B9%A6');
  assert.equal(routePath(''), 'home');
});

/** 每个原路由都要进入原页面适配器，不把业务页面换成演示稿。 */
test('Vue Router 匹配所有原路由并将未知路由回到首页', async () => {
  const {createMemoryHistory} = await import('../web 7M/node_modules/vue-router/dist/vue-router.mjs');
  const {createSiteRouter, SITE_ROUTES} = await import('../web 7M/src/framework/router.js');
  const router = createSiteRouter({render() {}}, createMemoryHistory());
  for (const name of SITE_ROUTES) {
    await router.push('/' + name + '/42?scope=all');
    assert.equal(router.currentRoute.value.name, name);
    assert.equal(router.currentRoute.value.params.id, '42');
  }
  await router.push('/unknown-page');
  assert.equal(router.currentRoute.value.name, 'home');
});

/** 原 go API 走同一 router；同页点击只重画一次，不压入重复历史。 */
test('原导航接口复用 Vue Router 并支持同页重新加载', async () => {
  globalThis.document = {createElement: () => ({dataset: {}, isConnected: true}), body: {appendChild() {}}};
  const {createMemoryHistory} = await import('../web 7M/node_modules/vue-router/dist/vue-router.mjs');
  const {createSiteRouter} = await import('../web 7M/src/framework/router.js');
  const {configureNavigation, go, setRenderer} = await import('../web 7M/src/core/nav.js');
  const router = createSiteRouter({render() {}}, createMemoryHistory());
  let renders = 0;
  setRenderer(() => {renders++;});
  configureNavigation(router);
  await go('home/books');
  assert.equal(router.currentRoute.value.fullPath, '/home/books');
  await go('home/books');
  assert.equal(renders, 1);
  await go('admin/people?scope=all&q=%E4%B9%A6');
  assert.equal(router.currentRoute.value.query.q, '书');
  assert.equal(router.currentRoute.value.query.scope, 'all');
  const {stopProgress} = await import('../web 7M/src/core/progress.js');
  stopProgress();
});

/** 首页现有排序操作必须沿用导航重画，不因 hash 适配拼接出错误函数名。 */
test('商品排序沿原入口重新渲染当前频道', async () => {
  const {clicks} = await import('../web 7M/src/actions/catalog.js');
  const {setRenderer, configureNavigation} = await import('../web 7M/src/core/nav.js');
  const {createMemoryHistory} = await import('../web 7M/node_modules/vue-router/dist/vue-router.mjs');
  const {createSiteRouter} = await import('../web 7M/src/framework/router.js');
  const {state} = await import('../web 7M/src/core/state.js');
  const {stopProgress} = await import('../web 7M/src/core/progress.js');
  let renders = 0;
  const router = createSiteRouter({render() {}}, createMemoryHistory());
  await router.push('/home/books');
  configureNavigation(router);
  globalThis.location = {hash: '#/home/books'};
  setRenderer(() => {renders++;});
  assert.doesNotThrow(() => clicks['feed-sort']({dataset: {value: 'price'}}));
  assert.equal(state.filter.sort, 'price');
  assert.equal(renders, 1);
  assert.equal(router.currentRoute.value.fullPath, '/home/books');
  stopProgress();
});

/** Pinia 不改变账号专属购物车键，也不把求购关联带给下一账号。 */
test('账号购物车和求购关联继续隔离', async () => {
  const values = new Map();
  globalThis.sessionStorage = {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value)};
  const {state, saveCart, loadCart} = await import('../web 7M/src/core/state.js');
  state.me = {id: 42};
  state.cart = [101];
  state.pendingWant = {want: 7, product: 101};
  saveCart();
  state.me = {id: 43};
  loadCart();
  assert.deepEqual(state.cart, []);
  assert.equal(state.pendingWant, null);
  state.me = {id: 42};
  loadCart();
  assert.deepEqual(state.cart, [101]);
});
