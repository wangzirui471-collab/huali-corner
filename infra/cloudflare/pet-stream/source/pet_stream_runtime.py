"""新增流端点的Worker适配；原业务调度与DTO由原ai_chat保有。"""

import asyncio
import json

from .pet_stream_core import (
    PreviewFilter,
    ProviderError,
    consume_sse,
    current_stream,
    event_bytes,
    validate_turn,
)


class BodyRequest:
    """保留原请求身份，只把已验证的新端点正文交回旧入口。"""

    def __init__(self, request, data):
        """复制原请求引用，正文不含任何新增私有上下文。"""
        self.request = request
        self.data = data

    def __getattr__(self, name):
        """把headers、url等身份信息交给原请求读取。"""
        return getattr(self.request, name)

    async def text(self):
        """提供可重复读取且已校验的JSON正文。"""
        return json.dumps(self.data, ensure_ascii=False)


class StreamSession:
    """单请求生命周期；hook、取消句柄与额度均不跨请求共享。"""

    def __init__(self, api, request, turn_id):
        """创建当前请求的事件队列与取消状态。"""
        self.api = api
        self.request = request
        self.turn_id = turn_id
        self.queue = asyncio.Queue(maxsize=512)
        self.charge = None
        self.charged = False
        self.failed = False
        self.cancelled = False
        self.abort = None
        self.reader = None
        self.task = None
        self.proxies = []
        self.preview = None

    def release_proxies(self):
        """在回调返回后销毁FFI代理，防止长驻Worker累积每轮闭包。"""
        for proxy in self.proxies:
            proxy.destroy()
        self.proxies.clear()

    def set_charge(self, callback, uid):
        """由原ai_chat在原quota检查后登记唯一计数入口。"""
        self.charge = callback
        self.charge_uid = uid

    def emit(self, name, value):
        """入队一个协议事件；慢消费者超过缓冲上限则安全失败。"""
        if not self.cancelled:
            self.queue.put_nowait(event_bytes(name, value))

    def delta(self, text):
        """把已经过滤思考内容的增量正文发给浏览器。"""
        visible = self.preview.feed(text)
        if visible:
            self.emit("delta", {"text": visible})

    async def model(self, question, context, env, history=None, open_mode=False):
        """使用原供应商配置和提示词进行一次真实流调用，不自动重试。"""
        try:
            from js import AbortController, Object, fetch
            from pyodide.ffi import to_js

            from .ai_support import (
                LEAK_STRONG,
                LEAK_WEAK,
                OPEN_PROMPT,
                SYSTEM_PROMPT,
                guard_leak,
            )

            if not self.charged:
                if self.charge is None:
                    raise ProviderError("缺少原业务额度入口")
                # 模型调用开始前占用原额度；停止和未知上游结果均不退回，防止绕额。
                await self.charge(self.charge_uid)
                self.charged = True
            key = getattr(env, "HC_AI_API_KEY", "") or ""
            if not key:
                raise ProviderError("供应商未配置")
            template, temperature, cap = (
                (OPEN_PROMPT, 0.7, 1000) if open_mode else (SYSTEM_PROMPT, 0.2, 600)
            )
            payload = {
                "model": getattr(env, "HC_AI_MODEL", "deepseek-flash"),
                "messages": [
                    {
                        "role": "system",
                        "content": template.format(
                            context=context or "（无）", query=question
                        ),
                    },
                    *[
                        item
                        for item in (history or [])
                        if item.get("role") in ("user", "assistant")
                        and item.get("content")
                    ],
                    {"role": "user", "content": question},
                ],
                "stream": True,
                "temperature": temperature,
                "max_tokens": cap,
            }
            self.abort = AbortController.new()
            options = to_js(
                {
                    "method": "POST",
                    "headers": {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + key,
                    },
                    "body": json.dumps(payload, ensure_ascii=False),
                    "signal": self.abort.signal,
                },
                dict_converter=Object.fromEntries,
            )
            response = await fetch(
                getattr(
                    env, "HC_AI_API_URL", "https://api.deepseek.com/chat/completions"
                ),
                options,
            )
            if response.status != 200 or response.body is None:
                raise ProviderError("供应商HTTP失败")
            self.reader = response.body.getReader()
            self.preview = PreviewFilter(LEAK_STRONG, LEAK_WEAK, guard_leak)
            answer = await consume_sse(self.network_chunks(), self.delta)
            visible = self.preview.feed("", final=True)
            if visible:
                self.emit("delta", {"text": visible})
            return answer
        except Exception:
            # 旧ai_answer会降级摘录，但此流不能把未知或失败的供应商结果报done。
            self.failed = True
            raise
        finally:
            await self.close_upstream()

    async def network_chunks(self):
        """逐块读取JS Reader，不把供应商完整正文缓存后再模拟打字。"""
        while True:
            item = await self.reader.read()
            if item.done:
                return
            yield bytes(item.value.to_py())

    async def close_upstream(self):
        """终止供应商请求并释放reader锁，适用于成功、失败与取消。"""
        if self.abort is not None:
            self.abort.abort()
            self.abort = None
        if self.reader is not None:
            reader, self.reader = self.reader, None
            try:
                await reader.cancel()
            except Exception:  # noqa: BLE001, S110 - 断连后的FFI取消失败不覆盖原终态。
                pass
            finally:
                reader.releaseLock()

    async def run(self):
        """在局部上下文调用原完整业务入口，最终DTO原样放入done。"""
        token = current_stream.set(self)
        try:
            self.emit("turn", {"client_turn_id": self.turn_id})
            async with asyncio.timeout(65):
                response = await self.api.ai_chat(self.request)
                if self.failed:
                    raise ProviderError("供应商流失败")
                result = json.loads(await response.text())
                self.emit("done", {"client_turn_id": self.turn_id, "result": result})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - HTTP流边界统一输出脱敏错误。
            status = getattr(exc, "status", 502)
            code, message = {
                401: ("UNAUTHENTICATED", "请先登录"),
                403: ("FORBIDDEN", "当前账号无权使用此功能"),
                429: ("RATE_LIMITED", "提问过快或今日次数已用完，请稍后再试"),
                503: ("AI_UNAVAILABLE", "AI暂时不可用，请转人工客服"),
            }.get(status, ("AI_STREAM_FAILED", "回答未完成，请稍后再试或转人工客服"))
            if not self.cancelled:
                # 队列满时丢弃剩余增量，以确保能发出明确的终态失败。
                while self.queue.full():
                    self.queue.get_nowait()
                self.emit("error", {"code": code, "message": message})
        finally:
            current_stream.reset(token)
            await self.close_upstream()
            if not self.cancelled:
                await self.queue.put(None)

    async def cancel(self, reason=None):
        """浏览器断连时立即取消模型与原业务任务，禁止补发完成事件。"""
        self.cancelled = True
        if self.abort is not None:
            self.abort.abort()
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.close_upstream()
        asyncio.get_running_loop().call_soon(self.release_proxies)


