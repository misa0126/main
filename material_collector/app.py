from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QPoint, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QDrag, QFont, QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .pipeline import PipelineConfig, run_pipeline
from .script_parser import split_script_into_scenes
from .viewer import SPEAKER_PATTERN, _speaker_class

SETTINGS_PATH = Path.home() / ".yukkuri_material_collector.json"
DEFAULT_OUTPUT_ROOT = Path.home() / "Documents" / "ゆっくり素材"
THUMB_SIZE = QSize(240, 135)

SPEAKER_COLORS = {"marisa": "#b58900", "reimu": "#c0392b", "other": "#4a6fa5"}
COLOR_OK = "#2e7d4f"
COLOR_WARN = "#b9650b"
COLOR_LINE = "#d9d5cc"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def reveal_in_file_manager(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


# ---------------------------------------------------------------- 設定ダイアログ


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("APIキーの設定")
        self.setMinimumWidth(520)
        self._fields: dict[str, QLineEdit] = {}
        form = QFormLayout()
        for key, label, required in [
            ("ANTHROPIC_API_KEY", "Claude APIキー (任意)", True),
            ("PEXELS_API_KEY", "Pexels APIキー (任意)", False),
            ("PIXABAY_API_KEY", "Pixabay APIキー (任意)", False),
        ]:
            field = QLineEdit(settings.get(key, ""))
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText("sk-ant-..." if required else "未設定なら使いません")
            self._fields[key] = field
            form.addRow(label, field)

        note = QLabel(
            "キーはこのパソコンの次のファイルに保存されます:\n"
            f"{SETTINGS_PATH}\n"
            "Claude APIキーがあると、台本を貼るだけでキーワード作成と画像の内容チェックまで自動で行います。\n"
            "キーがなくても、キーワード表を指定すれば素材集めはできます(内容チェックはなし)。\n"
            "Pexels / Pixabay のキーを入れると、風景や物の写真の取得元が増えます。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #6b675f;")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {key: field.text().strip() for key, field in self._fields.items()}


# ---------------------------------------------------------------- 素材集めの実行


class PipelineWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, config: PipelineConfig):
        super().__init__()
        self._config = config
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            run_pipeline(
                self._config,
                log=self.log.emit,
                progress=self.progress.emit,
                should_stop=lambda: self._stop,
            )
            self.finished.emit(str(self._config.output_dir))
        except Exception as e:  # 画面にエラーを出すため、すべての例外を受け取る
            self.log.emit(traceback.format_exc())
            self.failed.emit(f"{e.__class__.__name__}: {e}")


