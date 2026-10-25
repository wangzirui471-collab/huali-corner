"""保留线上Worker和scheduled入口，只增加独立流路径。"""

from urllib.parse import urlsplit

from app.cloudflare.api import Api
from app.cloudflare.http import guard
from app.cloudflare.pet_stream_runtime import stream_chat
from app.cloudflare.worker import Default as OriginalDefault


class Default(OriginalDefault):
    """除新增聊天流之外全部委托原线上入口。"""

    async def fetch(self, request):
        """匹配严格的POST新路径，其他方法和所有旧路径沿用原实现。"""
        if (
            request.method == "POST"
            and urlsplit(request.url).path == "/api/ai/chat/stream"
        ):
            return await guard(lambda: stream_chat(Api(self.env), request))
        return await super().fetch(request)
