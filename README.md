# PDF eBook Maker

スキャンした文書の画像をもとに、電子書籍として扱える（テキストが検索やコピー可能で、目次がついた）PDFファイルを生成するツールです。


![](images/toc-creation.png)

処理はすべてアプリを動作させている端末上で行われ、サーバー等には送信されません。

OCR処理はCPUのみで利用可能な軽量なアルゴリズムを使用しています。


## 使用方法

### ビルド済みファイルを使う場合

[Releases](https://github.com/nigimitama/pdf-ebook-maker/releases)ページに行き、お使いのOSに対応する実行ファイルをダウンロードしてください。


### 自分でビルドする場合

このリポジトリをクローンし、

- Windowsの場合は `build.bat`
- MacOS / Linuxの場合は `build.sh`

を実行してください



## ライセンス

本アプリ自体はMITライセンスです。

なお、本アプリは以下のサードパーティ製ソフトウェアを使用しています。

### NDLOCR-Lite (CC BY 4.0)

OCR処理に、国立国会図書館が提供する [NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite) を利用しています。NDLOCR-Lite は Creative Commons Attribution 4.0 (CC BY 4.0) のもとで提供されています（詳細は [NOTICE](./NOTICE) をご覧ください）。

本アプリにおける改変内容：
- アプリケーションへの統合
- 前処理および推論処理の調整

### Qt / PySide6 (LGPL v3)

GUIフレームワークに [Qt](https://www.qt.io/) および [PySide6](https://doc.qt.io/qtforpython-6/) を使用しています。これらは GNU Lesser General Public License v3 (LGPL v3) のもとで提供されています。

本アプリのソースコードはすべて公開されており、ビルドスクリプト（`build.sh` / `build.bat`）を使って任意のバージョンの Qt / PySide6 と組み合わせてビルドすることができます。これにより、LGPL v3 が求める「ライブラリの差し替え可能性」を担保しています。

- LGPL v3 ライセンス全文: https://www.gnu.org/licenses/lgpl-3.0.html
