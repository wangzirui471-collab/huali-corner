"""项目路径的唯一出口。

**改这个文件前请先读完整段。**这个项目历史上两次出现「后端启动了但页面全部 404」，
根因都是路径算错。

背景：后端在 `Backend mission/`，前端在 `web 7M/`，数据在项目根的 `var/` 与 `var-trial/`。
Python 里 `Path(__file__).parent` 给出的是**本文件所在目录**，不是项目根，直接拼路径会
去找不存在的 `Backend mission/web 7M/`、`Backend mission/var-trial/`。

本文件自身位于 `Backend mission/app/core/config.py`，所以：
    HERE    = Backend mission/app/core
    BACKEND = Backend mission          （上两级）
    ROOT    = 项目根                    （BACKEND 的上一级，若其中存在 web 7M）
             否则退回 BACKEND —— 后端被单独拷出去部署时走这个分支

所有路径在这里算一次，其余模块一律从这里取，不要再自己拼 `__file__`。
"""
from pathlib import Path

# 必须 resolve()：__file__ 可能是相对路径（例如 sys.path 里塞的是 '.'），
# 那样 HERE 会变成 'app/core' 这种相对路径，向上两级找不到项目根。
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
ROOT = BACKEND.parent if (BACKEND.parent / 'web 7M').is_dir() else BACKEND

WEB = ROOT / 'web 7M' if (ROOT / 'web 7M').is_dir() else BACKEND / 'web'
DOCS = ROOT / 'docs' if (ROOT / 'docs').is_dir() else BACKEND / 'docs'
ASSETS = WEB / 'assets'

COLLEGES_JSON = DOCS / 'research/guangzhou-college-options.json'


def data_dir(trial=False):
    """试用版与演示版的数据目录互斥，绝不共用同一个库。"""
    return str(ROOT / ('var-trial' if trial else 'var'))
