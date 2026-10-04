"""台本と区切り表から、台本順に番号を振った画像の検索リスト(Google画像検索ボタン付き)をHTML1ファイルで作る。

使い方:
    python -m material_collector.html_sheet 台本.txt 区切り表.txt --title 西崎義展
    (出力は「西崎義展_素材シート.html」)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .preset_keywords import parse_keyword_items
from .viewer import SPEAKER_PATTERN

TEMPLATE_PATH = Path(__file__).with_name("html_sheet_template.html")
START_PATTERN = re.compile(r"^\s*(\d+)\s*[:：]\s*(.*)$")


def parse_scene_table(text: str) -> list[dict]:
    """区切り表を読む。「## 見出し」と「開始行: 日本語=English, ...」の並び。"""
    segments: list[dict] = []
    topic = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            topic = line.lstrip("#").strip()
            continue
        if line.startswith("#"):
            continue
        match = START_PATTERN.match(line)
        if not match:
            raise ValueError(f"区切り表の書式が読めません: {line!r}")
        segments.append({"topic": topic, "start": int(match.group(1)), "keywords": parse_keyword_items(match.group(2))})
    starts = [s["start"] for s in segments]
    if starts != sorted(set(starts)):
        raise ValueError("区切り表の開始行は、小さい順に重複なく並べてください。")
    return segments


def script_lines(script_text: str) -> list[dict]:
    lines = []
    for raw in script_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        match = SPEAKER_PATTERN.match(raw)
        if match:
            lines.append({"speaker": match.group("speaker"), "text": match.group("line")})
        else:
            lines.append({"speaker": "", "text": raw})
    return lines


def build_sheet(script_text: str, table_text: str, title: str) -> str:
    lines = script_lines(script_text)
    segments = parse_scene_table(table_text)
    if not segments or segments[0]["start"] != 1:
        raise ValueError("区切り表の最初の開始行は 1 にしてください。")
    if segments[-1]["start"] > len(lines):
        raise ValueError(f"開始行 {segments[-1]['start']} が台本の行数({len(lines)}行)を超えています。")
    number = 0
    for i, segment in enumerate(segments):
        end = segments[i + 1]["start"] - 1 if i + 1 < len(segments) else len(lines)
        segment["end"] = end
        segment["lines"] = lines[segment["start"] - 1 : end]
        if not segment["keywords"]:
            raise ValueError(f"{segment['start']}行目からの区切りに画像がありません。どの区切りにも1枚以上入れてください。")
        images = []
        for keyword in segment.pop("keywords"):
            number += 1
            # 「日本語=英語=母語」の3つ目は母語の検索ワード
            en, _, native = keyword.en.partition("=")
            images.append({"no": number, "ja": keyword.ja, "en": en.strip() or keyword.ja, "native": native.strip()})
        segment["images"] = images

    data = {"title": title, "segments": segments}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("__TITLE__", title).replace("/*__DATA__*/null", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="台本と区切り表から、素材確認用のHTMLを作る")
    parser.add_argument("script", type=Path)
    parser.add_argument("table", type=Path)
    parser.add_argument("output", type=Path, nargs="?", help="省略すると「タイトル_素材シート.html」")
    parser.add_argument("--title", required=True)
    args = parser.parse_args(argv)
    html = build_sheet(
        args.script.read_text(encoding="utf-8"), args.table.read_text(encoding="utf-8"), args.title
    )
    output = args.output or Path(f"{args.title}_素材シート.html")
    output.write_text(html, encoding="utf-8")
    print(f"作成しました: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
