// 前端 ES 模块自检：mock 掉浏览器全局后逐个 import src/ 下所有模块。
// 拆成模块之后，最容易出的错是「新增了模块但忘了 import」或「两个模块循环依赖」，
// 这类问题在浏览器里往往要等到某个页面点开才暴露，这里能在提交前就拦住。
// 运行：node tests/frontend_modules.test.mjs
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

// fileURLToPath 会正确解码 %20 等转义：项目路径含空格（如 "WorkBuddy AI"）时，
// 手工用 .pathname 拼路径会得到 "WorkBuddy%20AI"，readdirSync 直接 ENOENT。
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'web 7M', 'src');

globalThis.window = {HUALI_STATIC_DEMO:false, addEventListener(){}, scrollTo(){}};
globalThis.sessionStorage = {getItem:()=>null, setItem(){}, removeItem(){}};
globalThis.localStorage = globalThis.sessionStorage;
globalThis.document = {
  querySelector:()=>null, querySelectorAll:()=>[], addEventListener(){},
  createElement:()=>({appendChild(){}, classList:{add(){}, remove(){}}}),
  documentElement:{style:{setProperty(){}}}
};
globalThis.fetch = async () => ({ok:false, json:async () => ({error:'mock'})});
try{ Object.defineProperty(globalThis, 'navigator', {value:{clipboard:{writeText:async () => {}}}, configurable:true}); }catch{}
globalThis.location = {hash:'', href:'http://localhost/'};

function walk(dir){
  return fs.readdirSync(dir, {withFileTypes:true}).flatMap(entry =>
    entry.isDirectory() ? walk(path.join(dir, entry.name))
                        : (entry.name.endsWith('.js') ? [path.join(dir, entry.name)] : []));
}

const files = walk(SRC).sort();
if (!files.length){
  console.error('没找到任何模块：' + SRC);
  process.exit(1);
}

let failed = 0;
for (const file of files){
  const rel = path.relative(SRC, file).replace(/\\/g, '/');
  try{
    await import(pathToFileURL(file).href);
  }catch(err){
    failed++;
    console.error('  FAIL ' + rel + '  ->  ' + err.message);
  }
}

// 入口必须存在，否则 index.html 会 404
const entry = path.join(SRC, 'main.js');
if (!fs.existsSync(entry)){
  failed++;
  console.error('  FAIL 缺少入口 src/main.js');
}

console.log(failed
  ? '前端模块自检失败：' + failed + ' 个模块无法加载（共 ' + files.length + ' 个）'
  : '前端模块自检通过：' + files.length + ' 个模块全部可加载，依赖无环，入口存在');
process.exit(failed ? 1 : 0);
