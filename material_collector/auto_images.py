"""区切り表の検索ワードで画像の候補を集め、選んだ画像を保存する(Yahoo!画像検索を使う)。

ユーザーの希望(「画像選びも勝手にやってくれるとすっごい助かる」)。Claude がクラウドで画像を選び、
画像リスト(HTML)に最初から入れた状態で渡すための道具。

使い方:
    # 1. 候補を集めて、番号ごとの候補の一覧画像(コンタクトシート)を作る
    python -m material_collector.auto_images candidates scripts/台本_scenes.txt 作業フォルダ

    # 2. 一覧画像を見て、作業フォルダ/picks.txt に「番号: 候補の番号」を書く(例: 「12: 3」。合うものがなければ「12: -」)
    #    本や雑誌に載った写真は、写真の所だけ切り抜く: 「3: 1 crop=0.58,0.03,0.96,0.38」(左,上,右,下。幅と高さに対する割合)

    # 3. 選んだ画像を保存する(作業フォルダ/選んだ画像/001_ワード.jpg)
    python -m material_collector.auto_images fetch 作業フォルダ

    # 4. 画像入りの画像リストを作る
    python -m material_collector.html_sheet 台本.txt 区切り表.txt 出力.html --title 名前 --images 作業フォルダ/選んだ画像
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .html_sheet import parse_scene_table

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PER_KEYWORD = 8
THUMB = 220
MAX_SIDE = 1280
SHEET_ROWS = 4  # 一覧画像1枚に何番分のせるか


def numbered_keywords(table_text: str) -> list[dict]:
    """画像リストと同じ通し番号で、検索ワードと場面を返す。"""
    rows = []
    for seg in parse_scene_table(table_text):
        for kw in seg["keywords"]:
            rows.append({"no": len(rows) + 1, "ja": kw.ja, "en": kw.en, "topic": seg["topic"]})
    return rows


def search_yahoo(session: requests.Session, query: str) -> list[dict]:
    url = "https://search.yahoo.co.jp/image/search?" + urllib.parse.urlencode({"p": query})
    text = session.get(url, timeout=20).text
    found, seen = [], set()
    pattern = re.compile(
        r'"thumbnail":\{"url":"(?P<thumb>[^"]+)".*?"original":\{"url":"(?P<orig>[^"]+)","height":(?P<h>\d+),"width":(?P<w>\d+)'
        r'.*?"refererUrl":"(?P<page>[^"]*)"'
    )
    for m in pattern.finditer(text):
        orig = m.group("orig").encode().decode("unicode_escape") if "\\u" in m.group("orig") else m.group("orig")
        if orig in seen:
            continue
        seen.add(orig)
        found.append({"thumb": m.group("thumb"), "orig": orig, "w": int(m.group("w")), "h": int(m.group("h")),
                      "page": m.group("page")})
    return found


def _font(size: int):
    for path in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_image(data: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.mode in ("RGBA", "LA", "P"):
            # 透明な所(いらすとやなど)は白にする。そのままRGBにすると黒くなる
            img = img.convert("RGBA")
            back = Image.new("RGB", img.size, "white")
            back.paste(img, mask=img.getchannel("A"))
            return back
        return img.convert("RGB")
    except Exception:
        return None


def cmd_candidates(table: Path, work: Path) -> int:
    rows = numbered_keywords(table.read_text(encoding="utf-8"))
    work.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = UA
    cand_path = work / "candidates.json"
    data = json.loads(cand_path.read_text(encoding="utf-8")) if cand_path.exists() else {}
    for row in rows:
        key = str(row["no"])
        if key in data and data[key]["cands"]:
            continue
        cands = search_yahoo(session, row["ja"])
        if len(cands) < 4 and row["en"]:
            cands += search_yahoo(session, row["en"])
        data[key] = {**row, "cands": cands[:PER_KEYWORD]}
        print(f"{row['no']:03d} {row['ja']}: 候補{len(data[key]['cands'])}件", flush=True)
        time.sleep(0.8)
    cand_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    font, small = _font(22), _font(18)
    sheets = work / "一覧"
    sheets.mkdir(exist_ok=True)
    keys = [str(r["no"]) for r in rows]
    for start in range(0, len(keys), SHEET_ROWS):
        chunk = keys[start:start + SHEET_ROWS]
        sheet = Image.new("RGB", (PER_KEYWORD * (THUMB + 8) + 8, len(chunk) * (THUMB + 70)), "white")
        draw = ImageDraw.Draw(sheet)
        for r, key in enumerate(chunk):
            item = data[key]
            y = r * (THUMB + 70)
            draw.text((8, y + 4), f"{int(key):03d} {item['ja']}  ／ 場面: {item['topic']}", fill="black", font=font)
            for c, cand in enumerate(item["cands"]):
                try:
                    img = load_image(session.get(cand["thumb"], timeout=15).content)
                except Exception:
                    img = None
                x = 8 + c * (THUMB + 8)
                if img:
                    img.thumbnail((THUMB, THUMB))
                    sheet.paste(img, (x + (THUMB - img.width) // 2, y + 36 + (THUMB - img.height) // 2))
                draw.rectangle([x, y + 36, x + 30, y + 62], fill="red")
                draw.text((x + 6, y + 36), str(c + 1), fill="white", font=font)
                draw.text((x + 34, y + 38), f"{cand['w']}x{cand['h']}", fill="blue", font=small)
        out = sheets / f"{int(chunk[0]):03d}-{int(chunk[-1]):03d}.jpg"
        sheet.save(out, quality=80)
        print("一覧:", out)
    return 0


def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:40]


def cmd_fetch(work: Path) -> int:
    data = json.loads((work / "candidates.json").read_text(encoding="utf-8"))
    picks = {}
    for line in (work / "picks.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)\s*:\s*([\d-]+)(?:\s+crop=([\d.]+),([\d.]+),([\d.]+),([\d.]+))?", line)
        if m:
            crop = tuple(float(v) for v in m.groups()[2:]) if m.group(3) else None
            picks[m.group(1).lstrip("0") or "0"] = (m.group(2), crop)
    out = work / "選んだ画像"
    out.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = UA
    missing = []
    for key, item in sorted(data.items(), key=lambda kv: int(kv[0])):
        pick, crop = picks.get(key, (None, None))
        name = f"{int(key):03d}_{safe_name(item['ja'])}.jpg"
        if (out / name).exists():
            continue
        if not pick or pick == "-":
            missing.append(int(key))
            continue
        cand = item["cands"][int(pick) - 1]
        img = None
        for url in (cand["orig"], cand["thumb"]):
            try:
                resp = session.get(url, timeout=20, headers={"Referer": cand["page"] or "https://search.yahoo.co.jp/"})
                img = load_image(resp.content) if resp.ok else None
            except Exception:
                img = None
            if img and min(img.size) >= 120:
                break
        if not img:
            missing.append(int(key))
            print(f"{int(key):03d} 保存できませんでした")
            continue
        if crop:
            # 本や雑誌の、写真の所だけ切り抜く(文字を入れずに、写真に見えるようにする)
            l, t, r, b = crop
            img = img.crop((round(l * img.width), round(t * img.height), round(r * img.width), round(b * img.height)))
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        img.save(out / name, quality=90)
        print(f"{int(key):03d} 保存 {img.size[0]}x{img.size[1]}")
    (work / "見つからなかった番号.txt").write_text("\n".join(map(str, missing)) + "\n", encoding="utf-8")
    print("入れられなかった番号:", ", ".join(map(str, missing)) or "なし")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("table", type=Path)
    c.add_argument("work", type=Path)
    f = sub.add_parser("fetch")
    f.add_argument("work", type=Path)
    args = parser.parse_args(argv)
    return cmd_candidates(args.table, args.work) if args.cmd == "candidates" else cmd_fetch(args.work)


if __name__ == "__main__":
    sys.exit(main())
