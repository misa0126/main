from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic, APIError
from PIL import Image

from .keyword_extractor import DEFAULT_MODEL
from .sources import Candidate, Keyword

SYSTEM_PROMPT = (
    "あなたはYouTubeの「ゆっくり解説」動画の素材チェック担当です。"
    "台本の1シーン、検索キーワード、画像の出典情報、画像そのものが与えられます。"
    "この画像がそのシーンの挿絵として内容的に合っているかを判定してください。"
    "顔だけで人物を特定することはせず、出典のタイトルや説明文と、写っている物・場所・時代・雰囲気が"
    "台本と矛盾しないかで判断してください。"
    "別人・別の場所・明らかに時代が違うもの・無関係な画像・文字だらけの画像・透かし入りの画像は不合格です。"
    '出力はJSONのみ: {"ok": true または false, "reason": "日本語で1文の理由"}'
)


@dataclass
class Verdict:
    ok: bool
    reason: str
    checked: bool = True


class RelevanceChecker:
    """Claudeに画像を見せて、シーンの内容と合っているかを判定させる。"""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, max_side: int = 768) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_side = max_side

    def check(self, image_path: Path, scene_text: str, keyword: Keyword, candidate: Candidate) -> Verdict:
        try:
            image_data = self._encode(image_path)
        except OSError:
            return Verdict(ok=False, reason="画像を読み込めませんでした")

        info = "\n".join(
            [
                f"検索キーワード: {keyword}",
                f"出典タイトル: {candidate.title or '(なし)'}",
                f"出典の説明: {candidate.description or '(なし)'}",
                f"取得元: {candidate.source}",
                "",
                "台本のシーン:",
                scene_text,
            ]
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                            },
                            {"type": "text", "text": info},
                        ],
                    }
                ],
            )
        except APIError as e:
            # 判定できなかった画像は落とさず「未判定」として残す
            return Verdict(ok=True, reason=f"判定失敗のため未確認: {e.__class__.__name__}", checked=False)

        raw = "".join(block.text for block in response.content if block.type == "text")
        return _parse_verdict(raw)

    def _encode(self, image_path: Path) -> str:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((self._max_side, self._max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _parse_verdict(raw: str) -> Verdict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(match.group(0) if match else raw)
        return Verdict(ok=bool(parsed.get("ok")), reason=str(parsed.get("reason", "")).strip())
    except (json.JSONDecodeError, AttributeError):
        return Verdict(ok=True, reason=f"判定結果を解釈できず未確認: {raw[:80]!r}", checked=False)
