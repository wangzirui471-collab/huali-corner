"""业务错误只描述用例结果，由 HTTP 边界决定响应封套。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldError:
    """可展示的字段错误；path 使用 DTO 字段路径，不携带用户原始输入。"""

    path: str
    message: str


class ApplicationError(Exception):
    """有稳定机器码的预期失败，便于 Web 与小程序一致处理。"""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 409,
        fields: tuple[FieldError, ...] = (),
    ) -> None:
        """记录错误码、展示文案、HTTP 状态及字段错误，不包装底层敏感信息。"""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields
