from __future__ import annotations

import requests

from .base import Candidate, Keyword, new_session


class PexelsSource:
    """Pexels。風景・物・雰囲気カット向け。APIキー(無料)が必要。"""

    name = "pexels"
    API_URL = "https://api.pexels.com/v1/search"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self._session = session or new_session()
        self._api_key = api_key

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]:
        try:
            response = self._session.get(
                self.API_URL,
                params={"query": keyword.en or keyword.ja, "per_page": min(max(limit, 1), 80)},
                headers={"Authorization": self._api_key},
                timeout=20,
            )
            response.raise_for_status()
            photos = response.json().get("photos", [])
        except (requests.RequestException, ValueError):
            return []

        return [
            Candidate(
                source=self.name,
                image_url=p.get("src", {}).get("large2x") or p.get("src", {}).get("original", ""),
                title=p.get("alt") or "",
                page_url=p.get("url") or "",
                author=p.get("photographer") or "",
                license="Pexels License",
                license_url="https://www.pexels.com/license/",
            )
            for p in photos
            if p.get("src")
        ][:limit]


class PixabaySource:
    """Pixabay。日本語キーワードでも検索できる。APIキー(無料)が必要。"""

    name = "pixabay"
    API_URL = "https://pixabay.com/api/"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self._session = session or new_session()
        self._api_key = api_key

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]:
        try:
            response = self._session.get(
                self.API_URL,
                params={
                    "key": self._api_key,
                    "q": keyword.ja,
                    "lang": "ja",
                    "image_type": "photo",
                    "safesearch": "true",
                    # Pixabay APIのper_pageは3以上が必須
                    "per_page": min(max(limit, 3), 200),
                },
                timeout=20,
            )
            response.raise_for_status()
            hits = response.json().get("hits", [])
        except (requests.RequestException, ValueError):
            return []

        return [
            Candidate(
                source=self.name,
                image_url=h.get("largeImageURL") or h.get("webformatURL", ""),
                title=h.get("tags") or "",
                page_url=h.get("pageURL") or "",
                author=h.get("user") or "",
                license="Pixabay Content License",
                license_url="https://pixabay.com/service/license-summary/",
            )
            for h in hits
            if h.get("largeImageURL") or h.get("webformatURL")
        ][:limit]
