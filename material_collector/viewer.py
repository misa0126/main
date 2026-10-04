from __future__ import annotations

import html
import re
from pathlib import Path

SPEAKER_PATTERN = re.compile(r"^(?P<speaker>[^「」\s]{1,10})「(?P<line>.*)」\s*$")

PAGE_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>素材確認シート</title>
<style>
:root {{
  --bg: #f6f5f2; --panel: #ffffff; --text: #23211d; --muted: #6b675f; --line: #e2dfd8;
  --marisa: #b58900; --reimu: #c0392b; --other: #4a6fa5;
  --ok: #2e7d4f; --warn: #b9650b; --warn-bg: #fff4e5; --pick: #4a6fa5;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1b1a18; --panel: #24221f; --text: #ece9e2; --muted: #a29d93; --line: #3a3732;
    --marisa: #e0b43a; --reimu: #ef7b6c; --other: #8fb0e0;
    --ok: #6cc28f; --warn: #f0a556; --warn-bg: #3a2c1a; --pick: #8fb0e0;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font-family: "Hiragino Sans", "Yu Gothic UI", "Meiryo", sans-serif; line-height: 1.6; }}
header {{ position: sticky; top: 0; z-index: 5; background: var(--panel); border-bottom: 1px solid var(--line);
  padding: 10px 20px; display: flex; gap: 20px; align-items: baseline; flex-wrap: wrap; }}
header h1 {{ font-size: 18px; margin: 0; }}
header .stats {{ color: var(--muted); font-size: 13px; }}
header a {{ color: var(--pick); font-size: 13px; }}
.hint {{ max-width: 1500px; margin: 12px auto 0; padding: 0 20px; color: var(--muted); font-size: 13px; }}
main {{ max-width: 1500px; margin: 0 auto; padding: 12px 20px 60px; }}
.scene {{ display: grid; grid-template-columns: minmax(280px, 1.1fr) minmax(200px, 0.7fr) minmax(320px, 1.6fr);
  gap: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px; margin-bottom: 12px; }}
.scene.missing {{ border-color: var(--warn); }}
.scene-no {{ font-size: 12px; color: var(--muted); font-weight: bold; margin-bottom: 4px; }}
.script p {{ margin: 0 0 4px; }}
.speaker {{ font-weight: bold; margin-right: 2px; }}
.speaker.marisa {{ color: var(--marisa); }}
.speaker.reimu {{ color: var(--reimu); }}
.speaker.other {{ color: var(--other); }}
.notes {{ font-size: 13px; color: var(--muted); border-left: 1px dashed var(--line); padding-left: 14px; }}
.notes ul {{ margin: 4px 0 0; padding-left: 18px; }}
.notes .warn {{ color: var(--warn); font-weight: bold; }}
.kw {{ display: inline-block; background: var(--bg); border: 1px solid var(--line); border-radius: 4px;
  padding: 0 6px; margin: 2px 4px 2px 0; font-size: 12px; color: var(--text); }}
.images {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; align-content: start; }}
.card {{ border: 2px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--bg); }}
.card.review {{ border-color: var(--warn); background: var(--warn-bg); }}
.card img {{ display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #000; cursor: grab; }}
.card .meta {{ padding: 5px 7px; font-size: 11px; line-height: 1.45; word-break: break-all; }}
.badge {{ display: inline-block; font-size: 11px; font-weight: bold; padding: 0 5px; border-radius: 3px; color: #fff; }}
.badge.ok {{ background: var(--ok); }}
.badge.warn {{ background: var(--warn); }}
.card .meta a {{ color: var(--pick); }}
.continued {{ color: var(--muted); font-size: 13px; padding: 12px; }}
.empty {{ color: var(--warn); font-size: 13px; padding: 20px; border: 2px dashed var(--warn); border-radius: 8px; text-align: center; }}
@media (max-width: 900px) {{
  .scene {{ grid-template-columns: 1fr; }}
  .notes {{ border-left: none; padding-left: 0; }}
}}
</style>
</head>
<body>
<header>
  <h1>素材確認シート</h1>
  <span class="stats">{stats}</span>
  {credits_link}
</header>
<p class="hint">左が台本、真ん中がメモ、右が候補画像です。使いたい画像をYMM4のタイムラインへドラッグしてください。
オレンジ枠の画像はライセンス未確認(Google検索)なので、出典を確認してから使ってください。</p>
<main>
{scenes}
</main>
<script>
// Chrome/Edgeで画像をドラッグしたとき、ファイルとして受け取れるようにする
document.querySelectorAll('.card img').forEach(function (img) {{
  img.addEventListener('dragstart', function (e) {{
    var name = img.dataset.name;
    var mime = name.endsWith('.png') ? 'image/png' : name.endsWith('.webp') ? 'image/webp' : 'image/jpeg';
    try {{ e.dataTransfer.setData('DownloadURL', mime + ':' + name + ':' + img.src); }} catch (err) {{}}
  }});
}});
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _speaker_class(speaker: str) -> str:
    if "魔理沙" in speaker:
        return "marisa"
    if "霊夢" in speaker:
        return "reimu"
    return "other"


def _render_script(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        match = SPEAKER_PATTERN.match(raw.strip())
        if match:
            speaker = match.group("speaker")
            lines.append(
                f'<p><span class="speaker {_speaker_class(speaker)}">{_esc(speaker)}</span>'
                f"「{_esc(match.group('line'))}」</p>"
            )
        elif raw.strip():
            lines.append(f"<p>{_esc(raw.strip())}</p>")
    return "\n".join(lines)


def _render_card(image: dict, scene_index: int, number: int, needs_review: bool) -> str:
    file_path = image["file"].replace("\\", "/")
    download_name = f"scene{scene_index:03d}_{number:02d}{Path(file_path).suffix}"
    if needs_review:
        badge = '<span class="badge warn">要確認</span>'
    else:
        badge = '<span class="badge ok">確認済み</span>'

    meta = [badge]
    if image.get("title"):
        meta.append(_esc(image["title"][:60]))
    if image.get("author"):
        meta.append(f"作者: {_esc(image['author'][:40])}")
    if image.get("license"):
        meta.append(_esc(image["license"]))
    link = image.get("page_url") or image.get("image_url")
    if link:
        meta.append(f'<a href="{_esc(link)}" target="_blank" rel="noopener">出典ページ</a>')

    return (
        f'<div class="card{" review" if needs_review else ""}">'
        f'<img src="{_esc(file_path)}" data-name="{_esc(download_name)}" loading="lazy" '
        f'alt="{_esc(image.get("title", ""))}" title="ドラッグしてYMM4へ">'
        f'<div class="meta">{"<br>".join(meta)}</div></div>'
    )


def _render_notes(scene: dict) -> str:
    items = []
    selected = scene.get("selected_images", [])
    review = scene.get("needs_review_images", [])
    if scene.get("skipped"):
        items.append("<li>画像を探さないシーンです(前のシーンの画像を続けて使う想定)。</li>")
    elif scene.get("error"):
        items.append(f'<li class="warn">このシーンはエラーで処理できませんでした: {_esc(scene["error"])}</li>')
    elif not selected and not review:
        items.append('<li class="warn">合う画像が見つかりませんでした。キーワードを参考に手動で探してください。</li>')
    if review:
        items.append(
            f'<li class="warn">要確認の画像が{len(review)}枚あります。権利を確認してから使ってください。</li>'
        )
    for number, image in enumerate(selected + review, start=1):
        relevance = image.get("relevance") or {}
        if relevance.get("reason"):
            prefix = "" if relevance.get("checked", True) else "(未判定) "
            items.append(f"<li>画像{number}: {prefix}{_esc(relevance['reason'])}</li>")
    if (selected or review) and all(not img.get("relevance") for img in selected + review):
        items.append("<li>内容チェックなし。候補から使う画像を選んでください。</li>")
    rejected = scene.get("rejected_by_relevance_check", [])
    if rejected:
        items.append(f"<li>内容が合わず除外した候補: {len(rejected)}枚</li>")

    keywords = "".join(
        f'<span class="kw">{_esc(k["ja"])}</span>' for k in scene.get("keywords", []) if k.get("ja")
    )
    return f"<div>検索キーワード</div><div>{keywords}</div><ul>{''.join(items)}</ul>"


def build_viewer(manifest: dict, output_dir: Path) -> Path:
    """manifestから、台本と候補画像を並べた確認用HTML(index.html)を出力する。"""
    sections = []
    total_selected = total_review = missing = 0
    for scene in manifest.get("scenes", []):
        selected = scene.get("selected_images", [])
        review = scene.get("needs_review_images", [])
        total_selected += len(selected)
        total_review += len(review)
        cards = [_render_card(img, scene["index"], n, False) for n, img in enumerate(selected, start=1)]
        cards += [
            _render_card(img, scene["index"], n, True) for n, img in enumerate(review, start=len(selected) + 1)
        ]
        if not cards and not scene.get("skipped"):
            missing += 1
        if cards:
            images_html = f'<div class="images">{"".join(cards)}</div>'
        elif scene.get("skipped"):
            images_html = '<div class="continued">前のシーンの画像のまま</div>'
        else:
            images_html = '<div class="empty">画像なし</div>'
        is_missing = not cards and not scene.get("skipped")
        sections.append(
            f'<section class="scene{" missing" if is_missing else ""}" id="scene-{scene["index"]}">'
            f'<div class="script"><div class="scene-no">シーン {scene["index"]}</div>{_render_script(scene.get("text", ""))}</div>'
            f'<div class="notes">{_render_notes(scene)}</div>'
            f"{images_html}</section>"
        )

    stats = f"{len(sections)}シーン ・ 確認済み {total_selected}枚 ・ 要確認 {total_review}枚 ・ 画像なし {missing}シーン"
    credits_link = (
        '<a href="CREDITS.txt" target="_blank">クレジット一覧(CREDITS.txt)</a>'
        if (output_dir / "CREDITS.txt").exists()
        else ""
    )
    page = PAGE_TEMPLATE.format(stats=_esc(stats), credits_link=credits_link, scenes="\n".join(sections))
    viewer_path = output_dir / "index.html"
    viewer_path.write_text(page, encoding="utf-8")
    return viewer_path
