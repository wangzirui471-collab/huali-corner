"""Isolated local Worker probe; never bind this to production resources."""

import base64
import hashlib
import io
import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image
from PIL import __version__ as pillow_version
from workers import asgi

from huali.infrastructure.images.normalize import (
    AVATAR_POLICY,
    PRODUCT_POLICY,
    normalize_image,
)
from huali.shared.errors import ApplicationError
from kdf_probe import derive

app = FastAPI()


class Default(asgi.entrypoint(app)):
    async def scheduled(self, controller, env, ctx):
        """重复执行本地定时探针时只保存一个事件，使用入口绑定 self.env。"""
        await self.env.DB.prepare(
            "INSERT OR IGNORE INTO probe_jobs(job_key,run_count) VALUES('cron-probe',1)"
        ).run()


@app.get("/api/health")
async def health(request: Request):
    """验证 FastAPI 可从请求上下文取得 D1 binding 并完成查询。"""
    env = request.scope["env"]
    row = await env.DB.prepare("SELECT 1 AS ok").first()
    return {"ok": row.ok == 1}


@app.post("/api/probe/rollback")
async def probe_rollback(request: Request):
    """故意让第二条语句违反 CHECK，确认第一条写入也在同批回滚。"""
    env = request.scope["env"]
    marker = "rollback-local-probe"
    await env.DB.prepare("DELETE FROM probe_atomic WHERE id=?").bind(marker).run()
    try:
        await env.DB.batch(
            [
                env.DB.prepare(
                    "INSERT INTO probe_atomic(id,marker,ok) VALUES(?,?,1)"
                ).bind(marker, "first"),
                env.DB.prepare(
                    "INSERT INTO probe_atomic(id,marker,ok) VALUES(?,?,0)"
                ).bind(marker + "-invalid", "second"),
            ]
        )
    except Exception as error:
        # 只有刻意制造的 CHECK 失败才算回滚证据，其他故障必须让探针失败。
        if "CHECK constraint failed" not in str(error):
            raise
        row = (
            await env.DB.prepare(
                "SELECT COUNT(*) AS count FROM probe_atomic WHERE id=?"
            )
            .bind(marker)
            .first()
        )
        return {"rollback_confirmed": row.count == 0}
    return JSONResponse({"rollback_confirmed": False}, status_code=500)


@app.get("/api/probe/r2")
async def probe_r2(request: Request):
    """向本地隔离桶写入合成文本，再读取以确认 R2 binding 可用。"""
    env = request.scope["env"]
    key = "local-probe/hello.txt"
    await env.MEDIA.put(key, b"local probe")
    obj = await env.MEDIA.get(key)
    return {"stored": obj is not None}


@app.get("/api/probe/cron")
async def probe_cron(request: Request):
    """返回本地 Cron 合成事件数，供外部脚本判断重复触发是否幂等。"""
    row = (
        await request.scope["env"]
        .DB.prepare(
            "SELECT COUNT(*) AS count FROM probe_jobs WHERE job_key='cron-probe'"
        )
        .first()
    )
    return {"events": row.count}


@app.get("/api/probe/kdf")
async def probe_kdf():
    """校验旧密码合成向量并返回算法墙钟耗时，不代表云端 CPU 预算。"""
    salt = "00112233445566778899aabbccddeeff"
    started = time.perf_counter()
    digest = derive("synthetic-test-password", salt)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "valid": digest
        == "5b5c8a087776399595ba97c7777b44876a6e11e68ca3205cfbcac349c6ba2ce1",
        "elapsed_ms": elapsed_ms,
        "stdlib_pbkdf2_available": hasattr(hashlib, "pbkdf2_hmac"),
    }


@app.post("/api/probe/twenty")
async def probe_twenty(request: Request):
    """使用一个 JSON 参数核对 20 行 batch，验证 JSON1 及原子断言路线。"""
    env = request.scope["env"]
    ids = list(range(20))
    await env.DB.prepare("DELETE FROM probe_atomic WHERE marker='twenty'").run()
    statements = [
        env.DB.prepare("INSERT INTO probe_atomic(id,marker,ok) VALUES(?,?,1)").bind(
            f"twenty-{number}", "twenty"
        )
        for number in ids
    ]
    statements.append(
        env.DB.prepare(
            "INSERT INTO probe_atomic(id,marker,ok) "
            "SELECT 'twenty-assert', 'twenty', "
            "CASE WHEN (SELECT COUNT(*) FROM probe_atomic WHERE marker='twenty')=20 "
            "AND json_array_length(?1)=20 THEN 1 ELSE 0 END"
        ).bind(json.dumps(ids))
    )
    await env.DB.batch(statements)
    row = await env.DB.prepare(
        "SELECT COUNT(*) AS count FROM probe_atomic WHERE marker='twenty'"
    ).first()
    return {"rows": row.count, "guard_parameters": 1}


@app.get("/api/{path:path}")
async def api_not_found(path: str):
    """未知 API 返回 JSON 404，避免被前端单页路由回退覆盖。"""
    return JSONResponse({"error": "NOT_FOUND"}, status_code=404)


@app.post("/api/probe/image")
async def probe_image(request: Request):
    """用实际图片适配器校验合成输入，重编码后核对本地 R2 字节与元数据。

    只验证图片计算与对象存取，不把此无身份的探针当作媒体授权接口。
    """
    data = await request.json()
    try:
        raw = base64.b64decode(data["content"], validate=True)
    except (ValueError, TypeError, KeyError):
        return JSONResponse({"code": "INVALID_IMAGE"}, status_code=422)
    policy = AVATAR_POLICY if data.get("kind") == "avatar" else PRODUCT_POLICY
    started = time.perf_counter()
    try:
        result = normalize_image(raw, policy)
    except ApplicationError as error:
        return JSONResponse({"code": error.code}, status_code=error.status)
    key = "local-probe/images/" + result.digest + ".webp"
    bucket = request.scope["env"].MEDIA
    await bucket.put(key, result.payload)
    stored = await bucket.get(key)
    buffer = await stored.arrayBuffer()
    restored = bytes(buffer.to_py()) if hasattr(buffer, "to_py") else bytes(buffer)
    with Image.open(io.BytesIO(restored)) as decoded:
        return {
            "format": decoded.format,
            "width": result.width,
            "height": result.height,
            "exif_entries": len(decoded.getexif()),
            "r2_round_trip": restored == result.payload,
            "output_bytes": len(restored),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "pillow_version": pillow_version,
        }


@app.get("/media/{path:path}")
async def media_not_found(path: str):
    """未知媒体返回 JSON 404，避免错误地返回首页 HTML。"""
    return JSONResponse({"error": "NOT_FOUND"}, status_code=404)
