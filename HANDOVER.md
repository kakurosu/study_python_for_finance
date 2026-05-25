# 引継ぎ書 — Study.Py Finance Edition

> このドキュメントは、次のセッションが本プロジェクトの状態を即座に把握するための引継ぎ書です。
> 最終更新: 2026-04-26

---

## 1. プロジェクト概要

**Study.Py — Finance Edition**: 金融計算（CMA 試験対応）を題材にした、対話型 Python 学習デスクトップアプリ。Progate のような穴埋め演習形式で 26 章構成、サンプル→演習→結果のページ式ウィザード。

- **目的**: 初学者〜中級者が「簡単なコードが書ける／コードを読める」レベルに到達。副次目標は証券アナリスト試験での数理・統計・ポートフォリオ理論の定着補助。
- **対象**: 個人学習用デスクトップアプリ（オフライン完結、シングルユーザー）。
- **リポジトリ**: https://github.com/kakurosu/learning_python (main ブランチ)

---

## 2. 重要: フォルダ構造（2 つあります）

OneDrive 同期ロックにより、フォルダリネームが完了せず **2 つのフォルダが並存** しています。両方を変更時は **必ず同期** してください。

| パス | ステータス | 説明 |
|------|----------|------|
| `C:/Users/skokh/OneDrive/デスクトップ/開発用フォルダ/study_python_finance/` | **canonical** | こちらを正とする。`pyproject.toml` の `name = study-python-finance` |
| `C:/Users/skokh/OneDrive/デスクトップ/開発用フォルダ/progate_python_finance/` | **legacy** | 旧称のフォルダ。OneDrive ロックで削除不可。中身は study_ と同期済み |

### 同期コマンド
```bash
cd "C:/Users/skokh/OneDrive/デスクトップ/開発用フォルダ"
cp -r study_python_finance/app/* progate_python_finance/app/
cp -r study_python_finance/content/* progate_python_finance/content/
cp study_python_finance/pyproject.toml study_python_finance/README.md \
   study_python_finance/uv.lock study_python_finance/.gitignore \
   progate_python_finance/
```

