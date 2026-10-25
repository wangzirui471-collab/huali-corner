"""运行已打补丁的原ai_chat与合成Worker供应商，验证额度和完整DTO。"""

import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[4]


class FakeResponse:
    """模拟Worker JSON响应，保留真实序列化步骤。"""

    def __init__(self, value):
        """保存JSON可序列化正文。"""
        self.value = value

    @classmethod
    def from_json(cls, value, **kwargs):
        """提供原http.json_response所需的最小平台接口。"""
        return cls(value)

    async def text(self):
        """返回原完整DTO的JSON。"""
        return json.dumps(self.value, ensure_ascii=False)


class FakeReader:
    """模拟逐块网络reader，并记录取消和释放。"""

    def __init__(self, frames, block=False):
        """配置合成正文块和可控的挂起点。"""
        self.frames = list(frames)
        self.block = block
        self.started = asyncio.Event()
        self.closed = False
        self.released = False

    async def read(self):
        """每次只返回一个网络块，支持在第二块前停止。"""
        self.started.set()
        if self.block and not self.frames:
            await asyncio.Event().wait()
        if not self.frames:
            return types.SimpleNamespace(done=True)
        value = self.frames.pop(0)
        return types.SimpleNamespace(
            done=False, value=types.SimpleNamespace(to_py=lambda: value)
        )

    async def cancel(self):
        """记录上游连接被取消。"""
        self.closed = True

    def releaseLock(self):
        """记录reader资源释放。"""
        self.released = True


