"""生成首页用的小凛贴纸 WebP（480/960 两档）和眨眼用的闭眼帧。

用法：python website/tools/make_rin_assets.py [眼部预览输出目录]

原图是 static/images/rin/ 下 1254px 的 PNG，生成结果写回同一目录。
闭眼帧：用左右肤色插值抹掉眼睛，再画上眼睑弧线。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RIN_DIR = Path(__file__).resolve().parent.parent / "static" / "images" / "rin"
STICKERS = ["welcome", "music", "manage", "confused"]
WIDTHS = [480, 960]

# 眼睛包围盒 (x0, x1, y0, y1)，基于 1254px 原图
EYES = {
    "manage": [(479, 523, 523, 665), (707, 753, 510, 654)],
    "confused": [(461, 505, 500, 646), (684, 728, 526, 670)],
}
# 外扩一圈，盖住眼睛的白色描边
EYE_PAD = 9
LID_COLOR = (38, 24, 20, 255)
LID_WIDTH = 8
SUPERSAMPLE = 4


def _skinlike(px):
    # 只认肤色和腮红：排除发丝描线（深棕）、头发（橙，R-B 大）和发丝旁的白边（R-B 接近 0）
    r, g, b = px[:3]
    return r > 235 and 12 <= r - b <= 70 and g < 248


def _skin_near(src, y, x, step):
    """从 x 开始朝 step 方向找最近的肤色像素（最多 30px，跨过发丝），找不到返回 None。"""
    for i in range(30):
        px = src[y, x + i * step]
        if _skinlike(px):
            return px
    return None


def _erase_eye(a, src, box):
    """在外扩的椭圆里逐行用左右两端的肤色插值，抹掉眼睛。"""
    x0, x1, y0, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 + EYE_PAD, (y1 - y0) / 2 + EYE_PAD
    for y in range(int(cy - ry), int(cy + ry) + 1):
        t = 1 - ((y - cy) / ry) ** 2
        if t <= 0:
            continue
        half = rx * t ** 0.5
        xl, xr = int(cx - half) - 2, int(cx + half) + 2
        left, right = _skin_near(src, y, xl, -1), _skin_near(src, y, xr, 1)
        if left is None or right is None:
            continue
        # 端点不是紧挨着的肤色，说明这一行碰到了发丝：只替换眼睛像素，保住棕色描线
        only_eye = not (_skinlike(src[y, xl]) and _skinlike(src[y, xr]))
        for x in range(xl, xr + 1):
            px = src[y, x]
            if only_eye and not (px[0] - px[2] < 60 or px[:3].sum() < 200):
                continue
            f = (x - xl) / (xr - xl)
            a[y, x] = left * (1 - f) + right * f


def make_blink(im, boxes):
    src = np.array(im.convert("RGBA")).astype(float)
    a = src.copy()
    for box in boxes:
        _erase_eye(a, src, box)
    out = Image.fromarray(a.clip(0, 255).astype("uint8"), "RGBA")

    s = SUPERSAMPLE
    lids = Image.new("RGBA", (im.width * s, im.height * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lids)
    for x0, x1, y0, y1 in boxes:
        w = (x1 - x0) * 1.6
        cx = (x0 + x1) / 2
        ly = y0 + (y1 - y0) * 0.62
        draw.arc(
            [(cx - w / 2) * s, (ly - w * 0.32) * s, (cx + w / 2) * s, (ly + w * 0.32) * s],
            25, 155, fill=LID_COLOR, width=LID_WIDTH * s,
        )
    lids = lids.resize(im.size, Image.LANCZOS)
    return Image.alpha_composite(out, lids)


def save_webp(im, name, width):
    h = round(im.height * width / im.width)
    im.resize((width, h), Image.LANCZOS).save(
        RIN_DIR / f"{name}-{width}.webp", "WEBP", quality=82, method=6
    )


def main():
    preview_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    for name in STICKERS:
        im = Image.open(RIN_DIR / f"{name}.png").convert("RGBA")
        variants = {name: im}
        if name in EYES:
            blink = make_blink(im, EYES[name])
            variants[f"{name}-blink"] = blink
            if preview_dir:
                blink.crop((380, 420, 860, 760)).resize((960, 680), Image.LANCZOS).save(
                    preview_dir / f"{name}-blink-eyes.png"
                )
        for vname, vim in variants.items():
            for w in WIDTHS:
                save_webp(vim, vname, w)
    avatar = Image.open(RIN_DIR / "bot-avatar.png").convert("RGBA")
    save_webp(avatar, "bot-avatar", 96)


if __name__ == "__main__":
    main()
