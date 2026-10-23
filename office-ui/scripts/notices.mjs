/** 将构建使用的生产依赖许可随静态资源交付；不复制依赖源码或开发工具。 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
const notices = ['华立转角办公面板 · 开源依赖许可', '由 npm 锁文件生成，仅收录生产依赖。'];
for (const [relative, entry] of Object.entries(lock.packages)){
  if (!relative || entry.dev) continue;
  const directory = path.join(root, relative);
  const metadata = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
  const license = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENSE-MIT', 'license', 'license.md']
    .find(name => fs.existsSync(path.join(directory, name)));
  notices.push(`\n${metadata.name} ${metadata.version} · ${metadata.license || '见上游许可'}`);
  if (license) notices.push(fs.readFileSync(path.join(directory, license), 'utf8'));
  else notices.push(metadata.repository ? JSON.stringify(metadata.repository) : '请参阅 npm 包元数据中的上游项目。');
}
fs.writeFileSync(path.join(root, '../web 7M/assets/office/THIRD-PARTY-NOTICES.txt'), notices.join('\n'), 'utf8');
