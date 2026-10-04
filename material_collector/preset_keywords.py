from __future__ import annotations

import re

from .script_parser import split_script_into_scenes
from .sources import Keyword

LINE_PATTERN = re.compile(r"^\s*(\d+)\s*[:：]\s*(.*)$")


def parse_keyword_table(text: str) -> dict[int, list[Keyword]]:
    """キーワード表を読む。書式: 「シーン番号: 日本語=English, ...」、「-」は画像不要のシーン。"""
    table: dict[int, list[Keyword]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_PATTERN.match(line)
        if not match:
            raise ValueError(f"キーワード表の書式が読めません: {line!r}(「番号: キーワード, ...」の形にしてください)")
        index, body = int(match.group(1)), match.group(2).strip()
        keywords = parse_keyword_items(body)
        table[index] = keywords
    return table


def parse_keyword_items(body: str) -> list[Keyword]:
    """「日本語=English, 日本語, ...」を読む。「-」や空なら空リスト。"""
    body = body.strip()
    if body in ("", "-", "ー", "－"):
        return []
    keywords = []
    for item in re.split(r"[,、，]", body):
        ja, _, en = item.strip().partition("=")
        ja, en = ja.strip(), en.strip()
        if ja or en:
            keywords.append(Keyword(ja=ja or en, en=en or ja))
    return keywords


class PresetKeywordExtractor:
    """キーワード表から、台本の各シーンのキーワードを返す(Claude APIを使わない)。"""

    def __init__(self, script_text: str, table_text: str) -> None:
        table = parse_keyword_table(table_text)
        self._by_text: dict[str, list[Keyword]] = {}
        self.missing: list[int] = []
        for scene in split_script_into_scenes(script_text):
            if scene.index in table:
                self._by_text[scene.text] = table[scene.index]
            else:
                self.missing.append(scene.index)

    def extract(self, scene_text: str) -> list[Keyword]:
        if scene_text not in self._by_text:
            raise ValueError("このシーンはキーワード表にありません。台本とキーワード表の番号がずれていないか確認してください。")
        return self._by_text[scene_text]
