"""将已验证的正式 Pillow Wasm wheel 安装到独立发布目录，不覆盖已有依赖。"""
import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / 'Backend mission').resolve()
DESTINATION = BACKEND / 'python_modules'
TAG = 'cp314-cp314-pyemscripten_2026_0_wasm32'


def require(condition, message):
    """无论 Python 是否开启优化，都执行发布制品校验。"""
    if not condition:
        raise ValueError(message)


def main():
    """先完整核验版本、哈希、路径及 Wasm 标头，再原子落到固定依赖目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--proof', required=True, type=Path)
    parser.add_argument('--check-only', action='store_true')
    options = parser.parse_args()
    proof = json.loads(options.proof.read_text(encoding='utf-8'))
    lock = json.loads((BACKEND / 'worker-pillow.lock.json').read_text(encoding='utf-8'))
    require(lock['sha256'] == proof['sha256'] and lock['abi'] == TAG, '制品与本次发布锁文件不一致')
    require(proof['version'] == '12.3.0', '正式 Pillow 制品校验失败')
    require(all(proof.get(key) is True for key in ('exif', 'bad_image_rejected', 'pixel_limit')), '正式 Pillow 制品校验失败')
    require(set(proof['formats']) == {'JPEG', 'PNG', 'WEBP'}, '正式 Pillow 制品校验失败')
    require(options.wheel.name == proof['wheel'] == 'pillow-12.3.0-' + TAG + '.whl', '正式 Pillow 制品校验失败')
    require(hashlib.sha256(options.wheel.read_bytes()).hexdigest() == proof['sha256'], '正式 Pillow 制品校验失败')
    with zipfile.ZipFile(options.wheel) as archive:
        require(archive.testzip() is None, '正式 Pillow 制品校验失败')
        require(sum(item.file_size for item in archive.infolist()) < 100 * 1024 * 1024, '正式 Pillow 制品校验失败')
        files = []
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            require(not name.is_absolute() and '..' not in name.parts and '\\' not in item.filename, '正式 Pillow 制品校验失败')
            require(name.parts[0] in {'PIL', 'pillow-12.3.0.dist-info', 'pillow.libs'}, '正式 Pillow 制品校验失败')
            require(not stat.S_ISLNK(item.external_attr >> 16), '正式 Pillow 制品校验失败')
            if item.is_dir():
                continue
            require(name.suffix.lower() not in {'.dll', '.pyd', '.dylib'}, '正式 Pillow 制品校验失败')
            if name.suffix == '.so':
                require(archive.read(item)[:4] == b'\0asm', item.filename)
            files.append(item)
        metadata = Parser().parsestr(archive.read('pillow-12.3.0.dist-info/METADATA').decode())
        require(metadata['Version'] == '12.3.0', '正式 Pillow 制品校验失败')
        wheel = Parser().parsestr(archive.read('pillow-12.3.0.dist-info/WHEEL').decode())
        require(TAG in wheel.get_all('Tag', []), '正式 Pillow 制品校验失败')
        require(DESTINATION.resolve().parent == BACKEND and BACKEND.is_relative_to(ROOT.resolve()), '正式 Pillow 制品校验失败')
        if not options.check_only:
            # 绝不覆盖原项目可能存在的 12.2.0 目录；只操作独立发布目录的新路径。
            require(not DESTINATION.exists(), '依赖目录已存在，请使用干净的独立发布目录')
            with tempfile.TemporaryDirectory(prefix='.pillow-verified-', dir=BACKEND) as temporary:
                staging = Path(temporary).resolve()
                require(staging.parent == BACKEND, '正式 Pillow 制品校验失败')
                for item in files:
                    target = staging / item.filename
                    require(target.resolve().is_relative_to(staging), '正式 Pillow 制品校验失败')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(item))
                (staging / 'huali-pillow-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
                staging.replace(DESTINATION)
    print(json.dumps({'version': proof['version'], 'sha256': proof['sha256'],
                      'checked': True, 'installed': not options.check_only}, ensure_ascii=False))


if __name__ == '__main__':
    main()
