"""Run against a local pywrangler dev server; no production resources."""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8787"


def fetch(path: str, method: str = "GET"):
    """请求本机隔离 Worker，统一返回状态码、内容类型和响应正文。"""
    request = Request(BASE + path, method=method)
    try:
        response = urlopen(request, timeout=90)
    except HTTPError as error:
        response = error
    with response:
        return (
            response.status,
            response.headers.get("Content-Type", ""),
            response.read(),
        )


def main():
    """依次验证本地路由、D1 回滚、R2、Cron 和旧密码向量；任一失败即停止。"""
    status, _, body = fetch("/api/health")
    assert status == 200 and json.loads(body)["ok"], (status, body)
    status, _, body = fetch("/api/probe/rollback", "POST")
    assert status == 200 and json.loads(body)["rollback_confirmed"], (status, body)
    status, _, body = fetch("/api/probe/twenty", "POST")
    assert status == 200 and json.loads(body) == {"rows": 21, "guard_parameters": 1}, (
        status,
        body,
    )
    status, _, body = fetch("/api/probe/r2")
    assert status == 200 and json.loads(body)["stored"], (status, body)
    fetch("/cdn-cgi/local/scheduled")
    fetch("/cdn-cgi/local/scheduled")
    status, _, body = fetch("/api/probe/cron")
    assert status == 200 and json.loads(body)["events"] == 1, (status, body)
    status, _, body = fetch("/api/probe/kdf")
    assert status == 200 and json.loads(body)["valid"], (status, body)
    print("KDF local elapsed_ms:", json.loads(body)["elapsed_ms"])
    for path in ("/api/missing", "/media/missing"):
        status, content_type, body = fetch(path)
        assert status == 404 and "application/json" in content_type, (
            path,
            status,
            body,
        )
    for path in ("/index.html", "/a/deep/link"):
        status, content_type, body = fetch(path)
        assert status == 200 and "text/html" in content_type, (path, status, body)
    print("Local Worker probe passed: FastAPI, D1 rollback/20 rows, R2, Cron, routing")


if __name__ == "__main__":
    main()
