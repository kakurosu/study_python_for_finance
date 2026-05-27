# Study.Py — Finance Edition

対話型 Python 学習アプリ。金融計算（期待値・分散・トラッキングエラー・シャープレシオ・ポートフォリオ最適化・モンテカルロ）から時系列・ML/DL・Streamlit・自動操作まで、26 章でステップアップできる。副次目標として証券アナリスト（CMA）試験での数理・統計・ポートフォリオ理論の定着補助。

UI は **HTML / CSS / JavaScript ベース**で、ローカルに FastAPI サーバを立て、起動時にお使いのブラウザを自動で開く構成です（旧 PyQt6 / QWebEngineView 構成は廃止）。ネイティブ UI ツールキットへの依存がないため、攻撃面が小さく、テーマ切替や独自スタイル拡張も Web 標準のままで完結します。

## 動作要件

- Windows / macOS / Linux
- Python 3.11+
- メモリ 1GB（PyTorch 章は 2GB+）
- [uv](https://docs.astral.sh/uv/) **0.11.6 以上** (パッケージマネージャ)

## セットアップ

`uv` 0.11.6 以上がインストール済みであることを前提とします（未インストールなら `pip install uv==0.11.6` / `winget install astral-sh.uv` / `brew install uv` / `curl -LsSf https://astral.sh/uv/install.sh | sh`）。

```bash
# バージョン確認
uv --version    # → uv 0.11.6 (...) 以上
```

```bash
cd study_python_finance

# 仮想環境 (.venv) を作成 + 全依存を同期
uv sync

# オプション機能を含めて一括導入
uv sync --extra dev --extra streamlit --extra automation
# 深層学習章を使うとき
uv sync --extra deep
# Playwright 章を使うとき (Chromium をローカルにインストール)
uv run playwright install chromium
```

## 起動

```bash
uv run python -m app.main
# もしくは
uv run study-python
```

実行すると以下のような起動バナーが出て、規定のブラウザが自動的に
`http://127.0.0.1:8765/` を開きます。

```
  ┌────────────────────────────────────────────────────────────┐
  │  Study.Py — Finance Edition                                │
  │  http://127.0.0.1:8765/                                    │
  └────────────────────────────────────────────────────────────┘

  Ctrl+C で停止します。ブラウザでこの URL を開いてください。
```

### CLI フラグ

```bash
uv run study-python --port 0          # 空きポートを自動取得
uv run study-python --no-browser      # ブラウザを開かずサーバのみ
```

#### ⚠️ ネットワーク公開 (`--host 0.0.0.0`)

本アプリは **認証なし** で動作し、`/api/run-code` 経由で任意の Python を
Jupyter カーネル上で実行できます。loopback (`127.0.0.1`) で動かしている
限り、他端末からは到達できないため安全です。

`--host 0.0.0.0` 等で **非 loopback アドレスにバインドする場合は明示的に
`--insecure-lan` フラグも併用する必要があります**:

```bash
uv run study-python --host 0.0.0.0 --insecure-lan
```

`--insecure-lan` 無しで非 loopback を指定するとアプリは起動を拒否します。
LAN 越しに使う場合、同ネットワーク上の任意のユーザがこの端末で
コード実行できる状態になることを十分理解した上で使用してください。
公開された環境 (社外ネットワーク、ホテル / 公共 Wi-Fi 等) では絶対に
使用しないでください。

## 開発者向け

```bash
# テスト
uv run pytest

# Lint / フォーマット
uv run ruff check .
uv run ruff format .
uv run mypy app/

# 依存追加
uv add some-package          # 通常依存
uv add --optional dev pytest # オプション依存に追加
```

## ディレクトリ

```
app/
  main.py             # CLI エントリポイント (FastAPI 起動 + ブラウザ自動オープン)
  server.py           # FastAPI アプリ・REST + Server-Sent Events
  web/                # フロントエンド (HTML / CSS / JS)
    index.html
    styles.css          ベース (ダーク / ライト 両対応)
    modern.css          グラスモーフィズム / 動的グラデーション
    app.js              ビュー切替・章ランナー・テストランナー
    vendor/katex/       数式描画 (ローカル同梱)
  resources/stickman/ # マスコット (PNG/SVG)
  resources/fonts/    # Inter / JetBrains Mono
  content/, db/, grading/, kernel/   # ドメインロジック (Qt 非依存)
content/chapters/     # 章定義 YAML（学生は編集しない）
content/tests/        # 実力テスト問題集
data/                 # 各章のサンプル CSV / HTML
tests/                # pytest（コアロジック）
scripts/              # 章 YAML 一括生成スクリプト
```

## 進捗のエクスポート

設定画面の **「進捗を JSON でダウンロード」** ボタンから、章の進捗 / 演習の提出履歴 / 実力テストの結果を 1 ファイル（`progress-YYYYMMDD-HHMMSS.json`）にまとめて保存できます。講師にまとめて提出したり、別の PC に進捗を移すときに使えます。

## ライセンス

MIT
