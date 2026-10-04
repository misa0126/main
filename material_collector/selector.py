from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError


def check_image(
    path: Path,
    min_width: int,
    min_height: int,
    seen_hashes: list,
    hash_distance_threshold: int = 5,
) -> imagehash.ImageHash | None:
    """破損・低解像度・既出画像との重複をふるいにかけ、合格なら知覚ハッシュを返す。"""
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            width, height = img.size
            if width < min_width or height < min_height:
                return None
            phash = imagehash.phash(img)
    except (UnidentifiedImageError, OSError):
        return None

    if any(phash - h <= hash_distance_threshold for h in seen_hashes):
        return None
    return phash
