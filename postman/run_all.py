"""一键跑完「转角」的三套 Postman 集合。

以前这些是打开 Postman 一个一个点的，现在一条命令搞定：

    python postman/run_all.py

它会自己做四件事，跑完自己收尾：
    1. 起 AI 客服服务（8094，本地摘录模式，不联网不花钱）
    2. 起后端（8095，试用模式 + 临时数据目录 + 不灌演示数据）
    3. 用 Newman 依次跑：主站全接口 → AI 客服 → FAQ 数据驱动
    4. 汇总成 postman/运行报告.md，然后关掉刚才起的两个服务

所有数据都写在系统临时目录里，不碰你平时用的 8081 / 8093，也不碰 var-trial/。

常用参数：
    --keep          跑完别关服务，留着手动调（会打印端口给你）
    --only api      只跑主站集合（可选 api / ai / faq，可写多个）
    --api-port N    后端端口，默认 8095
    --ai-port N     AI 服务端口，默认 8094
    --newman CMD    手动指定 newman 命令（找不到时用它）

退出码：全绿 0，有失败 1，服务没起来 2。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent          # 仓库根
POSTMAN = ROOT / 'postman'
AI = ROOT / 'ai_service'
BACKEND = ROOT / 'Backend mission' / 'server.py'
REPORT = POSTMAN / '运行报告.md'

COLLECTIONS = {
    'api': ('转角主站-全接口.postman_collection.json', '主站全接口（130 请求）'),
    'ai': ('转角AI客服.postman_collection.json', 'AI 客服（14 请求）'),
    'faq': ('转角AI客服-数据驱动回归.postman_collection.json', 'FAQ 数据驱动（11 行 CSV）'),
}

ADMIN_PHONE = '19065322759'
ADMIN_PASSWORD = 'Postman#2026'


def step(msg):
    print('\n' + '=' * 60)
    print(msg)
    print('=' * 60, flush=True)


def find_newman(override=''):
    """找 newman：PATH → WorkBuddy 自带那份 → npx 临时拉一个。"""
    if override:
        return override.split()
    exe = shutil.which('newman')
    if exe:
        return [exe]
    bundled = (Path.home() / '.workbuddy' / 'binaries' / 'node' / 'workspace'
               / 'node_modules' / 'newman' / 'bin' / 'newman.js')
    if bundled.exists() and shutil.which('node'):
        print('  PATH 里没有 newman，用 WorkBuddy 自带那份')
        return [shutil.which('node'), str(bundled)]
    print('  没找到 newman，改用 npx 临时下载（第一次会慢一点）')
    return ['npx', '-y', 'newman@6']


def wait_health(url, seconds=60):
    """轮询探活，超过 seconds 秒算失败。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if 200 <= r.status < 300:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true', help='跑完不关服务')
    ap.add_argument('--only', nargs='*', default=['api', 'ai', 'faq'],
                    choices=['api', 'ai', 'faq'])
    ap.add_argument('--api-port', type=int, default=8095)
    ap.add_argument('--ai-port', type=int, default=8094)
    ap.add_argument('--newman', default='')
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='huali-postman-'))
    data = tmp / 'data'
    data.mkdir(parents=True, exist_ok=True)
    api_url = 'http://127.0.0.1:%d' % args.api_port
    ai_url = 'http://127.0.0.1:%d' % args.ai_port
    procs = []

    step('0/4  临时目录：%s' % tmp)

    # 后端要 Pillow（app/account/avatars.py 处理头像要用）。
    # 系统 python 常常没装，项目虚拟环境里装了，这里提前说清楚，
    # 免得起不来的时候只看到一行 ModuleNotFoundError。
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('  警告：当前 python 没装 Pillow，后端可能起不来。')
        print('        Windows 上改用："%s\\.venv-trial\\Scripts\\python.exe" %s'
              % (ROOT, __file__))

    try:
        step('1/4  起 AI 客服服务（%d，本地摘录模式）' % args.ai_port)
        ai_env = dict(os.environ,
                      HC_AI_INDEX=str(tmp / 'ai-index.json'),
                      HC_AI_PORT=str(args.ai_port),
                      HC_AI_MOCK='1')
        # index.json 在 .gitignore 里，先按知识库现造一份（关键词检索，不要 Ollama）
        subprocess.run([sys.executable, 'ingest.py'], cwd=str(AI), env=ai_env, check=False)
        procs.append(subprocess.Popen([sys.executable, 'server.py'],
                                      cwd=str(AI), env=ai_env))

        step('2/4  起后端（%d，试用模式 + 临时数据目录）' % args.api_port)
        api_env = dict(os.environ,
                       HUALI_ADMIN_PHONE=ADMIN_PHONE,
                       HUALI_ADMIN_PASSWORD=ADMIN_PASSWORD,
                       HC_AI_URL=ai_url)
        procs.append(subprocess.Popen(
            [sys.executable, str(BACKEND), '--trial', '--no-seed',
             '--port', str(args.api_port), '--data', str(data)],
            cwd=str(BACKEND.parent), env=api_env))

        step('3/4  等两个服务就绪（最多 60 秒）')
        ok_api = wait_health(api_url + '/api/health')
        ok_ai = wait_health(ai_url + '/health')
        print('  后端：%s   AI 服务：%s' % ('起来了' if ok_api else '没起来',
                                            '起来了' if ok_ai else '没起来'))
        if not (ok_api and ok_ai):
            print('服务没起来，退出。看看上面的日志（AI 日志在控制台里）。')
            return 2

        step('4/4  跑集合（Newman）')
        newman = find_newman(args.newman)
        xmls, titles = [], []
        codes = []          # 每套集合的退出码，用来决定脚本最终退出码
        for key in args.only:
            name, title = COLLECTIONS[key]
            xml = tmp / ('newman-%s.xml' % key)
            cmd = newman + ['run', str(POSTMAN / name),
                            '--timeout-request', '30000',
                            '-r', 'cli,junit',
                            '--reporter-junit-export', str(xml)]
            if key == 'api':
                cmd += ['--env-var', 'baseUrl=' + api_url,
                        '--env-var', 'adminPhone=' + ADMIN_PHONE,
                        '--env-var', 'adminPassword=' + ADMIN_PASSWORD]
            else:
                cmd += ['-e', str(POSTMAN / '转角-本地8093.postman_environment.json'),
                        '--env-var', 'baseUrl=' + ai_url]
            if key == 'faq':
                cmd += ['-d', str(POSTMAN / 'faq-cases.csv')]
            print('\n>>> %s' % title)
            codes.append(subprocess.run(cmd, cwd=str(ROOT), check=False).returncode)
            xmls.append(str(xml))
            titles.append(title)

        step('汇总报告')
        subprocess.run([sys.executable, str(POSTMAN / 'tools' / 'report.py')]
                       + xmls + ['-o', str(REPORT), '--title'] + titles,
                       cwd=str(ROOT), check=False)
        print('\n报告：%s' % REPORT)
        # 全绿才是 0。挂了就返回 1，这样 CI / 调用方只看退出码就知道结果。
        return 0 if all(c == 0 for c in codes) else 1

    finally:
        if args.keep:
            print('\n--keep：服务留着没关，后端 %s / AI %s，用完自己结束进程。'
                  % (api_url, ai_url))
        else:
            for p in procs:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
            print('\n临时服务已关闭。junit 原始结果留在：%s' % tmp)


if __name__ == '__main__':
    sys.exit(main())
