from __future__ import annotations

import io

import requests
from PIL import Image


def make_jpeg(width: int = 800, height: int = 600, seed: int = 0) -> bytes:
    """互いに似ていないテスト画像を作る(seedごとに模様が変わる)。"""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            v = ((x * (seed + 3)) ^ (y * (seed * 7 + 1))) & 0xFF
            pixels[x, y] = (v, (v * (seed + 1)) & 0xFF, (255 - v))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", content_type="application/json"):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = {"Content-Type": content_type}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    """URLの前方一致で応答を返す。呼び出し履歴も記録する。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        self.calls.append((url, params or {}))
        for prefix, response in self.routes.items():
            if url.startswith(prefix):
                return response(url, params or {}) if callable(response) else response
        return FakeResponse(status_code=404)