git 管理しているのは **study_python_finance/** のみ（`.git` はこちら側）。

---

## 3. 技術スタック

| レイヤ | 採用 |
|--------|------|
| 言語 | Python 3.11+（3.13 で動作確認済み） |
| パッケージマネージャ | **uv 0.11.6+** (`pyproject.toml` で required-version 指定済み) |
| UI | HTML/CSS/JS（`app/web/`）+ FastAPI ローカルサーバ（`app/server.py`）。起動時に既定のブラウザを自動で開く構成。PyQt6/QWebEngineView の旧シェルは廃止 |
| カーネル | jupyter_client + ipykernel（バックグラウンドで IPython kernel を起動して実行） |
| データ層 | SQLAlchemy 2.0 + SQLite (`progress.db`) |
| スキーマ | Pydantic 2.6 |
| LLM (オプション) | anthropic SDK（`.env` の `ANTHROPIC_API_KEY` が設定されているときのみ「Ask AI」ボタン表示） |
| 数値計算 | numpy / pandas / matplotlib / scipy / scikit-learn / statsmodels |
| 深層学習 | PyTorch（章 22 のみ）|

### 起動コマンド
```bash
cd study_python_finance
uv sync                         # 基本依存をインストール
uv run python -m app.main       # アプリ起動
uv run pytest                   # テスト
```

オプション機能:
```bash
uv sync --extra dev --extra streamlit --extra automation
uv sync --extra deep            # PyTorch
uv run playwright install chromium  # 章 26 用
```

---

## 4. ディレクトリ構造

```
study_python_finance/
├── app/
│   ├── main.py                 # CLI エントリポイント（FastAPI 起動 + ブラウザ自動オープン）
│   ├── server.py               # FastAPI アプリ（REST + SSE）
│   ├── web/                    # フロントエンド (HTML / CSS / JS)
│   │   ├── index.html          # SPA 全 7 ビュー (Dashboard / Chapters / Practice / Tests / History / Settings / References)
│   │   ├── styles.css          # ベース (ダーク + ライト) — Inter / JetBrains Mono / KaTeX
│   │   ├── modern.css          # グラスモーフィズム / 動的グラデーション / フォーカスリング 強化レイヤ
│   │   ├── app.js              # SPA コントローラ — `bridge` shim が fetch で REST を叩く
│   │   └── vendor/katex/       # 数式描画ライブラリ
│   ├── kernel/manager.py       # Jupyter kernel ライフサイクル
│   ├── content/
│   │   ├── schemas.py          # Pydantic: Chapter / SamplePage / ExercisePage / TestCase
│   │   ├── test_schemas.py     # TestSet スキーマ
│   │   └── loader.py           # YAML → モデル
│   ├── grading/judge.py        # 採点（form 正規表現 + 動作チェック）
│   ├── db/
│   │   ├── models.py           # SQLAlchemy モデル
│   │   └── repo.py             # Repository
│   ├── llm/claude_client.py    # Claude API クライアント
│   └── resources/
│       ├── fonts/              # Inter / JetBrains Mono
│       └── stickman/           # 4 種の SVG+PNG (normal / happy / sad / explain)
├── content/
│   ├── chapters/01_*.yaml 〜 26_*.yaml   # 26 章コンテンツ
│   └── tests/phase_{a,b,c}_test.yaml     # 3 つの実力テスト
├── data/                       # サンプル CSV / HTML
├── tests/                      # pytest（25 件）
├── scripts/generate_chapters.py # 章 YAML 一括生成スクリプト（Claude API 使用）
├── pyproject.toml              # uv + 依存定義
├── uv.lock                     # 157 パッケージの解決結果（コミット済み）
├── .env.example                # ANTHROPIC_API_KEY サンプル
└── README.md
```

---

## 5. カリキュラム（26 章 / 6 フェーズ）

| Phase | 章 | テーマ | 演習数 |
|-------|----|------|------|
| **A** Python 文法基礎 | 01-10 | print, 変数と型, 演算, コメント, 組み込み関数, if, ループ, リスト, 辞書, 関数定義 | 23 |
| **B** 数値ライブラリ | 11-14 | NumPy, pandas 入門, matplotlib, pandas 応用 | 11 |
| **C** 金融計算 (CMA) | 15-19 | 期待値/分散, 共分散/TE, シャープレシオ/IR, ポートフォリオ最適化, モンテカルロ | 13 |
| **D** ML / DL | 20-22 | statsmodels ARIMA, scikit-learn, PyTorch 1層 MLP | 10 |
| **E** 外部連携 | 23-24 | requests + BeautifulSoup（ローカル HTML のみ）, Anthropic SDK 擬似 LLM | 7 |
| **F** アプリ開発 | 25-26 | Streamlit, PyAutoGUI / Playwright | 7 |

**実力テスト**: Phase A / B / C それぞれ 10 問、30 分制限、合格基準 60%。

すべての演習 (**71/71**) と全テスト問題 (**30/30**) は canonical answer で grading パス確認済み。

---

## 6. 設計上の重要な決定

### UI / UX
- **角丸ゼロ**: すべての要素で `border-radius: 0`。Persona 5 / Lumines 的なシャープデザイン。
- **白 + 鮮やかな赤**: `ACCENT = "#DC2626"` (red-600) を唯一の彩度色として使用。
- **Title Case 英字**: `UPPERCASE + letter-spacing` の装飾を撤廃。Back ボタンのスペックに統一（`font-size:11px; font-weight:700; letter-spacing:0`）。
- **棒人間は固定ストリップ**: 以前のフローティングオーバーレイは UI 要素と重なって不評。フッターの上に 60px の独立した行として配置（`app/ui/stickman.py` の `StickmanStrip`）。

### 採点ロジック
- **2 段階チェック** (`app/grading/judge.py`):
  1. **形式チェック**: `accept_patterns` の正規表現で書き方を確認
  2. **動作チェック**: 完成コードを kernel で実行し `test_cases`（`namespace_check` / `stdout_regex`）で評価
- 形式 NG でも動作合格なら正解扱い（学生が代替解を見つけた場合に救済）

### テストモード
- **Skip ボタン**: 分からない問題は失敗扱いで次へ
- **Solution ボタンは非表示**: ワンショット計測なのでカンニング防止
- フッター状態遷移:
  - Pre-submit: `Skip` + `Submit`
  - Post-submit: `Next Question`（最終問題は `Finish Test`）

### コードブロック
- **VSCode Light Modern** 風の配色（`app/ui/code_view.py`）:
  - キーワード: `#0000FF` (blue)
  - 制御フロー: `#AF00DB` (purple)
  - 文字列: `#A31515`、数値: `#098658`、関数: `#795E26`、クラス/型: `#267F99`
  - コメント: `#008000` italic
- 行番号ガター + ファイル名ヘッダーバー + RUN ボタン

### 結果ページ
- 64px の `Correct` / `Incorrect` 大字リビール（緑/赤）
- 正解時は **Checks セクションを非表示**（採点 jargon は学習者に不要）
- 不正解時のみ "What failed" を `× <detail>` の形で表示
- Output セクションは空のときは非表示
- ChapterView のフッターも結果オーバーレイ表示中は隠す（二重 CTA 回避）

### 「Ask AI」機能
- `.env` の `ANTHROPIC_API_KEY` が設定されている場合のみ結果ページに表示
- 200 字以内のヒント返答、答えは書かない指示でプロンプト固定
- 同一コードへの再呼び出しはキャッシュ

---

## 7. 解説の充実度

### 拡充済み（`基本形 / 使いどころ / 注意点` の 3 段構成）
- 章 01（def / lambda）
- 章 02 〜 10 の主要演習（一部）
- 章 11（NumPy ブロードキャスト）
- 章 15（期待値・分散）
- 章 17（シャープレシオ）

### 未拡充（テーマ的解説のみ）
- 章 12 (pandas), 13 (matplotlib), 14 (pandas 応用)
- 章 16 (共分散), 18 (ポートフォリオ最適化), 19 (モンテカルロ)
- 章 20-26 全般

→ 必要に応じて、ユーザー要望に応じて拡充してください。テンプレートとしては章 11 のブロードキャスト演習の prompt が良い見本。

---

## 8. 図出力 (matplotlib) の実装

カーネルは `display_data` の `image/png` を捕捉済み (`app/kernel/manager.py`)。サンプルで `plt.show()` を呼ぶと `OutputPane._add_image` が QPixmap でレンダリングする。

図出力サンプル付きの章:
- **章 13**: 折れ線・棒・散布図・ヒストグラム
- **章 19**: GBM 50 本のサンプルパス
- **章 21**: 線形回帰の訓練/テスト散布図 + 回帰直線
- **章 22**: 100 反復の Loss Curve（勾配降下可視化）

`OutputPane.render()` は画像があるときに自動で max-height キャップを外す（`setMaximumHeight(16777215)`）。

---

## 9. 既知の課題 / 未着手項目

### 既知の課題
- **OneDrive ロック問題**: `progate_python_finance/` フォルダが削除できない。両フォルダを手動で同期する必要あり。
- **章 11-26 の解説**: まだ薄い章が多い。テンプレ通り「基本形 / 使いどころ / 注意点」を追加する余地あり。

### Phase 5 (未着手): 配布
- PyInstaller での Windows 用 exe 化（`progate_python.exe` 単一ファイル）
- 章コンテンツと data/ を bundle に同梱
- GitHub Releases へのアップロード

### 将来拡張アイデア
- マルチユーザー対応（現在は `default` ユーザー固定）
- 章クリア状況のグラフ表示
- Claude による章 YAML 一括自動生成（`scripts/generate_chapters.py` のひな型あり、未実装）
- アプリ内エディタへの自動補完
- ステージング tests（Phase D/E/F 用）

---

## 10. テスト結果（最終）

```
pytest:                           25 / 25 PASS
章演習 (全章 canonical answer):   71 / 71 PASS
実力テスト (Phase A/B/C):         30 / 30 PASS
E2E 起動 + 全画面遷移:            OK
uv 0.11.6 + uv sync + uv run:     OK
```

---

## 11. Git / GitHub 状態

- **リモート**: `https://github.com/kakurosu/learning_python.git`
- **ブランチ**: `main`
- **最終コミット** (2026-04-26 時点):
  ```
  14638a8  Pin uv to >=0.11.6 and regenerate lockfile
  6982dd1  Switch from venv to uv as the package / venv manager
  29d7ac6  Merge remote-tracking branch 'origin/main' (resolve .gitignore conflict)
  9888f72  Initial commit — Study.Py Finance Edition
  ef8986b  Initial commit  (GitHub の元コミット — 標準 .gitignore のみ)
  ```

git リポジトリは `study_python_finance/.git/` にあり。`progate_python_finance/` 側は管理外。

---

## 12. ユーザーの好み（重要）

これまでのやり取りから読み取れる UI/UX 上の譲れない点:

1. **Title Case 英字**（UPPERCASE + 字間 NG）
2. **角丸ゼロ**、シャープな枠線
3. **白基調 + 鮮やかな赤** が唯一のアクセント色
4. **絵文字なし** — UI ラベルから絵文字を排除
5. **ビジネスグレードでスタイリッシュな見た目**（カジュアル / ゲーミー過ぎない）
6. **棒人間は固定配置**（コンテンツに被らない）
7. **コードブロックは VSCode Light Modern** の見た目
8. **スクロール最小化**: 760px 窓に収まるように
9. **Exercise の解説は「基本形 / 使いどころ / 注意点」を明示**
10. **テストはスキップ可能** & 採点 jargon を見せない

---

## 13. 次のセッションへの引継ぎポイント

### 起動・テスト・コミット
```bash
cd "C:/Users/skokh/OneDrive/デスクトップ/開発用フォルダ/study_python_finance"
uv sync                         # 環境準備
uv run python -m app.main       # 起動
uv run pytest                   # テスト

# コミット時
git add <files>
git -c commit.gpgsign=false commit -m "..."
git push origin main
```

### よくある作業パターン
- **章コンテンツの編集**: `content/chapters/NN_*.yaml` を編集 → 自動再読み込みされないので、アプリ再起動
- **採点ロジック変更**: `app/grading/judge.py` → `tests/test_grading.py` のテストを実行
- **UI 変更**: `app/ui/` 配下 → `uv run python -c "..."` でスモークテスト
- **新章追加**: `content/chapters/NN_*.yaml` を作成 → Pydantic スキーマ (`app/content/schemas.py`) で自動バリデーション

### 困ったとき
- ImportError: `uv sync` を再実行
- カーネル起動エラー: `uv run python -c "from app.kernel.manager import KernelSession; k = KernelSession(); k.start(); print('OK'); k.shutdown()"`
- 章 YAML が壊れた: `uv run python -c "from app.content.loader import load_chapter; from pathlib import Path; load_chapter(Path('content/chapters/01_hello.yaml'))"`

### 連絡先 (リポジトリ owner)
- GitHub: kakurosu
- ローカル開発者: skokh.hidi.herih@gmail.com (CLAUDE.md より)

---

以上。プロジェクトの状態は安定しており、追加開発も既存の枠組みの上でスムーズに進められるはずです。