async def stream_chat(api, request):
    """验证原登录身份和输入后返回ReadableStream；其他接口继续原入口。"""
    from js import Object, ReadableStream, Uint8Array
    from pyodide.ffi import create_proxy, to_js
    from workers import Response

    from .http import ApiError, json_body, require

    await api.page_user(request)
    require(await api.ai_enabled(), "AI 客服已关闭，请转人工客服", 503)
    try:
        data = validate_turn(await json_body(request))
    except ValueError as exc:
        raise ApiError(str(exc), 400) from None
    session = StreamSession(api, BodyRequest(request, data), data["client_turn_id"])

    def start(controller):
        """创建独立上下文任务；不等待模型完成即返回HTTP响应。"""
        session.task = asyncio.create_task(session.run())

    async def pull(controller):
        """按照浏览器读取速率逐事件输出，终态后关闭流。"""
        value = await session.queue.get()
        if value is None:
            controller.close()
            asyncio.get_running_loop().call_soon(session.release_proxies)
        else:
            controller.enqueue(Uint8Array.new(to_js(value)))

    callbacks = [create_proxy(start), create_proxy(pull), create_proxy(session.cancel)]
    session.proxies = callbacks
    stream = ReadableStream.new(
        to_js(
            dict(zip(("start", "pull", "cancel"), callbacks)),
            dict_converter=Object.fromEntries,
        )
    )
    return Response(
        stream,
        headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-store, no-transform",
            "X-Content-Type-Options": "nosniff",
        },
    )
