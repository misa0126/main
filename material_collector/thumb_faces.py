"""ユーザーの立ち絵(霊夢・魔理沙の顔、黒背景 1920x1080)から、サムネ用の表情差分PNGを作る。

    python -m material_collector.thumb_faces

material_collector/thumb_assets/tachie_source.jpg を読み、同じフォルダに
reimu_<表情>.png / marisa_<表情>.png(背景を透過)を書き出す。
目・口の位置は元画像に合わせて手で測った値。立ち絵を差し替えたら測り直すこと。
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSETS = Path(__file__).with_name("thumb_assets")
SOURCE = ASSETS / "tachie_source.jpg"
S = 4  # 線をなめらかにするため、4倍に拡大して描いてから縮める

SKIN = (255, 231, 211)
LINE = (70, 40, 35)
MOUTH = (150, 40, 45)
TONGUE = (235, 110, 110)
BLUE = (90, 160, 235)

# 元画像の座標。eyes は目(まゆ毛を含む)を囲む箱、mouth は口の中心、mark は怒りマークなどを置く頭の右上
CHARS = {
    "reimu": {"box": (20, 465, 356, 770), "eyes": [(158, 630, 214, 676), (258, 630, 306, 676)],
              "mouth": (235, 702), "mark": (300, 560), "sweat": (90, 640)},
    "marisa": {"box": (1460, 385, 1920, 770), "eyes": [(1580, 630, 1634, 676), (1676, 630, 1728, 676)],
               "mouth": (1655, 702), "mark": (1800, 560), "sweat": (1540, 650)},
}

EXPRESSIONS = ["ふつう", "にやり", "驚き", "焦り", "怒り", "泣き", "笑顔"]


def cut_out(source: Image.Image, box) -> Image.Image:
    """黒い背景だけを透明にする(輪郭の黒い線は残す)。"""
    crop = source.crop(box).convert("RGB")
    dark = Image.fromarray((np.asarray(crop).max(axis=2) < 30).astype(np.uint8) * 255)
    # 端からつながっている暗い所が背景
    background = dark.copy()
    w, h = background.size
    for x in range(w):
        for y in (0, h - 1):
            if background.getpixel((x, y)) == 255:
                ImageDraw.floodfill(background, (x, y), 128)
    for y in range(h):
        for x in (0, w - 1):
            if background.getpixel((x, y)) == 255:
                ImageDraw.floodfill(background, (x, y), 128)
    bg = Image.fromarray(((np.asarray(background) == 128) * 255).astype(np.uint8))
    fg = ImageChops.invert(bg).filter(ImageFilter.MaxFilter(5))  # 輪郭の線のぶんだけ広げる
    alpha = fg.filter(ImageFilter.GaussianBlur(0.8))
    out = crop.convert("RGBA")
    out.putalpha(alpha)
    return out


def local(c, box):
    return (c[0] - box[0]) * S, (c[1] - box[1]) * S


def erase_eyes(img: Image.Image, ch) -> None:
    """目とまゆ毛を肌の色で消す(閉じた目などを描くため)。髪の毛には触らない。"""
    a = np.asarray(img).copy()
    box = ch["box"]
    for (x0, y0, x1, y1) in ch["eyes"]:
        for y in range(y0 - box[1], y1 - box[1]):
            for x in range(x0 - box[0], x1 - box[0]):
                r, g, b, al = a[y, x]
                # 髪(霊夢は黒、魔理沙は黄)は残す。目の上のふちより上は髪とみなす
                is_hair_dark = max(r, g, b) < 90 and y < (y0 - box[1]) + 8
                is_hair_yellow = r > 200 and g > 170 and b < 120
                if not (is_hair_dark or is_hair_yellow):
                    a[y, x] = (*SKIN, al)
    img.paste(Image.fromarray(a))


def shrink_pupils(img: Image.Image, ch) -> None:
    """黒目(茶色)を白くして、小さな黒目を描き直す(驚いた顔)。"""
    a = np.asarray(img).copy()
    box = ch["box"]
    hsv = np.asarray(img.convert("RGB").convert("HSV")).astype(int)
    centers = []
    for (x0, y0, x1, y1) in ch["eyes"]:
        xs, ys = [], []
        for y in range(y0 - box[1], y1 - box[1]):
            for x in range(x0 - box[0], x1 - box[0]):
                h, s, v = hsv[y, x]
                if 5 < h < 25 and s > 120 and 60 < v < 250:
                    a[y, x, :3] = (250, 250, 252)
                    xs.append(x); ys.append(y)
        centers.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    img.paste(Image.fromarray(a))
    return centers


def half_lid(img: Image.Image, ch) -> list:
    """上まぶたを下ろして、目を半分閉じた「ジト目」にする。まぶたの線の位置を返す。"""
    a = np.asarray(img).copy()
    box = ch["box"]
    hsv = np.asarray(img.convert("RGB").convert("HSV")).astype(int)
    lids = []
    for (x0, y0, x1, y1) in ch["eyes"]:
        ys = [y for y in range(y0 - box[1], y1 - box[1]) for x in range(x0 - box[0], x1 - box[0])
              if 5 < hsv[y, x][0] < 25 and hsv[y, x][1] > 120 and 60 < hsv[y, x][2] < 250]
        top, bottom = min(ys), max(ys)
        cut = top + int((bottom - top) * 0.45)
        xs = []
        for y in range(y0 - box[1], cut):
            for x in range(x0 - box[0], x1 - box[0]):
                r, g, b, al = a[y, x]
                is_hair_yellow = r > 200 and g > 170 and b < 120
                is_hair_dark = max(r, g, b) < 90 and y < (y0 - box[1]) + 6
                if not (is_hair_yellow or is_hair_dark) and al > 0:
                    a[y, x, :3] = SKIN
                    xs.append(x)
        lids.append((min(xs) + 2, max(xs) - 2, cut))
    img.paste(Image.fromarray(a))
    return lids


def erase_mouth(d: ImageDraw.ImageDraw, ch) -> None:
    cx, cy = local(ch["mouth"], ch["box"])
    d.rectangle((cx - 30 * S, cy - 5 * S, cx + 30 * S, cy + 5 * S), fill=SKIN)


def sweat(d, x, y, size=1.0):
    r = 9 * S * size
    d.polygon([(x, y - 2.6 * r), (x - r * 0.95, y - r * 0.2), (x + r * 0.95, y - r * 0.2)], fill=(255, 255, 255), outline=None)
    d.ellipse((x - r, y - r, x + r, y + r), fill=BLUE, outline=(40, 90, 170), width=S * 2)
    d.polygon([(x, y - 2.6 * r), (x - r * 0.93, y - r * 0.35), (x + r * 0.93, y - r * 0.35)], fill=BLUE)
    d.line([(x, y - 2.6 * r), (x - r * 0.97, y - r * 0.25)], fill=(40, 90, 170), width=S * 2)
    d.line([(x, y - 2.6 * r), (x + r * 0.97, y - r * 0.25)], fill=(40, 90, 170), width=S * 2)
    d.ellipse((x - r * 0.5, y - r * 0.4, x - r * 0.1, y), fill=(220, 240, 255))


def anger_mark(d, x, y):
    """怒りマーク(💢): 4つの角から中心に向かってふくらむ弧。"""
    r = 20 * S
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = x + sx * r * 1.15, y + sy * r * 1.15
            toward = math.degrees(math.atan2(-sy, -sx))
            box = (cx - r, cy - r, cx + r, cy + r)
            d.arc(box, toward - 46, toward + 46, fill=(120, 0, 10), width=S * 9)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = x + sx * r * 1.15, y + sy * r * 1.15
            toward = math.degrees(math.atan2(-sy, -sx))
            box = (cx - r, cy - r, cx + r, cy + r)
            d.arc(box, toward - 43, toward + 43, fill=(235, 35, 45), width=S * 6)


def draw(name: str, expr: str, source: Image.Image) -> Image.Image:
    ch = CHARS[name]
    box = ch["box"]
    base = cut_out(source, box)
    centers = None
    if expr in ("笑顔",):
        erase_eyes(base, ch)
    lids = None
    if expr in ("驚き", "焦り"):
        centers = shrink_pupils(base, ch)
    if expr == "にやり":
        lids = half_lid(base, ch)
    big = base.resize((base.width * S, base.height * S), Image.LANCZOS)
    over = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    o = ImageDraw.Draw(over)  # 頭の外にはみ出すもの(汗・マーク)
    mx, my = local(ch["mouth"], box)
    w = S * 2.4
    if expr != "ふつう":
        erase_mouth(d, ch)
    if centers:
        for (ex, ey) in centers:
            ex, ey = ex * S, ey * S + 2 * S
            r = 5.5 * S
            d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=(110, 50, 20), outline=(40, 20, 10), width=S)
            d.ellipse((ex - r * 0.5, ey - r * 0.7, ex, ey - r * 0.2), fill=(255, 255, 255))
    if lids:
        for (lx0, lx1, ly) in lids:
            # まぶたの線(太め、少しななめ)
            d.line([(lx0 * S, ly * S + 2 * S), (lx1 * S, ly * S - 1 * S)], fill=(40, 25, 20), width=S * 4)
    if expr == "にやり":
        # 片方の口角が上がった、歯の見えるニヤッとした口
        top = [(mx - 22 * S, my - 2 * S), (mx, my + 1 * S), (mx + 22 * S, my - 9 * S)]
        bottom = [(mx + 22 * S, my - 9 * S), (mx + 8 * S, my + 9 * S), (mx - 8 * S, my + 9 * S), (mx - 22 * S, my - 2 * S)]
        d.polygon(top + bottom[1:], fill=MOUTH)
        d.polygon([(mx - 20 * S, my - 1 * S), (mx, my + 2 * S), (mx + 20 * S, my - 7 * S), (mx + 16 * S, my - 3 * S), (mx, my + 5 * S), (mx - 16 * S, my + 2 * S)], fill=(255, 255, 255))
        d.line(top, fill=LINE, width=int(w), joint="curve")
        d.line(bottom, fill=LINE, width=int(w), joint="curve")
    elif expr == "驚き":
        d.ellipse((mx - 11 * S, my - 10 * S, mx + 11 * S, my + 17 * S), fill=MOUTH, outline=LINE, width=int(w))
        d.chord((mx - 8 * S, my + 5 * S, mx + 8 * S, my + 17 * S), 200, 340, fill=TONGUE)
    elif expr == "焦り":
        pts = [(mx - 20 * S + i * S, my + 2 * S + 3.2 * S * math.sin(i / 40 * 3 * math.pi)) for i in range(41)]
        d.line(pts, fill=LINE, width=int(w), joint="curve")
        sx, sy = local(ch["sweat"], box)
        sweat(o, sx, sy, 1.15)
        sweat(o, sx + 14 * S, sy + 40 * S, 0.75)
    elif expr == "怒り":
        d.polygon([(mx - 20 * S, my + 12 * S), (mx - 11 * S, my - 5 * S), (mx + 11 * S, my - 5 * S), (mx + 20 * S, my + 12 * S)],
                  fill=MOUTH, outline=LINE, width=int(w))
        d.rectangle((mx - 10 * S, my - 3 * S, mx + 10 * S, my + 1 * S), fill=(255, 255, 255))
        anger_mark(o, *local(ch["mark"], box))
    elif expr == "泣き":
        pts = [(mx - 14 * S + i * S, my + 3 * S - 6 * S * math.sin(math.pi * i / 28)) for i in range(29)]
        d.line(pts, fill=LINE, width=int(w), joint="curve")
        for (x0, y0, x1, y1) in ch["eyes"]:
            tx = ((x0 + x1) / 2 - box[0]) * S
            top = (y1 - box[1] - 4) * S
            d.rounded_rectangle((tx - 6 * S, top, tx + 6 * S, top + 46 * S), radius=6 * S, fill=(150, 205, 250, 255))
            d.line([(tx - 6 * S, top), (tx - 6 * S, top + 46 * S)], fill=(70, 140, 220), width=S * 2)
            d.line([(tx + 6 * S, top), (tx + 6 * S, top + 46 * S)], fill=(70, 140, 220), width=S * 2)
    elif expr == "笑顔":
        for (x0, y0, x1, y1) in ch["eyes"]:
            cx, cy = ((x0 + x1) / 2 - box[0]) * S, ((y0 + y1) / 2 - box[1] + 6) * S
            d.arc((cx - 17 * S, cy - 12 * S, cx + 17 * S, cy + 14 * S), 200, 340, fill=(40, 25, 20), width=S * 4)
        d.chord((mx - 17 * S, my - 8 * S, mx + 17 * S, my + 20 * S), 0, 180, fill=MOUTH, outline=LINE, width=int(w))
        d.chord((mx - 9 * S, my + 6 * S, mx + 9 * S, my + 19 * S), 180, 360, fill=TONGUE)
    big = Image.alpha_composite(big, over) if expr in ("焦り", "怒り") else big
    return big.resize(base.size, Image.LANCZOS)


def main() -> int:
    source = Image.open(SOURCE).convert("RGB")
    for name in CHARS:
        for expr in EXPRESSIONS:
            out = ASSETS / f"{name}_{expr}.png"
            draw(name, expr, source).save(out, optimize=True)
            print("作成しました:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
