/** 检查 Vue 生产构建保留原公开样式、图片和办公/宠物静态包，不泄露项目配置。 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../web 7M');
const dist = path.join(root, 'dist');

/** 递归列出公开文件，排除新增的 Node 包作用域声明。 */
function walk(dir) {
  return fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const file = path.join(dir, entry.name);
    if (entry.name === 'package.json') return [];
    return entry.isDirectory() ? walk(file) : [file];
  });
}

const files = [
  ...walk(path.join(root, 'assets')),
  ...walk(path.join(root, 'miniprogram')),
  ...fs.readdirSync(root).filter(name => name.endsWith('.css')).map(name => path.join(root, name)),
  path.join(root, 'src/components/product-moderation.css'),
];
for (const file of files) {
  const relative = path.relative(root, file);
  assert.ok(fs.existsSync(path.join(dist, relative)), '构建遗漏 ' + relative);
  assert.ok(fs.readFileSync(file).equals(fs.readFileSync(path.join(dist, relative))), '原资源字节改变 ' + relative);
}
for (const file of ['package.json', 'package-lock.json', 'vite.config.js', 'node_modules', 'src/main.js', 'miniprogram/package.json']) {
  assert.ok(!fs.existsSync(path.join(dist, file)), '构建混入配置或未编译入口 ' + file);
}
const source = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const built = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
assert.deepEqual(built.match(/<link\b[^>]*rel="stylesheet"[^>]*>/g), source.match(/<link\b[^>]*rel="stylesheet"[^>]*>/g), '样式链接加载顺序变化');
console.log(JSON.stringify({ok: true, staticFiles: files.length, unchangedBytes: true, stylesheetOrderPreserved: true, projectConfigExcluded: true}));
