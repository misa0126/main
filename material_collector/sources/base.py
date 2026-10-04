from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

USER_AGENT = "YukkuriMaterialCollector/0.2 (https://github.com/misa0126/main; personal use)"
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


@dataclass
class Keyword:
    """検索キーワード。日本語の取得元と英語の取得元で使い分ける。"""

    ja: str
    en: str

    def __str__(self) -> str:
        return self.ja if self.ja == self.en else f"{self.ja} / {self.en}"


@dataclass
class Candidate:
    """取得元が返す候補画像1枚分の情報。"""

    source: str
    image_url: str
    title: str = ""
    page_url: str = ""
    author: str = ""
    license: str = ""
    license_url: str = ""
    description: str = ""
    # True: 取得元のライセンス情報で再利用可能と確認済み / False: 要確認
    verified: bool = True

    def credit_line(self) -> str:
        parts = [self.title or "(無題)"]
        if self.author:
            parts.append(f"作者: {self.author}")
        if self.license:
            parts.append(f"ライセンス: {self.license}")
        parts.append(f"出典: {self.page_url or self.image_url}")
        return " / ".join(parts)


class ImageSource(Protocol):
    name: str

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]: ...


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


_REJECT_PATTERNS = [
    r"\bnc\b",
    r"\bnd\b",
    r"non-?commercial",
    r"no-?deriv",
    r"fair use",
    r"all rights reserved",
    r"copyrighted",
]
_ACCEPT_PATTERNS = [
    r"public domain",
    r"\bpd\b",
    r"\bpdm\b",
    r"\bcc0\b",
    r"\bcc[ -]by\b",
]


def is_reusable_license(license_name: str) -> bool:
    """商用利用・改変が可能なライセンスかを判定する(NC/NDやGFDL単独は除外)。"""
    name = license_name.lower().replace("_", " ")
    if not name:
        return False
    if any(re.search(p, name) for p in _REJECT_PATTERNS):
        return False
    return any(re.search(p, name) for p in _ACCEPT_PATTERNS)


def download_image(session: requests.Session, url: str, dest_stem: Path, timeout: float = 20) -> Path | None:
    """画像をダウンロードして保存する。画像以外・大きすぎるファイル・通信失敗時はNone。"""
    try:
        response = session.get(url, timeout=timeout, stream=True)
    except requests.RequestException:
        return None
    with response:
        if response.status_code != 200:
            return None
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = CONTENT_TYPE_EXTENSIONS.get(content_type)
        if ext is None:
            return None
        data = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    return None
        except requests.RequestException:
            return None
    dest = dest_stem.with_suffix(ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(data))
    return dest
