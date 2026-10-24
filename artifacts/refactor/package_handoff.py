"""打包当前前后端接手增量及独立评审源码，逐项核对，不提交或修改工作区。"""

from hashlib import sha256
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parents[2]
base = 'e611c31084aae51f46b5fe94ff1802d0736eb50b'
subprocess.run(['git', 'merge-base', '--is-ancestor', base, 'HEAD'], cwd=root, check=True)
changed = set()
for arguments in (['git', 'diff', '--name-only', '-z', base], ['git', 'ls-files', '--others', '--exclude-standard', '-z']):
    changed.update(name for name in subprocess.check_output(arguments, cwd=root).decode('utf-8').split('\0') if name)
exact = {'.gitattributes', '.gitignore', 'scripts/refactor.ps1', 'tests/test_refactor_tasks.py', 'artifacts/refactor/package_handoff.py'}
assert all(name in exact or name.startswith(('apps/web/', 'apps/api/', 'contracts/', 'docs/refactor/', 'artifacts/refactor/ui-preview/')) for name in changed)
assert not subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=D', base], cwd=root).strip()

# 已构建试用包显式启用了身份/订单兼容开关，不能误称只需旧服务。
dist = root / 'apps/web/dist-trial'
assert (dist / 'index.html').is_file()
compiled = {path.relative_to(root).as_posix() for path in dist.rglob('*') if path.is_file()}

# 独立评审副本平时忽略；本次为完整交接显式附上源码/合成资源，不复制其 dist 或运行日志。
review_root = root / 'artifacts/refactor/ui-preview'
review_paths = [review_root / name for name in ('README.md', 'package.json', 'vite.config.js', 'index.html', 'jsconfig.review.json', '.prettierignore')]
for folder in ('src', 'public'):
    review_paths.extend(path for path in (review_root / folder).rglob('*') if path.is_file())
review = {path.relative_to(root).as_posix() for path in review_paths if path.is_file()}
entries = {}
files = sorted(changed | compiled | review)
for name in files:
    path = root / name
    assert path.is_file() and not path.is_symlink() and root in path.resolve().parents
    assert not any(part.startswith('.env') or part.startswith('.venv') or part in {'node_modules', '.wrangler', '__pycache__'} for part in Path(name).parts)
    assert path.suffix.lower() not in {'.db', '.sqlite', '.sqlite3', '.log'}
    entries['source/' + name] = path.read_bytes()

entries['BASE-COMMIT.txt'] = (base + '\n').encode()
entries['SOURCE-REVISION.txt'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root)
entries['CHANGED-FILES.txt'] = ('\n'.join(files) + '\n').encode('utf-8')
entries['README.md'] = '''# 华立转角前后端接手增量包（2026-10-24）

这是 e611c31084aae51f46b5fe94ff1802d0736eb50b 起点上的增量文件，不是完整仓库。
打包时的源码提交见 SOURCE-REVISION.txt；基线仅用于合并增量，不是最新交付号。
在另一台电脑另建该基线的全新干净副本，再合入 source/ 的相对路径。
不要覆盖脏工作区，不 reset/clean；不复制环境、依赖、数据库或用户媒体。

先核对 MANIFEST.sha256，再读 source/docs/refactor/AI-TAKEOVER-AND-INTEGRATION.md。
源码包括 Vue 前端候选、新 FastAPI 身份/订单 compat 与实际生成契约。
dist-trial 在构建时启用了兼容开关，真实联调需要旧隔离服务 8081 和新 API 8001。
默认生产构建仍未开放业务；新 API business_ready=false，旧服务仍是唯一 writer。

artifacts/refactor/ui-preview 是另附的只读合成界面评审源码，包含尚未应用到正式组件的方案。
它没有真实发送/交易能力，不可把其运行当作新 API 验收。
用户提到的智能客服模块在对方电脑，本包不包含该模块、模型密钥或真实模型调用结果。

本轮 API 30 项、正式前端 41 项及类型/风格/构建通过；详细证据与限制见 verification.md。
用户已授权将源码交付到 release/2026-10-trial-hotfix，推送结果须与远端 SHA 核对。
没有部署或真实数据迁移。旧 20261023 前端包不包含本轮 API 接入。
'''.encode('utf-8')
entries['MANIFEST.sha256'] = ''.join(f'{sha256(content).hexdigest()}  {name}\n' for name, content in sorted(entries.items())).encode('utf-8')
archive = root / 'artifacts/refactor/huali-refactor-handoff-20261024.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for name, content in sorted(entries.items()):
        bundle.writestr(name, content)

# 重新打开并核对 CRC、条目清单、字节与逐项 SHA256，避免交接包漏掉未提交代码。
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None and set(bundle.namelist()) == set(entries)
    for name, content in entries.items():
        assert bundle.read(name) == content
    for line in bundle.read('MANIFEST.sha256').decode('utf-8').splitlines():
        digest, name = line.split('  ', 1)
        assert sha256(bundle.read(name)).hexdigest() == digest
digest = sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
print(f'Source/doc/test: {len(changed)}, compiled: {len(compiled)}, review: {len(review)}, entries: {len(entries)}')
print(f'Bytes: {archive.stat().st_size}; CRC/content/SHA256: PASS')
print('SHA256: ' + digest)
