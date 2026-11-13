"""サムネ案の表(scripts/<名前>_thumb.txt)から、YouTubeのサムネを作るHTMLを作る。

    python -m material_collector.thumbnail scripts/oyama_yasuharu_thumb.txt 出力.html

表の書き方:

    # メモ(# で始まる行は読み飛ばす)
    名前: 大山康晴
    写真: 大山康晴 晩年=Yasuharu Oyama          ← 写真の検索ワード。書いた順に 1, 2, ... 番
    写真: 大山康晴 若い頃=young Yasuharu Oyama

    ## 案1                                       ← 案は3つまで(YouTubeの「テストと比較」が3枚まで)
    型: 右に写真                                  ← 右に写真 / 全面写真 / 比較
    帯: 永世五冠・タイトル80期                     ← 上の赤い帯の文字(なくてもよい)
    文字: 69歳まで|{A級}にいた男                   ← | で改行、{ } で囲んだ所が強調の色になる
    写真: 1                                       ← 使う写真の番号。比較は「1, 2」
    ラベル: 20歳, 69歳                            ← 比較のときの左右の文字
    霊夢: 驚き                                    ← ふつう にやり 驚き 焦り 怒り 泣き 笑顔
    魔理沙: にやり
    色: 黄                                        ← 強調の色: 黄 / 赤 / 水色
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image

from material_collector.thumb_faces import ASSETS, CHARS, EXPRESSIONS

TEMPLATE_PATH = Path(__file__).with_name("thumbnail_template.html")
LAYOUTS = ["右に写真", "全面写真", "比較"]
COLORS = {"黄": "#ffe600", "赤": "#ff3b3b", "水色": "#46d4ff"}
CHAR_KEYS = {"霊夢": "reimu", "魔理沙": "marisa"}


def parse_thumb_table(text: str) -> dict:
    name = ""
    photos: list[dict] = []
    plans: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        if line.startswith("##"):
            plans.append({"title": line.lstrip("#").strip(), "layout": "右に写真", "band": "", "text": "",
                          "photos": [1], "labels": ["", ""], "reimu": "ふつう", "marisa": "ふつう", "color": "黄"})
            continue
        key, sep, value = re.split(r"([:：])", line, maxsplit=1) if re.search(r"[:：]", line) else (line, "", "")
        if not sep:
            raise ValueError(f"「項目: 内容」の形になっていません: {line}")
        key, value = key.strip(), value.strip()
        if not plans:
            if key == "名前":
                name = value
            elif key == "写真":
                ja, _, en = value.partition("=")
                photos.append({"ja": ja.strip(), "en": en.strip() or ja.strip()})
            else:
                raise ValueError(f"案(## 案1)の前に書けるのは「名前」と「写真」だけです: {line}")
            continue
        plan = plans[-1]
        if key == "型":
            if value not in LAYOUTS:
                raise ValueError(f"型は {' / '.join(LAYOUTS)} のどれかにしてください: {line}")
            plan["layout"] = value
        elif key == "帯":
            plan["band"] = value
        elif key == "文字":
            plan["text"] = value
        elif key == "写真":
            plan["photos"] = [int(n) for n in re.split(r"[,、，\s]+", value) if n]
        elif key == "ラベル":
            labels = [s.strip() for s in re.split(r"[,、，]", value)]
            plan["labels"] = (labels + ["", ""])[:2]
        elif key in CHAR_KEYS:
            if value not in EXPRESSIONS:
                raise ValueError(f"表情は {' '.join(EXPRESSIONS)} のどれかにしてください: {line}")
            plan[CHAR_KEYS[key]] = value
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
        need = 2 if plan["layout"] == "比較" else 1
        if len(plan["photos"]) < need:
            raise ValueError(f"{plan['title']}: 比較の型は写真を2つ(例: 写真: 1, 2)書いてください。")
        for n in plan["photos"]:
            if not 1 <= n <= len(photos):
                raise ValueError(f"{plan['title']}: 写真 {n} 番がありません(写真は {len(photos)} つ)。")
        if not plan["text"]:
            raise ValueError(f"{plan['title']}: 「文字: 〇〇」を書いてください。")
    return {"name": name, "photos": photos, "plans": plans}


def face_data_urls() -> dict:
    """表情差分を WebP にして埋め込む(PNGのままだと重いため)。"""
    faces = {}
    for char in CHARS:
        for expr in EXPRESSIONS:
            buf = io.BytesIO()
            Image.open(ASSETS / f"{char}_{expr}.png").save(buf, "WEBP", quality=90, method=6)
            faces[f"{char}_{expr}"] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return faces


def build_thumbnail_page(table_text: str) -> str:
    data = parse_thumb_table(table_text)
    data["id"] = hashlib.sha1(("thumb\n" + data["name"] + "\n" + json.dumps(data["photos"], ensure_ascii=False)).encode("utf-8")).hexdigest()[:12]
    data["expressions"] = EXPRESSIONS
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
    args = parser.parse_args(argv)
    html = build_thumbnail_page(args.table.read_text(encoding="utf-8"))
    name = parse_thumb_table(args.table.read_text(encoding="utf-8"))["name"]
    output = args.output or Path(f"{name}_thumbnail.html")
    output.write_text(html, encoding="utf-8")
    print(f"作成しました: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
