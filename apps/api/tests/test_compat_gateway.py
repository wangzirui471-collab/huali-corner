"""旧 HTTP 边界的凭据隔离、超时和重定向测试。"""

import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import Request

from huali.infrastructure.legacy import LocalLegacyGateway, NoRedirect
from huali.shared.errors import ApplicationError


class GatewayTests(unittest.TestCase):
    """仅替换网络 opener，测试不访问任何真实地址。"""

    def test_timeout_is_not_retried(self) -> None:
        """不确定写入结果时只返回 502，不隐式重放付款请求。"""
        with patch("huali.infrastructure.legacy.build_opener") as factory:
            factory.return_value.open.side_effect = URLError("synthetic timeout")
            with self.assertRaises(ApplicationError) as caught:
                LocalLegacyGateway("http://127.0.0.1:8081")._request(
                    "POST",
                    "/api/order/action",
                    "synthetic",
                    {"id": 601, "action": "pay"},
                )
            self.assertEqual(caught.exception.status, 502)
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_no_arbitrary_target_or_redirect(self) -> None:
        """越过白名单前就拒绝请求，且重定向处理不会把会话带到另一地址。"""
        with patch("huali.infrastructure.legacy.build_opener") as factory:
            for path in (
                "https://external.invalid/api/me",
                "//external.invalid/api/me",
                "/api/staff/users",
            ):
                with self.assertRaises(ApplicationError):
                    LocalLegacyGateway("http://127.0.0.1:8081")._request(
                        "GET", path, "synthetic", None
                    )
            factory.assert_not_called()
        self.assertIsNone(
            NoRedirect().redirect_request(
                Request("http://127.0.0.1:8081/api/me"),
                None,
                302,
                "redirect",
                {},
                "https://external.invalid",
            )
        )

    def test_response_and_request_headers_are_bounded(self) -> None:
        """只发送本次 Bearer，响应必须是 JSON，不转发任意 Cookie、Origin 或上游头。"""
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {"Content-Type": "application/json"}
        response.read.return_value = b'{"id":7}'
        with patch("huali.infrastructure.legacy.build_opener") as factory:
            factory.return_value.open.return_value = response
            result = LocalLegacyGateway("http://127.0.0.1:8081")._request(
                "GET", "/api/me", "only-this-session", None
            )
            self.assertEqual(result.data, {"id": 7})
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:8081/api/me")
            self.assertEqual(
                request.get_header("Authorization"), "Bearer only-this-session"
            )
            self.assertIsNone(request.get_header("Cookie"))
            self.assertIsNone(request.get_header("Origin"))
            response.headers = {"Content-Type": "text/html"}
            with self.assertRaises(ApplicationError):
                LocalLegacyGateway("http://127.0.0.1:8081")._request(
                    "GET", "/api/me", "synthetic", None
                )
