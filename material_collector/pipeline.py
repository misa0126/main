from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .keyword_extractor import KeywordExtractor
from .relevance import RelevanceChecker, Verdict
from .script_parser import split_script_into_scenes
from .selector import check_image
from .viewer import build_viewer
from .sources import (
    DEFAULT_SOURCES,
    Candidate,
    GoogleFallbackSource,
    ImageSource,
    Keyword,
    build_sources,
    download_image,
    new_session,
)

SELECTED_DIR = "selected"
REVIEW_DIR = "needs_review"


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
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    google_fallback: bool = True
    check_relevance: bool = True


@dataclass
class _Picked:
    path: Path
    keyword: Keyword
    candidate: Candidate
    verdict: Verdict | None

    def to_manifest(self, output_dir: Path) -> dict:
        c = self.candidate
        return {
            "file": str(self.path.relative_to(output_dir)),
            "keyword": str(self.keyword),
            "source": c.source,
            "title": c.title,
            "author": c.author,
            "license": c.license,
            "license_url": c.license_url,
            "page_url": c.page_url,
            "image_url": c.image_url,
            "license_verified": c.verified,
            "relevance": None
            if self.verdict is None
            else {"ok": self.verdict.ok, "checked": self.verdict.checked, "reason": self.verdict.reason},
        }


class _SceneCollector:
    """1シーン分の候補をふるいにかけ、合格した画像を出力先へコピーする。"""

    def __init__(self, config: PipelineConfig, scene_dir: Path, scene_text: str, checker: RelevanceChecker | None):
        self._config = config
        self._scene_dir = scene_dir
        self._scene_text = scene_text
        self._checker = checker
        self._seen_hashes: list = []
        self._seen_urls: set[str] = set()
        self.selected: list[_Picked] = []
        self.review: list[_Picked] = []
        self.rejected: list[dict] = []

    @property
    def shortage(self) -> int:
        return self._config.images_per_scene - len(self.selected) - len(self.review)

    def consider(self, path: Path, keyword: Keyword, candidate: Candidate) -> bool:
        if candidate.image_url in self._seen_urls:
            return False
        self._seen_urls.add(candidate.image_url)

        if self._config.keep_candidates:
            keep_dir = self._scene_dir / "candidates"
            keep_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, keep_dir / f"{candidate.source.replace(':', '_')}_{path.name}")

        phash = check_image(path, self._config.min_width, self._config.min_height, self._seen_hashes)
        if phash is None:
            return False

        verdict = None
        if self._checker is not None:
            verdict = self._checker.check(path, self._scene_text, keyword, candidate)
            if not verdict.ok:
                self.rejected.append(
                    {"image_url": candidate.image_url, "title": candidate.title, "reason": verdict.reason}
                )
                return False

        self._seen_hashes.append(phash)
        bucket = self.selected if candidate.verified else self.review
        dest_dir = self._scene_dir / (SELECTED_DIR if candidate.verified else REVIEW_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{len(bucket) + 1:03d}{path.suffix.lower()}"
        shutil.copy2(path, dest)
        bucket.append(_Picked(dest, keyword, candidate, verdict))
        return True


def run_pipeline(
    config: PipelineConfig,
    *,
    extractor: KeywordExtractor | None = None,
    sources: list[ImageSource] | None = None,
    google: GoogleFallbackSource | None = None,
    checker: RelevanceChecker | None = None,
    session: requests.Session | None = None,
    log=print,
) -> dict:
    script_text = config.script_path.read_text(encoding="utf-8")
    scenes = split_script_into_scenes(script_text)
    if not scenes:
        raise ValueError("台本からシーンを検出できませんでした。空行でシーンを区切ってください。")

    model_kwargs: dict = {"model": config.model} if config.model else {}
    if extractor is None:
        extractor = KeywordExtractor(keywords_per_scene=config.keywords_per_scene, **model_kwargs)
    if sources is None:
        sources, skipped = build_sources(config.sources)
        for reason in skipped:
            log(f"取得元をスキップ: {reason}")
    if google is None and config.google_fallback:
        google = GoogleFallbackSource()
    if checker is None and config.check_relevance:
        checker = RelevanceChecker(**model_kwargs)
    session = session or new_session()

    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"script": str(config.script_path), "scenes": []}
    credits: list[str] = []

    with tempfile.TemporaryDirectory(prefix="material_candidates_") as tmp:
        tmp_path = Path(tmp)
        for scene in scenes:
            scene_dir = config.output_dir / f"scene_{scene.index:03d}"
            scene_dir.mkdir(parents=True, exist_ok=True)
            work_dir = tmp_path / f"scene_{scene.index:03d}"
            log(f"シーン {scene.index}/{len(scenes)} を処理中")

            keywords = extractor.extract(scene.text)
            (scene_dir / "keywords.txt").write_text("\n".join(str(k) for k in keywords), encoding="utf-8")

            collector = _SceneCollector(config, scene_dir, scene.text, checker)
            download_count = 0
            for keyword in keywords:
                for source in sources:
                    if collector.shortage <= 0:
                        break
                    for candidate in source.search(keyword, config.candidates_per_keyword):
                        if collector.shortage <= 0:
                            break
                        download_count += 1
                        path = download_image(session, candidate.image_url, work_dir / f"{download_count:04d}")
                        if path is not None:
                            collector.consider(path, keyword, candidate)

            # ライセンス確認済みの取得元で足りない分だけ、Google検索の結果を「要確認」として補う
            if google is not None and collector.shortage > 0:
                for i, keyword in enumerate(keywords):
                    if collector.shortage <= 0:
                        break
                    for path, candidate in google.fetch(keyword, work_dir / f"google_{i}", config.candidates_per_keyword):
                        if collector.shortage <= 0:
                            break
                        collector.consider(path, keyword, candidate)

            scene_credits = [p.candidate.credit_line() for p in collector.selected]
            if scene_credits:
                (scene_dir / "credits.txt").write_text("\n".join(scene_credits) + "\n", encoding="utf-8")
                credits.extend(scene_credits)

            manifest["scenes"].append(
                {
                    "index": scene.index,
                    "text": scene.text,
                    "keywords": [{"ja": k.ja, "en": k.en} for k in keywords],
                    "selected_images": [p.to_manifest(config.output_dir) for p in collector.selected],
                    "needs_review_images": [p.to_manifest(config.output_dir) for p in collector.review],
                    "rejected_by_relevance_check": collector.rejected,
                }
            )

    if credits:
        unique_credits = list(dict.fromkeys(credits))
        (config.output_dir / "CREDITS.txt").write_text(
            "【使用素材】\n" + "\n".join(unique_credits) + "\n", encoding="utf-8"
        )
    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    build_viewer(manifest, config.output_dir)
    return manifest
