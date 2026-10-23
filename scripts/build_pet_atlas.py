"""把一张白底的宠物精灵表切成透明图集 + 头像。

桌宠图集约定：一行一个动作，列数固定；每行有效帧数可以不同（尾巴几格是空的）。
新素材（比如给「小毛」补独立形象）走一遍这个脚本，把产出丢进
web 7M/assets/ai-pet/，再在 src/components/pet-skins.js 里加一条即可。

用法：
    python scripts/build_pet_atlas.py 素材.png daqiao --cols 8

做法与取舍：
  · 只把「与画布边缘连通的白色」当背景。角色身体是白的，但被深色描边围住，
    泛洪进不去，所以不会把脸挖空。
  · 行/列边界靠投影找，不按等分切。这张素材的行高从 141 到 167 不等，
    等分会把帧切断，动作播放时出现半截身体。
  · 同一行的所有帧用同一个纵向裁剪带，行内相对位置才不会上下漂。
"""
import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web 7M' / 'assets' / 'ai-pet'
WHITE = 238          # 认定为白的阈值（JPG 压缩会把 255 压到 250 左右）
INK_MIN = 0.02       # 帧内非白像素低于这个比例就算空格子


def projection_bands(im, axis):
    """按投影切出内容带。axis=0 取列带，axis=1 取行带。"""
    gray = im.convert('L')
    w, h = gray.size
    data = gray.tobytes()
    if axis == 0:
        counts = [0] * w
        for y in range(h):
            base = y * w
            for x in range(w):
                if data[base + x] < WHITE:
                    counts[x] += 1
    else:
        counts = [0] * h
        for y in range(h):
            base = y * w
            row = data[base:base + w]
            counts[y] = sum(1 for v in row if v < WHITE)
    bands, start = [], None
    for i, v in enumerate(counts):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, len(counts)))
    # 去掉 1~2 像素的杂点带（JPG 边缘噪点）
    return [(s, e) for s, e in bands if e - s > 8]


def knockout_white(im):
    """挖白底并给边缘做一圈羽化，消掉 JPG 白边。"""
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()

    def white(x, y):
        r, g, b, _ = px[x, y]
        return r >= WHITE and g >= WHITE and b >= WHITE

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if white(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and white(nx, ny):
                seen[ny * w + nx] = 1
                q.append((nx, ny))

    for y in range(h):
        base = y * w
        for x in range(w):
            if seen[base + x]:
                px[x, y] = (255, 255, 255, 0)
                continue
            r, g, b, _ = px[x, y]
            edge = ((x and seen[base + x - 1]) or (x + 1 < w and seen[base + x + 1])
                    or (y and seen[base - w + x]) or (y + 1 < h and seen[base + w + x]))
            if edge:
                lum = (r + g + b) / 3
                px[x, y] = (r, g, b, int(max(0, min(255, (248 - lum) * 7))))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('slug', help='输出文件名前缀，例如 daqiao')
    ap.add_argument('--cols', type=int, default=8)
    ap.add_argument('--avatar', type=int, nargs=2, default=(2, 0), metavar=('ROW', 'COL'))
    args = ap.parse_args()

    im = knockout_white(Image.open(args.source))
    cols = projection_bands(im, 0)
    rows = projection_bands(im, 1)
    if len(cols) != args.cols:
        raise SystemExit(f'检测到 {len(cols)} 列，与 --cols {args.cols} 不符，先核对素材')

    cell = max(max(e - s for s, e in cols), max(e - s for s, e in rows)) + 4
    atlas = Image.new('RGBA', (cell * args.cols, cell * len(rows)), (0, 0, 0, 0))
    px = im.load()

    def ink_ratio(box):
        x0, y0, x1, y1 = box
        n = t = 0
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                t += 1
                if px[x, y][3] > 24:
                    n += 1
        return n / max(1, t)

    frames = []
    for ri, (y0, y1) in enumerate(rows):
        n = 0
        for ci, (x0, x1) in enumerate(cols):
            if ink_ratio((x0, y0, x1, y1)) < INK_MIN:
                continue
            n = ci + 1
            frame = im.crop((x0, y0, x1, y1))
            atlas.paste(frame, (ci * cell + (cell - frame.width) // 2,
                                ri * cell + (cell - frame.height) // 2), frame)
        frames.append(n)

    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / f'{args.slug}-atlas.webp'
    atlas.save(out, 'WEBP', quality=88, method=6)

    ar, ac = args.avatar
    f = atlas.crop((ac * cell, ar * cell, (ac + 1) * cell, (ar + 1) * cell))
    f = f.crop(f.getbbox())
    side = max(f.size) + 10
    av = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    av.paste(f, ((side - f.width) // 2, (side - f.height) // 2), f)
    av.resize((256, 256), Image.LANCZOS).save(ASSETS / f'{args.slug}-avatar.png')

    print(json.dumps({
        'atlas': str(out.relative_to(ROOT)).replace('\\', '/'),
        'size': atlas.size,
        'cell': cell,
        'rows': len(rows),
        'frames_per_row': frames,
    }, ensure_ascii=False, indent=2))
    print('\n把上面的 cell / rows / frames_per_row 填进 src/components/pet-skins.js')


if __name__ == '__main__':
    main()