class FlowTests(unittest.IsolatedAsyncioTestCase):
    """使用原业务入口，而非复制一份业务规则验证成功与失败。"""

    @classmethod
    def setUpClass(cls):
        """只把线上备份复制至临时目录，不改原备份。"""
        spec = importlib.util.spec_from_file_location(
            "stage_flow", Path(__file__).parents[1] / "stage_stream.py"
        )
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        cls.temp = tempfile.TemporaryDirectory()
        stage = Path(cls.temp.name) / "stage"
        builder.build_stage(ROOT / ".local-config/live-worker-5e7bd074", stage)
        sys.path.insert(0, str(stage / "modules"))
        sys.modules["workers"] = types.SimpleNamespace(Response=FakeResponse)
        from app.cloudflare import ai_support, pet_stream_core, pet_stream_runtime

        cls.ai, cls.runtime, cls.core = ai_support, pet_stream_runtime, pet_stream_core

    @classmethod
    def tearDownClass(cls):
        """清理临时测试副本，保留真实线上备份。"""
        cls.temp.cleanup()

    async def asyncSetUp(self):
        """为每项测试创建独立会话、额度与合成供应商。"""
        self.sent = []
        self.reader = FakeReader([])
        self.charges = []
        self.quota_checks = []
        owner = self

        class Api(self.ai.AiSupport):
            """只替代平台I/O，继续运行原ai_chat和ai_answer。"""

            env = types.SimpleNamespace(
                HC_AI_API_KEY="synthetic-only", HC_AI_MODEL="original-synthetic-model"
            )
            db = None

            async def page_user(self, request):
                """提供合成已认证用户。"""
                return 73

            async def ai_enabled(self):
                """在合成环境启用AI。"""
                return True

            async def ai_quota(self, uid):
                """记录原quota入口只执行一次。"""
                owner.quota_checks.append(uid)

            async def ai_count(self, uid):
                """记录唯一原计数入口。"""
                owner.charges.append(uid)

        async def fetch(url, options):
            """确认预扣已经发生后才允许模型网络请求。"""
            self.assertEqual(owner.charges, [73])
            owner.sent.append(json.loads(options["body"]))
            return types.SimpleNamespace(
                status=200, body=types.SimpleNamespace(getReader=lambda: owner.reader)
            )

        class Abort:
            """模拟JS AbortController。"""

            signal = object()

            @classmethod
            def new(cls):
                """创建独立的取消句柄。"""
                return cls()

            def abort(self):
                """模拟平台取消，不发起任何真实网络请求。"""

        sys.modules["js"] = types.SimpleNamespace(
            AbortController=Abort,
            Object=types.SimpleNamespace(fromEntries=dict),
            fetch=fetch,
        )
        sys.modules["pyodide"] = types.ModuleType("pyodide")
        sys.modules["pyodide.ffi"] = types.SimpleNamespace(
            to_js=lambda value, **kwargs: value
        )
        self.api = Api()

    def session(self, question):
        """创建与真实端点相同的单轮session。"""
        request = self.runtime.BodyRequest(
            object(), {"question": question, "history": []}
        )
        return self.runtime.StreamSession(
            self.api, request, "18431369-6170-42b2-b4ca-6565b96422bd"
        )

    def events(self, session):
        """读取合成会话已经输出的全部事件。"""
        values = []
        while not session.queue.empty():
            value = session.queue.get_nowait()
            if value:
                name, data = value.decode().strip().split("\n", 1)
                values.append((name[7:], json.loads(data[6:])))
        return values

    async def test_rule_answer_keeps_complete_dto_without_model_or_charge(self):
        """问候继续走原规则，完整support等元数据由done返回。"""
        session = self.session("你好")
        await session.run()
        events = self.events(session)
        self.assertEqual([name for name, value in events], ["turn", "done"])
        result = events[-1][1]["result"]
        self.assertEqual(result["mode"], "rule")
        self.assertIn("support", result)
        self.assertEqual(self.charges, [])
        self.assertEqual(self.sent, [])
        self.assertEqual(self.quota_checks, [73])
        self.assertIsNone(self.core.current_stream.get())

    async def test_model_once_and_original_postprocessing_dto(self):
        """原模型配置和提示词不变，增量被原后处理修正并仅扣一次。"""
        self.reader.frames = [
            b'data: {"choices":[{"delta":{"content":"<think>hidden</think>hello **world**"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
        session = self.session("宇宙起源有哪些科学假说")
        await session.run()
        events = self.events(session)
        self.assertEqual([name for name, value in events], ["turn", "delta", "done"])
        self.assertEqual(events[1][1]["text"], "hello **world**")
        self.assertEqual(events[-1][1]["result"]["answer"], "hello world")
        self.assertEqual(events[-1][1]["result"]["mode"], "llm")
        self.assertEqual(self.sent[0]["model"], "original-synthetic-model")
        self.assertIs(self.sent[0]["stream"], True)
        self.assertEqual(self.charges, [73])
        self.assertEqual(self.quota_checks, [73])
        self.assertTrue(self.reader.closed and self.reader.released)

    async def test_eof_failure_cannot_be_old_fallback_done(self):
        """即使原业务捕获模型异常并摘录，流仍必须失败且不退预扣额度。"""
        self.reader.frames = [
            b'data: {"choices":[{"delta":{"content":"partial "}}]}\n\n'
        ]
        session = self.session("宇宙起源有哪些科学假说")
        await session.run()
        events = self.events(session)
        self.assertEqual([name for name, value in events], ["turn", "delta", "error"])
        self.assertEqual(events[-1][1]["code"], "AI_STREAM_FAILED")
        self.assertEqual(self.charges, [73])

    async def test_cancel_aborts_model_and_keeps_reserved_charge(self):
        """停止时reader和任务均取消，不发done也不因停止绕额度。"""
        self.reader.block = True
        session = self.session("宇宙起源有哪些科学假说")
        session.task = asyncio.create_task(session.run())
        await self.reader.started.wait()
        await session.cancel()
        self.assertTrue(session.task.cancelled())
        self.assertTrue(self.reader.closed and self.reader.released)
        self.assertEqual(self.charges, [73])
        self.assertNotIn("done", [name for name, value in self.events(session)])

    async def test_old_json_chat_keeps_nonstream_payload_and_original_count(self):
        """没有局部hook的旧JSON入口继续原非流供应商调用与事后计数。"""
        payloads = []

        async def fetch(url, **options):
            """在原非流网络边界提供完整合成JSON。"""
            self.assertEqual(self.charges, [])
            payloads.append(json.loads(options["body"]))
            response = FakeResponse(
                {"choices": [{"message": {"content": "旧入口完整回答"}}]}
            )
            response.status = 200
            return response

        sys.modules["workers"].fetch = fetch
        request = self.runtime.BodyRequest(
            object(), {"question": "宇宙起源有哪些科学假说", "history": []}
        )
        response = await self.api.ai_chat(request)
        result = json.loads(await response.text())
        self.assertEqual(result["answer"], "旧入口完整回答")
        self.assertIs(payloads[0]["stream"], False)
        self.assertEqual(self.charges, [73])
        self.assertEqual(self.quota_checks, [73])
        self.assertIsNone(self.core.current_stream.get())

    async def test_prompt_fingerprint_cannot_leak_through_preview(self):
        """跨块提示词指纹由原出口拦截前，预览同样不能发给浏览器。"""
        for pieces in [
            ["【参", "考资料】PRIVATE PROMPT"],
            ["【参**", "考资料】PRIVATE PROMPT"],
            ["先给结论再解释", "PRIVATE PROMPT", "聊天框不渲染"],
            ["先给**结论**再解释", "PRIVATE PROMPT", "聊天框不渲染"],
            ["A" * 200, "A" * 200],
        ]:
            self.charges.clear()
            self.reader.frames = [
                (
                    "data: "
                    + json.dumps({"choices": [{"delta": {"content": part}}]})
                    + "\n\n"
                ).encode()
                for part in pieces
            ] + [b"data: [DONE]\n\n"]
            session = self.session("宇宙起源有哪些科学假说")
            await session.run()
            events = self.events(session)
            self.assertEqual([name for name, value in events], ["turn", "done"])
            self.assertTrue(events[-1][1]["result"]["leak_blocked"])
            self.assertEqual(self.charges, [73])


if __name__ == "__main__":
    unittest.main()
