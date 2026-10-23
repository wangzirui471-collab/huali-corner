/** 验证真实 Vue 面板到办公业务 API；先启动 office_browser_fixture.py，数据全部为合成。 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const origin = process.env.HC_OFFICE_TEST_ORIGIN || 'http://127.0.0.1:8137';
const shots = path.resolve(process.env.HC_OFFICE_SHOTS || '../office-shots');
fs.mkdirSync(shots, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.HC_BROWSER_PATH || undefined });

/** 创建干净会话，从截图同一个「待处理工单」按钮进入真实处理面板。 */
async function open(width = 1280){
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.request.post(origin + '/__office_reset__');
  await page.goto(origin + '/__office_test__');
  await page.getByRole('button', { name: '待处理工单', exact: true }).click();
  await page.getByRole('dialog', { name: '工单办公 · L1' }).waitFor();
  return page;
}

try {
  const page = await open();
  assert.equal(await page.locator('.hc-office-ticket').count(), 3);
  assert.equal(await page.getByText('不能展示的内部备注').count(), 0);
  await page.getByRole('button', { name: '选择本页可处理项', exact: true }).click();
  await page.getByRole('button', { name: '生成逐单回复草稿', exact: true }).click();
  await page.locator('[data-ticket-id="11"] textarea').first().fill('请补充图片格式和具体报错内容，我们会据此核实。');
  const prepared = page.waitForResponse(response => response.url().endsWith('/tickets/prepare'));
  await page.getByRole('button', { name: '核对并预览执行计划', exact: true }).click();
  const proposal = await (await prepared).json();
  await page.getByRole('button', { name: '确认执行', exact: true }).waitFor();
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: '确认执行', exact: true }).click();
  assert.equal((await (await page.request.get(origin + '/__office_state__')).json()).replies, 0);
  await page.screenshot({ path: path.join(shots, 'desktop-preview.png'), fullPage: true });
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '确认执行', exact: true }).click();
  await page.getByText('已按确认计划处理3条工单；受理和复核不等于已解决。', { exact: true }).waitFor();
  const after = await (await page.request.get(origin + '/__office_state__')).json();
  assert.equal(after.replies, 3);
  assert.ok(after.states.every(ticket => ticket.status === 'processing'));
  const replay = await page.request.post(origin + '/api/ai/office/tickets/confirm', {
    headers: { Authorization: 'Bearer test-5' }, data: { proposal_id: proposal.proposal_id, confirmed: true }
  });
  assert.equal(replay.status(), 200);
  assert.equal((await (await page.request.get(origin + '/__office_state__')).json()).replies, 3);
  await page.close();
  console.log('PASS desktop: real details, edited draft, cancel, atomic confirmation, replay');

  const stale = await open();
  await stale.getByRole('button', { name: '选择本页可处理项', exact: true }).click();
  const newMessage = await stale.request.post(origin + '/api/ticket/reply', {
    headers: { Authorization: 'Bearer test-5' }, data: { id: 11, body: '用户补充了新的关键证据。' }
  });
  assert.equal(newMessage.status(), 200);
  await stale.getByRole('button', { name: '生成逐单回复草稿', exact: true }).click();
  await stale.getByText('工单已有新消息或处理变化，请刷新明细后重新核对', { exact: true }).waitFor();
  assert.equal(await stale.locator('[data-ticket-id="11"] textarea').first().inputValue(), '');
  await stale.close();
  console.log('PASS stale snapshot: new message blocks drafting until the operator refreshes');

  const mobile = await open(390);
  await mobile.getByRole('button', { name: '选择本页可处理项', exact: true }).click();
  await mobile.getByRole('button', { name: '生成逐单回复草稿', exact: true }).click();
  await mobile.screenshot({ path: path.join(shots, 'mobile-drafts.png'), fullPage: true });
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await mobile.evaluate(() => window.testLogout());
  await mobile.getByRole('dialog', { name: '工单办公 · L1' }).waitFor({ state: 'detached' });
  await mobile.close();
  console.log('PASS mobile: editable drafts, no horizontal overflow, logout clears private panel');

  // 全局宠物请求允许跨路由等待；换号必须清掉已显示内容、上下文和迟到响应。
  const privacy = await browser.newPage();
  let held;
  let seen;
  let calls = 0;
  let nextHistory;
  const waiting = new Promise(resolve => { seen = resolve; });
  await privacy.route('**/api/ai/chat', async route => {
    calls++;
    if (calls === 2){ held = route; seen(); return; }
    if (calls === 3) nextHistory = route.request().postDataJSON().history;
    await route.fulfill({ json: { answer: calls === 1 ? 'OWNER_PRIVATE_BEFORE' : '新账号回答' } });
  });
  await privacy.goto(origin + '/__office_test__');
  await privacy.locator('#ai-pet-q').fill('第一条合成问题');
  await privacy.locator('#ai-pet-form button[type=submit]').click();
  await privacy.getByText('OWNER_PRIVATE_BEFORE', { exact: true }).waitFor();
  await privacy.locator('#ai-pet-q').fill('第二条延迟合成问题');
  await privacy.locator('#ai-pet-form button[type=submit]').click();
  await waiting;
  await privacy.evaluate(async () => {
    window.testLogout();
    const { state } = await import('/src/core/state.js');
    const { rememberSession } = await import('/src/core/session.js');
    state.token = 'test-2'; state.me = { id: 2, role: 'user' };
    rememberSession(state.token);
  });
  assert.equal(await privacy.getByText('OWNER_PRIVATE_BEFORE', { exact: true }).count(), 0);
  await held.fulfill({ json: { answer: 'OWNER_PRIVATE_LATE' } });
  await privacy.waitForFunction(() => !document.querySelector('#ai-pet-form button[type=submit]').disabled);
  assert.equal(await privacy.getByText('OWNER_PRIVATE_LATE', { exact: true }).count(), 0);
  assert.equal(await privacy.getByRole('button', { name: '工单办公', exact: true }).isVisible(), false);
  await privacy.locator('#ai-pet-q').fill('第三条新账号问题');
  await privacy.locator('#ai-pet-form button[type=submit]').click();
  await privacy.getByText('新账号回答', { exact: true }).waitFor();
  assert.deepEqual(nextHistory, []);
  await privacy.close();
  console.log('PASS account isolation: displayed content, late global response, history and owner controls cleared');
} finally {
  await browser.close();
}
