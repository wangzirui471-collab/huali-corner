"""图片规则使用合成像素，不读取真实用户照片或 EXIF。"""

import io
import unittest

from PIL import Image

from huali.infrastructure.images.normalize import (
    AVATAR_POLICY,
    PRODUCT_POLICY,
    ImagePolicy,
    normalize_image,
)
from huali.shared.errors import ApplicationError


def synthetic_image(mode="RGB", size=(48, 24), file_format="PNG", **options):
    """将纯色合成像素编码为图片，便于控制格式、尺寸和 EXIF。"""
    color = (255, 0, 0, 80) if mode == "RGBA" else "red"
    with Image.new(mode, size, color) as image:
        output = io.BytesIO()
        image.save(output, file_format, **options)
        return output.getvalue()


class ImageTests(unittest.TestCase):
    """覆盖真实格式校验、方向、元数据、上限、透明度与静态约束。"""

    def test_normal_formats_become_webp(self):
        """JPEG、PNG 和 WebP 输入均返回可重新解码且尺寸正确的 WebP。"""
        for file_format in ("JPEG", "PNG", "WEBP"):
            result = normalize_image(
                synthetic_image(file_format=file_format), PRODUCT_POLICY
            )
            with Image.open(io.BytesIO(result.payload)) as output:
                self.assertEqual(output.format, "WEBP")
                self.assertEqual(output.size, (48, 24))
            self.assertEqual(len(result.digest), 64)

    def test_exif_orientation_is_applied_and_metadata_removed(self):
        """EXIF 旋转实际改变输出方向，重编码后不携带旧 EXIF 或描述。"""
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "synthetic-private-description"
        result = normalize_image(
            synthetic_image(file_format="JPEG", exif=exif), PRODUCT_POLICY
        )
        self.assertEqual((result.width, result.height), (24, 48))
        with Image.open(io.BytesIO(result.payload)) as output:
            self.assertFalse(output.getexif())
            self.assertNotIn("exif", output.info)

    def test_avatar_limits_edge_and_preserves_alpha(self):
        """头像缩至 512 边长并保留透明度，商品采用既有 RGB 输出约定。"""
        source = synthetic_image(mode="RGBA", size=(1024, 512))
        result = normalize_image(source, AVATAR_POLICY)
        self.assertEqual((result.width, result.height), (512, 256))
        with Image.open(io.BytesIO(result.payload)) as output:
            self.assertIn("A", output.getbands())
            self.assertEqual(output.getpixel((0, 0))[3], 80)
        product = normalize_image(source, PRODUCT_POLICY)
        with Image.open(io.BytesIO(product.payload)) as output:
            self.assertEqual(output.mode, "RGB")

    def test_size_and_pixels_are_rejected_before_output(self):
        """空输入、字节超限和像素超限均明确拒绝，不返回可保存对象。"""
        policy = ImagePolicy(100, 10, 8, False)
        for content in (b"", b"x" * 101, synthetic_image(size=(4, 4))):
            with self.subTest(size=len(content)), self.assertRaises(ApplicationError):
                normalize_image(content, policy)

    def test_unsupported_truncated_and_animated_input_are_rejected(self):
        """扩展名不能代替真实格式；截断图片和多帧图不能作为静态实拍图。"""
        frame = Image.new("RGB", (8, 8), "blue")
        animated = io.BytesIO()
        with frame:
            with Image.new("RGB", (8, 8), "red") as other:
                frame.save(
                    animated,
                    "WEBP",
                    save_all=True,
                    append_images=[other],
                    duration=100,
                    loop=0,
                )
        for content in (
            b"not-an-image.png",
            synthetic_image(file_format="BMP"),
            synthetic_image()[:20],
            animated.getvalue(),
        ):
            with self.subTest(size=len(content)), self.assertRaises(ApplicationError):
                normalize_image(content, PRODUCT_POLICY)


if __name__ == "__main__":
    unittest.main()
