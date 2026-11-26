"""選んだ人の写真が本人かどうかを、顔の照合で確かめる(別人の写真を入れないため)。

ユーザーの希望(2026年11月26日、小林清志で「本人じゃない写真使われてた」「次回から自動でやるようにしてて」)。
小林清志では、昭和ガイドというサイトの「小林清志」のページの写真が3枚とも別人だった。

やること:
  1. 区切り表から、人の写真の番号を取り出す(「|名前」付きはその人。名前なしで検索ワードに主人公の名前が入っているものは主人公)
  2. その人の名前で Yahoo!画像検索をして、顔が1つだけ写った写真を集め、たがいに似ている顔のまとまりを「本人の見本」にする
     (検索結果に別人が混じっても、いちばん大きなまとまりを本人とみなす)
  3. 選んだ画像の顔を見本と比べ、点数(0〜1)が低いものを「別人の疑い」として出す。
     別人の疑いの番号には、同じ番号の候補のうち見本に合うものを、大きい順に出す(選び直し用)

使い方:
    python -m material_collector.face_check 作業フォルダ scripts/<名前>_scenes.txt --name 主人公の名前

    作業フォルダは auto_images と同じ(candidates.json と 選んだ画像/ があるところ)。
    結果は画面と 作業フォルダ/顔の照合.txt に出る。別人の疑いがあると終了コード 1。

限界(結果は「怪しい番号を知らせるもの」として使い、最後は画像を見て決める):
  ・若い頃と晩年のように年が離れた写真、サングラスで目が隠れた写真は、本人でも点数が下がることがある
  ・アニメ・イラストの顔は比べられない(役の絵に「|声優の名前」を付けた番号は、疑いと出ても気にしなくてよい)
  ・横顔・小さすぎる顔は見つからないことがある(「顔が見つからない」と出る)

顔の検出と照合のモデル(OpenCV の YuNet と SFace)は、最初の1回だけ ~/.cache/material_collector に取ってくる。
`pip install "opencv-python-headless<5"` が要る。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

from .auto_images import UA, load_image, search_yahoo
from .html_sheet import parse_scene_table

MODEL_DIR = Path.home() / ".cache" / "material_collector"
MODELS = {
    "yunet.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "sface.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
SAME = 0.363  # SFace のコサイン類似度で「同じ人」とみなす目安(OpenCV の推奨値)
REF_SEARCH = 24  # 見本を作るために見る検索結果の数
DETECT_SIDE = 640  # 顔を探すときの画像の長い辺(1920px のままだと顔が見つからなかった)


def person_rows(table_text: str, main_name: str) -> list[dict]:
    """人の写真の番号と、写っているはずの人の名前を返す(画像リストと同じ通し番号)。"""
    rows, no = [], 0
    for seg in parse_scene_table(table_text):
        for kw, caption in zip(seg["keywords"], seg["captions"]):
            no += 1
            if "いらすとや" in kw.ja:
                continue
            if caption:
                names = split_names(caption)
            elif main_name and main_name in kw.ja.replace(" ", ""):
                names = [main_name]
            else:
                continue
            rows.append({"no": no, "ja": kw.ja, "names": names})
    return rows


def split_names(caption: str) -> list[str]:
    """名前のテロップを人ごとに分ける(「山田康雄・納谷悟朗」→ 2人)。

    「リー・マーヴィン」「モンキー・パンチ」のように、カタカナだけの切れはしができる「・」は、
    1人の名前の中の点なので分けない。
    """
    caption = caption.replace("、", "/").replace("，", "/")
    names = []
    for chunk in caption.split("/"):
        parts = [p.strip() for p in chunk.split("・") if p.strip()]
        if any(re.fullmatch(r"[ァ-ヴー]+", p) for p in parts):
            names.append(chunk.strip())
        else:
            names.extend(parts)
    return [n for n in names if n]


def ensure_models() -> dict[str, Path]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, url in MODELS.items():
        path = MODEL_DIR / name
        if not path.exists() or path.stat().st_size < 10000:  # 1KB に満たないのは Git LFS の目印だけのファイル
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        paths[name] = path
    return paths


class FaceMatcher:
    def __init__(self) -> None:
        import cv2  # 使うときだけ読む(入っていなければ案内を出す)
        import numpy as np

        self.cv2, self.np = cv2, np
        paths = ensure_models()
        self.det = cv2.FaceDetectorYN.create(str(paths["yunet.onnx"]), "", (320, 320), 0.7)
        self.rec = cv2.FaceRecognizerSF.create(str(paths["sface.onnx"]), "")

    def faces(self, img: Image.Image) -> list:
        """画像の顔ごとの特徴を返す。"""
        rgb = img.convert("RGB")
        rgb.thumbnail((DETECT_SIDE, DETECT_SIDE))  # 大きな写真のままだと顔が見つからないことがある
        if min(rgb.size) < 40:
            return []
        arr = self.cv2.cvtColor(self.np.asarray(rgb), self.cv2.COLOR_RGB2BGR)
        self.det.setInputSize((arr.shape[1], arr.shape[0]))
        _, found = self.det.detect(arr)
        if found is None:
            return []
        return [self.rec.feature(self.rec.alignCrop(arr, f)) for f in found]

    def score(self, a, b) -> float:
        return float(self.rec.match(a, b, self.cv2.FaceRecognizerSF_FR_COSINE))


def build_reference(matcher: FaceMatcher, session: requests.Session, name: str, hint: str = "") -> list:
    """名前の検索結果から、たがいに似ている顔のいちばん大きなまとまりを「本人の見本」にする。

    hint は区切り表の検索ワード(「今井正 映画監督 写真」など)。肩書きが入っていると、
    同じ名前の別人(今井正という名前の別の人)が見本に混ざりにくい。
    """
    cands = []
    queries = [hint] if hint and name in hint else []
    queries += [f"{name} 写真", name]
    for query in queries:
        try:
            cands += search_yahoo(session, query)
        except Exception:
            pass
        time.sleep(0.8)
    feats, seen = [], set()
    for cand in cands:
        if len(feats) >= REF_SEARCH or cand["orig"] in seen:
            continue
        seen.add(cand["orig"])
        try:
            img = load_image(session.get(cand["thumb"], timeout=15).content)
        except Exception:
            img = None
        if img is None:
            continue
        found = matcher.faces(img)
        if len(found) == 1:  # 何人も写った写真は、どの顔が本人か分からないので見本にしない
            feats.append(found[0])
    best: list = []
    for f in feats:
        group = [g for g in feats if matcher.score(f, g) >= SAME]
        if len(group) > len(best):
            best = group
    return best if len(best) >= 3 else []


def best_score(matcher: FaceMatcher, faces: list, ref: list) -> float:
    return max((matcher.score(f, r) for f in faces for r in ref), default=0.0)


def check(work: Path, table: Path, main_name: str) -> tuple[list[str], bool]:
    rows = person_rows(table.read_text(encoding="utf-8"), main_name)
    data = json.loads((work / "candidates.json").read_text(encoding="utf-8"))
    chosen = work / "選んだ画像"
    matcher = FaceMatcher()
    session = requests.Session()
    session.headers["User-Agent"] = UA
    refs: dict[str, list] = {}
    lines, suspicious = [], False
    for row in rows:
        files = sorted(chosen.glob(f"{row['no']:03d}_*"))
        if not files:
            continue
        faces = matcher.faces(Image.open(files[0]))
        if not faces:
            lines.append(f"{row['no']:03d} {row['ja']}: 顔が見つからない(横顔・小さい顔・絵。画像を見て確かめる)")
            continue
        for name in row["names"]:
            if name not in refs:
                refs[name] = build_reference(matcher, session, name, row["ja"])
            ref = refs[name]
            if not ref:
                lines.append(f"{row['no']:03d} {name}: 見本の顔が集まらず確かめられない(画像を見て確かめる)")
                continue
            score = best_score(matcher, faces, ref)
            if score >= SAME:
                lines.append(f"{row['no']:03d} {name}: 本人らしい({score:.2f})")
                continue
            suspicious = True
            lines.append(f"{row['no']:03d} {name}: ★別人の疑い({score:.2f}) {row['ja']}")
            # 同じ番号の候補から、見本に合うものを大きい順に出す(選び直し用)
            good = []
            for k, cand in enumerate(data.get(str(row["no"]), {}).get("cands", []), start=1):
                try:
                    img = load_image(session.get(cand["thumb"], timeout=15).content)
                except Exception:
                    img = None
                if img is None:
                    continue
                s = best_score(matcher, matcher.faces(img), ref)
                if s >= SAME:
                    good.append((cand["w"] * cand["h"], k, s, cand))
            if good:
                good.sort(reverse=True)
                lines.append("      選び直し候補: " + "、".join(f"{k}番({c['w']}x{c['h']}・{s:.2f})" for _, k, s, c in good))
            else:
                lines.append("      候補の中に本人らしい顔がない(検索ワードを変えて候補を集め直す)")
    return lines, suspicious


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("work", type=Path, help="auto_images の作業フォルダ")
    parser.add_argument("table", type=Path, help="区切り表")
    parser.add_argument("--name", required=True, help="主人公の名前(区切り表の検索ワードに入っている書き方)")
    args = parser.parse_args(argv)
    try:
        lines, suspicious = check(args.work, args.table, args.name)
    except ImportError:
        print('顔の照合に OpenCV が要ります: pip install "opencv-python-headless<5"')
        return 2
    text = "\n".join(lines)
    print(text)
    print("別人の疑い: " + ("あり(★の番号を見て、別人なら選び直し候補から選び直す)" if suspicious else "なし"))
    (args.work / "顔の照合.txt").write_text(text + "\n", encoding="utf-8")
    return 1 if suspicious else 0


if __name__ == "__main__":
    sys.exit(main())
