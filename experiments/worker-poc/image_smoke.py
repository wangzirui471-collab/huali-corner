"""对本机 Worker 发送合成图片，核对方向、重编码、R2 与输入压力边界。"""

import base64
import io
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image


def encode_image(size=(48, 24), file_format="PNG", **options):
    """生成无真实个人信息的纯色图片，返回编码二进制。"""
    with Image.new("RGB", size, "red") as image:
        stream = io.BytesIO()
        image.save(stream, file_format, **options)
        return stream.getvalue()


def probe(content: bytes, kind="product"):
    """向回环地址的图片探针发请求，返回状态及 JSON；从不接收远程 URL。"""
    body = json.dumps(
        {"content": base64.b64encode(content).decode("ascii"), "kind": kind}
    ).encode("utf-8")
    request = Request(
        "http://127.0.0.1:8787/api/probe/image",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = urlopen(request, timeout=180)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def encode_animation():
    """生成两帧合成 WebP，确认静态图片规则不会悄悄只取第一帧。"""
    output = io.BytesIO()
    with (
        Image.new("RGB", (8, 8), "red") as first,
        Image.new("RGB", (8, 8), "blue") as second,
    ):
        first.save(output, "WEBP", save_all=True, append_images=[second], duration=100)
    return output.getvalue()


def expect_success(label, content, size, kind="product"):
    """核对合法合成输入的输出尺寸、无 EXIF 和 R2 完整性，并打印平台耗时。"""
    status, result = probe(content, kind)
    assert status == 200, (label, status, result)
    assert result["format"] == "WEBP" and result["r2_round_trip"], (label, result)
    assert (result["width"], result["height"]) == size, (label, result)
    assert result["exif_entries"] == 0, (label, result)
    print(label, json.dumps(result, ensure_ascii=False))


def main():
    """依次验证常见格式、EXIF、最大像素/字节以及超限与动画拒绝。"""
    for file_format in ("JPEG", "PNG", "WEBP"):
        expect_success(file_format, encode_image(file_format=file_format), (48, 24))
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "synthetic-private-metadata"
    expect_success("EXIF", encode_image(file_format="JPEG", exif=exif), (24, 48))
    expect_success("avatar", encode_image(size=(1024, 512)), (512, 256), "avatar")
    expect_success("20M pixels", encode_image(size=(5000, 4000)), (1600, 1280))
    # JPEG 尾部合成填充补至旧接口的 5 MiB 上限，单独压测请求体缓冲。
    jpeg = encode_image(file_format="JPEG")
    largest = jpeg + b"\0" * (5 * 1024 * 1024 - len(jpeg))
    expect_success("5 MiB bytes", largest, (48, 24))
    for label, content, code in (
        ("byte limit", largest + b"\0", "IMAGE_SIZE_LIMIT"),
        ("pixel limit", encode_image(size=(5001, 4000)), "IMAGE_PIXEL_LIMIT"),
        ("truncated", b"not-an-image", "INVALID_IMAGE"),
        ("animated", encode_animation(), "ANIMATED_IMAGE"),
    ):
        status, result = probe(content)
        assert status in (413, 422) and result["code"] == code, (label, status, result)
    print(
        "Local image probe passed; cloud CPU/memory and authenticated media are separate gates."
    )


if __name__ == "__main__":
    main()
