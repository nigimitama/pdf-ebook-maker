"""WizardPanel — 6-step accordion wizard for the PDF Ebook Maker workflow.

Steps
-----
1. ファイルの指定             — drop files / browse
2. OCR実行                   — contrast/resize options, OCR run button
3. 傾きを補正                — deskew correction option and preview
4. 目次の指定                — page-category list + TOC editor review
5. 出力ファイル名              — cover thumbnail, suggested title, output filename
6. PDF出力                    — save directory, generate button + progress

Signals
-------
ocr_requested(RunOptions): user clicked the OCR run button in Step 2.
rotation_requested(bool):  user clicked next in Step 3 (bool = apply deskew).
pdf_requested():           user clicked generate in Step 6.
files_changed(list[str]):  files were added/cleared (used by MainWindow to start preloader).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from document_structure import DocumentStructure

from .constants import (
    BG_GRAY,
    BORDER,
    BORDER_LIGHT,
    CORAL,
    TEXT_MUTED,
    TEXT_PRI,
    TEXT_SEC,
)
from .drop_zone import DropZone
from .output_card import OutputCard
from .progress_card import ProgressCard
from .run_options import RunOptions
from .step_card import StepCard
from .structure_panel import StructurePanel

_CB_STYLE = f"""
    QCheckBox {{
        font-size:13px; color:{TEXT_PRI};
        spacing:10px; background:transparent; border:none;
    }}
    QCheckBox::indicator {{ width:18px; height:18px; border-radius:4px; }}
    QCheckBox::indicator:checked {{ background:{CORAL}; border:none; }}
    QCheckBox::indicator:unchecked {{
        background:white; border:2px solid {BORDER_LIGHT}; border-radius:4px;
    }}
"""

_SPINBOX_STYLE = f"""
    QSpinBox, QDoubleSpinBox {{
        background:{BG_GRAY}; border:1px solid {BORDER_LIGHT};
        border-radius:6px; padding:2px 6px;
        font-size:13px; color:{TEXT_PRI};
    }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color:{TEXT_MUTED}; border-color:{BORDER};
    }}
