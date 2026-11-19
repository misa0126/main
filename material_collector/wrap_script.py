"""台本のセリフが長いとき、「」の中で改行する(ユーザーの希望。34文字を超えたら区切りのいいところで改行)。

使い方:
    python -m material_collector.wrap_script scripts/台本.txt [scripts/台本_scenes.txt] [scripts/台本_yomi.txt]

・「」の中が34文字を超えるセリフだけ改行する。34文字以内はそのまま(2026年11月19日に36文字から34文字に変えた。ユーザーの希望)
・霊夢のセリフは、「！」「？」「。」の後ろで 霊夢「」 を分ける(長さに関係なく。『』の中と、セリフの最後は除く。ユーザーの希望)
    霊夢「えっ！そんなことあるの？」 → 霊夢「えっ！」 霊夢「そんなことあるの？」
・行の数がいちばん少なくなるように、区切りのよい所で改行する(「！」「？」「。」の後ろ > 「、」の後ろ > 「』」の後ろ・「『」の前 >
  漢字・カタカナの前の助詞(は・が・を・の など)の後ろ)。同じくらいなら前の行を長くする(34文字以内でいちばん後ろの「、」)
・改行すると「台本の空行を除いた行番号」がずれるので、区切り表と読みの表の行番号も一緒に付け直す
・1つのセリフは2行まで。3行になりそうなときは、2行に収まる所の「、」の後ろでセリフを2つに分ける(ユーザーの希望)
    魔理沙「〜
    〜、」
    魔理沙「〜」
  読みの表を一緒に付けると、分けたセリフの読みも「、」「。」「？」の位置で分ける
・すでに改行してある台本にもう一度かけても、行は増えない(1つにつないでから折り返す)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LIMIT = 34
SENTENCE_SPLIT_SPEAKERS = ("霊夢",)  # 文の終わりごとに「」を分ける話者(ユーザーの希望)
MARK = re.compile(r"、|[。！？!?]+")
SPEAKER = re.compile(r"^(?P<speaker>[^「」\s]+)「(?P<body>.*)$")
SENTENCE_END = "？！。"
PUNCT_AFTER = "、"
STRONG_AFTER = "』"
PARTICLES = "はがをにでともへやの"
HIRAGANA = re.compile(r"[ぁ-ゖ]")


def _break_score(text: str, n: int) -> int:
    """text[:n] の後ろで改行したときの、区切りのよさ(0 は区切りにしない)。"""
    ch = text[n - 1]
    if ch in SENTENCE_END and text[n] not in SENTENCE_END + "」』" and text[:n].count("『") <= text[:n].count("』"):
        return 4  # 文の終わり(「！」「？」「。」の後ろ。『』の中は除く)がいちばん(ユーザーの希望)
    if ch in PUNCT_AFTER:
        return 3
    if ch in STRONG_AFTER:
        return 2
    if text[n] in "『「":
        return 2
    if ch in PARTICLES and not HIRAGANA.match(text[n]):
        return 1
    return 0


def wrap_body(body: str, limit: int = LIMIT) -> list[str]:
    """「」の中身を、limit 文字以内の行に分ける。

    行の数がいちばん少なくなる分け方のうち、区切りのよい所(「！？。」>「、」>「』」>助詞の後ろ)で切る。
    同じくらいなら、ユーザーの例と同じく前の行を長くする(34文字以内でいちばん後ろの「、」)。
    """
    length = len(body)
    if length <= limit:
        return [body]
    for allow_any in (False, True):
        # best[i] = ((行数, -区切りのよさの合計, -切った位置の合計), 直前に切った位置)
        best: dict[int, tuple[tuple[int, int, int], int]] = {0: ((0, 0, 0), -1)}
        for i in range(1, length + 1):
            score = 0 if i == length else _break_score(body, i)
            if i < length and score == 0 and not allow_any:
                continue
            for j in range(max(0, i - limit), i):
                if j not in best:
                    continue
                (lines, neg_score, neg_pos), _ = best[j]
                key = (lines + 1, neg_score - score, neg_pos - (i if i < length else 0))
                if i not in best or key < best[i][0]:
                    best[i] = (key, j)
        if length in best:
            cuts = []
            i = length
            while i > 0:
                cuts.append(i)
                i = best[i][1]
            parts, prev = [], 0
            for c in reversed(cuts):
                parts.append(body[prev:c])
                prev = c
            return parts
    return [body[i : i + limit] for i in range(0, length, limit)]


def _serifs(script_text: str) -> list[tuple[str, str]]:
    """台本を (話者, 中身) の並びにする。「」の中の改行は1つにつなぐ。"""
    serifs: list[list[str]] = []
    open_serif = False
    for raw in script_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = SPEAKER.match(line)
        if match and not open_serif:
            serifs.append([match.group("speaker"), match.group("body")])
        elif serifs:
            serifs[-1][1] += line
        else:
            raise ValueError(f"話者のないセリフがあります: {line!r}")
        open_serif = not serifs[-1][1].endswith("」")
    result = []
    for speaker, body in serifs:
        if not body.endswith("」"):
            raise ValueError(f"「」が閉じていないセリフがあります: {speaker}「{body}")
        result.append((speaker, body[:-1]))
    return result


def _old_starts(script_text: str) -> list[int]:
    """今の台本で、各セリフが何行目から始まるか(空行を除いた行番号)。"""
    starts = []
    number = 0
    open_serif = False
    for raw in script_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        number += 1
        if not open_serif:
            starts.append(number)
        open_serif = not line.endswith("」")
    return starts


def split_serif(body: str, limit: int = LIMIT) -> list[list[str]]:
    """1つのセリフを、2行まで(1行は limit 文字以内)のセリフに分ける(ユーザーの希望)。

    2行に収まるならそのまま。3行になりそうなら、2行に収まる範囲の区切りのよい所(「、」の後ろが一番)で
    セリフを2つに分け、残りも同じように続ける。戻り値はセリフごとの行のリスト。
    """
    rows = wrap_body(body, limit)
    if len(rows) <= 2:
        return [rows]
    best = None
    for p in range(1, min(len(body) - 1, 2 * limit) + 1):
        score = _break_score(body, p)
        if not score or len(wrap_body(body[:p], limit)) > 2:
            continue
        key = (score, p)
        if best is None or key > best:
            best = key
    cut = best[1] if best else len(rows[0]) + len(rows[1])
    return [wrap_body(body[:cut], limit)] + split_serif(body[cut:], limit)


def split_sentences(body: str) -> list[str]:
    """「！」「？」「。」の後ろでセリフを分ける(『』の中とセリフの最後は除く。霊夢のセリフ用。ユーザーの希望)。"""
    parts, prev = [], 0
    for n in range(1, len(body)):
        if _break_score(body, n) == 4:
            parts.append(body[prev:n])
            prev = n
    parts.append(body[prev:])
    return parts


def _marks(text: str) -> int:
    """読みと台本で数をそろえる区切りの数(「、」と、続けて書いた「。！？」のまとまり)。"""
    return len(MARK.findall(text))


def wrap_script(script_text: str, limit: int = LIMIT) -> tuple[str, dict[int, list[tuple[int, int]]]]:
    """折り返した台本と、{前の開始行: [(新しい開始行, そのセリフより前にある区切り(「、」「。」など)の数), ...]} を返す。

    1つのセリフが2つ以上に分かれたときは、リストに分かれた先の数だけ入る。空行の並びはそのまま残す。
    """
    serifs = _serifs(script_text)
    old_starts = _old_starts(script_text)
    # 空行の位置(何番目のセリフの後に空行があるか)を残す
    blank_after: set[int] = set()
    count = 0
    open_serif = False
    for raw in script_text.splitlines():
        line = raw.strip()
        if not line:
            if count:
                blank_after.add(count)
            continue
        if not open_serif:
            count += 1
        open_serif = not line.endswith("」")

    out: list[str] = []
    mapping: dict[int, list[tuple[int, int]]] = {}
    number = 0
    for index, (speaker, body) in enumerate(serifs, start=1):
        parts = []
        commas = 0
        pieces = split_sentences(body) if speaker in SENTENCE_SPLIT_SPEAKERS else [body]
        for rows in (r for piece in pieces for r in split_serif(piece, limit)):
            parts.append((number + 1, commas))
            commas += _marks("".join(rows))
            rows = list(rows)
            rows[0] = f"{speaker}「{rows[0]}"
            rows[-1] = f"{rows[-1]}」"
            out.extend(rows)
            number += len(rows)
        mapping[old_starts[index - 1]] = parts
        if index in blank_after and index != len(serifs):
            out.append("")
    return "\n".join(out) + "\n", mapping


def _split_reading(reading: str, comma_counts: list[int]) -> list[str] | None:
    """読みを区切り(「、」「。」「？」)の数で分ける(台本と読みの表は句読点がそろっている決まり)。合わなければ None。"""
    ends = [m.end() for m in MARK.finditer(reading)]
    pieces, prev = [], 0
    for need in comma_counts[1:]:
        if need < 1 or need > len(ends) or ends[need - 1] <= prev:
            return None
        pieces.append(reading[prev : ends[need - 1]])
        prev = ends[need - 1]
    pieces.append(reading[prev:])
    if not pieces[-1]:
        return None
    return pieces


def renumber(table_text: str, mapping: dict, *, reading: bool = False) -> str:
    """区切り表・読みの表の「開始行:」を付け直す。

    reading=True(読みの表)のときは、2つに分かれたセリフの読みも「、」の位置で分けて、分かれた先ごとに1行ずつ書く。
    """
    lines = []
    for raw in table_text.splitlines():
        match = re.match(r"^(\s*)(\d+)(\s*:)", raw)
        if match and not raw.lstrip().startswith("#"):
            old = int(match.group(2))
            if old not in mapping:
                raise ValueError(f"{old} 行目はセリフの始まりではありません: {raw!r}")
            parts = mapping[old]
            if isinstance(parts, int):
                parts = [(parts, 0)]
            body = raw[match.end():]
            if reading and len(parts) > 1:
                pieces = _split_reading(body.strip(), [c for _, c in parts])
                if pieces is not None:
                    for (start, _), piece in zip(parts, pieces):
                        lines.append(f"{match.group(1)}{start}{match.group(3)} {piece}")
                    continue
                print(f"注意: {old} 行目の読みは句読点の数が台本と合わないので分けられませんでした(分かれた最初のセリフに付けたまま)", file=sys.stderr)
            raw = f"{match.group(1)}{parts[0][0]}{match.group(3)}{body}"
        lines.append(raw)
    return "\n".join(lines) + ("\n" if table_text.endswith("\n") else "")


def _is_reading_table(path: Path, text: str) -> bool:
    if "yomi" in path.name or "読み" in path.name:
        return True
    data = [l for l in text.splitlines() if re.match(r"^\s*\d+\s*:", l)]
    return bool(data) and not any("=" in l for l in data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="台本の長いセリフを「」の中で改行し、区切り表・読みの表の行番号を付け直す")
    parser.add_argument("script")
    parser.add_argument("tables", nargs="*", help="行番号を付け直す区切り表・読みの表")
    parser.add_argument("--limit", type=int, default=LIMIT)
    args = parser.parse_args(argv)

    script_path = Path(args.script)
    wrapped, mapping = wrap_script(script_path.read_text(encoding="utf-8"), args.limit)
    tables = {}
    for p in args.tables:
        text = Path(p).read_text(encoding="utf-8")
        tables[Path(p)] = renumber(text, mapping, reading=_is_reading_table(Path(p), text))
    script_path.write_text(wrapped, encoding="utf-8")
    for path, text in tables.items():
        path.write_text(text, encoding="utf-8")
    changed = sum(1 for old, parts in mapping.items() if old != parts[0][0])
    split = sum(1 for parts in mapping.values() if len(parts) > 1)
    print(f"折り返しました: {script_path}(セリフ{len(mapping)}個、行番号が変わったセリフ{changed}個、2つ以上に分けたセリフ{split}個)")
    for path in tables:
        print(f"行番号を付け直しました: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
