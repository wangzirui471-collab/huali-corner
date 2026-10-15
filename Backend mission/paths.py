"""项目路径的统一出口。

后端被收进 `Backend mission/` 之后，就再也不能用 `Path(__file__).parent` 直接定位
前端、文档和数据目录了 —— 那样会去找 `Backend mission/web 7M/`，而它并不存在。
所有路径在这里算一次，其余模块从这里取。

根目录的判定：如果本文件所在目录的上一级存在 `web 7M`，说明是正常的项目结构，
根目录取上一级；否则退回本文件所在目录 —— 这样把后端单独拷出去部署时也不会崩。
"""
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent if (HERE.parent / 'web 7M').is_dir() else HERE

WEB = ROOT / 'web 7M' if (ROOT / 'web 7M').is_dir() else HERE / 'web'
DOCS = ROOT / 'docs' if (ROOT / 'docs').is_dir() else HERE / 'docs'
ASSETS = WEB / 'assets'

COLLEGES_JSON = DOCS / 'research/guangzhou-college-options.json'


def data_dir(trial=False):
    """试用版与演示版的数据目录互斥，绝不共用同一个库。"""
    return str(ROOT / ('var-trial' if trial else 'var'))
