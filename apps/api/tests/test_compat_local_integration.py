"""真实本机 HTTP 适配与全新合成 SQLite 的登录、订单链路测试。"""

import importlib.util
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from huali.bootstrap import create_app
from huali.shared.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


class LocalCompatibilityTests(unittest.TestCase):
    """只启动临时回环端口与全新数据目录，不读取现有数据库或管理员凭据。"""

    def test_login_checkout_and_both_parties(self) -> None:
        """经 FastAPI 和真实旧 HTTP writer 验证登录、下单重放、越权、交付和退出。"""
        artifact_root = ROOT / "artifacts/refactor"
        artifact_root.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory(
                prefix="compat-integration-", dir=artifact_root
            ) as directory,
            patch.dict(os.environ, {"HC_DB": ""}),
        ):
            # 只把旧模块导入测试进程；新应用运行时仍通过显式端口连接，不依赖 Market。
            sys.path.insert(0, str(ROOT / "Backend mission"))
            try:
                spec = importlib.util.spec_from_file_location(
                    "compat_legacy_server", ROOT / "Backend mission/server.py"
                )
                assert spec is not None and spec.loader is not None
                legacy = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(legacy)
            finally:
                sys.path.pop(0)
            server = legacy.make_server(directory, port=0, trial=True, host="127.0.0.1")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                market = server.market
                buyer = market.register_password(
                    "buyer@example.invalid", "Synthetic-Only-321", "合成买家"
                )["user"]["id"]
                seller = market.register_password(
                    "seller@example.invalid", "Synthetic-Only-321", "合成卖家"
                )["user"]["id"]
                market.register_password(
                    "other@example.invalid", "Synthetic-Only-321", "合成旁观者"
                )
                photos = []
                for angle, color in zip(
                    ("front", "side", "top"), ("red", "green", "blue"), strict=True
                ):
                    buffer = io.BytesIO()
                    Image.new("RGB", (100, 100), color).save(buffer, "PNG")
                    photos.append(
                        market.add_upload(seller, buffer.getvalue(), angle)["id"]
                    )
                product = market.publish(
                    seller,
                    dict(
                        title="合成教材",
                        category="books",
                        price=1800,
                        original_price=5000,
                        delivery_fee=0,
                        delivery="pickup",
                        region="合成公共地点",
                        description="仅供本机合成测试",
                        photos=photos,
                        college="计算机工程学院",
                        edition="第七版",
                        publisher="合成出版社",
                        condition="有少量笔记",
                        notes="少量",
                        missing="无缺页",
                        accessories="无附件",
                        bought="2026-01",
                    ),
                )["id"]
                settings = Settings(
                    environment="test",
                    legacy_origin=f"http://127.0.0.1:{server.server_port}",
                )
                with TestClient(create_app(settings)) as client:
                    tokens = {}
                    for account in ("buyer", "seller", "other"):
                        response = client.post(
                            "/api/v1/compat/auth/login",
                            json={
                                "phone": account + "@example.invalid",
                                "password": "Synthetic-Only-321",
                            },
                        )
                        self.assertEqual(
                            response.status_code, 200, response.json().get("code")
                        )
                        tokens[account] = {
                            "Authorization": "Bearer "
                            + response.json()["data"]["token"]
                        }
                    self.assertEqual(
                        client.get("/api/v1/compat/me", headers=tokens["buyer"]).json()[
                            "data"
                        ]["id"],
                        buyer,
                    )
                    payload = {
                        "product_ids": [product],
                        "key": "synthetic-checkout-original",
                        "delivery": "pickup",
                        "appointment": time.time() + 7200,
                        "address": "",
                    }
                    response = client.post(
                        "/api/v1/compat/checkout", headers=tokens["buyer"], json=payload
                    )
                    self.assertEqual(
                        response.status_code, 200, response.json().get("code")
                    )
                    order_id = response.json()["data"]["id"]
                    repeated = client.post(
                        "/api/v1/compat/checkout", headers=tokens["buyer"], json=payload
                    )
                    self.assertEqual(repeated.json()["data"]["id"], order_id)
                    self.assertEqual(
                        len(
                            client.get(
                                "/api/v1/compat/orders", headers=tokens["buyer"]
                            ).json()["data"]
                        ),
                        1,
                    )
                    self.assertEqual(
                        client.get(
                            f"/api/v1/compat/order?id={order_id}",
                            headers=tokens["other"],
                        ).status_code,
                        403,
                    )
                    for actor, action in (
                        ("buyer", "pay"),
                        ("seller", "confirm_schedule"),
                        ("seller", "deliver"),
                        ("buyer", "handover"),
                        ("buyer", "receive"),
                    ):
                        response = client.post(
                            "/api/v1/compat/order/action",
                            headers=tokens[actor],
                            json={"id": order_id, "action": action},
                        )
                        self.assertEqual(
                            response.status_code,
                            200,
                            (action, response.json().get("code")),
                        )
                    detail = client.get(
                        f"/api/v1/compat/order?id={order_id}", headers=tokens["buyer"]
                    ).json()["data"]
                    self.assertEqual(detail["status"], "completed")
                    self.assertEqual(detail["total"], 1800)
                    self.assertEqual(
                        client.post(
                            "/api/v1/compat/auth/logout",
                            headers=tokens["buyer"],
                            json={},
                        ).status_code,
                        200,
                    )
                    self.assertEqual(
                        client.get(
                            "/api/v1/compat/me", headers=tokens["buyer"]
                        ).status_code,
                        401,
                    )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
