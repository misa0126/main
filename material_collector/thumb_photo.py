"""サムネ用に写真を加工する(人間電・すあし社長のサムネを見直して足した。2026年11月27日)。

ユーザーの希望:「重厚感とか画像の切り抜いたりイラスト風にしたり色々工夫されてる」。
2つのチャンネルは、写真をそのまま使わず、
  - 人物を切り抜いて、場面や地図の手前に大きく重ねる
  - 写真を、細部をくっきりさせた絵画(イラスト)のような見た目にし、こはく色や青で色を付ける
ということをしている。ここではその2つを作る。

使い方:
    # 絵画風: 細部をくっきりさせて、色を付ける(色調: 重厚 = 暗いこはく色、鮮やか = 自然な色を少し強く)
    python -m material_collector.thumb_photo 絵画風 入力.jpg 出力.jpg --色調 重厚

    # 切り抜き: 人物だけを残して、まわりを透明にしたPNGにする(rembg が要る。pip install "rembg[cpu]")
    #   --crop 左,上,右,下(幅と高さに対する割合)で、先に写真の一部だけにできる
    #   --絵画風 重厚 を付けると、切り抜いた人物も絵画風にする
    python -m material_collector.thumb_photo 切り抜き 入力.jpg 出力.png --crop 0,0,0.48,0.85 --絵画風 重厚

できた画像は、サムネ案の表で「写真:」に並べ、--photo で渡す。切り抜きのPNGは表の「切り抜き:」で重ねる。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# 明るさごとの色(暗い所 → 明るい所)。白黒写真にも色が付く
TONES = {
    # 人間電のような、ろうそくや炎に照らされた暗いこはく色
    "重厚": [(0, (3, 2, 1)), (0.3, (30, 16, 8)), (0.55, (88, 50, 24)), (0.8, (182, 124, 64)), (1, (255, 222, 160))],
    # すあし社長のような、青みのある冷たい色(地図や報道写真)
    "冷たい": [(0, (4, 8, 16)), (0.3, (30, 46, 70)), (0.6, (110, 128, 150)), (0.85, (200, 210, 220)), (1, (255, 252, 245))],
    # 肌が自然に見える、あたたかい色(白黒の人物写真に色を付けたように見せる)
    "肌色": [(0, (10, 8, 8)), (0.3, (70, 52, 44)), (0.55, (150, 112, 92)), (0.8, (222, 186, 160)), (1, (255, 246, 236))],
}


def _gradient_map(gray: np.ndarray, tone: str) -> np.ndarray:
    stops = TONES[tone]
    xs = np.array([s[0] for s in stops]) * 255
    out = np.zeros(gray.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(gray, xs, [s[1][c] for s in stops])
    return out


def illustrate(img: Image.Image, tone: str = "重厚", strength: float = 1.0) -> Image.Image:
    """写真を、細部がくっきりした絵画のような見た目にする。透明な所(切り抜き)はそのまま残す。"""
    import cv2

    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = np.asarray(img.convert("RGB"))
    # 小さい写真は先に大きくしておく(絵の具のような塗りが細かくなり、粗さが目立たない)
    scale = max(1.0, 1400 / max(rgb.shape[:2]))
    if scale > 1:
        rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        if alpha is not None:
            alpha = alpha.resize((rgb.shape[1], rgb.shape[0]), Image.LANCZOS)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    # 1. 細部を強く(HDRのような、しわや布の質感が浮き出る見た目)
    detail = cv2.detailEnhance(bgr, sigma_s=12, sigma_r=0.18)
    # 2. 塗りを平らにして、絵の具で描いたような面にする
    paint = cv2.edgePreservingFilter(detail, flags=cv2.RECURS_FILTER, sigma_s=30, sigma_r=0.25)
    mixed = cv2.addWeighted(detail, 0.55, paint, 0.45, 0)
    # 3. 明るさの差を部分ごとに強める(重厚感)
    lab = cv2.cvtColor(mixed, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8)).apply(lab[..., 0])
    mixed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    gray = cv2.cvtColor(mixed, cv2.COLOR_BGR2GRAY).astype(np.float32)
    colored = cv2.cvtColor(mixed, cv2.COLOR_BGR2RGB).astype(np.float32)
    if tone in TONES:
        mapped = _gradient_map(gray, tone)
        # 元が白黒ならほぼ全部、カラーなら元の色を少し残す
        sat = float(np.mean(np.std(colored, axis=2)))
        keep = 0.0 if sat < 6 else 0.35
        colored = mapped * (1 - keep) + colored * keep
    out = np.clip(colored * strength + np.asarray(rgb, np.float32) * (1 - strength), 0, 255).astype(np.uint8)
    result = Image.fromarray(out).filter(ImageFilter.UnsharpMask(radius=2, percent=90, threshold=2))
    if alpha is not None:
        result.putalpha(alpha)
    return result


def cutout(img: Image.Image, crop: tuple[float, float, float, float] | None = None) -> Image.Image:
    """人物(手前に写っているもの)だけを残し、まわりを透明にする。"""
    from rembg import new_session, remove

    if crop:
        w, h = img.size
        img = img.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    out = remove(img.convert("RGB"), session=new_session("isnet-general-use"))
    # ふちの半端な透明を少し締めて、背景の色が残らないようにする
    a = np.asarray(out.getchannel("A")).astype(np.float32) / 255
    a = np.clip((a - 0.12) / 0.76, 0, 1)
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    box = out.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    return out.crop(box) if box else out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="サムネ用に写真を加工する(絵画風・切り抜き)")
    parser.add_argument("mode", choices=["絵画風", "切り抜き"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--色調", dest="tone", default="重厚", choices=list(TONES) + ["なし"])
    parser.add_argument("--強さ", dest="strength", type=float, default=1.0)
    parser.add_argument("--crop", help="左,上,右,下(幅と高さに対する割合)")
    parser.add_argument("--絵画風", dest="paint", choices=list(TONES) + ["なし"], help="切り抜いた人物も絵画風にする")
    args = parser.parse_args(argv)
    img = Image.open(args.input)
    if args.mode == "絵画風":
        out = illustrate(img.convert("RGB"), args.tone, args.strength).convert("RGB")
        out.save(args.output, quality=94)
    else:
        crop = tuple(float(x) for x in args.crop.split(",")) if args.crop else None
        out = cutout(img, crop)
        if args.paint:
            out = illustrate(out, args.paint, args.strength)
        out.save(args.output.with_suffix(".png"))
    print(f"作成しました: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
