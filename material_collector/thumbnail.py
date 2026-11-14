"""サムネ案の表(scripts/<名前>_thumb.txt)から、YouTubeのサムネを作るHTMLを作る。

    python -m material_collector.thumbnail scripts/oyama_yasuharu_thumb.txt 出力.html

表の書き方:

    # メモ(# で始まる行は読み飛ばす)
    名前: 大山康晴
    名前の表示: 大山 康晴                         ← サムネに出す名前(姓と名の間に空白など。なくてもよい)
    写真: 大山康晴 晩年=Yasuharu Oyama          ← 写真の検索ワード。書いた順に 1, 2, ... 番
    写真: 大山康晴 若い頃=young Yasuharu Oyama

    ## 案1                                       ← 案は3つまで(YouTubeの「テストと比較」が3枚まで)
    型: 顔アップ                                  ← 顔アップ / 右に写真 / 全面写真 / 比較 / 文字だけ
                                                     顔アップ: 顔を大きく、上に赤い一言(文字)、下に黄色の名前。白黒になる
                                                     吹き出し: カラーの写真、上に黄色の一言(上の文字)、下に大きな赤い文字、
                                                               ゆっくりを大きめにしてセリフの吹き出しを付ける
                                                     文字だけ: 黒い背景に文字だけ
    上の文字: 入門した次の日にボコボコ            ← 吹き出しの型の上の一言
    霊夢のセリフ: 戦争に病気まで…                 ← 吹き出し(どの型でも付く。| で改行)
    魔理沙のセリフ: それでも必ずはい上がる
    帯: 永世五冠・タイトル80期                     ← 上の赤い帯の文字(なくてもよい)
    文字: 69歳まで|{A級}にいた男                   ← | で改行、{ } で囲んだ所が強調の色になる
    写真: 1                                       ← 使う写真の番号。比較は「1, 2」
    タイトル: 大山康晴｜なぜ手術後も指し続けたのか？【ゆっくり生涯解説】 ← この案と組にする動画タイトル(なくてもよい)。HTMLにコピーボタン付きで出る
    ラベル: 20歳, 69歳                            ← 比較のときの左右の文字
    ゆっくりの大きさ: 1.5                         ← 1 がふつう。2 で2倍(顔アップは1でもスマホで見える大きさ)
    顔の大きさ: 大                                ← 顔アップは「大」が標準(目が一言のすぐ下に来るまで顔を大きく。おでこは隠れる)。「ふつう」で顔全体を出す
    白黒: はい                                    ← 写真を白黒に(顔アップは最初から白黒)
    霊夢: 驚き                                    ← ふつう にやり 驚き 焦り 怒り 泣き 笑顔 なし
                                                     書かなければ一言から自動で決まる(FACE_RULES)
    魔理沙: にやり
    色: 黄                                        ← 強調の色: 黄 / 赤 / 水色
"""

from __future__ import annotations

import argparse
import subprocess
import base64
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from material_collector.thumb_faces import ASSETS, CHARS, EXPRESSIONS

TEMPLATE_PATH = Path(__file__).with_name("thumbnail_template.html")
LAYOUTS = ["顔アップ", "吹き出し", "右に写真", "全面写真", "比較", "文字だけ"]
FACE_CHOICES = EXPRESSIONS + ["なし"]
COLORS = {"黄": "#ffe600", "赤": "#ff3b3b", "水色": "#46d4ff"}
CHAR_KEYS = {"霊夢": "reimu", "魔理沙": "marisa"}

# 一言から霊夢・魔理沙の表情を決める決まり。上から順に見て、最初に当てはまったものを使う。
# サムネ作成ページでも同じ決まりを使い、一言を書きかえると表情も自動で変わる。
FACE_RULES = [
    # 悲しい話・苦しい話(「死ぬまで〜」は記録の話なので除く)
    (r"がん|癌|病|亡くな|最期|命|涙|消え|失っ|孤独|自殺|悲|奪われ|追われ|事故|別れ|死(?!ぬまで)", "驚き", "泣き"),
    # ひどい目にあった話
    (r"裏切|いじめ|殴|ボコ|差別|追放|クビ|騙|だま|怒", "怒り", "焦り"),
    # 怖い話・ヤバい話
    (r"ヤバ|やば|狂|地獄|恐|怖|残酷|残虐|閲覧注意|呪|闇", "焦り", "驚き"),
    # すごい話・記録の話・不思議な話(どれにも当てはまらないときもこれ)
    (r"", "驚き", "にやり"),
]


def guess_faces(text: str) -> tuple[str, str]:
    """一言に合う(霊夢, 魔理沙)の表情。"""
    for pattern, reimu, marisa in FACE_RULES:
        if re.search(pattern, text):
            return reimu, marisa
    return "驚き", "にやり"


