"""サムネ用に写真を加工する(人間電・すあし社長のサムネを見直して足した。2026年11月27日)。

ユーザーの希望:「重厚感とか画像の切り抜いたりイラスト風にしたり色々工夫されてる」。
2つのチャンネルは、写真をそのまま使わず、
  - 人物を切り抜いて、場面や地図の手前に大きく重ねる
  - 写真を、細部をくっきりさせた絵画(イラスト)のような見た目にし、こはく色や青で色を付ける
ということをしている。ここではその2つを作る。

使い方:
    # カラー: AIで大きくして(Real-ESRGAN)色を付け(DDColor)、映画のような色にする(--光 炎 = 人間電、夜 = すあし社長)。
    #   参考チャンネルの絵にいちばん近い。白黒の古い写真はまずこれを使う
    python -m material_collector.thumb_photo カラー 入力.jpg 出力.jpg --光 炎
    #   切り抜きと一緒に: 切り抜き 入力.jpg 出力.png --crop ... --カラー --光 炎

    # 絵画風: 細部をくっきりさせて、色を付ける(色調: 重厚 = 暗いこはく色、鮮やか = 自然な色を少し強く)
    python -m material_collector.thumb_photo 絵画風 入力.jpg 出力.jpg --色調 重厚

    # 切り抜き: 人物だけを残して、まわりを透明にしたPNGにする(rembg が要る。pip install "rembg[cpu]")
    #   地図や物を切り抜くときは --もの を付ける
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


def cutout(img: Image.Image, crop: tuple[float, float, float, float] | None = None, model: str = "birefnet-portrait") -> Image.Image:
    """人物(手前に写っているもの)だけを残し、まわりを透明にする。

    model: 人物は birefnet-portrait(髪や肩のふちまできれい。白黒の古い写真でも背景が残りにくい)、
    地図や物は isnet-general-use。birefnet は重いので、1枚ずつ実行する(並べて動かすとメモリが足りなくなった)。
    """
    from rembg import new_session, remove

    if crop:
        w, h = img.size
        img = img.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    out = remove(img.convert("RGB"), session=new_session(model))
    # ふちの半端な透明を少し締めて、背景の色が残らないようにする
    a = np.asarray(out.getchannel("A")).astype(np.float32) / 255
    a = np.clip((a - 0.12) / 0.76, 0, 1)
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    box = out.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    return out.crop(box) if box else out



# ---- AIで色を付ける・大きくする(2026年11月27日。ユーザー「文字入れはめっちゃいいのに画像が全然ちがう…」) ----
# 参考チャンネルの絵はAIで作ったカラーの細かい絵。白黒の古い写真を、AIで色を付けて(DDColor)、
# 細部を保って大きくし(Real-ESRGAN)、映画のような色にすると近づく。
# モデルは初回に Hugging Face から ~/.cache/thumb_models に取る(DDColor 121MB、Real-ESRGAN 67MB)
MODEL_DIR = Path.home() / ".cache" / "thumb_models"
MODELS = {
    "ddcolor.onnx": ("https://huggingface.co/ipsilondev/ddcolor-onnx/resolve/main/ddcolor_paper_tiny.onnx",
                     "324c626acebe624c3f10fcdf1ca85f3c1ba9e896f1457b2ad5072237e34b5c87"),
    "realesrgan_x4.onnx": ("https://huggingface.co/imgdesignart/realesrgan-x4-onnx/resolve/main/onnx/model.onnx", None),
}
_sessions: dict = {}


def _session(name: str):
    import hashlib
    import urllib.request

    import onnxruntime as ort

    if name in _sessions:
        return _sessions[name]
    path = MODEL_DIR / name
    if not path.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        url, sha = MODELS[name]
        print(f"モデルを取っています: {name}")
        urllib.request.urlretrieve(url, path)
        if sha and hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            path.unlink()
            raise RuntimeError(f"{name} の中身が違います(取り直してください)")
    _sessions[name] = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return _sessions[name]


def upscale(img: Image.Image, max_side: int = 2200) -> Image.Image:
    """Real-ESRGAN で4倍に大きくする(64画素ずつ区切って、重なりを付けてつなぐ)。大きくしすぎないよう先に縮める。"""
    rgb = img.convert("RGB")
    if max(rgb.size) * 4 > max_side:
        k = max_side / 4 / max(rgb.size)
        if k < 1:
            rgb = rgb.resize((max(1, int(rgb.width * k)), max(1, int(rgb.height * k))), Image.LANCZOS)
    sess = _session("realesrgan_x4.onnx")
    name = sess.get_inputs()[0].name
    a = np.asarray(rgb, np.float32) / 255
    h, w = a.shape[:2]
    tile, pad = 64, 6
    out = np.zeros((h * 4, w * 4, 3), np.float32)
    step = tile - pad * 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            y0, x0 = max(0, min(y - pad, h - tile)), max(0, min(x - pad, w - tile))
            patch = a[y0:y0 + tile, x0:x0 + tile]
            ph, pw = patch.shape[:2]
            if ph < tile or pw < tile:
                patch = np.pad(patch, ((0, tile - ph), (0, tile - pw), (0, 0)), mode="edge")
            res = sess.run(None, {name: patch.transpose(2, 0, 1)[None]})[0][0].transpose(1, 2, 0)
            # 区切りのふちを捨てて、まん中だけを使う
            ys, xs = y - y0, x - x0
            hh, ww = min(step, h - y), min(step, w - x)
            out[y * 4:(y + hh) * 4, x * 4:(x + ww) * 4] = res[ys * 4:(ys + hh) * 4, xs * 4:(xs + ww) * 4]
    return Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8))


def colorize(img: Image.Image) -> Image.Image:
    """DDColor で白黒写真に色を付ける(明るさは元のまま、色だけを足す)。"""
    import cv2

    rgb = np.asarray(img.convert("RGB"), np.float32) / 255
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    small = cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_AREA)
    sl = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
    sl[..., 1:] = 0
    grey = cv2.cvtColor(sl, cv2.COLOR_LAB2RGB)
    ab = _session("ddcolor.onnx").run(None, {"input": grey.transpose(2, 0, 1)[None].astype(np.float32)})[0][0].transpose(1, 2, 0)
    ab = cv2.resize(ab, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    lab[..., 1:] = ab
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8))


def cinematic(img: Image.Image, look: str = "炎") -> Image.Image:
    """映画のような色と光にする(色は残す)。
    炎: 人間電のような、暗い所は深い青緑、明るい所はろうそくや炎のオレンジ。細部をくっきり
    夜: すあし社長のような、青い夜の中で人の顔が浮かぶ色"""
    import cv2

    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = np.asarray(img.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    bgr = cv2.detailEnhance(bgr, sigma_s=8, sigma_r=0.12)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[..., 0])
    f = cv2.cvtColor(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    lum = f.mean(axis=2, keepdims=True)
    if look == "炎":
        shadow, high = np.array([0.05, 0.16, 0.20]), np.array([1.0, 0.62, 0.25])
    else:
        shadow, high = np.array([0.02, 0.08, 0.22]), np.array([1.0, 0.85, 0.7])
    # 暗い所ほど shadow の色、明るい所ほど high の色を「重ねる」(soft-light 風)
    tint = shadow * (1 - lum) + high * lum
    f = np.where(f < 0.5, 2 * f * tint, 1 - 2 * (1 - f) * (1 - tint)) * 0.55 + f * 0.45
    # 彩度を上げる
    hsv = cv2.cvtColor(np.clip(f, 0, 1).astype(np.float32), cv2.COLOR_RGB2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.35, 0, 1)
    f = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    # S字カーブで黒を締める(重厚感)
    f = np.clip(f, 0, 1)
    f = f * f * (3 - 2 * f) * 0.6 + f * 0.4
    out = Image.fromarray(np.clip(f * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    if alpha is not None:
        out.putalpha(alpha.resize(out.size))
    return out


def restore(img: Image.Image, look: str = "炎", color: bool = True, enlarge: bool = True) -> Image.Image:
    """古い白黒写真を、大きく・カラーに・映画のような色にする(参考チャンネルの絵に近づける)。"""
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    out = img.convert("RGB")
    if enlarge and max(out.size) < 1600:
        out = upscale(out)
    if color:
        out = colorize(out)
    if alpha is not None:
        out.putalpha(alpha.resize(out.size, Image.LANCZOS))
    return cinematic(out, look)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="サムネ用に写真を加工する(絵画風・切り抜き)")
    parser.add_argument("mode", choices=["絵画風", "切り抜き", "カラー"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--色調", dest="tone", default="重厚", choices=list(TONES) + ["なし"])
    parser.add_argument("--強さ", dest="strength", type=float, default=1.0)
    parser.add_argument("--crop", help="左,上,右,下(幅と高さに対する割合)")
    parser.add_argument("--もの", dest="thing", action="store_true", help="人物ではなく地図や物を切り抜く(isnet-general-use を使う)")
    parser.add_argument("--光", dest="look", default="炎", choices=["炎", "夜"], help="カラーの色: 炎(人間電) / 夜(すあし社長)")
    parser.add_argument("--カラー", dest="restore", action="store_true", help="切り抜いた人物を、大きく・カラー・映画のような色にする")
    parser.add_argument("--絵画風", dest="paint", choices=list(TONES) + ["なし"], help="切り抜いた人物も絵画風にする")
    args = parser.parse_args(argv)
    img = Image.open(args.input)
    if args.mode == "カラー":
        restore(img, args.look).convert("RGB").save(args.output, quality=94)
    elif args.mode == "絵画風":
        out = illustrate(img.convert("RGB"), args.tone, args.strength).convert("RGB")
        out.save(args.output, quality=94)
    else:
        crop = tuple(float(x) for x in args.crop.split(",")) if args.crop else None
        out = cutout(img, crop, "isnet-general-use" if args.thing else "birefnet-portrait")
        if args.restore:
            out = restore(out, args.look)
        elif args.paint:
            out = illustrate(out, args.paint, args.strength)
        out.save(args.output.with_suffix(".png"))
    print(f"作成しました: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
