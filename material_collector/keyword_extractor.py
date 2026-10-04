from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic

from .sources import Keyword

DEFAULT_MODEL = os.environ.get("MATERIAL_TOOL_MODEL", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT_TEMPLATE = (
    "あなたはYouTubeの「ゆっくり解説」動画向けの素材選定アシスタントです。"
    "与えられた台本の1シーン分のセリフから、画像検索に適した検索キーワードを"
    "{n}個提案してください。"
    "できるだけ具体的で画像化しやすい名詞・固有名詞・情景を優先し、"
    "「解説」「今日」のような抽象的すぎる言葉は避けてください。"
    "人物は姓名をそろえて書き、必要なら年代や場所を添えてください。"
    "各キーワードは日本語(ja)と、海外の画像サイトで検索するための英語(en)の両方で書いてください。"
    "出力はJSON配列のみとし、他の文章は一切含めないでください。"
    '例: [{{"ja": "東京タワー", "en": "Tokyo Tower"}}, {{"ja": "昭和の銀座", "en": "Ginza 1950s"}}]'
)


class KeywordExtractor:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        keywords_per_scene: int = 3,
    ) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._keywords_per_scene = keywords_per_scene

    def extract(self, scene_text: str) -> list[Keyword]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            system=SYSTEM_PROMPT_TEMPLATE.format(n=self._keywords_per_scene),
            messages=[{"role": "user", "content": scene_text}],
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
        keywords = _parse_keywords(raw, self._keywords_per_scene)
        if not keywords:
            raise ValueError(f"キーワードを抽出できませんでした。モデル応答: {raw!r}")
        return keywords


def _parse_keywords(raw: str, limit: int) -> list[Keyword]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        keywords = []
        for item in parsed:
            if isinstance(item, dict):
                ja = str(item.get("ja") or item.get("en") or "").strip()
                en = str(item.get("en") or ja).strip()
            else:
                ja = en = str(item).strip()
            if ja:
                keywords.append(Keyword(ja=ja, en=en))
        return keywords[:limit]

    # フォールバック: カンマ/改行/読点区切りとして解釈する
    fallback = re.split(r"[,\n、]", raw)
    words = [k.strip(" \"'[]{}") for k in fallback if k.strip(" \"'[]{}")]
    return [Keyword(ja=w, en=w) for w in words][:limit]
