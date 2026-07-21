from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass
class SelectedImage:
    source_path: Path
    dest_path: Path
    keyword: str


def select_best_images(
    candidates_dir: Path,
    keyword: str,
    selected_dir: Path,
    limit: int,
    min_width: int,
    min_height: int,
    seen_hashes: list,
    hash_distance_threshold: int = 5,
    start_index: int = 1,
) -> list[SelectedImage]:
    """候補画像を解像度・重複でふるいにかけ、上位を選別してコピーする。"""
    if limit <= 0 or not candidates_dir.exists():
        return []

    selected_dir.mkdir(parents=True, exist_ok=True)
    selected: list[SelectedImage] = []
    files = sorted(p for p in candidates_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)

    for path in files:
        if len(selected) >= limit:
            break
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                width, height = img.size
                if width < min_width or height < min_height:
                    continue
                phash = imagehash.average_hash(img)
        except (UnidentifiedImageError, OSError):
            continue

        if any(phash - h <= hash_distance_threshold for h in seen_hashes):
            continue

        dest_path = selected_dir / f"{start_index + len(selected):03d}{path.suffix.lower()}"
        dest_path.write_bytes(path.read_bytes())

        seen_hashes.append(phash)
        selected.append(SelectedImage(source_path=path, dest_path=dest_path, keyword=keyword))

    return selected