class InputPage(QWidget):
    """台本を貼り付けて素材集めを始める画面。"""

    run_requested = Signal(object)
    open_requested = Signal(str)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings

        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText(
            "ここに台本を貼り付けてください。\n\n"
            "空行で区切ったひとかたまりが1シーンになり、シーンごとに画像を集めます。\n\n"
            "魔理沙「今回は美輪明宏について解説するぜ」\n"
            "魔理沙「1935年、長崎に生まれたんだ」\n\n"
            "霊夢「どんな人生だったのかしら」"
        )
        self.script_edit.textChanged.connect(self._update_scene_count)
        self.scene_count = QLabel("0シーン")

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例: 美輪明宏")
        self.root_edit = QLineEdit(settings.get("output_root", str(DEFAULT_OUTPUT_ROOT)))
        browse = QPushButton("参照...")
        browse.clicked.connect(self._browse_root)
        root_row = QHBoxLayout()
        root_row.addWidget(self.root_edit, 1)
        root_row.addWidget(browse)

        self.images_spin = QSpinBox()
        self.images_spin.setRange(1, 6)
        self.images_spin.setValue(int(settings.get("images_per_scene", 3)))
        self.google_check = QCheckBox("足りない分をGoogle画像検索で補う(要確認として分けて表示)")
        self.google_check.setChecked(bool(settings.get("google_fallback", True)))

        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("APIキーなしで使う場合に指定(例: miwa_akihiro_keywords.txt)")
        keywords_browse = QPushButton("参照...")
        keywords_browse.clicked.connect(self._browse_keywords)
        keywords_row = QHBoxLayout()
        keywords_row.addWidget(self.keywords_edit, 1)
        keywords_row.addWidget(keywords_browse)

        form = QFormLayout()
        form.addRow("動画のタイトル", self.title_edit)
        form.addRow("キーワード表", keywords_row)
        form.addRow("保存先フォルダ", root_row)
        form.addRow("1シーンの候補画像", self.images_spin)
        form.addRow("", self.google_check)

        self.start_button = QPushButton("素材を集める")
        self.start_button.setMinimumHeight(40)
        self.start_button.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.start_button.clicked.connect(self._start)
        open_button = QPushButton("前回の結果を開く...")
        open_button.clicked.connect(self._open_existing)
        buttons = QHBoxLayout()
        buttons.addWidget(open_button)
        buttons.addStretch(1)
        buttons.addWidget(self.start_button)

        header = QHBoxLayout()
        header.addWidget(QLabel("台本"))
        header.addStretch(1)
        header.addWidget(self.scene_count)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.script_edit, 1)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _update_scene_count(self):
        count = len(split_script_into_scenes(self.script_edit.toPlainText()))
        self.scene_count.setText(f"{count}シーン")

    def _browse_root(self):
        folder = QFileDialog.getExistingDirectory(self, "保存先フォルダ", self.root_edit.text())
        if folder:
            self.root_edit.setText(folder)

    def _browse_keywords(self):
        path, _ = QFileDialog.getOpenFileName(self, "キーワード表を選ぶ", "", "テキストファイル (*.txt);;すべてのファイル (*)")
        if path:
            self.keywords_edit.setText(path)

    def _open_existing(self):
        folder = QFileDialog.getExistingDirectory(self, "結果フォルダを選ぶ(manifest.jsonのあるフォルダ)", self.root_edit.text())
        if folder:
            self.open_requested.emit(folder)

    def _start(self):
        text = self.script_edit.toPlainText().strip()
        if not split_script_into_scenes(text):
            QMessageBox.warning(self, "台本がありません", "台本を貼り付けてから押してください。")
            return
        keywords_path = None
        if self.keywords_edit.text().strip():
            keywords_path = Path(self.keywords_edit.text().strip())
            if not keywords_path.exists():
                QMessageBox.warning(self, "キーワード表が見つかりません", f"{keywords_path} がありません。")
                return
        title = self.title_edit.text().strip() or "台本"
        safe_title = "".join(c for c in title if c not in '\\/:*?"<>|').strip() or "台本"
        output_dir = Path(self.root_edit.text().strip() or DEFAULT_OUTPUT_ROOT) / (
            f"{safe_title}_{datetime.now():%Y%m%d_%H%M}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        script_path = output_dir / "script.txt"
        script_path.write_text(text + "\n", encoding="utf-8")

        self._settings.update(
            output_root=self.root_edit.text().strip(),
            images_per_scene=self.images_spin.value(),
            google_fallback=self.google_check.isChecked(),
        )
        save_settings(self._settings)
        self.run_requested.emit(
            PipelineConfig(
                script_path=script_path,
                output_dir=output_dir,
                images_per_scene=self.images_spin.value(),
                google_fallback=self.google_check.isChecked(),
                keyword_table_path=keywords_path,
            )
        )


class RunPage(QWidget):
    """実行中の進み具合を表示する画面。"""

    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = QLabel("準備中...")
        self.status.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.bar = QProgressBar()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.stop_button = QPushButton("中止する(ここまでの結果は残ります)")
        self.stop_button.clicked.connect(self._stop)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(self.log_view, 1)
        layout.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignRight)

    def reset(self):
        self.status.setText("素材を集めています...")
        self.bar.setRange(0, 0)
        self.log_view.clear()
        self.stop_button.setEnabled(True)

    def on_progress(self, done: int, total: int):
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.status.setText(f"素材を集めています... {done}/{total}シーン完了")

    def append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def _stop(self):
        self.stop_button.setEnabled(False)
        self.status.setText("中止しています(今のシーンが終わるまでお待ちください)...")
        self.stop_requested.emit()


