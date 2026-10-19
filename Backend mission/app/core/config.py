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

# 学院下拉选项：取自学校在校生信息表的「学院」列去重（2026-10 提取）。
# **只保留学院名称**；学生姓名/学号/成绩等个人信息从未进入本仓库。
# 表里同时存在少量历史名称（如「城建学院」「外国语学院」），保留是为了让
# 仍按旧称填写的学生也能选到，不代表学校最新组织关系。
COLLEGES = ['城建学院','城建与资源勘探学院','管理学院','会计学院','机电工程学院','计算机工程学院',
            '健康与护理学院','教育学院','经贸学院','商学院','体育学院','外国语学院',
            '新闻与智能传播学院','新艺术与设计学院','新影视与动画学院','药学院',
            '应用外国语学院/国际教育学院','智能制造学院']

# 年级（入学年份）选项。注册时必选其一或留空，空值不猜测。
GRADES = ['2022级','2023级','2024级','2025级','2026级']


def data_dir(trial=False):
    """试用版与演示版的数据目录互斥，绝不共用同一个库。"""
    return str(ROOT / ('var-trial' if trial else 'var'))
