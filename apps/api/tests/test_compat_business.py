"""登录及订单兼容入口的权限、单一写入口与失败语义测试。"""

import unittest

from fastapi.testclient import TestClient
from pydantic import JsonValue

from huali.bootstrap import create_app
from huali.modules.compat.ports import LegacyResponse
from huali.shared.settings import Settings


class FakeGateway:
    """记录调用并返回合成旧 DTO，不接触数据库、网络或真实账号。"""

    def __init__(self) -> None:
        """每个测试独立记录调用，便于证明没有自动重放写操作。"""
        self.calls: list[tuple[str, str, str, dict[str, JsonValue] | None]] = []
        self.response = LegacyResponse(200, {"ok": True})

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, JsonValue] | None = None,
    ) -> LegacyResponse:
        """返回预设合成结果，保存传给原 writer 的完整参数用于核对。"""
        self.calls.append((method, path, token, body))
        return self.response


class CompatBusinessTests(unittest.TestCase):
    """未配置真实依赖时不得默默写演示库，也不得返回占位成功。"""

    def test_login_requires_explicit_upstream(self) -> None:
        """登录路由存在，但未配置唯一旧服务时明确返回不可用。"""
        with TestClient(create_app(Settings(environment="test"))) as client:
            response = client.post(
                "/api/v1/compat/auth/login",
                json={
                    "phone": "synthetic@example.invalid",
                    "password": "synthetic-only",
                },
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "LEGACY_NOT_CONFIGURED")

    def test_orders_require_bearer(self) -> None:
        """订单入口必须先验证存在 Bearer 会话，不接受页面自报用户编号。"""
        with TestClient(create_app(Settings(environment="test"))) as client:
            response = client.get("/api/v1/compat/orders")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "UNAUTHENTICATED")

    def test_login_and_kdf_do_not_change_credentials(self) -> None:
        """口令或摘要二选一原样进入旧登录；轮数和盐也不被新边界降低。"""
        gateway = FakeGateway()
        gateway.response = LegacyResponse(
            200, {"token": "synthetic-token", "user": {"id": 7}}
        )
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            for credentials in ({"password": "synthetic-secret"}, {"digest": "a" * 64}):
                response = client.post(
                    "/api/v1/compat/auth/login",
                    json={"phone": "synthetic@example.invalid", **credentials},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["data"]["user"]["id"], 7)
                self.assertEqual(
                    gateway.calls[-1][3],
                    {"phone": "synthetic@example.invalid", **credentials},
                )
            gateway.response = LegacyResponse(
                200, {"salt": "ab" * 16, "rounds": 600000}
            )
            response = client.get(
                "/api/v1/compat/auth/salt?phone=synthetic%40example.invalid"
            )
            self.assertEqual(response.json()["data"]["rounds"], 600000)
            self.assertEqual(
                gateway.calls[-1][1], "/api/auth/salt?phone=synthetic%40example.invalid"
            )

    def test_invalid_inputs_never_call_writer(self) -> None:
        """拒绝多套凭据、bool 编号、重复商品及自报身份/金额，不泄露原口令。"""
        gateway = FakeGateway()
        checkout = {
            "product_ids": [11],
            "key": "original-key",
            "delivery": "pickup",
            "appointment": 1900000000,
        }
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            response = client.post(
                "/api/v1/compat/auth/login",
                json={
                    "phone": "synthetic",
                    "password": "private-value",
                    "digest": "a" * 64,
                },
            )
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private-value", response.text)
            for change in (
                {"product_ids": [True]},
                {"product_ids": [11, 11]},
                {"total": 1},
                {"user_id": 8},
                {"appointment": True},
            ):
                response = client.post(
                    "/api/v1/compat/checkout",
                    headers={"Authorization": "Bearer synthetic"},
                    json={**checkout, **change},
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(gateway.calls, [])

    def test_checkout_passes_original_key_once(self) -> None:
        """下单仍是原 writer 的一次调用，头与正文请求键冲突时不写入。"""
        gateway = FakeGateway()
        gateway.response = LegacyResponse(200, {"id": 601, "total": 1800})
        body = {
            "product_ids": [11],
            "key": "original-key",
            "delivery": "pickup",
            "appointment": 1900000000,
        }
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            response = client.post(
                "/api/v1/compat/checkout",
                headers={
                    "Authorization": "Bearer buyer",
                    "Idempotency-Key": "other-key",
                },
                json=body,
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(gateway.calls, [])
            response = client.post(
                "/api/v1/compat/checkout",
                headers={
                    "Authorization": "Bearer buyer",
                    "Idempotency-Key": "original-key",
                },
                json=body,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["total"], 1800)
            self.assertEqual(
                gateway.calls,
                [("POST", "/api/checkout", "buyer", {**body, "address": ""})],
            )

    def test_identity_and_order_commands_keep_original_authorization(self) -> None:
        """身份、列表、详情和订单动作均携带原会话，不接受另一套 actor 来源。"""
        gateway = FakeGateway()
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            headers = {"Authorization": "Bearer original-session"}
            gateway.response = LegacyResponse(200, [{"id": 601, "total": 1800}])
            self.assertEqual(
                client.get("/api/v1/compat/orders", headers=headers).json()["data"][0][
                    "id"
                ],
                601,
            )
            gateway.response = LegacyResponse(200, {"id": 601})
            for path in ("/me", "/order?id=601"):
                self.assertEqual(
                    client.get("/api/v1/compat" + path, headers=headers).status_code,
                    200,
                )
            for path, body in (
                ("/auth/logout", {}),
                ("/order/action", {"id": 601, "action": "pay"}),
                ("/order/update", {"id": 601, "appointment": 1900000000}),
                ("/order/change", {"id": 4, "accept": True}),
            ):
                self.assertEqual(
                    client.post(
                        "/api/v1/compat" + path, headers=headers, json=body
                    ).status_code,
                    200,
                )
            self.assertTrue(
                all(call[2] == "original-session" for call in gateway.calls)
            )
            gateway.response = LegacyResponse(403, {"error": "private SQL detail"})
            response = client.post(
                "/api/v1/compat/order/action",
                headers=headers,
                json={"id": 601, "action": "receive"},
            )
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("private SQL detail", response.text)

    def test_upstream_failure_does_not_retry_or_revoke_session(self) -> None:
        """上游故障保持 5xx 和原键；真正的 401 与 429 分别映射，不混淆。"""
        gateway = FakeGateway()
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            headers = {"Authorization": "Bearer synthetic"}
            gateway.response = LegacyResponse(500, {"error": "private SQL"})
            response = client.post(
                "/api/v1/compat/order/action",
                headers=headers,
                json={"id": 601, "action": "pay"},
            )
            self.assertEqual(response.status_code, 502)
            self.assertEqual(len(gateway.calls), 1)
            self.assertNotIn("private SQL", response.text)
            gateway.response = LegacyResponse(429, {}, "30")
            self.assertEqual(
                client.get("/api/v1/compat/me", headers=headers).headers["Retry-After"],
                "30",
            )
            gateway.response = LegacyResponse(401, {})
            self.assertEqual(
                client.get("/api/v1/compat/me", headers=headers).status_code, 401
            )
            gateway.response = LegacyResponse(200, [])
            self.assertEqual(
                client.get("/api/v1/compat/me", headers=headers).status_code, 502
            )

    def test_origin_and_route_allowlist(self) -> None:
        """跨站请求和未登记的管理操作不能利用兼容层获得服务端代理能力。"""
        gateway = FakeGateway()
        with TestClient(
            create_app(Settings(environment="test"), legacy_gateway=gateway)
        ) as client:
            response = client.get(
                "/api/v1/compat/orders",
                headers={
                    "Authorization": "Bearer synthetic",
                    "Origin": "https://evil.invalid",
                },
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(client.get("/api/v1/compat/staff/users").status_code, 404)
        self.assertEqual(gateway.calls, [])

    def test_settings_reject_remote_and_production_upstream(self) -> None:
        """本轮仅启用本机隔离兼容，不允许配置成真实远程业务或带账号 URL。"""
        for origin in (
            "http://evil.invalid:8081",
            "http://user:secret@127.0.0.1:8081",
            "http://127.0.0.1:8081/private",
            "http://127.0.0.1:8001",
        ):
            with self.assertRaises(ValueError):
                Settings(environment="test", legacy_origin=origin)
        with self.assertRaises(ValueError):
            Settings(environment="production", legacy_origin="http://127.0.0.1:8081")
        self.assertEqual(
            Settings.from_environment(
                {"HUALI_ENV": "test", "HUALI_LEGACY_ORIGIN": "http://127.0.0.1:8081"}
            ).legacy_origin,
            "http://127.0.0.1:8081",
        )


if __name__ == "__main__":
    unittest.main()
