"""Start the local trial with a suitable interpreter and optional offline wheels."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / 'repair-wheels'
PROBE = '''import sys, json, struct
from importlib.metadata import version, PackageNotFoundError
packages = {}
for distribution, module in [('Pillow', 'PIL.Image'), ('PyMySQL', 'pymysql')]:
    try:
        __import__(module)
        packages[distribution] = version(distribution)
    except (ImportError, PackageNotFoundError, OSError):
        packages[distribution] = None
print(json.dumps(dict(executable=sys.executable, version=list(sys.version_info[:2]),
                     bits=struct.calcsize('P')*8, platform=sys.platform, packages=packages)))
'''


@dataclass
class Runtime:
    executable: str
    version: tuple
    bits: int
    platform: str
    packages: dict

    @property
    def ready(self):
        return (self.version >= (3, 10)
                and self.packages.get('Pillow') == '12.3.0'
                and self.packages.get('PyMySQL') == '1.2.3')


def probe_runtime(executable):
    try:
        result = subprocess.run([str(executable), '-c', PROBE], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=15)
        if result.returncode:
            return None
        data = json.loads(result.stdout)
        return Runtime(data['executable'], tuple(data['version']), data['bits'],
                       data['platform'], data['packages'])
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return None


def launcher_paths(output):
    for line in output.splitlines():
        match = re.search(r'([A-Za-z]:\\.*python\.exe)\s*$', line, re.I)
        if match:
            yield Path(match.group(1))


def candidates():
    paths = [ROOT/'.venv-trial/Scripts/python.exe', ROOT/'.venv/Scripts/python.exe',
             ROOT/'Backend mission/.venv/Scripts/python.exe', Path(sys.executable)]
    paths.extend(Path(path) for name in ('python', 'python3')
                 if (path := shutil.which(name)) and 'WindowsApps' not in path)
    if sys.platform == 'win32':
        launcher = shutil.which('py.exe')
        if launcher:
            try:
                result = subprocess.run([launcher, '-0p'], capture_output=True, text=True,
                                        encoding='utf-8', errors='replace', timeout=10)
                paths.extend(launcher_paths(result.stdout))
            except (OSError, subprocess.TimeoutExpired):
                pass
        roots = []
        if os.environ.get('LOCALAPPDATA'):
            roots.append(Path(os.environ['LOCALAPPDATA'])/'Programs/Python')
        if os.environ.get('ProgramFiles'):
            roots.append(Path(os.environ['ProgramFiles']))
        for root in roots:
            paths.extend(sorted(root.glob('Python3*/python.exe'), reverse=True))
    seen = set()
    for path in paths:
        key = os.path.normcase(str(path.resolve()))
        if path.is_file() and key not in seen:
            seen.add(key)
            yield path


def find_ready_runtime(executables):
    for executable in executables:
        runtime = probe_runtime(executable)
        if runtime and runtime.ready:
            return runtime
    return None


def verify_wheelhouse(directory):
    manifest = json.loads((directory/'SHA256SUMS.json').read_text(encoding='utf-8'))
    files = {path.name for path in directory.glob('*.whl')}
    if not files or files != set(manifest):
        raise ValueError('Offline wheel manifest does not match the files')
    for filename, expected in manifest.items():
        if Path(filename).name != filename or '/' in filename or '\\' in filename:
            raise ValueError('Invalid offline wheel name')
        actual = hashlib.sha256((directory/filename).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Offline wheel checksum failed: ' + filename)


def install_offline(executables):
    if not WHEELS.is_dir():
        raise ValueError('Missing repair-wheels folder. Extract the full local startup repair package.')
    verify_wheelhouse(WHEELS)
    runtime = None
    for executable in executables:
        candidate = probe_runtime(executable)
        if candidate and candidate.platform == 'win32' and candidate.bits == 64:
            tag = 'cp%d%d-' % candidate.version
            if list(WHEELS.glob('pillow-12.3.0-' + tag + '*-win_amd64.whl')):
                runtime = candidate
                break
    if not runtime:
        raise ValueError('Offline repair needs an installed 64-bit Python 3.12 or 3.13.')
    managed = ROOT/'.venv-trial'
    target = managed/'Scripts/python.exe'
    if not target.exists():
        subprocess.run([runtime.executable, '-m', 'venv', str(managed)], check=True)
    target_runtime = probe_runtime(target)
    if not target_runtime or not list(WHEELS.glob(
            'pillow-12.3.0-cp%d%d-*-win_amd64.whl' % target_runtime.version)):
        raise ValueError('Existing .venv-trial uses an unsupported Python; it was left unchanged.')
    env = dict(os.environ, PIP_CONFIG_FILE=os.devnull)
    subprocess.run([str(target), '-m', 'pip', '--isolated', '--disable-pip-version-check',
                    'install', '--no-index', '--no-deps', '--find-links', str(WHEELS),
                    '-r', str(ROOT/'Backend mission/requirements.txt')], env=env, check=True)
    result = probe_runtime(target)
    if not result or not result.ready:
        raise ValueError('The offline environment failed the dependency check.')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check only; do not install or start')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--data', help='Optional existing or isolated trial data directory')
    args = parser.parse_args(argv)
    # 统一解析为长路径：Windows 8.3 短名（如 ADMINI~1）下，若 command 用短名而
    # 子进程把 __file__ resolve 成长名，server.py 的 cwd 自检断言会失败、
    # 启动器表现为"启动即退出"。command 与 cwd 必须同构。
    server = (ROOT/'Backend mission/server.py').resolve()
    if not server.is_file():
        print('[ERROR] Put this launcher and scripts folder in the project root.')
        return 1
    available = list(candidates())
    runtime = find_ready_runtime(available)
    if not runtime and args.check:
        print('[ERROR] No interpreter has the required Pillow and PyMySQL versions.')
        return 1
    try:
        if not runtime:
            print('Preparing an isolated .venv-trial from verified offline packages...', flush=True)
            runtime = install_offline(available)
        print('Python: ' + runtime.executable, flush=True)
        print('Dependencies ready: Pillow 12.3.0, PyMySQL 1.2.3', flush=True)
        if args.check:
            return 0
        command = [runtime.executable, str(server), '--trial', '--port', str(args.port), '--lan']
        if args.data:
            command.extend(['--data', str(Path(args.data).resolve())])
        print('Starting local trial on port %d. Keep this window open.' % args.port, flush=True)
        print('Existing trial data location is preserved. Stop with Ctrl+C.', flush=True)
        return subprocess.call(command, cwd=str(server.parent))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('[ERROR] ' + str(error))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
