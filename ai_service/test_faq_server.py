"""用合成资料验证内部 FAQ HTTP 边界；阻断所有供应商网络调用。"""

import http.client
import json
import sys
import threading
import unittest
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import faq_server


class FaqServerTests(unittest.TestCase):
    """验证服务认证、受控上下文、供应商失败和无工具调用合同。"""

    @classmethod
    def setUpClass(cls):
        """只启动随机回环端口，不连接旧业务服务或模型供应商。"""
        cls.server = faq_server.create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        """停止本测试拥有的服务器并释放回环端口。"""
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        """配置合成服务令牌和 mock 模式，任何意外外网调用立即失败。"""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
            ("TOKEN", "test-service-token"),
            ("PROVIDER", "mock"),
            ("API_KEY", ""),
            ("MOCK", False),
        ):
            self.stack.enter_context(patch.object(faq_server.config, name, value))
        self.stack.enter_context(
            patch.object(
                urllib.request.OpenerDirector,
                "open",
                side_effect=AssertionError("测试禁止供应商网络"),
            )
        )

    def request(self, body=None, token="test-service-token", path="/faq/answer"):
        """发送真实回环 HTTP，返回状态码和 JSON；只使用合成输入。"""
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        self.addCleanup(connection.close)
        payload = json.dumps(
            body
            or {"question": "怎样付款", "context": "全部资金为模拟，不产生真实扣款。"},
            ensure_ascii=False,
        )
        connection.request(
            "POST",
            path,
            body=payload.encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_mock_uses_supplied_context_without_index_or_provider(self):
        """mock 只摘录传入的公开资料，不读取旧索引或调用模型。"""
        with patch.object(
            faq_server.rag, "load_index", side_effect=AssertionError("禁止索引")
        ):
            status, data = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(set(data), {"answer_text", "mode"})
        self.assertIn("全部资金为模拟", data["answer_text"])
        self.assertEqual(data["mode"], "mock")

    def test_missing_service_configuration_is_unavailable(self):
        """没有配置内部服务令牌时关闭入口，不能变成匿名模型代理。"""
        with patch.object(faq_server.config, "TOKEN", ""):
            self.assertEqual(self.request()[0], 503)

    def test_incorrect_service_token_is_unauthorized(self):
        """原业务 Bearer 或任意其他令牌都不等于内部服务认证。"""
        self.assertEqual(self.request(token="untrusted-user-token")[0], 401)

    def test_extra_fields_and_invalid_lengths_are_rejected(self):
        """拒绝历史、身份、自报令牌、非字符串和超长字段。"""
        valid = {"question": "怎样付款", "context": "仅模拟支付。"}
        bodies = [
            dict(valid, **{key: "forbidden"}) for key in ("history", "user_id", "token")
        ]
        bodies += [
            dict(valid, question=" "),
            dict(valid, question="问" * 801),
            dict(valid, context="文" * 12001),
            dict(valid, question=123),
            dict(valid, context=""),
            {"question": "问"},
            ["question", "context"],
        ]
        for body in bodies:
            with self.subTest(body_type=type(body).__name__):
                self.assertEqual(self.request(body)[0], 422)

    def test_only_faq_endpoint_is_exposed(self):
        """旧 chat、reply、reload 和商品工具不能从该入口使用。"""
        for path in ("/chat", "/reply", "/reload", "/health"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0], 404)

    def test_no_api_key_falls_back_to_mock(self):
        """默认 api 配置没有密钥时使用摘录，不发起付费调用。"""
        with patch.object(faq_server.config, "PROVIDER", "api"):
            self.assertEqual(self.request()[1]["mode"], "mock")

    def test_api_reuses_existing_provider_once(self):
        """仅调用已有 provider 一次并裁剪推理标记，不伪造来源。"""
        with (
            patch.object(faq_server.config, "PROVIDER", "api"),
            patch.object(faq_server.config, "API_KEY", "synthetic-key"),
            patch.object(
                faq_server.rag,
                "call_api",
                return_value="<think>内部推理</think>仅模拟付款。",
            ) as provider,
        ):
            status, data = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(data, {"answer_text": "仅模拟付款。", "mode": "llm"})
        provider.assert_called_once_with("怎样付款", "全部资金为模拟，不产生真实扣款。")

    def test_model_failure_is_502_without_retry(self):
        """供应商失败保留错误状态，交给前端保留原问题和人工入口。"""
        with (
            patch.object(faq_server.config, "PROVIDER", "api"),
            patch.object(faq_server.config, "API_KEY", "synthetic-key"),
            patch.object(
                faq_server.rag, "call_api", side_effect=TimeoutError("synthetic")
            ) as provider,
        ):
            status, data = self.request()
        self.assertEqual(status, 502)
        self.assertNotIn("answer_text", data)
        provider.assert_called_once()

    def test_unsupported_provider_is_rejected(self):
        """当前只批准 mock/api；不能悄悄启用其他模型或后端工具。"""
        with patch.object(faq_server.config, "PROVIDER", "ollama"):
            self.assertEqual(self.request()[0], 503)


if __name__ == "__main__":
    unittest.main()
