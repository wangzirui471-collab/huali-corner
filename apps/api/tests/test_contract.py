"""新 HTTP 契约的成功、输入错误、未知错误与环境隔离测试。"""

import unittest

from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from huali.bootstrap import create_app
from huali.shared.errors import ApplicationError, FieldError
from huali.shared.settings import Settings


class ContractTests(unittest.TestCase):
    """使用合成端点检查协议边界；这些测试路由不会进入实际应用。"""

    def setUp(self) -> None:
        """每个测试建立独立应用，避免路由或状态在用例之间泄漏。"""
        self.app = create_app(Settings(environment="test"))
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_health_and_request_id(self) -> None:
        """健康检查带统一封套和安全头，用户不能指定服务端请求编号。"""
        response = self.client.get("/api/v1/health", headers={"X-Request-ID": "fake"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["business_ready"], False)
        self.assertEqual(body["data"]["environment"], "test")
        self.assertEqual(body["meta"], {"schema_version": "v1", "simulation": True})
        self.assertEqual(response.headers["X-Request-ID"], body["request_id"])
        self.assertNotEqual(body["request_id"], "fake")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_api_and_media_misses_are_json(self) -> None:
        """API 与媒体未知路径返回 JSON 404，不会返回前端 HTML。"""
        for path in ("/api/missing", "/api/v1/missing", "/media/missing"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "NOT_FOUND")

    def test_validation_does_not_echo_credentials(self) -> None:
        """字段校验失败仅暴露路径和安全文案，不回显输入中的凭据。"""

        class Input(BaseModel):
            """仅用于触发校验失败的合成请求模型。"""

            password: int

        @self.app.post("/synthetic/input")
        async def endpoint(data: Input) -> None:
            """测试路由无业务写入，只触发 FastAPI 输入校验。"""

        response = self.client.post(
            "/synthetic/input", json={"password": "secret-value"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("secret-value", response.text)
        self.assertEqual(response.json()["error"]["fields"][0]["path"], "body.password")

    def test_application_error_keeps_stable_code(self) -> None:
        """业务失败保留稳定机器码及字段位置，供各客户端统一处理。"""

        @self.app.get("/synthetic/conflict")
        async def endpoint() -> None:
            """模拟商品版本冲突，不执行数据库操作。"""
            raise ApplicationError(
                "VERSION_CONFLICT",
                "商品已变化",
                fields=(FieldError("product_id", "请刷新"),),
            )

        response = self.client.get("/synthetic/conflict")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(response.json()["error"]["fields"][0]["message"], "请刷新")

    def test_unknown_error_is_private_and_has_request_id(self) -> None:
        """未知异常不会泄漏 SQL 或敏感值，500 响应仍能按编号排查。"""

        @self.app.get("/synthetic/failure")
        async def endpoint(request: Request) -> None:
            """制造带敏感内容的异常，验证边界会隐藏该内容。"""
            raise RuntimeError("SELECT secret-password FROM credentials")

        response = self.client.get("/synthetic/failure")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret-password", response.text)
        self.assertEqual(
            response.headers["X-Request-ID"], response.json()["request_id"]
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_http_error_preserves_retry_after(self) -> None:
        """限流等协议错误保留 Retry-After，避免客户端立即重复请求。"""

        @self.app.get("/synthetic/limited")
        async def endpoint() -> None:
            """模拟协议层限流，仅用于响应头兼容测试。"""
            raise HTTPException(429, headers={"Retry-After": "30"})

        self.assertEqual(
            self.client.get("/synthetic/limited").headers["Retry-After"], "30"
        )

    def test_configuration_requires_explicit_environment(self) -> None:
        """缺失或错误配置不能静默启动为演示环境；生产关闭交互文档。"""
        for values in ({}, {"HUALI_ENV": "prodution"}):
            with self.assertRaises(ValueError):
                Settings.from_environment(values)
        self.assertEqual(
            Settings.from_environment({"HUALI_ENV": "local"}).environment, "local"
        )
        production = create_app(Settings(environment="production"))
        with TestClient(production) as client:
            self.assertEqual(client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
