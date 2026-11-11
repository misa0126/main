"""YMM4のプロジェクト(.ymmp)に、区切り表どおりに画像を自動で並べる。

流れ:
    1. YMM4で「ツール → 台本読み込み」から台本を読み込み、声が入った状態でプロジェクトを保存する
    2. 画像リスト(HTML)に画像を貼り、「まとめて保存(ZIP)」で番号付きのZIPにする
       (または「001_〇〇.jpg」のように番号を頭に付けた画像を1つのフォルダに保存する)
    3. このツールで、保存したプロジェクト・台本・区切り表・画像のZIP(かフォルダ)を指定する
       → 「(元の名前)_画像入り.ymmp」ができる(元のプロジェクトは書き換えない)

使い方:
    python -m material_collector.ymmp_images プロジェクト.ymmp scripts/oyama_yasuharu.txt \
        scripts/oyama_yasuharu_scenes.txt 素材/大山康晴
"""

from __future__ import annotations

import argparse
import bisect
import copy
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .html_sheet import normalize, parse_scene_table, script_utterances

VOICE_TYPE = "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker"
IMAGE_TYPE = "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".jfif", ".avif"}
NUMBER_PATTERN = re.compile(r"^0*(\d+)(?:\D|$)")
REMARK = "画像自動配置"


@dataclass
class Placement:
    no: int
    keyword: str
    frame: int
    length: int
    path: Path | None


# ---------- プロジェクト ----------