"""

_TRANSPARENT = "background:transparent; border:none; border-radius:0;"

_COVER_THUMB_SIZE = 96


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


class WizardPanel(QWidget):
    """Scrollable wizard panel with 6 accordion steps."""

    ocr_requested = Signal(object)  # RunOptions
    rotation_requested = Signal(bool)  # apply_deskew
    pdf_requested = Signal()
    files_changed = Signal(list)  # list[str] — for preloader
    ocr_step_activated = Signal()  # emitted when Step 2 becomes visible

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        self._expander: _FileExpander | None = None
        self._cover_image_path: str = ""
        self._cover_ocr_lines: list = []
        self._ocr_image_paths: list[str] = []
        self._ocr_results: dict[str, list] = {}
        self._angle_overrides: dict[str, float] = {}
        self._cached_preview_samples: list | None = None
        self._rotation_preview_worker = None
        self.setStyleSheet(f"background:{BG_GRAY};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def current_files(self) -> list[str]:
        return list(self._files)

    @property
    def current_options(self) -> RunOptions:
        return RunOptions(
            output_dir=self._output_dir_edit.text().strip(),
            output_name=self._output_card.output_name,
            sort_by_name=True,
            contrast_adjust=self._cb_contrast.isChecked(),
            brightness=self._spin_brightness.value(),
            gamma=self._spin_gamma.value(),
            resize_width=self._spin_resize_w.value()
            if self._cb_resize_w.isChecked()
            else None,
            resize_height=self._spin_resize_h.value()
            if self._cb_resize_h.isChecked()
            else None,
            jpeg_quality=self._spin_jpeg_quality.value(),
        )

    @property
    def current_structure(self) -> DocumentStructure:
        return self._structure_panel.current_structure

    @property
    def angle_overrides(self) -> dict[str, float]:
        """Correction angles to pass to RotationWorker.

        Uses pre-estimated angles from the preview worker as a base so that
        re-estimation is skipped during actual correction.  User-edited values
        (confirmed via the preview dialog) take priority over the estimates.
        """
        base: dict[str, float] = {}
        if self._cached_preview_samples is not None:
            for sample in self._cached_preview_samples:
                if sample.angle is not None:
                    base[sample.path] = sample.angle
        base.update(self._angle_overrides)
        return base

    def on_ocr_done(self, image_paths: list[str], ocr_results: dict[str, list]) -> None:
        """Call when OCR worker finishes. Activates the correction step."""
        self._ocr_image_paths = image_paths
        self._ocr_results = ocr_results
        self._cached_preview_samples = None
        n = len(image_paths)
        self._step2.set_completed(f"OCR完了 ({n} ページ)")
        self._step3.set_active()
        self._ocr_btn.setEnabled(True)
        self._start_rotation_preview_worker()

    def on_correction_done(
        self,
        structure: DocumentStructure,
        ocr_results: dict[str, list],
        was_corrected: bool = False,
    ) -> None:
        """Call when correction step finishes (with or without deskew)."""
        self._structure_panel.load(structure, ocr_results)
        if structure.suggested_title:
            self._output_card.set_output_name(structure.suggested_title)
            self._suggested_title_lbl.setText(
                f"推定タイトル: {structure.suggested_title}"
            )
        if structure.pages:
            self._cover_image_path = structure.pages[0].path
            self._cover_ocr_lines = (ocr_results or {}).get(self._cover_image_path, [])
            self._cover_row.setVisible(True)
            self._load_cover_thumbnail()
        status = "傾き補正完了" if was_corrected else "スキップ"
        self._step3.set_completed(status)
        self._step4.set_active()
        self._correction_btn.setEnabled(True)

    def set_ocr_progress(self, value: int, message: str, note: str = "") -> None:
        self._ocr_progress_card.set_progress(value, message, note)

    def set_rotation_progress(self, value: int, message: str, note: str = "") -> None:
        self._rotation_progress_card.set_progress(value, message, note)

    def on_pdf_done(self) -> None:
        self._pdf_btn.setEnabled(True)

    def on_error(self, message: str) -> None:
        self._ocr_progress_card.set_progress(0, "エラーが発生しました", message)
        self._rotation_progress_card.set_progress(0, "エラーが発生しました", message)
        self._pdf_btn.setEnabled(True)
        self._ocr_btn.setEnabled(True)
        self._correction_btn.setEnabled(True)

    def set_running(self, running: bool) -> None:
        self._ocr_btn.setEnabled(not running)
        self._correction_btn.setEnabled(not running)
        self._pdf_btn.setEnabled(not running)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setStyleSheet(f"background:{BG_GRAY};")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(40, 24, 40, 24)
        inner.setSpacing(8)

        self._step1 = StepCard(
            1, "ファイルの指定", self._make_step1_content(), collapsible=False
        )
        self._step2 = StepCard(2, "OCR実行", self._make_step2_content())
        self._step3 = StepCard(3, "傾きを補正", self._make_step3_content())
        self._step4 = StepCard(4, "目次の指定", self._make_step4_content())
        self._step5 = StepCard(5, "出力ファイル名", self._make_step5_content())
        self._step6 = StepCard(6, "PDF出力", self._make_step6_content())

        inner.addWidget(self._step1)
        inner.addWidget(self._step2)
        inner.addWidget(self._step3)
        inner.addWidget(self._step4)
        inner.addWidget(self._step5)
        inner.addWidget(self._step6)
        inner.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._step1.set_active()

    # ── Step 1: File selection ─────────────────────────────────────────────────

    def _make_step1_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        self._drop_zone.btn_files.clicked.connect(self._browse_files)
        self._drop_zone.btn_folder.clicked.connect(self._browse_folder)
        layout.addWidget(self._drop_zone)

        self._load_label = QLabel()
        self._load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_label.setStyleSheet(
            f"font-size:13px;color:{TEXT_SEC};background:transparent;border:none;"
        )
        self._load_label.setVisible(False)
        layout.addWidget(self._load_label)

        clear_row = QWidget()
        clear_row.setStyleSheet(_TRANSPARENT)
        cr_layout = QHBoxLayout(clear_row)
        cr_layout.setContentsMargins(0, 0, 0, 0)
        cr_layout.addStretch()
        clear_btn = QPushButton("🗑  クリア")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_GRAY};color:{TEXT_MUTED};
                border:none;border-radius:6px;
                padding:4px 10px;font-size:12px;
            }}
            QPushButton:hover {{ background:#fee2e2;color:#ef4444; }}
        """)
        clear_btn.clicked.connect(self._clear_files)
        cr_layout.addWidget(clear_btn)
        clear_row.setVisible(False)
        self._clear_row = clear_row
        layout.addWidget(clear_row)

        return w

    # ── Step 2: Options + OCR ──────────────────────────────────────────────────

    def _make_step2_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(
            _lbl(
                "🖼  画像処理オプション",
                f"font-size:13px; font-weight:700; color:{TEXT_PRI};"
                " background:transparent; border:none;",
            )
        )

        layout.addWidget(self._make_contrast_section())
        layout.addWidget(self._make_resize_section())

        self._preview_btn = QPushButton("🔍  仕上がり確認")
        self._preview_btn.setFixedHeight(40)
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.setEnabled(False)
        self._preview_btn.setStyleSheet(f"""
            QPushButton {{
                background:#F0F5FF; color:#6366F1;
                border:1px solid #C7D2FE; border-radius:10px;
                font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:#E0E7FF; }}
            QPushButton:pressed {{ background:#C7D2FE; }}
            QPushButton:disabled {{ background:{BG_GRAY}; color:{TEXT_MUTED}; border-color:{BORDER_LIGHT}; }}
        """)
        self._preview_btn.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self._preview_btn)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{BORDER};")
        layout.addWidget(sep)

        self._ocr_btn = QPushButton("▶  OCRを実行する")
        self._ocr_btn.setFixedHeight(48)
        self._ocr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CORAL};color:white;
                border:none;border-radius:10px;
                font-size:15px;font-weight:700;
            }}
            QPushButton:hover {{ background:#ff5252; }}
            QPushButton:pressed {{ background:#e53e3e; }}
            QPushButton:disabled {{ background:{BORDER_LIGHT};color:{TEXT_MUTED}; }}
        """)
        self._ocr_btn.clicked.connect(self._on_ocr_clicked)
        layout.addWidget(self._ocr_btn)

        self._ocr_progress_card = ProgressCard()
        layout.addWidget(self._ocr_progress_card)

        return w

    # ── Step 3: Image correction (deskew) ─────────────────────────────────────

    def _make_step3_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(
            _lbl(
                "📐  傾き補正オプション",
                f"font-size:13px; font-weight:700; color:{TEXT_PRI};"
                " background:transparent; border:none;",
            )
        )

        self._cb_deskew = QCheckBox("画像の傾き補正を行う")
        self._cb_deskew.setChecked(True)
        self._cb_deskew.setStyleSheet(_CB_STYLE)
        layout.addWidget(self._cb_deskew)

        note = _lbl(
            "　OCRの読み取り結果を用いて傾きを自動補正します",
            f"font-size:12px; color:{TEXT_SEC}; background:transparent; border:none;",
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._correction_preview_btn = QPushButton("🔍  仕上がり確認")
        self._correction_preview_btn.setFixedHeight(40)
        self._correction_preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._correction_preview_btn.setEnabled(False)
        self._correction_preview_btn.setStyleSheet(f"""
            QPushButton {{
                background:#F0F5FF; color:#6366F1;
                border:1px solid #C7D2FE; border-radius:10px;
                font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:#E0E7FF; }}
            QPushButton:pressed {{ background:#C7D2FE; }}
            QPushButton:disabled {{ background:{BG_GRAY}; color:{TEXT_MUTED}; border-color:{BORDER_LIGHT}; }}
        """)
        self._correction_preview_btn.clicked.connect(
            self._on_correction_preview_clicked
        )
        layout.addWidget(self._correction_preview_btn)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{BORDER};")
        layout.addWidget(sep)

        btn_row = QWidget()
        btn_row.setStyleSheet(_TRANSPARENT)
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        back3_btn = self._make_back_btn()
        back3_btn.clicked.connect(self._on_step3_back)
        btn_layout.addWidget(back3_btn)
        btn_layout.addStretch()

        self._correction_btn = QPushButton("次へ  ›")
        self._correction_btn.setFixedHeight(44)
        self._correction_btn.setFixedWidth(140)
        self._correction_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._correction_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CORAL};color:white;
                border:none;border-radius:10px;
                font-size:14px;font-weight:700;
            }}
            QPushButton:hover {{ background:#ff5252; }}
            QPushButton:pressed {{ background:#e53e3e; }}
            QPushButton:disabled {{ background:{BORDER_LIGHT};color:{TEXT_MUTED}; }}
        """)
        self._correction_btn.clicked.connect(self._on_step3_next)
        btn_layout.addWidget(self._correction_btn)
        layout.addWidget(btn_row)

        self._rotation_progress_card = ProgressCard()
        layout.addWidget(self._rotation_progress_card)

        return w

    # ── Step 4: TOC / Structure review ────────────────────────────────────────

    def _make_step4_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._structure_panel = StructurePanel()
        self._structure_panel.setMinimumHeight(460)
        layout.addWidget(self._structure_panel)

        btn_row = QWidget()
        btn_row.setStyleSheet(_TRANSPARENT)
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(16, 12, 16, 16)
        btn_layout.setSpacing(8)

        back4_btn = self._make_back_btn()
        back4_btn.clicked.connect(self._on_step4_back)
        btn_layout.addWidget(back4_btn)
        btn_layout.addStretch()

        next4_btn = QPushButton("次へ  ›")
        next4_btn.setFixedHeight(44)
        next4_btn.setFixedWidth(140)
        next4_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next4_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CORAL};color:white;
                border:none;border-radius:10px;
                font-size:14px;font-weight:700;
            }}
            QPushButton:hover {{ background:#ff5252; }}
        """)
        next4_btn.clicked.connect(self._on_step4_next)
        btn_layout.addWidget(next4_btn)
        layout.addWidget(btn_row)

        return w

    # ── Step 5: Output filename ────────────────────────────────────────────────

    def _make_step5_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        self._cover_row = QWidget()
        self._cover_row.setStyleSheet(_TRANSPARENT)
        cover_layout = QHBoxLayout(self._cover_row)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(16)

        self._cover_thumb = QLabel("🖼")
        self._cover_thumb.setFixedSize(_COVER_THUMB_SIZE, _COVER_THUMB_SIZE)
        self._cover_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_thumb.setStyleSheet(
            f"background:{BG_GRAY}; border-radius:10px; font-size:28px;"
        )
        cover_layout.addWidget(self._cover_thumb)

        title_col = QWidget()
        title_col.setStyleSheet(_TRANSPARENT)
        title_layout = QVBoxLayout(title_col)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)
        title_layout.addStretch()
        self._suggested_title_lbl = _lbl(
            "",
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;",
        )
        title_layout.addWidget(self._suggested_title_lbl)
        title_layout.addStretch()
        cover_layout.addWidget(title_col, stretch=1)

        self._cover_row.setVisible(False)
        layout.addWidget(self._cover_row)

        self._output_card = OutputCard()
        layout.addWidget(self._output_card)

        self._step5_error = QLabel()
        self._step5_error.setStyleSheet(
            "font-size:12px;color:#EF4444;background:transparent;border:none;"
        )
        self._step5_error.setVisible(False)
        layout.addWidget(self._step5_error)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        back5_btn = self._make_back_btn()
        back5_btn.clicked.connect(self._on_step5_back)
        btn_layout.addWidget(back5_btn)
        btn_layout.addStretch()

        next5_btn = QPushButton("次へ  ›")
        next5_btn.setFixedHeight(44)
        next5_btn.setFixedWidth(140)
        next5_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next5_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CORAL};color:white;
                border:none;border-radius:10px;
                font-size:14px;font-weight:700;
            }}
            QPushButton:hover {{ background:#ff5252; }}
        """)
        next5_btn.clicked.connect(self._on_step5_next)
        btn_layout.addWidget(next5_btn)
        layout.addLayout(btn_layout)

        return w

    # ── Step 6: PDF generation ─────────────────────────────────────────────────

    def _make_step6_content(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(_TRANSPARENT)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        back6_row = QHBoxLayout()
        back6_btn = self._make_back_btn()
        back6_btn.clicked.connect(self._on_step6_back)
        back6_row.addWidget(back6_btn)
        back6_row.addStretch()
        layout.addLayout(back6_row)

        layout.addWidget(
            _lbl(
                "保存先フォルダ",
                f"font-size:13px; font-weight:600; color:{TEXT_PRI};"
                " background:transparent; border:none;",
            )
        )
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("/path/to/output")
        self._output_dir_edit.setFixedHeight(40)
        self._output_dir_edit.setStyleSheet(f"""
            QLineEdit {{
                background:{BG_GRAY}; border:1px solid {BORDER};
                border-radius:8px; padding:0 12px;
                font-size:13px; color:{TEXT_PRI};
            }}
            QLineEdit:focus {{ border-color:#6366F1; }}
        """)
        browse_btn = QPushButton("📁  参照")
        browse_btn.setFixedHeight(40)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("""
            QPushButton {
                background: #F0F5FF; color: #6366F1;
                border: none; border-radius: 8px;
                padding: 0 14px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #E0E7FF; }
        """)
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self._output_dir_edit, stretch=1)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        self._step6_error = QLabel()
        self._step6_error.setStyleSheet(
            "font-size:12px;color:#EF4444;background:transparent;border:none;"
        )
        self._step6_error.setVisible(False)
        layout.addWidget(self._step6_error)

        self._pdf_btn = QPushButton("▶  PDFを生成する")
        self._pdf_btn.setFixedHeight(56)
        self._pdf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pdf_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CORAL};color:white;
                border:none;border-radius:14px;
                font-size:16px;font-weight:700;
            }}
            QPushButton:hover {{ background:#ff5252; }}
            QPushButton:pressed {{ background:#e53e3e; }}
            QPushButton:disabled {{ background:{BORDER_LIGHT};color:{TEXT_MUTED}; }}
        """)
        self._pdf_btn.clicked.connect(self._on_pdf_clicked)
        layout.addWidget(self._pdf_btn)

        return w

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if path:
            self._output_dir_edit.setText(path)

    # ── Cover thumbnail (Step 5) ───────────────────────────────────────────────

    def _load_cover_thumbnail(self) -> None:
        from .thumbnail_worker import ThumbnailWorker  # noqa: PLC0415

        worker = ThumbnailWorker(self._cover_image_path)
        worker.signals.ready.connect(self._on_cover_thumb_ready)
        QThreadPool.globalInstance().start(worker)

    def _on_cover_thumb_ready(self, px: QPixmap) -> None:
        s = _COVER_THUMB_SIZE
        scaled = px.scaled(
            s,
            s,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > s or scaled.height() > s:
            x = (scaled.width() - s) // 2
            y = (scaled.height() - s) // 2
            scaled = scaled.copy(x, y, s, s)
        self._cover_thumb.setPixmap(scaled)
        self._cover_thumb.setText("")
        self._cover_thumb.setStyleSheet("background:transparent; border-radius:10px;")
        self._cover_thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cover_thumb.mousePressEvent = lambda _: self._open_cover_preview()  # type: ignore[method-assign]

    def _open_cover_preview(self) -> None:
        from .page_preview_dialog import PagePreviewDialog  # noqa: PLC0415

        PagePreviewDialog(self._cover_image_path, 0, self._cover_ocr_lines, self).exec()

    # ── Options sub-sections ───────────────────────────────────────────────────

    def _make_contrast_section(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(_TRANSPARENT)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self._cb_contrast = QCheckBox("画像のコントラストを調整")
        self._cb_contrast.setChecked(True)
        self._cb_contrast.setStyleSheet(_CB_STYLE)
        v.addWidget(self._cb_contrast)

        self._contrast_params = QWidget()
        self._contrast_params.setStyleSheet(_TRANSPARENT)
        row = QHBoxLayout(self._contrast_params)
        row.setContentsMargins(28, 0, 0, 0)
        row.setSpacing(8)

        row.addWidget(
            _lbl(
                "明るさ",
                f"font-size:12px;color:{TEXT_SEC};background:transparent;border:none;",
            )
        )
        self._spin_brightness = QSpinBox()
        self._spin_brightness.setRange(-100, 100)
        self._spin_brightness.setValue(20)
        self._spin_brightness.setFixedWidth(64)
        self._spin_brightness.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(self._spin_brightness)

        row.addSpacing(8)
        row.addWidget(
            _lbl(
                "ガンマ",
                f"font-size:12px;color:{TEXT_SEC};background:transparent;border:none;",
            )
        )
        self._spin_gamma = QDoubleSpinBox()
        self._spin_gamma.setRange(0.1, 5.0)
        self._spin_gamma.setSingleStep(0.1)
        self._spin_gamma.setDecimals(1)
        self._spin_gamma.setValue(1.6)
        self._spin_gamma.setFixedWidth(64)
        self._spin_gamma.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(self._spin_gamma)
        row.addStretch()

        v.addWidget(self._contrast_params)
        self._cb_contrast.toggled.connect(self._contrast_params.setEnabled)
        return container

    def _make_resize_section(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(_TRANSPARENT)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self._cb_resize_w, self._spin_resize_w = self._make_resize_row(
            "横幅を揃える", 1080, v
        )
        self._cb_resize_w.setChecked(True)
        self._cb_resize_h, self._spin_resize_h = self._make_resize_row(
            "縦幅を揃える", 1920, v
        )

        quality_row = QWidget()
        quality_row.setStyleSheet(_TRANSPARENT)
        row = QHBoxLayout(quality_row)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(8)
        row.addWidget(
            _lbl(
                "JPEG品質",
                f"font-size:12px;color:{TEXT_SEC};background:transparent;border:none;",
            )
        )
        self._spin_jpeg_quality = QSpinBox()
        self._spin_jpeg_quality.setRange(1, 95)
        self._spin_jpeg_quality.setValue(75)
        self._spin_jpeg_quality.setFixedWidth(64)
        self._spin_jpeg_quality.setStyleSheet(_SPINBOX_STYLE)
        self._spin_jpeg_quality.setToolTip(
            "出力PDFに埋め込む画像のJPEG圧縮品質（1〜95、高いほど高品質・大容量）"
        )
        row.addWidget(self._spin_jpeg_quality)
        row.addWidget(
            _lbl(
                "/ 95",
                f"font-size:12px;color:{TEXT_SEC};background:transparent;border:none;",
            )
        )
        row.addStretch()
        v.addWidget(quality_row)
        return container

    def _make_resize_row(
        self, label: str, default_px: int, layout: QVBoxLayout
    ) -> tuple[QCheckBox, QSpinBox]:
        row_w = QWidget()
        row_w.setStyleSheet(_TRANSPARENT)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        cb = QCheckBox(label)
        cb.setStyleSheet(_CB_STYLE)
        row.addWidget(cb)

        spin = QSpinBox()
        spin.setRange(1, 9999)
        spin.setValue(default_px)
        spin.setFixedWidth(72)
        spin.setEnabled(False)
        spin.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(spin)

        row.addWidget(
            _lbl(
                "px",
                f"font-size:12px;color:{TEXT_SEC};background:transparent;border:none;",
            )
        )
        row.addStretch()

        cb.toggled.connect(spin.setEnabled)
        layout.addWidget(row_w)
        return cb, spin

    # ── File management ────────────────────────────────────────────────────────

    def _on_files_dropped(self, paths: list[str]) -> None:
        self._drop_zone.setVisible(False)
        self._load_label.setText("読み込み中...")
        self._load_label.setVisible(True)
        self._clear_row.setVisible(False)

        self._expander = _FileExpander(paths, set(self._files))
        self._expander.progress.connect(self._on_load_progress)
        self._expander.done.connect(self._on_load_done)
        self._expander.start()

    def _on_load_progress(self, current: int, total: int) -> None:
        self._load_label.setText(f"{current}/{total} 件を読み込み中...")

    def _on_load_done(self, paths: list[str]) -> None:
        self._expander = None
        self._load_label.setVisible(False)
        if paths:
            self._files.extend(paths)
        self._refresh_step1()

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "画像ファイルを選択",
            "",
            "画像ファイル (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.tif)",
        )
        if paths:
            self._on_files_dropped(paths)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if path:
            self._on_files_dropped([path])

    def _clear_files(self) -> None:
        self._files.clear()
        self._ocr_image_paths.clear()
        self._ocr_results.clear()
        self._angle_overrides.clear()
        self._cached_preview_samples = None
        self._load_label.setVisible(False)
        self._clear_row.setVisible(False)
        self._drop_zone.setVisible(True)
        self._preview_btn.setEnabled(False)
        self._correction_preview_btn.setEnabled(False)
        self._step1.set_active()
        self._step2.set_locked()
        self._step3.set_locked()
        self._step4.set_locked()
        self._step5.set_locked()
        self._step6.set_locked()
        self.files_changed.emit([])

    def _refresh_step1(self) -> None:
        has_files = bool(self._files)
        n = len(self._files)
        self._clear_row.setVisible(has_files)
        self._drop_zone.setVisible(not has_files)
        self._preview_btn.setEnabled(has_files)
        if has_files:
            self._step1.set_completed(f"{n} ファイル選択済み")
            self._step2.set_active()
            self.files_changed.emit(list(self._files))
            self.ocr_step_activated.emit()
        else:
            self._step1.set_active()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _make_back_btn(self) -> QPushButton:
        btn = QPushButton("‹  戻る")
        btn.setFixedHeight(44)
        btn.setFixedWidth(110)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_GRAY};color:{TEXT_SEC};
                border:1px solid {BORDER_LIGHT};border-radius:10px;
                font-size:14px;font-weight:600;
            }}
            QPushButton:hover {{ background:{BORDER};color:{TEXT_PRI}; }}
        """)
        return btn

    # ── Button handlers ────────────────────────────────────────────────────────

    def _on_preview_clicked(self) -> None:
        if not self._files:
            return
        import random  # noqa: PLC0415
        from .preview_worker import PreviewWorker  # noqa: PLC0415

        sample_paths = random.sample(self._files, min(10, len(self._files)))
        self._preview_btn.setEnabled(False)
        self._preview_btn.setText("処理中...")
        self._preview_worker = PreviewWorker(
            sample_paths, self.current_options, len(self._files)
        )
        self._preview_worker.finished.connect(
            lambda samples, mb: self._on_preview_done(samples, mb)
        )
        self._preview_worker.error.connect(self._on_preview_error)
        self._preview_worker.start()

    def _on_preview_done(self, samples: list, estimated_mb: float) -> None:
        from .preview_dialog import ImagePreviewDialog  # noqa: PLC0415

        self._preview_btn.setEnabled(True)
        self._preview_btn.setText("🔍  仕上がり確認")
        ImagePreviewDialog(samples, estimated_mb, len(self._files), parent=self).exec()

    def _on_preview_error(self, msg: str) -> None:
        self._preview_btn.setEnabled(True)
        self._preview_btn.setText("🔍  仕上がり確認")
        from PySide6.QtWidgets import QMessageBox  # noqa: PLC0415

        QMessageBox.warning(self, "プレビューエラー", msg)

    def _start_rotation_preview_worker(self) -> None:
        """Start background angle estimation. Called automatically after OCR."""
        from .rotation_preview_worker import RotationPreviewWorker  # noqa: PLC0415

        self._correction_preview_btn.setEnabled(False)
        self._correction_preview_btn.setText("角度を推定中...")
        self._rotation_preview_worker = RotationPreviewWorker(
            list(self._ocr_image_paths), dict(self._ocr_results)
        )
        self._rotation_preview_worker.progress.connect(
            lambda pct, msg: self._correction_preview_btn.setText(f"{msg}  {pct}%")
        )
        self._rotation_preview_worker.finished.connect(
            self._on_rotation_preview_worker_done
        )
        self._rotation_preview_worker.error.connect(self._on_correction_preview_error)
        self._rotation_preview_worker.start()

    def _on_correction_preview_clicked(self) -> None:
        if self._cached_preview_samples is not None:
            self._show_correction_preview_dialog(self._cached_preview_samples)
        elif self._ocr_image_paths:
            # Fallback: worker hasn't finished yet — shouldn't normally be reached
            # because the button is disabled while the worker runs.
            self._start_rotation_preview_worker()

    def _on_rotation_preview_worker_done(
        self, samples: list, _estimated_mb: float
    ) -> None:
        self._cached_preview_samples = samples
        self._correction_preview_btn.setEnabled(True)
        self._correction_preview_btn.setText("🔍  仕上がり確認")

    def _show_correction_preview_dialog(self, samples: list) -> None:
        from .preview_dialog import ImagePreviewDialog  # noqa: PLC0415

        dlg = ImagePreviewDialog(
            samples,
            0.0,
            len(self._ocr_image_paths),
            parent=self,
            show_size_info=False,
            header_text="推定した傾きが大きい順に並べています。誤りがあれば角度を修正して「この角度で補正する」をクリックしてください。",
            accept_label="この角度で補正する",
        )
        if dlg.exec():
            self._angle_overrides = dlg.get_angle_overrides()
            # Persist the confirmed angles and rendered after-images back into
            # the cache so re-opening the dialog shows what the user last confirmed.
            dlg.get_updated_samples(samples)

    def _on_correction_preview_error(self, msg: str) -> None:
        self._correction_preview_btn.setEnabled(True)
        self._correction_preview_btn.setText("🔍  仕上がり確認")
        from PySide6.QtWidgets import QMessageBox  # noqa: PLC0415

        QMessageBox.warning(self, "プレビューエラー", msg)

    def _on_ocr_clicked(self) -> None:
        self._ocr_btn.setEnabled(False)
        opts = RunOptions(
            output_dir="",
            output_name="output_ebook",
            sort_by_name=True,
            contrast_adjust=self._cb_contrast.isChecked(),
            brightness=self._spin_brightness.value(),
            gamma=self._spin_gamma.value(),
            resize_width=self._spin_resize_w.value()
            if self._cb_resize_w.isChecked()
            else None,
            resize_height=self._spin_resize_h.value()
            if self._cb_resize_h.isChecked()
            else None,
            jpeg_quality=self._spin_jpeg_quality.value(),
        )
        self.ocr_requested.emit(opts)

    def _on_step3_next(self) -> None:
        self._correction_btn.setEnabled(False)
        self.rotation_requested.emit(self._cb_deskew.isChecked())

    def _on_step3_back(self) -> None:
        self._step3.set_locked()
        self._step2.set_active()

    def _on_step4_next(self) -> None:
        self._step4.set_completed("目次確認済み")
        self._step5.set_active()

    def _on_step4_back(self) -> None:
        self._step4.set_locked()
        self._step3.set_active()

    def _on_step5_next(self) -> None:
        if not self._output_card.output_name:
            self._step5_error.setText("⚠  出力ファイル名を入力してください")
            self._step5_error.setVisible(True)
            return
        self._step5_error.setVisible(False)
        self._step5.set_completed(self._output_card.output_name)
        self._step6.set_active()

    def _on_step5_back(self) -> None:
        self._step5.set_locked()
        self._step4.set_active()

    def _on_step6_back(self) -> None:
        self._step6.set_locked()
        self._step5.set_active()

    def _on_pdf_clicked(self) -> None:
        if not self._output_dir_edit.text().strip():
            self._step6_error.setText("⚠  保存先フォルダを指定してください")
            self._step6_error.setVisible(True)
            return
        self._step6_error.setVisible(False)
        self._pdf_btn.setEnabled(False)
        self.pdf_requested.emit()


# ── _FileExpander ─────────────────────────────────────────────────────────────

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"})


class _FileExpander(QThread):
    """Expand raw dropped paths to individual image file paths in a background thread.

    Signals
    -------
    progress(current, total): emitted for each file processed.
    done(list[str]):          emitted once with all new (non-duplicate) paths.
    """

    progress = Signal(int, int)  # (current, total)
    done = Signal(list)  # list[str]

    def __init__(self, paths: list[str], existing: set[str]) -> None:
        super().__init__()
        self._paths = paths
        self._existing = existing

    def run(self) -> None:
        # Phase 1: collect all candidate image paths (to know total upfront)
        candidates: list[str] = []
        for p in self._paths:
            path = Path(p)
            if path.is_dir():
                candidates.extend(
                    str(f)
                    for f in sorted(path.iterdir())
                    if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
                )
            elif path.suffix.lower() in _IMAGE_EXTS:
                candidates.append(p)

        # Phase 2: filter duplicates, emit per-file progress
        total = len(candidates)
        result: list[str] = []
        for i, p in enumerate(candidates):
            if p not in self._existing:
                result.append(p)
            self.progress.emit(i + 1, total)

        self.done.emit(result)
