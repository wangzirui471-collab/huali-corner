"""Python Worker 入口。

网页和 /api 同源：静态资源由 Workers Assets 直接返回，只有 /api/* 和 /media/*
会进到这里（见 wrangler.jsonc 的 run_worker_first）。
"""
from workers import WorkerEntrypoint

from .api import Api
from .http import guard


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        api = Api(self.env)
        # guard 负责把 DomainError 翻成状态码、把未知异常兜成 500（不外泄堆栈）。
        return await guard(lambda: api.dispatch(request))
