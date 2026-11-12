/** 执行真实 Postman 脚本，验证人工意图的在线/离线合同与错误行为拒绝，不改 AI 规则。 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../postman');

/** 提供本集合使用的断言链；生产 CI 仍由 Newman/Chai 执行这些同一脚本。 */
function expect(value) {
  const chain = {
    eql(other) {assert.deepEqual(value, other); return chain;},
    match(regex) {assert.match(value, regex); return chain;},
    include(word) {assert.ok(value.includes(word)); return chain;},
    above(number) {assert.ok(value > number); return chain;},
    a(type) {assert.equal(typeof value, type); return chain;},
    an(type) {if (type === 'array') assert.ok(Array.isArray(value)); else chain.a(type); return chain;},
    status(number) {assert.equal(value, number); return chain;},
  };
  for (const key of ['to', 'be', 'have', 'that', 'is']) Object.defineProperty(chain, key, {get: () => chain});
  Object.defineProperty(chain, 'empty', {get: () => {assert.equal(value.length, 0); return chain;}});
  return chain;
}

/** 找到指定集合中的实际测试脚本，避免在单测复制第二套判定逻辑。 */
function findScript(file, prefix) {
  const collection = JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
  const items = collection.item.flatMap(item => item.item || [item]);
  const item = items.find(item => item.name.startsWith(prefix));
  return item.event.find(event => event.listen === 'test').script.exec.join('\n');
}

/** 将服务响应和 CSV 行注入独立沙盒；断言必须实际执行且失败不能被忽略。 */
function execute(script, body, data = {}) {
  let assertions = 0;
  const pm = {
    expect,
    test(_name, callback) {assertions++; callback();},
    response: {json: () => body, to: expect(200)},
    iterationData: {get: key => data[key]},
  };
  vm.runInNewContext(script, {pm, console: {log() {}}});
  assert.ok(assertions >= 3);
}

const direct = findScript('转角AI客服.postman_collection.json', '04 ');
const faq = findScript('转角AI客服-数据驱动回归.postman_collection.json', 'FAQ ');
const humanRow = fs.readFileSync(path.join(root, 'faq-cases.csv'), 'utf8').trim().split(/\r?\n/).find(row => row.startsWith('我要转人工,'));
const [question, expected_action, expected_keyword] = humanRow.split(',');

for (const online of [true, false]) {
  /** 营业时转接，非营业时留言；两种结果都保留空知识来源和清晰说明。 */
  test('人工意图脚本在' + (online ? '在线' : '离线') + '时验证实际合同', () => {
    const body = {support: {online, hours: '08:00—20:00'}, action: online ? 'transfer' : 'leave_message', answer: online ? '可以转人工，请先核对工单。' : '客服现在不在线，请留言，明天上班后处理。', sources: []};
    execute(direct, body);
    execute(faq, body, {question, expected_action, expected_keyword});
    assert.throws(() => execute(direct, {...body, action: online ? 'leave_message' : 'transfer'}));
    assert.throws(() => execute(faq, {...body, action: 'reply'}, {question, expected_action, expected_keyword}));
  });
}
