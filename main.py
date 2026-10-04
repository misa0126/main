from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from material_collector.pipeline import PipelineConfig, run_pipeline
from material_collector.sources import DEFAULT_SOURCES


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ゆっくり解説向け: 台本から画像素材を自動収集するツール",
    )
    parser.add_argument("script", type=Path, help="台本テキストファイルのパス(シーンは空行区切り)")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="出力先ディレクトリ")
    parser.add_argument("--keywords-per-scene", type=int, default=3, help="シーンごとに生成する検索キーワード数")
    parser.add_argument("--candidates-per-keyword", type=int, default=8, help="キーワードごとにダウンロードする候補画像数")
    parser.add_argument("--images-per-scene", type=int, default=3, help="シーンごとに最終選別する画像数")
    parser.add_argument("--min-width", type=int, default=400, help="選別する画像の最小幅(px)")
    parser.add_argument("--min-height", type=int, default=300, help="選別する画像の最小高さ(px)")
    parser.add_argument("--model", type=str, default=None, help="キーワード抽出と内容チェックに使うClaudeモデルID")
    parser.add_argument("--keep-candidates", action="store_true", help="選別前の候補画像もすべて保存する")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(DEFAULT_SOURCES),
        help="ライセンス確認済みの取得元(カンマ区切り、左ほど優先)",
    )
    parser.add_argument(
        "--no-google",
        action="store_true",
        help="足りない分をGoogle画像検索で補わない(補った画像は needs_review/ に入る)",
    )
    parser.add_argument(
        "--no-relevance-check",
        action="store_true",
        help="Claudeによる画像と台本の内容チェックを行わない",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("エラー: 環境変数 ANTHROPIC_API_KEY が設定されていません。", file=sys.stderr)
        return 1

    if not args.script.exists():
        print(f"エラー: 台本ファイルが見つかりません: {args.script}", file=sys.stderr)
        return 1

    config = PipelineConfig(
        script_path=args.script,
        output_dir=args.output,
        keywords_per_scene=args.keywords_per_scene,
        candidates_per_keyword=args.candidates_per_keyword,
        images_per_scene=args.images_per_scene,
        min_width=args.min_width,
        min_height=args.min_height,
        model=args.model,
        keep_candidates=args.keep_candidates,
        sources=[name.strip() for name in args.sources.split(",") if name.strip()],
        google_fallback=not args.no_google,
        check_relevance=not args.no_relevance_check,
    )

    manifest = run_pipeline(config)
    total_selected = sum(len(s["selected_images"]) for s in manifest["scenes"])
    total_review = sum(len(s["needs_review_images"]) for s in manifest["scenes"])
    print(f"完了: {len(manifest['scenes'])}シーン、ライセンス確認済み {total_selected}枚、要確認 {total_review}枚")
    print(f"出力先: {config.output_dir.resolve()}")
    print(f"確認シート: {(config.output_dir / 'index.html').resolve()} (ブラウザで開いてください)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
