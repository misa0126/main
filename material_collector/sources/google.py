from __future__ import annotations

import logging
import time
from pathlib import Path

from icrawler import ImageDownloader
from icrawler.builtin import GoogleImageCrawler

from .base import Candidate, Keyword

logging.getLogger("icrawler").setLevel(logging.WARNING)


class _UrlRecordingDownloader(ImageDownloader):
    """保存したファイル名と元画像URLの対応を記録するダウンローダー。"""

    recorded: dict[str, str]

    def process_meta(self, task):
        if task.get("success") and task.get("filename"):
            self.recorded[task["filename"]] = task["file_url"]


class GoogleFallbackSource:
    """Google画像検索(ライセンス絞り込みあり)。権利未確認のため結果は「要確認」扱い。"""

    name = "google"

    def __init__(self, sleep_after: float = 1.0) -> None:
        self._sleep_after = sleep_after

    def fetch(self, keyword: Keyword, dest_dir: Path, max_num: int) -> list[tuple[Path, Candidate]]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        recorded: dict[str, str] = {}
        downloader_cls = type("_Downloader", (_UrlRecordingDownloader,), {"recorded": recorded})
        crawler = GoogleImageCrawler(
            downloader_cls=downloader_cls,
            storage={"root_dir": str(dest_dir)},
            log_level=logging.WARNING,
        )
        crawler.crawl(
            keyword=keyword.ja,
            max_num=max_num,
            filters={"size": "medium", "license": "commercial,modify"},
        )
        # 連続リクエストによるブロックを避けるための間隔
        time.sleep(self._sleep_after)

        results = []
        for filename, url in sorted(recorded.items()):
            path = dest_dir / filename
            if path.exists():
                results.append(
                    (
                        path,
                        Candidate(
                            source=self.name,
                            image_url=url,
                            title=keyword.ja,
                            license="不明(Googleの「商用・改変可」絞り込み結果。要確認)",
                            verified=False,
                        ),
                    )
                )
        return results
