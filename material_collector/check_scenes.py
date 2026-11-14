"""区切り表の見直し用チェック。画像を切り替えるタイミングが、台本の話とずれていないかを確かめる。

使い方:
    python -m material_collector.check_scenes scripts/台本.txt scripts/台本_scenes.txt

区切り表の各画像には「@きっかけ」を書いておく。その画像を出すきっかけになる、台本の中の言葉:
    57: 関根金次郎=Kinjiro Sekine|関根金次郎 @実力で勝ち取る
    18: いらすとや 熱 子供=irasutoya fever child @腸チフス/熱
  ・「/」で区切ると、どれか1つが出てくればよい
  ・本人の写真で話を続けるときなど、きっかけの言葉がないときは「@-」
このチェックで分かること:
  - きっかけの言葉が、その画像を出しているあいだに出てこない
  - きっかけの言葉が、出し始めの2セリフより後で初めて出てくる(切り替えが早すぎる)
  - きっかけの言葉が、1つ前の画像の最後の2セリフにもう出てくる(切り替えが遅すぎる)
  - 霊夢のセリフから始まっている(あいづち・ツッコミは前の区切りに含める)
  - 長すぎる・短すぎる、きっかけ(@)が書いていない
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import re

from .html_sheet import parse_scene_table, script_utterances

REIMU = "霊夢"
HEAD = 2  # 出し始めの何セリフ以内に、きっかけの言葉が出てくればよいか
MIN_LINES = 2
MAX_LINES = 12  # 話が変わらないなら長くてよいので、目安を大きく超えたときだけ知らせる


def _script_rows(script_text: str) -> list[dict]:
    """空行を除いた1行ごとに、その行が属するセリフ(話者・全文・何番目のセリフか)を返す。

    「」の中で改行しているセリフ(36文字を超えて折り返したもの)は、続きの行も同じセリフとして扱う。
    """
    utterances, line_to_utterance = script_utterances(script_text)
    speakers: dict[int, str] = {}
    rows = [raw.strip() for raw in script_text.splitlines() if raw.strip()]
    for row, u in zip(rows, line_to_utterance):
        if u not in speakers:
            m = re.match(r"^([^「」\s]{1,10})「", row)
            speakers[u] = m.group(1) if m else ""
    return [
        {"speaker": speakers[u], "text": utterances[u], "utt": u, "head": i == 0 or line_to_utterance[i - 1] != u}
        for i, u in enumerate(line_to_utterance)
    ]


def _first_hit(words: list[str], lines: list[dict], first: int, last: int) -> int | None:
    for number in range(first, last + 1):
        if any(w in lines[number - 1]["text"] for w in words):
            return number
    return None


def check(script_text: str, table_text: str) -> list[dict]:
    lines = _script_rows(script_text)
    segments = parse_scene_table(table_text)
    total = len(lines)
    if segments and segments[-1]["start"] > total:
        raise ValueError(f"区切り表の開始行 {segments[-1]['start']} が、台本の行数 {total} を超えています。")
    images = []
    number = 0
    for i, seg in enumerate(segments):
        end = segments[i + 1]["start"] - 1 if i + 1 < len(segments) else total
        span = max(end - seg["start"] + 1, 1)
        count = len(seg["keywords"]) or 1
        for k, kw in enumerate(seg["keywords"]):
            number += 1
            # YMM4に並べるときと同じく、1つの区切りに2枚あれば、セリフを等分して順に出す
            images.append({
                "no": number, "topic": seg["topic"], "ja": kw.ja, "triggers": seg["triggers"][k],
                "first": seg["start"] + span * k // count, "last": seg["start"] + span * (k + 1) // count - 1,
                "seg_start": k == 0,
            })
    for idx, img in enumerate(images):
        first, last = img["first"], img["last"]
        warnings = []
        if img["seg_start"] and first != 1 and lines[first - 1]["speaker"] == REIMU:
            warnings.append("霊夢のセリフから始まっている → 1つ前の区切りに含める")
        words = img["triggers"]
        if words is None:
            warnings.append("きっかけ(@)が書いていない")
        elif words and words != ["-"]:
            hit = _first_hit(words, lines, first, last)
            if hit is None:
                later = _first_hit(words, lines, last + 1, total)
                earlier = _first_hit(words, lines, 1, first - 1)
                where = f"(台本では {later} 行目に出てくる)" if later else (f"(台本では {earlier} 行目に出てくる)" if earlier else "(台本のどこにも出てこない)")
                warnings.append(f"きっかけ「{'/'.join(words)}」が、この画像のあいだに出てこない{where}")
            elif lines[hit - 1]["utt"] - lines[first - 1]["utt"] >= HEAD:
                warnings.append(f"きっかけ「{'/'.join(words)}」は {hit} 行目で初めて出てくる → 切り替えが早すぎる(開始行を {hit} 前後に)")
            if idx > 0 and img["seg_start"]:
                prev = images[idx - 1]
                # 1つ前の画像の最後の2セリフ(出し始めの2セリフは除く)
                last_utt = lines[prev["last"] - 1]["utt"]
                head_utt = lines[prev["first"] - 1]["utt"] + HEAD
                tail_from = next(
                    (r for r in range(prev["first"], prev["last"] + 1) if lines[r - 1]["utt"] >= max(head_utt, last_utt - 1)),
                    prev["last"] + 1,
                )
                early = _first_hit(words, lines, tail_from, prev["last"])
                if early is not None:
                    warnings.append(f"きっかけ「{'/'.join(words)}」は 1つ前の画像の {early} 行目でもう出てくる → 切り替えが遅すぎる(開始行を {early} に)")
        n = len({line["utt"] for line in lines[first - 1 : last]})
        if n > MAX_LINES:
            warnings.append(f"{n}セリフと長い → 話の流れが変わる所で分ける")
        elif n < MIN_LINES and first != 1:
            warnings.append(f"{n}セリフと短い")
        img["lines"] = lines[first - 1 : last]
        img["warnings"] = warnings
    return images


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="区切り表の画像の切り替えが、台本の話とずれていないか確かめる")
    parser.add_argument("script", type=Path)
    parser.add_argument("table", type=Path)
    parser.add_argument("--all", action="store_true", help="警告のない画像も、セリフと一緒に全部出す")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    images = check(args.script.read_text(encoding="utf-8"), args.table.read_text(encoding="utf-8"))
    flagged = [img for img in images if img["warnings"]]
    for img in images:
        if not (args.all or img["warnings"]):
            continue
        print(f"\n[{img['no']}] {img['first']}〜{img['last']}行 {img['ja']}  (## {img['topic']})")
        for w in img["warnings"]:
            print(f"  ⚠ {w}")
        for offset, line in enumerate(img["lines"]):
            if line.get("head", True):
                print(f"    {img['first'] + offset}: {line['speaker']}「{line['text'][:40]}」")
    print(f"\n画像{len(images)}枚のうち、直したほうがよさそうな所があるのは{len(flagged)}枚です。")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
