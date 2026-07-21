from __future__ import annotations

import logging
import time
from pathlib import Path

from icrawler.builtin import GoogleImageCrawler

logging.getLogger("icrawler").setLevel(logging.WARNING)


def download_candidates(
    keyword: str,
    dest_dir: Path,
    max_num: int,
    sleep_after: float = 1.0,
) -> Path:
    """Google画像検索から候補画像をダウンロードする。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    crawler = GoogleImageCrawler(
        storage={"root_dir": str(dest_dir)},
        log_level=logging.WARNING,
    )
    crawler.crawl(
        keyword=keyword,
        max_num=max_num,
        filters={"size": "medium"},
    )
    # 連続リクエストによるブロックを避けるための間隔
    time.sleep(sleep_after)
    return dest_dir
