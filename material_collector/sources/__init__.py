from __future__ import annotations

import os

from .base import Candidate, ImageSource, Keyword, download_image, is_reusable_license, new_session
from .google import GoogleFallbackSource
from .met import MetMuseumSource
from .openverse import OpenverseSource
from .stock import PexelsSource, PixabaySource
from .wikimedia import WikimediaCommonsSource

# ライセンス確認済みの取得元。並び順が検索の優先順位になる。
DEFAULT_SOURCES = ["wikimedia", "openverse", "met", "pexels", "pixabay"]

__all__ = [
    "Candidate",
    "DEFAULT_SOURCES",
    "GoogleFallbackSource",
    "ImageSource",
    "Keyword",
    "build_sources",
    "download_image",
    "is_reusable_license",
    "new_session",
]


def build_sources(names: list[str]) -> tuple[list[ImageSource], list[str]]:
    """名前のリストから取得元を作る。APIキー未設定などで使えないものは理由付きで返す。"""
    session = new_session()
    sources: list[ImageSource] = []
    skipped: list[str] = []
    for name in names:
        if name == "wikimedia":
            sources.append(WikimediaCommonsSource(session))
        elif name == "openverse":
            sources.append(OpenverseSource(session))
        elif name == "met":
            sources.append(MetMuseumSource(session))
        elif name == "pexels":
            key = os.environ.get("PEXELS_API_KEY")
            if key:
                sources.append(PexelsSource(key, session))
            else:
                skipped.append("pexels (PEXELS_API_KEY 未設定)")
        elif name == "pixabay":
            key = os.environ.get("PIXABAY_API_KEY")
            if key:
                sources.append(PixabaySource(key, session))
            else:
                skipped.append("pixabay (PIXABAY_API_KEY 未設定)")
        else:
            raise ValueError(f"不明な取得元です: {name}")
    return sources, skipped
