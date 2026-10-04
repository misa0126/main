from __future__ import annotations

import requests

from .base import Candidate, Keyword, is_reusable_license, new_session

API_URL = "https://api.openverse.org/v1/images/"


def _license_label(code: str, version: str) -> str:
    code = (code or "").lower()
    if code == "cc0":
        return "CC0"
    if code == "pdm":
        return "Public Domain Mark"
    return f"CC {code.upper()} {version}".strip()


class OpenverseSource:
    """Openverse。Flickrなどに公開されたCC画像を横断検索する。情景カットの数が多い。"""

    name = "openverse"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or new_session()

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]:
        params = {
            "q": keyword.en or keyword.ja,
            "license_type": "commercial,modification",
            "page_size": min(max(limit, 1), 20),
        }
        try:
            response = self._session.get(API_URL, params=params, timeout=20)
            response.raise_for_status()
            results = response.json().get("results", [])
        except (requests.RequestException, ValueError):
            return []

        candidates = []
        for item in results:
            license_name = _license_label(item.get("license", ""), item.get("license_version", ""))
            if not is_reusable_license(license_name) or not item.get("url"):
                continue
            candidates.append(
                Candidate(
                    source=f"{self.name}:{item.get('source', '')}",
                    image_url=item["url"],
                    title=item.get("title") or "",
                    page_url=item.get("foreign_landing_url") or "",
                    author=item.get("creator") or "",
                    license=license_name,
                    license_url=item.get("license_url") or "",
                )
            )
        return candidates[:limit]
