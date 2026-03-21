@echo off
uv run --with pyinstaller pyinstaller ^
  --windowed ^
  --onefile ^
  --noconfirm ^
  --name pdf-ebook-maker ^
  --paths src ^
  --add-data "src/ocr/model;ocr/model" ^
  --add-data "src/ocr/config;ocr/config" ^
  --add-data "images/pdfbook.ico;images" ^
  --icon "images/pdfbook.ico" ^
  src/main.py
