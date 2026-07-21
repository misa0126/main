from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Scene:
    index: int
    text: str


def split_script_into_scenes(script_text: str) -> list[Scene]:
    """台本を空行区切りでシーンに分割する。"""
    raw_blocks = re.split(r"\n\s*\n", script_text.strip())
    scenes = []
    for i, block in enumerate(raw_blocks, start=1):
        block = block.strip()
        if block:
            scenes.append(Scene(index=i, text=block))
    return scenes
