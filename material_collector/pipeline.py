from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .image_search import download_candidates
from .keyword_extractor import KeywordExtractor
from .script_parser import split_script_into_scenes
from .selector import select_best_images


@dataclass
class PipelineConfig:
    script_path: Path
    output_dir: Path
    keywords_per_scene: int = 3
    candidates_per_keyword: int = 8
    images_per_scene: int = 3
    min_width: int = 400
    min_height: int = 300
    model: str | None = None
    keep_candidates: bool = False


def run_pipeline(config: PipelineConfig) -> dict:
    script_text = config.script_path.read_text(encoding="utf-8")
    scenes = split_script_into_scenes(script_text)
    if not scenes:
        raise ValueError("台本からシーンを検出できませんでした。空行でシーンを区切ってください。")

    extractor_kwargs: dict = {"keywords_per_scene": config.keywords_per_scene}
    if config.model:
        extractor_kwargs["model"] = config.model
    extractor = KeywordExtractor(**extractor_kwargs)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"script": str(config.script_path), "scenes": []}

    with tempfile.TemporaryDirectory(prefix="material_candidates_") as tmp:
        tmp_path = Path(tmp)
        for scene in scenes:
            scene_dir = config.output_dir / f"scene_{scene.index:03d}"
            selected_dir = scene_dir / "selected"
            scene_dir.mkdir(parents=True, exist_ok=True)

            keywords = extractor.extract(scene.text)
            (scene_dir / "keywords.txt").write_text("\n".join(keywords), encoding="utf-8")

            seen_hashes: list = []
            scene_selected = []
            for keyword in keywords:
                if len(scene_selected) >= config.images_per_scene:
                    break

                candidates_dir = tmp_path / f"scene_{scene.index:03d}" / keyword.replace(" ", "_")
                download_candidates(keyword, candidates_dir, config.candidates_per_keyword)

                remaining = config.images_per_scene - len(scene_selected)
                picked = select_best_images(
                    candidates_dir=candidates_dir,
                    keyword=keyword,
                    selected_dir=selected_dir,
                    limit=remaining,
                    min_width=config.min_width,
                    min_height=config.min_height,
                    seen_hashes=seen_hashes,
                    start_index=len(scene_selected) + 1,
                )
                scene_selected.extend(picked)

                if config.keep_candidates:
                    keep_dir = scene_dir / "candidates" / keyword.replace(" ", "_")
                    keep_dir.mkdir(parents=True, exist_ok=True)
                    for f in candidates_dir.iterdir():
                        shutil.copy2(f, keep_dir / f.name)

            manifest["scenes"].append(
                {
                    "index": scene.index,
                    "text": scene.text,
                    "keywords": keywords,
                    "selected_images": [
                        str(s.dest_path.relative_to(config.output_dir)) for s in scene_selected
                    ],
                }
            )

    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
