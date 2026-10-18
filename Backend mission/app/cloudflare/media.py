"""R2 媒体层。

与旧实现的关系
--------------
旧代码把图片写在本地 `var/uploads/`，通过 `Path` 读文件。Workers 没有持久化文件系统，
对象存储换成 R2，但**图片校验规则完全复用** `account/avatars.py` 的
`user_normalize_avatar()`：它已经是纯函数（bytes 进、bytes 出），不碰数据库和磁盘。

即：格式白名单（JPEG/PNG/WebP）、像素上限、拒绝动画/多帧、EXIF 方向纠正、
重编码成 WebP 去元数据 —— 一条都不放宽。

权限
----
桶必须保持私有。不要把 `r2.dev` 公开访问打开，也不要返回对象直链。
读取一律走带鉴权的路由（`/media/<key>`），由服务端校验归属后再从 R2 取。

键的命名
--------
    media/<prefix>/<owner_id>/<sha256 前 32 位>.webp

用内容摘要命名有两个好处：同一张图重复上传不产生多份对象；键里带 owner_id，
鉴权时可以先按前缀做归属判断，不必先取对象。
"""
import hashlib

from ..core.errors import DomainError

__all__ = ['MediaStore']

CONTENT_TYPE = 'image/webp'


class MediaStore:
    def __init__(self, binding):
        if binding is None:
            raise RuntimeError('R2 binding MEDIA is missing')
        self._bucket = binding

    @staticmethod
    def normalize(content):
        """复用既有校验与重编码，返回干净 WebP 字节。"""
        # 延迟导入：avatars 模块顶层引用了 sqlite3/pathlib，放到函数内更安全。
        from ..account.avatars import user_normalize_avatar

        return user_normalize_avatar(content)

    @staticmethod
    def key_for(prefix, owner_id, payload):
        digest = hashlib.sha256(payload).hexdigest()[:32]
        if not prefix or '/' in prefix:
            raise ValueError('prefix must be a single path segment')
        return f'media/{prefix}/{int(owner_id)}/{digest}.webp'

    async def put_image(self, content, prefix, owner_id):
        """校验 -> 重编码 -> 写入 R2。返回键，不返回任何 URL。"""
        payload = self.normalize(content)
        key = self.key_for(prefix, owner_id, payload)
        written = await self._bucket.put(key, payload, {
            'httpMetadata': {'contentType': CONTENT_TYPE},
            # 私有对象：不允许浏览器/CDN 当公开资源缓存。
            'customMetadata': {'owner': str(int(owner_id)), 'scope': prefix},
        })
        if written is None:
            raise DomainError('图片保存失败，请稍后重试', 503)
        return {'key': key, 'bytes': len(payload), 'digest': hashlib.sha256(payload).hexdigest()}

    async def read(self, key):
        """取对象正文。调用方必须先完成归属鉴权。"""
        if not key.startswith('media/'):
            raise DomainError('资源不存在', 404)
        stored = await self._bucket.get(key)
        if stored is None:
            raise DomainError('资源不存在', 404)
        body = await stored.arrayBuffer()
        raw = bytes(body.to_py()) if hasattr(body, 'to_py') else bytes(body)
        return raw, CONTENT_TYPE

    async def delete(self, key):
        if not key.startswith('media/'):
            raise ValueError('refusing to delete outside media/ prefix')
        await self._bucket.delete(key)

    @staticmethod
    def owns(key, owner_id):
        """键里带 owner，用于便宜的归属预判；最终仍以数据库记录为准。"""
        parts = key.split('/')
        return len(parts) >= 4 and parts[0] == 'media' and parts[2] == str(int(owner_id))