def parse_thumb_table(text: str) -> dict:
    name = ""
    name_display = ""
    photos: list[dict] = []
    plans: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        if line.startswith("##"):
            plans.append({"title": line.lstrip("#").strip(), "layout": "右に写真", "band": "", "text": "",
                          "photos": [1], "labels": ["", ""], "mono": False, "top": "", "reimu_says": "", "marisa_says": "", "face_scale": 1.0, "big_face": None, "reimu": None, "marisa": None, "color": "黄", "video_title": ""})
            continue
        key, sep, value = re.split(r"([:：])", line, maxsplit=1) if re.search(r"[:：]", line) else (line, "", "")
        if not sep:
            raise ValueError(f"「項目: 内容」の形になっていません: {line}")
        key, value = key.strip(), value.strip()
        if not plans:
            if key == "名前":
                name = value
            elif key == "名前の表示":
                name_display = value
            elif key == "写真":
                ja, _, en = value.partition("=")
                photos.append({"ja": ja.strip(), "en": en.strip() or ja.strip()})
            else:
                raise ValueError(f"案(## 案1)の前に書けるのは「名前」「名前の表示」「写真」だけです: {line}")
            continue
        plan = plans[-1]
        if key == "型":
            if value not in LAYOUTS:
                raise ValueError(f"型は {' / '.join(LAYOUTS)} のどれかにしてください: {line}")
            plan["layout"] = value
            plan["mono"] = plan["mono"] or value == "顔アップ"
        elif key == "上の文字":
            plan["top"] = value
        elif key in ("霊夢のセリフ", "魔理沙のセリフ"):
            plan["reimu_says" if key.startswith("霊夢") else "marisa_says"] = value
        elif key == "帯":
            plan["band"] = value
        elif key == "文字":
            plan["text"] = value
        elif key == "タイトル":  # この案と組にする動画タイトル(「名前｜タイトル」の形)
            plan["video_title"] = value
        elif key == "写真":
            plan["photos"] = [int(n) for n in re.split(r"[,、，\s]+", value) if n]
        elif key == "ラベル":
            labels = [s.strip() for s in re.split(r"[,、，]", value)]
            plan["labels"] = (labels + ["", ""])[:2]
        elif key in CHAR_KEYS:
            if value not in FACE_CHOICES:
                raise ValueError(f"表情は {' '.join(FACE_CHOICES)} のどれかにしてください: {line}")
            plan[CHAR_KEYS[key]] = value
        elif key == "ゆっくりの大きさ":
            try:
                plan["face_scale"] = float(value)
            except ValueError:
                raise ValueError(f"ゆっくりの大きさは数字で書いてください(1 がふつう、2 で2倍): {line}") from None
            if not 0.5 <= plan["face_scale"] <= 2.5:
                raise ValueError(f"ゆっくりの大きさは 0.5〜2.5 にしてください: {line}")
        elif key == "顔の大きさ":
            if value not in ("大", "ふつう"):
                raise ValueError(f"顔の大きさは「大」か「ふつう」にしてください: {line}")
            plan["big_face"] = value == "大"
        elif key == "白黒":
            if value not in ("はい", "いいえ"):
                raise ValueError(f"白黒は「はい」か「いいえ」にしてください: {line}")
            plan["mono"] = value == "はい"
        elif key == "色":
            if value not in COLORS:
                raise ValueError(f"色は {' / '.join(COLORS)} のどれかにしてください: {line}")
            plan["color"] = value
        else:
            raise ValueError(f"知らない項目です: {line}")
    if not name:
        raise ValueError("「名前: 〇〇」を書いてください。")
    if not photos:
        raise ValueError("「写真: 検索ワード」を1つ以上書いてください。")
    if not plans:
        raise ValueError("案(## 案1)を1つ以上書いてください。")
    if len(plans) > 3:
        raise ValueError("案は3つまでにしてください(YouTubeのテストと比較が3枚までのため)。")
    for plan in plans:
        auto_reimu, auto_marisa = guess_faces(plan["text"])  # 書いていなければ一言から決める
        plan["reimu"] = plan["reimu"] or auto_reimu
        plan["marisa"] = plan["marisa"] or auto_marisa
        if plan["big_face"] is None:  # 顔アップは顔を大きくするのが標準(ユーザーと決めた)
            plan["big_face"] = plan["layout"] == "顔アップ"
        need = {"比較": 2, "文字だけ": 0}.get(plan["layout"], 1)
        if len(plan["photos"]) < need:
            raise ValueError(f"{plan['title']}: 比較の型は写真を2つ(例: 写真: 1, 2)書いてください。")
        for n in plan["photos"]:
            if not 1 <= n <= len(photos):
                raise ValueError(f"{plan['title']}: 写真 {n} 番がありません(写真は {len(photos)} つ)。")
        if not plan["text"]:
            raise ValueError(f"{plan['title']}: 「文字: 〇〇」を書いてください。")
    return {"name": name, "name_display": name_display or name, "photos": photos, "plans": plans}


