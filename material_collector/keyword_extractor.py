from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic

DEFAULT_MODEL = os.environ.get("MATERIAL_TOOL_MODEL", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT_TEMPLATE = (
    "あなたはYouTubeの「ゆっくり解説」動画向けの素材選定アシスタントです。"
    "与えられた台本の1シーン分のセリフから、画像検索に適した検索キーワードを"
    "{n}個、日本語で提案してください。"
    "できるだけ具体的で画像化しやすい名詞・固有名詞・情景を優先し、"
    "「解説」「今日」のような抽象的すぎる言葉は避けてください。"
    "出力はJSON配列のみとし、他の文章は一切含めないでください。"
    '例: ["東京タワー", "夜景", "高層ビル"]'
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

    def extract(self, scene_text: str) -> list[str]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=200,
            system=SYSTEM_PROMPT_TEMPLATE.format(n=self._keywords_per_scene),
            messages=[{"role": "user", "content": scene_text}],
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
        keywords = _parse_keywords(raw, self._keywords_per_scene)
        if not keywords:
            raise ValueError(f"キーワードを抽出できませんでした。モデル応答: {raw!r}")
        return keywords


def _parse_keywords(raw: str, limit: int) -> list[str]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return [str(k).strip() for k in parsed if str(k).strip()][:limit]
    except json.JSONDecodeError:
        pass

    # フォールバック: カンマ/改行/読点区切りとして解釈する
    fallback = re.split(r"[,\n、]", raw)
    return [k.strip(" \"'[]") for k in fallback if k.strip(" \"'[]")][:limit]
