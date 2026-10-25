"""仅用合成供应商片段验证流式协议，不连接模型或业务数据库。"""

import asyncio
import json
import pathlib
import sys
import unittest

SOURCE = pathlib.Path(__file__).parents[1] / "source"
sys.path.insert(0, str(SOURCE))
from pet_stream_core import ProviderError, consume_sse, current_stream, validate_turn


class StreamTests(unittest.IsolatedAsyncioTestCase):
    """覆盖真正增量、上游失败、取消与请求隔离。"""

    async def test_incremental_before_provider_finishes(self):
        """下一网络块仍未产生时第一正文块必须已经通知界面。"""
        observed = []

        async def chunks():
            """提供必须由消费端先处理上一块才能继续的合成网络流。"""
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            self.assertEqual(observed, ["first"])
            yield b'data: {"choices":[{"delta":{"reasoning_content":"SECRET","content":" next"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        result = await consume_sse(chunks(), observed.append)
        self.assertEqual(result, "first next")
        self.assertEqual(observed, ["first", " next"])

    async def test_utf8_multiline_and_think_cross_chunks(self):
        """UTF8与隐藏思考标签即使逐字节分割也不能泄漏。"""
        raw = (
            "".join(
                "data: "
                + json.dumps(
                    {"choices": [{"delta": {"content": value}}]}, ensure_ascii=False
                )
                + "\r\n\r\n"
                for value in [
                    "<thi",
                    "nk>秘密",
                    "</th",
                    "ink>你好",
                    '<think x="1">藏',
                    "</think>。",
                ]
            )
            + "data: [DONE]\r\n\r\n"
        )
        observed = []

        async def chunks():
            """模拟任意UTF8网络边界。"""
            for value in raw.encode():
                yield bytes([value])

        await consume_sse(chunks(), observed.append)
        self.assertEqual("".join(observed), "你好。")

    async def test_missing_done_and_provider_error_fail(self):
        """EOF或错误事件都不能变成成功完成。"""
        for wire in [
            b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
            b'data: {"error":{"message":"SECRET"}}\n\n',
        ]:

            async def chunks(wire=wire):
                """提供不完整或失败的供应商事件。"""
                yield wire

            with self.assertRaises(ProviderError):
                await consume_sse(chunks(), lambda text: None)

    async def test_empty_done_and_incomplete_hidden_prefix_do_not_succeed(self):
        """只有思考或空结束不能冒充成功，残缺思考标签也不能泄漏。"""
        for content in ["", "<think>private</think>", "<thi"]:
            observed = []

            async def chunks(content=content):
                """构造没有公开正文的供应商正常结束事件。"""
                yield (
                    "data: "
                    + json.dumps({"choices": [{"delta": {"content": content}}]})
                    + "\n\ndata: [DONE]\n\n"
                ).encode()

            with self.assertRaises(ProviderError):
                await consume_sse(chunks(), observed.append)
            self.assertEqual(observed, [])

    async def test_context_isolation_and_reset(self):
        """并行请求不能共享模型hook，退出后恢复无hook状态。"""

        async def one(value):
            """在线程任务上下文内设置独立hook。"""
            token = current_stream.set(value)
            try:
                await asyncio.sleep(0)
                self.assertEqual(current_stream.get(), value)
            finally:
                current_stream.reset(token)

        await asyncio.gather(one("a"), one("b"))
        self.assertIsNone(current_stream.get())

    async def test_cancel_closes_source(self):
        """取消消费必须执行网络生成器清理。"""
        closed = asyncio.Event()
        started = asyncio.Event()

        async def chunks():
            """等待取消并记录清理。"""
            try:
                started.set()
                await asyncio.Event().wait()
                yield b""
            finally:
                closed.set()

        task = asyncio.create_task(consume_sse(chunks(), lambda text: None))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(closed.is_set())

    def test_strict_request_contract(self):
        """新接口拒绝额外私有上下文、超长问题及无效轮次。"""
        base = {
            "question": "你好",
            "history": [],
            "client_turn_id": "18431369-6170-42b2-b4ca-6565b96422bd",
        }
        self.assertEqual(validate_turn(base), base)
        for extra in [
            {"question": "a" * 301},
            {"client_turn_id": "bad"},
            {"history": [{}] * 5},
            {"order_id": 1},
            {"history": [{"role": "system", "content": "x"}]},
        ]:
            with self.assertRaises(ValueError):
                validate_turn(base | extra)


if __name__ == "__main__":
    unittest.main()
