/** 执行全部前端与小程序合同测试，任何脚本失败都返回非零状态。 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const files = fs.readdirSync(path.join(root, 'tests')).filter(name => /\.test\.(?:mjs|js|cjs)$/.test(name)).sort();
let failures = 0;
for (const file of files) {
  const result = spawnSync(process.execPath, [path.join(root, 'tests', file)], {cwd: root, stdio: 'inherit'});
  if (result.error || result.status !== 0) failures++;
}
console.log(`前端脚本 ${files.length} 个，失败 ${failures} 个`);
process.exitCode = failures ? 1 : 0;
