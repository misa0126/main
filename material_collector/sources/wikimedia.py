from __future__ import annotations

import requests

from .base import Candidate, Keyword, is_reusable_license, new_session, strip_html

API_URL = "https://commons.wikimedia.org/w/api.php"
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp", "image/tiff"}


class WikimediaCommonsSource:
    """Wikimedia Commons。人物・史跡・歴史資料に強い。"""

    name = "wikimedia"

    def __init__(self, session: requests.Session | None = None, thumb_width: int = 1600) -> None:
        self._session = session or new_session()
        self._thumb_width = thumb_width

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]:
        results = self._search_one(keyword.ja, limit)
        if len(results) < limit and keyword.en and keyword.en != keyword.ja:
            seen = {c.image_url for c in results}
            for c in self._search_one(keyword.en, limit):
                if c.image_url not in seen:
                    results.append(c)
        return results[:limit]

    def _search_one(self, query: str, limit: int) -> list[Candidate]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            # ライセンスで除外される分を見越して多めに取る
            "gsrlimit": min(limit * 3, 50),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": self._thumb_width,
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ImageDescription|ObjectName",
            "iiextmetadatalanguage": "ja",
        }
        try:
            response = self._session.get(API_URL, params=params, timeout=20)
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
        except (requests.RequestException, ValueError):
            return []

        candidates = []
        for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in SUPPORTED_MIME:
                continue
            meta = info.get("extmetadata", {})
            license_name = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            if not is_reusable_license(license_name):
                continue
            candidates.append(
                Candidate(
                    source=self.name,
                    image_url=info.get("thumburl") or info.get("url", ""),
                    title=strip_html(meta.get("ObjectName", {}).get("value", "")) or page.get("title", ""),
                    page_url=info.get("descriptionurl", ""),
                    author=strip_html(meta.get("Artist", {}).get("value", "")),
                    license=license_name,
                    license_url=meta.get("LicenseUrl", {}).get("value", ""),
                    description=strip_html(meta.get("ImageDescription", {}).get("value", ""))[:300],
                )
            )
            if len(candidates) >= limit:
                break
        return candidates
