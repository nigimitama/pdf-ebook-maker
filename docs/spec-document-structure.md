# 文書構造エディター 仕様書

## 概要

OCR 処理完了後にPDF出力前のステップとして「文書構造エディター」を追加する。
各画像ファイルのカテゴリ（表紙・目次・本文）を確認・編集し、目次エントリを人間が修正してからPDFを生成できるようにする。

---

## ワークフロー変更

### 現状
```
ファイル選択 → [OCR + PDF生成] → 完了
```

### 変更後
```
ファイル選択 → [OCRフェーズ] → 文書構造エディター → [PDF生成フェーズ] → 完了
```

---

## 機能要件

### 1. ページカテゴリ

各画像ファイルに以下のカテゴリを付与できる。

| カテゴリ | 表示名 | 説明 |
|----------|--------|------|
| `cover` | 表紙 | PDF のタイトルページ。**常に1枚目（index 0）に固定**。ユーザーが他のページに変更不可 |
| `toc` | 目次 | 目次ページ。OCR結果から自動検出。人間が修正可能 |
| `body` | 本文 | 本文ページ |
| `uncategorized` | 未分類 | 自動分類できなかったページ |

**自動カテゴリ割り当てルール（OCR完了直後に実行）:**
- index 0 → `cover`（固定・変更不可）
- OCRテキストに「目次」「もくじ」「CONTENTS」「contents」が含まれるページ → `toc`
- それ以外 → `body`

### 2. PDF ファイル名の自動推定

- 表紙ページのOCRテキストから最初の行（または最も文字数が多い行）を候補とする
- 候補をファイル名に使えない文字（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）を除去してデフォルト値にセット
- OCRテキストが空の場合は現状通り「output」をデフォルト値とする

### 3. 目次エントリの自動解析

OCRテキストから目次エントリを抽出する。対象は `toc` カテゴリのページ。

**抽出パターン（正規表現ベース）:**
- `第X章\s+(.+?)[\s・…]+(\d+)` → level=1
- `第X節\s+(.+?)[\s・…]+(\d+)` → level=2
- 行末が数字で終わる行（`^(.+?)\s*[\s・…]{2,}\s*(\d+)$`）→ level=1

各エントリは `(タイトル, ページ番号)` のペア。ページ番号は文書内の0-based indexに変換して保持する（表示は1-based）。

### 4. 目次エントリの手動編集

抽出された目次エントリを人間が以下の操作で修正できる：
- タイトルの変更（インライン編集）
- 対象ページ番号の変更（スピンボックス）
- 見出しレベルの変更（1〜3）
- エントリの追加・削除
- 上下の並び替え

### 5. PDF 出力への目次埋め込み

`reportlab` の PDF アウトライン（ブックマーク）機能を利用して目次を埋め込む。

```python
canvas.bookmarkPage(key, fit="FitH", top=page_height)
canvas.addOutlineEntry(title, key, level=level - 1, closed=False)
```

---

## アーキテクチャ設計

### 新規モジュール

```
src/
  document_structure/
    __init__.py           # PageEntry, TocEntry, DocumentStructure を公開
    models.py             # データクラス定義
    detector.py           # OCRテキストからの自動カテゴリ・目次検出
  ui/
    structure_panel.py    # 文書構造エディターパネル（新規）
    pdf_worker.py         # PDF生成専用ワーカー（OcrWorkerから分離）
```

### データモデル

```python
# src/document_structure/models.py

PageCategory = Literal["cover", "toc", "body", "uncategorized"]

@dataclass
class PageEntry:
    path: str           # 絶対パス
    index: int          # 文書内の0-based順序
    category: PageCategory

@dataclass
class TocEntry:
    title: str
    page_index: int     # 対象画像の0-based index
    level: int = 1      # 見出しレベル（1=章, 2=節, 3=項）

@dataclass
class DocumentStructure:
    pages: list[PageEntry]
    toc_entries: list[TocEntry]
    suggested_title: str = ""  # 表紙から推定したPDFタイトル
```

### モジュール間シグナルフロー

