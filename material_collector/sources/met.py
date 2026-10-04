from __future__ import annotations

import requests

from .base import Candidate, Keyword, new_session

API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"


class MetMuseumSource:
    """メトロポリタン美術館オープンアクセス。パブリックドメインの美術品・肖像画。"""

    name = "met"

    def __init__(self, session: requests.Session | None = None, max_lookups: int = 20) -> None:
        self._session = session or new_session()
        self._max_lookups = max_lookups

    def search(self, keyword: Keyword, limit: int) -> list[Candidate]:
        try:
            response = self._session.get(
                f"{API_BASE}/search",
                params={"q": keyword.en or keyword.ja, "hasImages": "true"},
                timeout=20,
            )
            response.raise_for_status()
            object_ids = response.json().get("objectIDs") or []
        except (requests.RequestException, ValueError):
            return []

        candidates = []
        for object_id in object_ids[: self._max_lookups]:
            if len(candidates) >= limit:
                break
            try:
                obj_response = self._session.get(f"{API_BASE}/objects/{object_id}", timeout=20)
                obj_response.raise_for_status()
                obj = obj_response.json()
            except (requests.RequestException, ValueError):
                continue
            image_url = obj.get("primaryImageSmall") or obj.get("primaryImage")
            if not obj.get("isPublicDomain") or not image_url:
                continue
            candidates.append(
                Candidate(
                    source=self.name,
                    image_url=image_url,
                    title=obj.get("title") or "",
                    page_url=obj.get("objectURL") or "",
                    author=obj.get("artistDisplayName") or "",
                    license="Public domain (CC0, The Met Open Access)",
                    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                    description=" ".join(filter(None, [obj.get("objectDate"), obj.get("culture")])),
                )
            )
        return candidates
