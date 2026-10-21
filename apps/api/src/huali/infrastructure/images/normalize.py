"""保留既有图片上限和方向处理，用独立适配器验证 Pillow 平台能力。"""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from huali.shared.errors import ApplicationError


@dataclass(frozen=True)
class ImagePolicy:
    """输入字节、像素和输出边长；所有上限均在完整解码前检查。"""

    max_bytes: int
    max_pixels: int
    output_edge: int
    preserve_alpha: bool


AVATAR_POLICY = ImagePolicy(2 * 1024 * 1024, 16_000_000, 512, True)
PRODUCT_POLICY = ImagePolicy(5 * 1024 * 1024, 20_000_000, 1600, False)


@dataclass(frozen=True)
class NormalizedImage:
    """已重编码的静态 WebP；摘要用于重复图片检测，尺寸用于预留展示空间。"""

    payload: bytes
    width: int
    height: int
    digest: str


def normalize_image(content: bytes, policy: ImagePolicy) -> NormalizedImage:
    """校验真实格式和大小，纠正 EXIF 方向后生成去元数据的 WebP。

    content 只接受图片二进制，policy 区分头像与商品上限；失败抛出可展示
    的 ApplicationError。此函数不写 R2，校验失败不会产生孤立对象。
    """
    if not isinstance(content, bytes) or not 0 < len(content) <= policy.max_bytes:
        raise ApplicationError("IMAGE_SIZE_LIMIT", "图片为空或超过大小上限", 413)
    try:
        # 在解码器入口限定格式，避免先解析无关格式、再按扩展名或 format 拒绝。
        with Image.open(io.BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ApplicationError("INVALID_IMAGE", "仅支持 JPEG、PNG 或 WebP", 422)
            if not 0 < image.width * image.height <= policy.max_pixels:
                raise ApplicationError("IMAGE_PIXEL_LIMIT", "图片像素超过上限", 413)
            if (
                getattr(image, "is_animated", False)
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ApplicationError("ANIMATED_IMAGE", "请上传静态实拍图片", 422)
            image.verify()
        with Image.open(io.BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as image:
            image.load()
            with ImageOps.exif_transpose(image) as oriented:
                alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                mode = "RGBA" if policy.preserve_alpha and alpha else "RGB"
                with oriented.convert(mode) as converted:
                    converted.thumbnail(
                        (policy.output_edge, policy.output_edge),
                        Image.Resampling.LANCZOS,
                    )
                    # 新画布避免 convert/copy 继承 EXIF、注释或其他上传元数据。
                    with Image.new(mode, converted.size) as clean:
                        clean.paste(converted)
                        output = io.BytesIO()
                        clean.save(output, "WEBP", quality=85)
                        payload = output.getvalue()
                        return NormalizedImage(
                            payload,
                            clean.width,
                            clean.height,
                            hashlib.sha256(payload).hexdigest(),
                        )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ApplicationError(
            "INVALID_IMAGE", "请上传完整有效的静态图片", 422
        ) from None