def face_data_urls() -> dict:
    """表情差分を WebP にして埋め込む(PNGのままだと重いため)。"""
    faces = {}
    for char in CHARS:
        for expr in EXPRESSIONS:
            buf = io.BytesIO()
            Image.open(ASSETS / f"{char}_{expr}.png").save(buf, "WEBP", quality=90, method=6)
            faces[f"{char}_{expr}"] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return faces


def find_face(image_bytes: bytes) -> dict:
    """写真のいちばん大きい顔の位置(写真のピクセルで中心と高さ)。

    顔が写真の端までいっぱいだと見つけにくいので、まわりに余白を足してから探す。
    見つからないとき(OpenCV がないときも)は、人物写真によくある位置(まん中のやや上)と考える。
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    fallback = {"cx": img.width / 2, "cy": img.height * 0.42, "h": img.height * 0.5,
                "iw": img.width, "ih": img.height, "guessed": True}
    try:
        import cv2
    except ImportError:
        return fallback
    pad = int(max(img.size) * 0.25)
    gray = cv2.copyMakeBorder(np.asarray(img), pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    min_side = max(24, min(img.size) // 8)
    found = []
    for xml in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"):
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        found += list(detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(min_side, min_side)))
    if not found:
        return fallback
    x, y, w, h = max(found, key=lambda f: f[2] * f[3])
    return {"cx": float(x + w / 2 - pad), "cy": float(y + h / 2 - pad), "h": float(h), "iw": img.width, "ih": img.height}


def embed_photos(photo_paths: dict[int, Path]) -> tuple[dict, dict]:
    """ページに最初から入れておく写真(data URL)と、その顔の位置。"""
    embedded, faces = {}, {}
    for no, path in photo_paths.items():
        raw = path.read_bytes()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if max(img.size) > 1600:  # ページが重くならないように縮める
            img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=92)
        raw = buf.getvalue()
        embedded[str(no)] = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
        faces[str(no)] = find_face(raw)
    return embedded, faces


def build_thumbnail_page(table_text: str, photo_paths: dict[int, Path] | None = None) -> str:
    data = parse_thumb_table(table_text)
    for no in photo_paths or {}:
        if not 1 <= no <= len(data["photos"]):
            raise ValueError(f"写真 {no} 番は表にありません(写真は {len(data['photos'])} つ)。")
    data["embedded"], data["face_boxes"] = embed_photos(photo_paths or {})
    data["id"] = hashlib.sha1(("thumb\n" + data["name"] + "\n" + json.dumps(data["photos"], ensure_ascii=False)).encode("utf-8")).hexdigest()[:12]
    data["expressions"] = FACE_CHOICES
    data["face_rules"] = [[pattern, reimu, marisa] for pattern, reimu, marisa in FACE_RULES]
    data["layouts"] = LAYOUTS
    data["colors"] = COLORS
    data["faces"] = face_data_urls()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("__TITLE__", data["name"]).replace("/*__DATA__*/null", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="サムネ案の表から、YouTubeのサムネを作るHTMLを作る")
    parser.add_argument("table", type=Path)
    parser.add_argument("output", type=Path, nargs="?", help="省略すると「名前_thumbnail.html」")
    parser.add_argument("--photo", action="append", default=[], metavar="番号=ファイル",
                        help="写真を最初から入れておく(例: --photo 1=oyama.jpg)。顔の位置に合わせて自動で拡大・配置する")
    parser.add_argument("--render", type=Path, metavar="フォルダ",
                        help="できたサムネを案ごとにJPGで保存する(Node.js の Playwright が要る)")
    args = parser.parse_args(argv)
    photo_paths = {}
    for item in args.photo:
        no, sep, path = item.partition("=")
        if not sep or not no.strip().isdigit():
            parser.error(f"--photo は「番号=ファイル」で書いてください: {item}")
        photo_paths[int(no)] = Path(path)
    html = build_thumbnail_page(args.table.read_text(encoding="utf-8"), photo_paths)
    name = parse_thumb_table(args.table.read_text(encoding="utf-8"))["name"]
    output = args.output or Path(f"{name}_thumbnail.html")
    output.write_text(html, encoding="utf-8")
    print(f"作成しました: {output}")
    if args.render:
        args.render.mkdir(parents=True, exist_ok=True)
        script = Path(__file__).with_name("render_thumbnails.js")
        subprocess.run(["node", str(script), str(output.resolve()), str(args.render.resolve()), name], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
