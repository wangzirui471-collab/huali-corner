"""Worker 入口（wrangler main 指向本文件）。

真正的实现在 app/cloudflare/worker.py；这里只做一层薄壳，
让 `app` 包与 main 处于同一目录，Wrangler 才能把模块打进包。
"""
from app.cloudflare.worker import Default

__all__ = ['Default']
