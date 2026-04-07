#!/bin/bash
set -e

args=(
  --windowed
  --noconfirm
  --name pdf-ebook-maker
  --paths src
  --add-data "src/ocr/model:ocr/model"
  --add-data "src/ocr/config:ocr/config"
  --add-data "images/pdfbook.ico:images"
  --icon "images/pdfbook.ico"
)

# MacOSの場合は--onefileじゃなく--onedir（デフォルト値）でビルドして.appファイルにさせる
[[ "$(uname -s)" != "Darwin" ]] && args+=(--onefile)

uv run --with pyinstaller pyinstaller "${args[@]}" src/main.py
