"""纯Python的SSE协议与逐块思考过滤；不依赖Worker或业务数据库。"""

import codecs
import contextvars
import json
import re
from uuid import UUID

current_stream = contextvars.ContextVar("pet_ai_stream", default=None)


class ProviderError(Exception):
    """上游响应失败或未完整结束；细节只留在服务端。"""


def validate_turn(data):
    """校验新接口的有限输入，不允许客户端添加私有资料上下文。"""
    if not isinstance(data, dict) or set(data) - {
        "question",
        "history",
        "client_turn_id",
    }:
        raise ValueError("请求字段不合法")
    question = data.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 300:
        raise ValueError("问题需为1至300字")
    turn_id = data.get("client_turn_id")
    try:
        if not isinstance(turn_id, str) or str(UUID(turn_id)) != turn_id.lower():
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("client_turn_id需为UUID") from None
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > 4:
        raise ValueError("历史最多4条")
    for item in history:
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "content"}
            or item["role"] not in ("user", "assistant")
            or not isinstance(item["content"], str)
            or len(item["content"]) > 300
        ):
            raise ValueError("历史格式不合法")
    return {"question": question, "history": history, "client_turn_id": turn_id}


class ThinkFilter:
    """保留潜在标签前缀，防止跨网络块的思考正文泄漏。"""

    def __init__(self):
        """初始化标签缓冲、隐藏块与代码围栏状态。"""
        self.pending = ""
        self.hidden = False
        self.fence = False

    def feed(self, text, final=False):
        """返回当前可安全公开的正文；未闭合思考块始终丢弃。"""
        self.pending += text
        out = []
        while self.pending:
            lower = self.pending.lower()
            if self.hidden:
                marker = "```" if self.fence else "</think>"
                position = lower.find(marker)
                if position < 0:
                    self.pending = self.pending[-(len(marker) - 1) :]
                    break
                self.pending = self.pending[position + len(marker) :]
                self.hidden = False
                self.fence = False
                continue
            if lower.startswith("<think"):
                position = lower.find(">")
                if position < 0:
                    break
                self.pending = self.pending[position + 1 :]
                self.hidden = True
                continue
            marker = next(
                (
                    item
                    for item in ("```think", "```reasoning")
                    if lower.startswith(item)
                ),
                None,
            )
            if marker:
                self.pending = self.pending[len(marker) :]
                self.hidden = True
                self.fence = True
                continue
            if any(
                item.startswith(lower)
                for item in ("<think", "```think", "```reasoning")
            ):
                if final:
                    self.pending = ""
                break
            out.append(self.pending[0])
            self.pending = self.pending[1:]
        return "".join(out)


class PreviewFilter:
    """增量保留潜在提示词、JSON与编码片段，复用原完整出口判定。"""

    def __init__(self, strong, weak, checker):
        """接收原模块指纹和纯出口函数，不复制另一套业务安全词表。"""
        self.markers = tuple(strong) + tuple(weak)
        self.weak = tuple(weak)
        self.checker = checker
        self.text = ""
        self.emitted = 0
        self.sensitive_at = None
        self.blocked = False

    def feed(self, text, final=False):
        """普通正文即时放行，不能撤回的风险片段保留至完整判定。"""
        self.text += text
        if self.blocked:
            return ""
        # 原后处理会去掉Markdown标记；匹配视图亦去掉它们，防止分块插入绕过。
        positions = [
            index for index, value in enumerate(self.text) if value not in "*`"
        ]
        inspected = "".join(self.text[index] for index in positions)
        if self.checker({"answer": self.text}).get("leak_blocked") or self.checker(
            {"answer": inspected}
        ).get("leak_blocked"):
            self.blocked = True
            return ""
        cut = len(self.text)
        if not final:
            # 第一处弱指纹起暂停预览，防止第二处到来前已泄漏第一处。
            for marker in self.weak:
                position = inspected.find(marker)
                if position >= 0:
                    position = positions[position]
                    self.sensitive_at = (
                        position
                        if self.sensitive_at is None
                        else min(self.sensitive_at, position)
                    )
            if self.sensitive_at is not None:
                cut = min(cut, self.sensitive_at)
            opened = []
            for position, character in enumerate(self.text):
                if character == "{":
                    opened.append(position)
                elif character == "}" and opened:
                    opened.pop()
            if opened:
                cut = min(cut, opened[0])
            # 长编码串只有达到原400字符门槛才可判定，整段候选不能提前外发。
            encoded = re.search(r"[A-Za-z0-9+/=]+$", self.text)
            if encoded:
                cut = min(cut, encoded.start())
            for marker in self.markers:
                for size in range(1, min(len(marker), len(inspected)) + 1):
                    if inspected.endswith(marker[:size]):
                        cut = min(cut, positions[len(inspected) - size])
        value = self.text[self.emitted : cut]
        self.emitted = max(self.emitted, cut)
        return value


async def consume_sse(chunks, emit):
    """逐字节解码OpenAI兼容SSE，仅发布content，完整[DONE]后才返回。"""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    answer = []
    visible_answer = []
    total_chars = 0
    thinking = ThinkFilter()
    async for chunk in chunks:
        buffer += decoder.decode(chunk)
        buffer = buffer.replace("\r\n", "\n")
        if len(buffer) > 128 * 1024:
            raise ProviderError("供应商事件过大")
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            value = "\n".join(
                line[5:].lstrip(" ")
                for line in frame.split("\n")
                if line.startswith("data:")
            )
            if not value:
                continue
            if value == "[DONE]":
                tail = thinking.feed("", final=True)
                if tail:
                    emit(tail)
                    visible_answer.append(tail)
                if not "".join(visible_answer).strip():
                    raise ProviderError("供应商未返回公开正文")
                return "".join(answer)
            try:
                data = json.loads(value)
                if not isinstance(data, dict) or data.get("error"):
                    raise ProviderError("供应商返回错误")
                choices = data.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                content = delta.get("content") or ""
                if not isinstance(content, str):
                    raise ProviderError("供应商正文格式错误")
            except (ValueError, TypeError, AttributeError, KeyError, IndexError):
                raise ProviderError("供应商协议错误") from None
            answer.append(content)
            total_chars += len(content)
            if total_chars > 64 * 1024:
                raise ProviderError("供应商回答过大")
            visible = thinking.feed(content)
            if visible:
                emit(visible)
                visible_answer.append(visible)
    raise ProviderError("供应商流未完整结束")


def event_bytes(name, payload):
    """输出一条JSON SSE事件，禁止把换行解释为第二条协议消息。"""
    return (
        "event: " + name + "\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
    ).encode()
