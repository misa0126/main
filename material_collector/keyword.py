from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Keyword:
    """検索キーワード。日本語の取得元と英語の取得元で使い分ける。

    画像リスト(html_sheet)が追加ライブラリなしで動くよう、依存のないこのファイルに置く。
    """

    ja: str
    en: str

    def __str__(self) -> str:
        return self.ja if self.ja == self.en else f"{self.ja} / {self.en}"
