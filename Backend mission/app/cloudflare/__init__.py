"""Cloudflare Workers 运行时适配层。

这一层只解决"同一个业务在 Workers 上怎么落地"，不放业务规则：

    d1.py     异步 D1 访问与 batch 事务原语
    crypto.py 异步 PBKDF2（Web Crypto），与旧库格式兼容
    media.py  R2 私有对象存储，复用既有图片校验

业务规则仍然留在 account/ catalog/ trade/ 等领域包里。
旧入口 server.py（ThreadingHTTPServer）与 core/database.py（同步 sqlite3/MySQL）
不在此层改造范围内，它们在 Workers 上无法运行，原因见 d1.py 顶部说明。
"""