def load_project(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def get_timeline(project: dict) -> dict:
    if "Timelines" in project and project["Timelines"]:
        index = project.get("SelectedTimelineIndex", 0)
        if not isinstance(index, int) or not 0 <= index < len(project["Timelines"]):
            index = 0
        return project["Timelines"][index]
    if "Timeline" in project:
        return project["Timeline"]
    raise ValueError("YMM4のプロジェクトファイルとして読めませんでした(タイムラインが見つかりません)。")


def voice_items(timeline: dict) -> list[dict]:
    voices = [item for item in timeline.get("Items", []) if item.get("$type", "").startswith(VOICE_TYPE.split(",")[0])]
    return sorted(voices, key=lambda item: (item.get("Frame", 0), item.get("Layer", 0)))


SPEAKER_PREFIX = re.compile(r"^\s*[^「」\s]{1,10}「")


def voice_text(serif: str) -> str:
    """YMM4のセリフを突き合わせ用の文字列にする(先頭に「魔理沙「」のような名前が残っていれば外す)。"""
    return normalize(SPEAKER_PREFIX.sub("", serif or "", count=1))


def char_map(script: str, voice: str, window: int = 400, key: int = 6) -> tuple[list[int], int]:
    """台本の文字ごとに、YMM4のセリフをつなげた文字列の中の位置を返す。

    名前が付いている、1つのセリフが2つに分かれている、記号や言い回しが少し違う、
    セリフを足した・消した、といった違いがあっても、前後の一致している文字で位置を合わせる。
    戻り値: (位置の一覧, 一致した文字数)。位置が len(voice) なら「最後より後ろ」。
    """
    n, m = len(script), len(voice)
    positions = [m] * n
    i = j = matched = 0
    while i < n and j < m:
        if script[i] == voice[j]:
            positions[i] = j
            matched += 1
            i += 1
            j += 1
            continue
        script_key, voice_key = script[i : i + key], voice[j : j + key]
        skip_voice = voice.find(script_key, j, j + window + key) if len(script_key) == key else -1
        skip_script = script.find(voice_key, i, i + window + key) if len(voice_key) == key else -1
        if skip_voice != -1 and (skip_script == -1 or skip_voice - j <= skip_script - i):
            j = skip_voice  # YMM4側にだけある文字を飛ばす
        elif skip_script != -1:
            for t in range(i, skip_script):  # 台本側にだけある文字を飛ばす
                positions[t] = j
            i = skip_script
        else:
            positions[i] = j  # 1文字だけ違う
            i += 1
            j += 1
    return positions, matched


# ---------- 画像 ----------


def index_images(folder: Path) -> tuple[dict[int, Path], list[str]]:
    found: dict[int, Path] = {}
    warnings: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        match = NUMBER_PATTERN.match(path.stem)
        if not match:
            continue
        no = int(match.group(1))
        if no in found:
            warnings.append(f"{no}番の画像が2つあります。{found[no].name} を使い、{path.name} は使いません。")
            continue
        found[no] = path
    return found, warnings


def unpack_zip(path: Path) -> Path:
    """画像リストの「まとめて保存」で作ったZIPを、ZIPと同じ場所の同名フォルダに展開する。"""
    folder = path.with_suffix("") if path.suffix else path.with_name(path.name + "_画像")
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = Path(info.filename).name  # フォルダ構造や「..」は無視して、ファイル名だけ使う
            if info.is_dir() or not name:
                continue
            (folder / name).write_bytes(archive.read(info))
    return folder


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


# ---------- 配置 ----------


def plan_placements(
    script_text: str, table_text: str, voices: list[dict], image_files: dict[int, Path]
) -> tuple[list[Placement], list[str]]:
    utterances, line_to_utterance = script_utterances(script_text)
    segments = parse_scene_table(table_text)
    if not segments or segments[0]["start"] != 1:
        raise ValueError("区切り表の最初の開始行は 1 にしてください。")
    if segments[-1]["start"] > len(line_to_utterance):
        raise ValueError(f"開始行 {segments[-1]['start']} が台本の行数({len(line_to_utterance)}行)を超えています。")
    if not voices:
        raise ValueError("プロジェクトにセリフ(ボイスアイテム)がありません。先にYMM4で台本を読み込んで保存してください。")

    script_joined = "".join(normalize(u) for u in utterances)
    starts, offset = [], 0
    for u in utterances:
        starts.append(offset)
        offset += len(normalize(u))
    texts = [voice_text(v.get("Serif", "")) for v in voices]
    voice_joined = "".join(texts)
    voice_starts, offset = [], 0
    for t in texts:
        voice_starts.append(offset)
        offset += len(t)
    positions, matched = char_map(script_joined, voice_joined)
    if not script_joined or matched < len(script_joined) * 0.3:
        samples = " / ".join(v.get("Serif", "")[:20] for v in voices[:3])
        raise ValueError(
            "台本とYMM4のセリフがほとんど一致しません。別の台本のプロジェクトではありませんか？"
            f"(YMM4の最初のセリフ: {samples})"
        )
    notes: list[str] = []
    if len(utterances) != len(voices):
        notes.append(f"台本のセリフは{len(utterances)}個、プロジェクトのセリフは{len(voices)}個で数が違いますが、本文で位置を合わせました。")
    end_of_voices = max(v.get("Frame", 0) + v.get("Length", 0) for v in voices)

    def frame_of_utterance(utterance: int) -> int:
        if utterance >= len(utterances) or starts[utterance] >= len(script_joined):
            return end_of_voices
        position = positions[starts[utterance]]
        if position >= len(voice_joined):
            return end_of_voices
        k = bisect.bisect_right(voice_starts, position) - 1
        frame, length, size = int(voices[k].get("Frame", 0)), int(voices[k].get("Length", 0)), len(texts[k])
        # 1つのセリフにまとめられていたときは、文字の位置の割合で途中のフレームにする
        return frame + (length * (position - voice_starts[k]) // size if size else 0)

    placements: list[Placement] = []
    number = 0
    for i, segment in enumerate(segments):
        first = line_to_utterance[segment["start"] - 1]
        if i + 1 < len(segments):
            after = line_to_utterance[segments[i + 1]["start"] - 1]
        else:
            after = len(utterances)
        keywords = segment["keywords"]
        count = len(keywords)
        span = max(after - first, 1)
        for k, keyword in enumerate(keywords):
            number += 1
            start_u = first + (span * k) // count
            end_u = first + (span * (k + 1)) // count
            start = frame_of_utterance(start_u)
            end = frame_of_utterance(end_u) if end_u < len(utterances) else end_of_voices
            if end <= start:
                notes.append(f"{number}番({keyword.ja})は表示する長さが取れないので置きませんでした。")
                continue
            placements.append(Placement(number, keyword.ja, start, end - start, image_files.get(number)))
    return placements, notes


def _animated(value: float, new_format: bool, shape: dict | None = None) -> dict:
    """アニメーションできる値。プロジェクトにある値の形(新しいYMM4はBezierなども持つ)をまねて作る。"""
    if new_format:
        result = copy.deepcopy(shape) if shape and "Values" in shape else {"Span": 0.0, "AnimationType": "なし"}
        result["Values"] = [{"Value": float(value)}]
        result["AnimationType"] = "なし"
        return result
    return {"From": float(value), "To": 0.0, "AnimationType": "なし", "Span": 0.0}


def build_image_item(
    path: Path | str, frame: int, length: int, layer: int, x: float, y: float, zoom: float, new_format: bool, shape: dict | None = None
) -> dict:
    def animated(value: float, new_format: bool) -> dict:
        return _animated(value, new_format, shape)

    item = {
        "$type": IMAGE_TYPE,
        "FilePath": str(path),
        "X": animated(x, new_format),
        "Y": animated(y, new_format),
        "Opacity": animated(100, new_format),
        "Zoom": animated(zoom, new_format),
        "Rotation": animated(0, new_format),
        "FadeIn": 0.0,
        "FadeOut": 0.0,
        "Blend": "Normal",
        "IsInverted": False,
        "IsAlwaysOnTop": False,
        "VideoEffects": [],
        "Group": 0,
        "Frame": int(frame),
        "Layer": int(layer),
        "Length": int(length),
        "PlaybackRate": 100.0,
        "ContentOffset": "00:00:00",
        "IsLocked": False,
        "IsHidden": False,
    }
    if new_format:
        item["Z"] = animated(0, True)
        item["IsClippingWithObjectAbove"] = False
        item["IsZOrderEnabled"] = False
        item["KeyFrames"] = {"Frames": [], "Count": 0}
        item["Remark"] = REMARK
    return item


def add_images(
    project: dict,
    script_text: str,
    table_text: str,
    image_folder: Path,
    *,
    layer: int | None = None,
    fit_width: float = 0.62,
    fit_height: float = 0.69,
    x: float = 0.0,
    y: float = -166.0,
) -> tuple[dict, list[Placement], list[str]]:
    project = copy.deepcopy(project)
    timeline = get_timeline(project)
    voices = voice_items(timeline)
    image_files, notes = index_images(image_folder)
    placements, plan_notes = plan_placements(script_text, table_text, voices, image_files)
    notes += plan_notes

    items = timeline.setdefault("Items", [])
    # 前に自動で置いた画像があれば入れ替える(何度でもやり直せるように)
    items[:] = [item for item in items if not (item.get("$type") == IMAGE_TYPE and item.get("Remark") == REMARK)]
    layer_settings = timeline.get("LayerSettings") if isinstance(timeline.get("LayerSettings"), dict) else {}
    labels = [s for s in layer_settings.get("Items", []) if isinstance(s, dict)]
    labeled = [int(s.get("Layer", 0)) for s in labels if s.get("Label") != "画像"]
    max_layer = max([int(item.get("Layer", 0)) for item in items] + [int(timeline.get("MaxLayer", 0))] + labeled)
    target_layer = max_layer + 1 if layer is None else layer
    new_format = any("Values" in (v.get("X") or {}) for v in voices) or "Timelines" in project
    shape = next((v.get("X") for v in voices if isinstance(v.get("X"), dict) and "Values" in v["X"]), None)
    if labels and not any(int(s.get("Layer", -1)) == target_layer for s in labels):
        label = copy.deepcopy(labels[0])
        label.update({"Layer": target_layer, "Label": "画像", "IsHidden": False})
        labels.append(label)
        layer_settings["Items"] = labels

    video = timeline.get("VideoInfo") or {}
    width, height = float(video.get("Width", 1920)), float(video.get("Height", 1080))
    for placement in placements:
        if placement.path is None:
            continue
        zoom = 100.0
        size = image_size(placement.path)
        if size and size[0] > 0 and size[1] > 0:
            zoom = round(min(width * fit_width / size[0], height * fit_height / size[1]) * 100, 1)
        items.append(
            build_image_item(placement.path.resolve(), placement.frame, placement.length, target_layer, x, y, zoom, new_format, shape)
        )

    timeline["MaxLayer"] = max(int(timeline.get("MaxLayer", 0)), target_layer)
    end = max([int(i.get("Frame", 0)) + int(i.get("Length", 0)) for i in items] + [0])
    if isinstance(timeline.get("Length"), int):
        timeline["Length"] = max(timeline["Length"], end)
    notes.append(f"画像はレイヤー{target_layer}に置きました。")
    return project, placements, notes


def default_output(project_path: Path) -> Path:
    return project_path.with_name(f"{project_path.stem}_画像入り{project_path.suffix}")


def ask_path(prompt: str) -> Path:
    while True:
        answer = input(prompt).strip().strip('"').strip()
        if answer:
            return Path(answer)


def ask_missing(args: argparse.Namespace) -> None:
    """ドラッグ&ドロップ(.bat)から起動したとき、足りないものを画面で聞く。"""
    if args.table is None:
        tables = sorted(Path("scripts").glob("*_scenes.txt"))
        if tables:
            print("どの台本の画像を並べますか？番号を入れてEnterを押してください。")
            for i, table in enumerate(tables, 1):
                print(f"  {i}: {table.name.removesuffix('_scenes.txt')}")
            while args.table is None:
                answer = input("番号: ").strip()
                if answer.isdigit() and 1 <= int(answer) <= len(tables):
                    args.table = tables[int(answer) - 1]
        else:
            args.table = ask_path("区切り表(_scenes.txt)をこの画面にドラッグしてEnter: ")
    if args.script is None:
        guess = args.table.with_name(args.table.name.replace("_scenes.txt", ".txt"))
        args.script = guess if guess.exists() else ask_path("台本(.txt)をこの画面にドラッグしてEnter: ")
    if args.images is None:
        args.images = ask_path("画像リストで保存したZIP(または画像のフォルダ)をこの画面にドラッグしてEnter: ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YMM4のプロジェクトに、区切り表どおりに画像を並べる")
    parser.add_argument("project", type=Path, help="台本を読み込んで保存した .ymmp")
    parser.add_argument("script", type=Path, nargs="?", help="台本(.txt)")
    parser.add_argument("table", type=Path, nargs="?", help="区切り表(_scenes.txt)")
    parser.add_argument("images", type=Path, nargs="?", help="画像リストで保存したZIP、または「001_〇〇.jpg」のように番号を付けた画像のフォルダ")
    parser.add_argument("--ask", action="store_true", help="足りないものを画面で聞く(.batから使う)")
    parser.add_argument("-o", "--output", type=Path, help="省略すると「元の名前_画像入り.ymmp」")
    parser.add_argument("--layer", type=int, help="画像を置くレイヤー(省略すると一番上の空いたレイヤー)")
    parser.add_argument("--fit-width", type=float, default=0.62, help="画面の横幅に対する画像の最大の大きさ(0〜1)")
    parser.add_argument("--fit-height", type=float, default=0.69, help="画面の高さに対する画像の最大の大きさ(0〜1)")
    parser.add_argument("--x", type=float, default=0.0, help="画像の横位置(画面中央が0)")
    parser.add_argument("--y", type=float, default=-166.0, help="画像の縦位置(画面中央が0、マイナスで上)")
    args = parser.parse_args(argv)

    if args.ask:
        ask_missing(args)
    elif None in (args.script, args.table, args.images):
        parser.error("台本・区切り表・画像フォルダを指定してください。")
    if args.images.is_file() and zipfile.is_zipfile(args.images):
        args.images = unpack_zip(args.images)
        print(f"ZIPを展開しました: {args.images}")
    if not args.images.is_dir():
        parser.error(f"画像のZIPかフォルダが見つかりません: {args.images}")
    project, placements, notes = add_images(
        load_project(args.project),
        args.script.read_text(encoding="utf-8-sig"),
        args.table.read_text(encoding="utf-8-sig"),
        args.images,
        layer=args.layer,
        fit_width=args.fit_width,
        fit_height=args.fit_height,
        x=args.x,
        y=args.y,
    )
    output = args.output or default_output(args.project)
    if output.resolve() == args.project.resolve():
        parser.error("元のプロジェクトを上書きしないよう、別の名前を指定してください。")
    output.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    placed = [p for p in placements if p.path is not None]
    missing = [p for p in placements if p.path is None]
    print(f"作成しました: {output}")
    print(f"画像を {len(placed)} 枚置きました。")
    for note in notes:
        print(f"・{note}")
    if missing:
        print(f"フォルダに見つからなかった番号({len(missing)}枚。その場所は空けてあります):")
        for p in missing:
            print(f"  {p.no:03d} {p.keyword}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