```
OcrWorker
  .ocr_done(dict[str, list])   → MainWindow._on_ocr_done()
                                   → detector.build_structure() で DocumentStructure 生成
                                   → StructurePanel を表示・データ渡し
                                   → OutputCard の output_name をデフォルト更新

StructurePanel
  .export_requested(DocumentStructure)  → MainWindow._on_export_requested()
                                           → PdfWorker 起動

PdfWorker
  .progress(int, str, str)     → SettingsPanel.set_progress()
  .finished()                  → MainWindow._on_pdf_finished()
  .error(str)                  → MainWindow._on_worker_error()
```

### OcrWorker の変更

- OCR 完了時点で `ocr_done(dict[str, list])` シグナルを emit
- PDF 生成処理を除去（PdfWorker に移管）
- `finished` シグナルは OCR 完了時に emit（PDFを待たない）

### PdfWorker（新規）

```python
class PdfWorker(QThread):
    progress = Signal(int, str, str)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        structure: DocumentStructure,
        opts: RunOptions,
    ) -> None: ...
```

### build_pdf の変更

```python
def build_pdf(
    ...
    toc_entries: list[TocEntry] | None = None,   # 追加
) -> None:
```

ページを描画するループの中で、そのページに対応する `TocEntry` があれば ReportLab ブックマークを埋め込む。

---

## UIレイアウト

### 現状のレイアウト

```
┌────────────────────────┬──────────────────────┐
│  FilePanel (660px)     │  SettingsPanel       │
│  ファイル選択           │  設定・実行           │
└────────────────────────┴──────────────────────┘
```

### 変更後（OCR完了後にStructurePanelを中央に挿入）

```
┌───────────────┬─────────────────────────┬──────────────────────┐
│ FilePanel     │  StructurePanel         │  SettingsPanel       │
│ （固定幅）    │  文書構造エディター      │  設定・実行           │
│               │  （stretch=1）          │                      │
└───────────────┴─────────────────────────┴──────────────────────┘
```

OCR完了前は StructurePanel は非表示。OCR完了後にスライドイン表示される。

### StructurePanel 内部レイアウト

```
┌─────────────────────────────────────────────────┐
│  📄 文書構造                                     │
├──────────────────────────┬──────────────────────┤
│  ページ一覧              │  目次エントリ         │
│                          │                      │
│  [🖼] 001.png            │  [+] エントリ追加     │
│      カテゴリ: [表紙 ▼]  │                      │
│                          │  第1章 はじめに       │
│  [🖼] 002.png            │   ページ: [3 ▲▼]    │
│      カテゴリ: [目次 ▼]  │   レベル: [1 ▲▼]    │
│                          │   [✏タイトル編集]    │
│  [🖼] 003.png            │   [✕]                │
│      カテゴリ: [本文 ▼]  │  ─────────────       │
│  ...                     │  第2章 ...            │
│                          │                      │
├──────────────────────────┴──────────────────────┤
│              [▶  PDF を出力する]                 │
└─────────────────────────────────────────────────┘
```

---

## 非機能要件・制約

- `src/ocr/ndl_parser.py`, `src/ocr/reading_order/` はベンダードコード。改変しない
- ファイルは200行以内を目安
- `utils`/`helpers` などの汎用命名は使わない
- OCR未実行（`run_ocr=False`）の場合は StructurePanel をスキップしてすぐ PDF 生成する（現状フローを維持）
- lintは `ruff check`、型チェックは `pyright` でパスすること

---

## 実装順序

1. `src/document_structure/models.py` — データクラス定義
2. `src/document_structure/detector.py` — 自動検出ロジック
3. `src/document_structure/__init__.py` — 公開API
4. `src/ui/ocr_worker.py` — `ocr_done` シグナル追加、PDF生成処理を除去
5. `src/ui/pdf_worker.py` — PDF生成専用ワーカー（新規）
6. `src/pdf/builder.py` — `toc_entries` 引数追加、ブックマーク埋め込み
7. `src/ui/structure_panel.py` — 文書構造エディターUI（新規）
8. `src/ui/main_window.py` — 2フェーズフロー対応
