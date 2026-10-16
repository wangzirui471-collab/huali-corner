"""Build a clean layered source package, never a copy of runtime account data."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXTENSIONS={'.py','.js','.mjs','.css','.html','.json','.svg','.png','.jpg','.jpeg','.webp','.wxml','.wxss','.md','.txt','.yaml','.bat'}
FORBIDDEN={'var','var-trial','uploads','backups','node_modules','__pycache__','.git','.codex','.agents','attachments','artifacts'}
DIRECTORIES=('Backend mission','web 7M','scripts','tests','docs')

def sources():
    files=[ROOT/name for name in ['README.md','AGENTS.md','start-trial.bat','start-trial-8081.bat']]
    for directory in DIRECTORIES:
        for path in (ROOT/directory).rglob('*'):
            relative=path.relative_to(ROOT)
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS:continue
            if FORBIDDEN.intersection(relative.parts) or path.name.startswith('.') or '.private.' in path.name:continue
            files.append(path)
    return sorted(set(files))

def build(output):
    output=Path(output)
    if output.exists():raise FileExistsError('请选择尚不存在的输出文件，避免覆盖旧交付包')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        revision=subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):revision='source-package'
    entries={path.relative_to(ROOT).as_posix():path.read_bytes() for path in sources()}
    manifest={'base_revision':revision,'format':'layered-source','simulation':True,
              'note':'源码包不含账号、数据库、上传或备份。金额和付款均为模拟。',
              'sha256':{name:hashlib.sha256(content).hexdigest() for name,content in entries.items()}}
    entries['package-manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(entries.items()):archive.writestr('zhuanjiao-trial/'+name,content)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(build(args.output))