# ---------------------------------------------------------------- 確認画面


class ImageCard(QFrame):
    """ドラッグでYMM4などへファイルとして渡せる画像カード。"""

    def __init__(self, image_path: Path, info: dict, needs_review: bool, parent=None):
        super().__init__(parent)
        self._path = image_path
        self._info = info
        self._press_pos: QPoint | None = None
        color = COLOR_WARN if needs_review else COLOR_LINE
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ border: 2px solid {color}; border-radius: 6px; background: {'#fff4e5' if needs_review else '#faf9f6'}; }}"
        )
        self.setFixedWidth(THUMB_SIZE.width() + 12)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        pixmap = QPixmap(str(image_path))
        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setFixedSize(THUMB_SIZE)
        self._thumb.setStyleSheet("background: #000;")
        if not pixmap.isNull():
            self._thumb.setPixmap(
                pixmap.scaled(THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )

        badge_color, badge_text = (COLOR_WARN, "要確認") if needs_review else (COLOR_OK, "確認済み")
        lines = [f'<span style="background:{badge_color}; color:#fff; font-weight:bold;">&nbsp;{badge_text}&nbsp;</span>']
        for key, prefix in [("title", ""), ("author", "作者: "), ("license", "")]:
            if info.get(key):
                lines.append(html.escape(prefix + str(info[key])[:50]))
        meta = QLabel("<br>".join(lines))
        meta.setWordWrap(True)
        meta.setStyleSheet("font-size: 11px; color: #4a463f;")
        meta.setMaximumWidth(THUMB_SIZE.width())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._thumb)
        layout.addWidget(meta)
        self.setToolTip("ドラッグでYMM4へ / クリックで拡大 / 右クリックでコピーなど")

    def _mime(self) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self._path.resolve()))])
        return mime

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        drag.setMimeData(self._mime())
        if self._thumb.pixmap() is not None and not self._thumb.pixmap().isNull():
            drag.setPixmap(self._thumb.pixmap().scaledToWidth(160))
        self._press_pos = None
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event):
        if self._press_pos is not None and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            self._show_large()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        copy_image = QAction("画像をコピー", menu)
        copy_image.triggered.connect(self._copy)
        reveal = QAction("フォルダで表示", menu)
        reveal.triggered.connect(lambda: reveal_in_file_manager(self._path))
        menu.addAction(copy_image)
        menu.addAction(reveal)
        link = self._info.get("page_url") or self._info.get("image_url")
        if link:
            open_source = QAction("出典ページを開く", menu)
            open_source.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(link)))
            menu.addAction(open_source)
        menu.exec(event.globalPos())

    def _copy(self):
        mime = self._mime()
        image = QImage(str(self._path))
        if not image.isNull():
            mime.setImageData(image)
        QGuiApplication.clipboard().setMimeData(mime)

    def _show_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self._info.get("title") or self._path.name)
        label = QLabel()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pixmap = QPixmap(str(self._path))
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    int(screen.width() * 0.8),
                    int(screen.height() * 0.8),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout = QVBoxLayout(dialog)
        layout.addWidget(label)
        dialog.exec()


