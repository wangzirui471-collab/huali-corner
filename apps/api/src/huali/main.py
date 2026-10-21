"""本地 ASGI 入口：先显式设置 HUALI_ENV，再用 uvicorn 加载。"""

import os

from huali.bootstrap import create_app
from huali.shared.settings import Settings

app = create_app(Settings.from_environment(os.environ))