def _script_html(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        match = SPEAKER_PATTERN.match(raw.strip())
        if match:
            speaker = match.group("speaker")
            color = SPEAKER_COLORS[_speaker_class(speaker)]
            lines.append(
                f'<b style="color:{color}">{html.escape(speaker)}</b>「{html.escape(match.group("line"))}」'
            )
        elif raw.strip():
            lines.append(html.escape(raw.strip()))
    return "<br>".join(lines)


def _notes_html(scene: dict) -> str:
    keywords = "、".join(k.get("ja", "") for k in scene.get("keywords", []))
    items = []
    selected = scene.get("selected_images", [])
    review = scene.get("needs_review_images", [])
    if scene.get("skipped"):
        items.append("画像を探さないシーンです(前のシーンの画像を続けて使う想定)。")
    elif scene.get("error"):
        items.append(f'<b style="color:{COLOR_WARN}">エラーで処理できませんでした: {html.escape(scene["error"])}</b>')
    elif not selected and not review:
        items.append(f'<b style="color:{COLOR_WARN}">合う画像が見つかりませんでした。手動で探してください。</b>')
    if review:
        items.append(f'<b style="color:{COLOR_WARN}">要確認の画像が{len(review)}枚あります。権利を確認してから使ってください。</b>')
    for number, image in enumerate(selected + review, start=1):
        reason = (image.get("relevance") or {}).get("reason")
        if reason:
            items.append(f"画像{number}: {html.escape(reason)}")
    if (selected or review) and all(not img.get("relevance") for img in selected + review):
        items.append("内容チェックなし。候補から使う画像を選んでください。")
    rejected = scene.get("rejected_by_relevance_check", [])
    if rejected:
        items.append(f"内容が合わず除外: {len(rejected)}枚")
    body = "".join(f"<li>{item}</li>" for item in items)
    return f'<span style="color:#6b675f">検索キーワード</span><br>{html.escape(keywords)}<ul style="margin-left:-20px">{body}</ul>'


class ReviewPage(QWidget):
    """左に台本、真ん中にメモ、右に候補画像を並べる確認画面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header = QLabel("まだ結果がありません。「台本」タブで素材を集めてください。")
        self.header.setStyleSheet("font-size: 14px;")
        self.header.setWordWrap(True)
        open_folder = QPushButton("フォルダを開く")
        open_folder.clicked.connect(self._open_folder)
        open_credits = QPushButton("クレジット一覧を開く")
        open_credits.clicked.connect(self._open_credits)
        top = QHBoxLayout()
        top.addWidget(self.header, 1)
        top.addWidget(open_credits)
        top.addWidget(open_folder)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.scroll, 1)
        self._folder: Path | None = None

    def load(self, folder: Path) -> None:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self._folder = folder
        content = QWidget()
        grid = QGridLayout(content)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        total_selected = total_review = missing = 0
        for row, scene in enumerate(manifest.get("scenes", [])):
            selected = scene.get("selected_images", [])
            review = scene.get("needs_review_images", [])
            total_selected += len(selected)
            total_review += len(review)
            if not selected and not review and not scene.get("skipped"):
                missing += 1

            script = QLabel(
                f'<span style="color:#6b675f; font-weight:bold">シーン {scene["index"]}</span><br>{_script_html(scene.get("text", ""))}'
            )
            script.setWordWrap(True)
            script.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            script.setAlignment(Qt.AlignmentFlag.AlignTop)

            notes = QLabel(_notes_html(scene))
            notes.setWordWrap(True)
            notes.setAlignment(Qt.AlignmentFlag.AlignTop)
            notes.setStyleSheet("font-size: 12px;")

            images = QWidget()
            images_layout = QHBoxLayout(images)
            images_layout.setContentsMargins(0, 0, 0, 0)
            images_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            for info, needs_review in [(i, False) for i in selected] + [(i, True) for i in review]:
                path = folder / info["file"]
                if path.exists():
                    images_layout.addWidget(ImageCard(path, info, needs_review))
            if images_layout.count() == 0 and scene.get("skipped"):
                continued = QLabel("前のシーンの画像のまま")
                continued.setStyleSheet("color:#6b675f; padding: 12px;")
                images_layout.addWidget(continued)
            elif images_layout.count() == 0:
                empty = QLabel("画像なし")
                empty.setStyleSheet(f"color:{COLOR_WARN}; border: 2px dashed {COLOR_WARN}; padding: 24px;")
                images_layout.addWidget(empty)

            for column, widget in enumerate([script, notes, images]):
                grid.addWidget(widget, row * 2, column, Qt.AlignmentFlag.AlignTop)
            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setStyleSheet(f"color: {COLOR_LINE};")
            grid.addWidget(divider, row * 2 + 1, 0, 1, 3)

        self.scroll.setWidget(content)
        self.header.setText(
            f"<b>{html.escape(folder.name)}</b>　"
            f"{len(manifest.get('scenes', []))}シーン ・ 確認済み {total_selected}枚 ・ "
            f'<span style="color:{COLOR_WARN}">要確認 {total_review}枚</span> ・ 画像なし {missing}シーン　'
            "<br>画像をYMM4へドラッグして使ってください(右クリックでコピーも可)。"
        )

    def _open_folder(self):
        if self._folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))

    def _open_credits(self):
        if self._folder and (self._folder / "CREDITS.txt").exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder / "CREDITS.txt")))


# ---------------------------------------------------------------- メインウィンドウ


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ゆっくり素材集め")
        self.resize(1400, 900)
        self._settings = load_settings()

        self.tabs = QTabWidget()
        self.input_page = InputPage(self._settings)
        self.run_page = RunPage()
        self.review_page = ReviewPage()
        self.tabs.addTab(self.input_page, "台本")
        self.tabs.addTab(self.run_page, "進み具合")
        self.tabs.addTab(self.review_page, "確認シート")
        self.setCentralWidget(self.tabs)

        settings_action = QAction("APIキーの設定...", self)
        settings_action.triggered.connect(self._edit_settings)
        self.menuBar().addMenu("設定").addAction(settings_action)

        self.input_page.run_requested.connect(self._start)
        self.input_page.open_requested.connect(lambda folder: self._show_result(Path(folder)))
        self.run_page.stop_requested.connect(self._stop)
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None

    def _edit_settings(self) -> bool:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._settings.update(dialog.values())
        save_settings(self._settings)
        return True

    def _start(self, config: PipelineConfig):
        if self._thread is not None:
            return
        has_api_key = bool(self._settings.get("ANTHROPIC_API_KEY"))
        if not has_api_key and config.keyword_table_path is None:
            QMessageBox.information(
                self,
                "APIキーかキーワード表が必要です",
                "Claude APIキーがない場合は、「キーワード表」にキーワード表のファイルを指定してください。\n"
                "APIキーを使う場合は、メニューの「設定 → APIキーの設定」で入力してください。",
            )
            return
        # APIキーがなければ内容チェックはしない(キーワード表のキーワードで集めるだけ)
        config.check_relevance = has_api_key
        for key in ("ANTHROPIC_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY"):
            if self._settings.get(key):
                os.environ[key] = self._settings[key]
            else:
                os.environ.pop(key, None)

        self.run_page.reset()
        self.tabs.setCurrentWidget(self.run_page)
        self.input_page.start_button.setEnabled(False)

        self._thread = QThread(self)
        self._worker = PipelineWorker(config)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.run_page.append_log)
        self._worker.progress.connect(self.run_page.on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _stop(self):
        if self._worker is not None:
            self._worker.stop()

    def _cleanup(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.input_page.start_button.setEnabled(True)

    def _on_finished(self, folder: str):
        self._cleanup()
        self.run_page.status.setText("完了しました")
        self._show_result(Path(folder))

    def _on_failed(self, message: str):
        self._cleanup()
        self.run_page.status.setText("エラーで止まりました")
        QMessageBox.critical(self, "エラー", f"素材集めが途中で止まりました。\n\n{message}")

    def _show_result(self, folder: Path):
        if not (folder / "manifest.json").exists():
            QMessageBox.warning(self, "結果が見つかりません", f"{folder} に manifest.json がありません。")
            return
        self.review_page.load(folder)
        self.tabs.setCurrentWidget(self.review_page)


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont(app.font().family(), 10))
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and (Path(sys.argv[1]) / "manifest.json").exists():
        window._show_result(Path(sys.argv[1]))
    return app.exec()
