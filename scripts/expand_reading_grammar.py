"""Prepend a per-question "読み方ガイド" to each Reading review question.

Each question in `content/chapters/{11,16,22,26,29,32}_reading_phase_?.yaml`
gets a leading **「この問題の文法ポイント」** section inserted at the top of
its `prompt`. The section explains the grammar / API being tested so that
a learner can complete the Reading review **without** re-opening the source
chapter — i.e. the review chapter becomes self-contained.

Idempotency: the guard marker is the literal string
``**この問題の文法ポイント**`` — if the prompt already starts with it, the
question is skipped.

Usage:
    uv run python scripts/expand_reading_grammar.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "content" / "chapters"

MARKER = "**この問題の文法ポイント**"


# Per-question grammar guide, keyed by (chapter_id, question_index_0based).
# Each value is the multi-line text that will be prepended to the prompt.
GUIDES: dict[tuple[int, int], str] = {
    # ─── Ch11 — Phase A 復習 ────────────────────────────────
    (11, 0): (
        "**この問題の文法ポイント**\n\n"
        "- `print(...)` は値を **画面に出力** する組み込み関数。引数の文字列はクォートを取り除いて出力。\n"
        "- 文字列リテラルは `\"...\"` か `'...'` で囲む。クォートが抜けると `NameError`。\n"
        "- 末尾の改行はデフォルトで自動付加 (`end=\"\\n\"`)。\n\n"
        "**読み方**: `print()` の括弧の中だけを見て、それがそのまま画面に出ます。"
    ),
    (11, 1): (
        "**この問題の文法ポイント**\n\n"
        "- 小数点を含むリテラル (`3.14`) は `float` 型 / 整数 (`3`) は `int` 型 / クォート囲み (`\"3\"`) は `str` 型 / `True/False` は `bool` 型。\n"
        "- `type(x)` は **オブジェクトの型** を `<class '...'>` の形で返す。\n\n"
        "**読み方**: 代入されている値の **表記** を見て型を判定 — 小数点があるなら float、と覚える。"
    ),
    (11, 2): (
        "**この問題の文法ポイント**\n\n"
        "- `//` は **整数除算** (商の整数部)。`17 // 5 = 3`。\n"
        "- `%` は **剰余** (割った余り)。`17 % 5 = 2`。\n"
        "- 普通の割り算 `/` は `float` を返す (`17 / 5 = 3.4`)。\n\n"
        "**読み方**: 演算子の **記号 1 個か 2 個か** で動作が変わるので、`/` と `//` を取り違えない。"
    ),
    (11, 3): (
        "**この問題の文法ポイント**\n\n"
        "- 行頭の `#` 以降はその行末まで **コメント** として無視される。\n"
        "- 行の途中にある `#` も、それ以降は **同じ行のコメント** になる (インラインコメント)。\n"
        "- コメント部分は Python が実行しないので、`print(\"...\")` がコメントの中にあっても出力されない。\n\n"
        "**読み方**: 各行で `#` の位置を見て、その左側だけが実行される、と読む。"
    ),
    (11, 4): (
        "**この問題の文法ポイント**\n\n"
        "- `sum(iter)` は要素の合計、`len(iter)` は要素数を返す **組み込み関数**。\n"
        "- `sum(nums) / len(nums)` で **平均** を計算するのが定型。\n"
        "- 整数同士の `/` でも結果は float (`100 / 4 == 25.0`)。\n\n"
        "**読み方**: まず `sum` の値、次に `len` の値を頭で計算してから割る。"
    ),
    (11, 5): (
        "**この問題の文法ポイント**\n\n"
        "- `if cond: ... elif cond2: ... else: ...` は **上から順に条件を試して、最初に真になったブロックだけ** を実行する。\n"
        "- 一度どれかが実行されると、残りの `elif/else` は **スキップ**される。\n"
        "- 各ブロックの中はインデント (4 スペース) で表す。\n\n"
        "**読み方**: 上から条件を順に評価し、最初に True になった行の `print` だけが動く、と追う。"
    ),
    (11, 6): (
        "**この問題の文法ポイント**\n\n"
        "- `range(start, stop, step)` は `start` から `stop` の **手前** までを `step` ずつ進む整数列。\n"
        "- `stop` は **含まない** (半開区間)。`range(2, 8, 2)` は 2, 4, 6 の 3 個。\n"
        "- `for x in range(...)` でループ回数を制御するのが定型。\n\n"
        "**読み方**: 「start から始めて step ずつ足し、stop の前で止まる」と数え上げる。"
    ),
    (11, 7): (
        "**この問題の文法ポイント**\n\n"
        "- リストの **スライス** `xs[i:j]` は index `i` から `j` の **手前** までの新しいリストを返す。\n"
        "- 元のリストは変わらない (非破壊)。`i` 省略で先頭から、`j` 省略で末尾まで。\n"
        "- 負のインデックスは末尾から (`xs[-1]` で最後の要素)。\n\n"
        "**読み方**: 「`i` 番から、`j` 番の **手前** まで」と区切って数える。"
    ),
    (11, 8): (
        "**この問題の文法ポイント**\n\n"
        "- 辞書 `d[key]` でキーから値を取り出す。**存在しないキー** だと `KeyError`。\n"
        "- `d.get(key, default)` は **キーが無くてもエラーにならず** デフォルト値を返す安全版。\n"
        "- 辞書のキー一覧は `d.keys()`、値は `d.values()`、ペアは `d.items()`。\n\n"
        "**読み方**: `.get(key, default)` の第 2 引数を見て、キーが無いときの返り値を判定。"
    ),
    (11, 9): (
        "**この問題の文法ポイント**\n\n"
        "- `def f(x, y=デフォルト): return ...` で関数を定義。\n"
        "- `return` は関数の **戻り値** を呼び出し元に返して関数を抜ける。\n"
        "- デフォルト引数 (`rate=0.1`) は呼び出し時に省略可能。\n\n"
        "**読み方**: `return` の右辺を頭で計算し、呼び出し側の引数値を代入してみる。"
    ),
    # ─── Ch16 — Phase B 復習 ────────────────────────────────
    (16, 0): (
        "**この問題の文法ポイント**\n\n"
        "- NumPy 配列にスカラーを掛けると **各要素にブロードキャスト** で適用される (`np.array([1,2,3]) * 10 == [10,20,30]`)。\n"
        "- 同じ計算を `for` ループで書くより圧倒的に速い。\n"
        "- ブロードキャストは「形が違う配列同士でも自動でサイズを合わせる」ルール。\n\n"
        "**読み方**: 配列とスカラーを掛けたら **各要素にスカラーが掛かる** とイメージ。"
    ),
    (16, 1): (
        "**この問題の文法ポイント**\n\n"
        "- `ndarray.mean()` は **全要素の算術平均** を返す。\n"
        "- 多次元配列で行・列ごとに集計したいときは `axis=0` (列方向) / `axis=1` (行方向) を指定。\n"
        "- `np.mean(arr)` でも同じ結果。\n\n"
        "**読み方**: 要素を全部足して要素数で割る、と紙の上で計算。"
    ),
    (16, 2): (
        "**この問題の文法ポイント**\n\n"
        "- `pd.Series(data, index=[...])` で **ラベル付き 1 次元配列** を作る。\n"
        "- インデックスはラベルなので `s[\"a\"]` のように文字列でアクセスできる (DataFrame の 1 列分に相当)。\n"
        "- ラベルが整数でも、`s[0]` は **位置** ではなく **ラベル** として解釈される (混乱の元)。\n\n"
        "**読み方**: `index=` で指定したラベルと、それぞれに対応する値のペアを 1 個ずつ確認。"
    ),
    (16, 3): (
        "**この問題の文法ポイント**\n\n"
        "- DataFrame は **2 次元の表データ**。`df[\"col_name\"]` で 1 列 (Series) を取り出す。\n"
        "- 条件で行を絞るときは `df[df[\"col\"] > 100]` (boolean indexing) を使う。\n"
        "- 列名と行 index が **両方** あるので、混同しないように。\n\n"
        "**読み方**: `df[\"...\"]` は **列の名前**、`df[条件]` は **行の真偽値**、と区別。"
    ),
    (16, 4): (
        "**この問題の文法ポイント**\n\n"
        "- matplotlib の主要関数: `plt.plot` (折れ線)、`plt.bar` (棒)、`plt.scatter` (散布)、`plt.hist` (ヒストグラム)。\n"
        "- 用途で使い分ける: 時系列 → plot、カテゴリ別 → bar、2 変数の関係 → scatter、分布 → hist。\n"
        "- 描画後に `plt.show()` で表示。\n\n"
        "**読み方**: 関数名がそのまま描画タイプ、と覚える。"
    ),
    (16, 5): (
        "**この問題の文法ポイント**\n\n"
        "- `plt.scatter(x, y)` は **2 つの数値配列の点を打つ** 散布図。各点 (x[i], y[i]) が独立に描画される。\n"
        "- 2 変数の **相関** を視覚化するのに最適。線で繋がない。\n"
        "- 折れ線が良ければ `plt.plot`、棒が良ければ `plt.bar`。\n\n"
        "**読み方**: 「2 つの量の関係」を見たいなら scatter、と判断。"
    ),
    (16, 6): (
        "**この問題の文法ポイント**\n\n"
        "- `df.groupby(col)` は **特定の列の値で行をまとめる** 操作。`.mean()` などで集計する。\n"
        "- SQL の `GROUP BY` と同じ。「カテゴリ別の平均」「セクター別の合計」が典型用途。\n"
        "- 結果は **グループ列が index** の Series / DataFrame。\n\n"
        "**読み方**: `groupby(\"X\")` で X が同じ行をまとめ、そのあと集計関数を適用、と読む。"
    ),
    (16, 7): (
        "**この問題の文法ポイント**\n\n"
        "- `left.merge(right, on=\"key\")` は 2 つの DataFrame を **key 列の値が一致する行** で結合 (SQL の JOIN)。\n"
        "- `how=` で `\"inner\"` (両方にある, 既定) / `\"left\"` (左を残す) / `\"outer\"` (両方) を選ぶ。\n"
        "- 結合後の行数は how と key の重複具合で決まる。\n\n"
        "**読み方**: `on=` の列で **値が同じ行同士を横に並べる**、とイメージ。"
    ),
    # ─── Ch22 — Phase C 復習 ────────────────────────────────
    (22, 0): (
        "**この問題の文法ポイント**\n\n"
        "- 期待値は $E[R] = \\sum_i p_i \\cdot r_i$ (確率重み付き平均)。\n"
        "- NumPy では `(probs * returns).sum()` で 1 行。\n"
        "- 確率 `probs` は合計 1 でなければならない (確認: `probs.sum() == 1.0`)。\n\n"
        "**読み方**: 「シナリオごとの確率 × リターン」を足し合わせる、と公式どおりに計算。"
    ),
    (22, 1): (
        "**この問題の文法ポイント**\n\n"
        "- `np.std(arr, ddof=1)` は **不偏標準偏差** ((n-1) で割る、サンプル統計)。\n"
        "- `ddof=0` は母分散ベース (n で割る)、Python 既定。\n"
        "- 金融データは「サンプルから母集団を推測」する場面が多いので `ddof=1` を使うのが業界標準。\n\n"
        "**読み方**: `ddof=1` を見たら **不偏 (= サンプル統計)** と判定。"
    ),
    (22, 2): (
        "**この問題の文法ポイント**\n\n"
        "- `np.cov(a, b, ddof=1)` は **2 列の共分散行列** (2x2) を返す。\n"
        "- 対角成分 `cov[0,0]`, `cov[1,1]` はそれぞれ **a の分散**、**b の分散**。\n"
        "- 非対角 `cov[0,1] == cov[1,0]` は a と b の **共分散**。\n\n"
        "**読み方**: 行と列が同じ index の場所は「自分の分散」、違うところは「他との関係」と覚える。"
    ),
    (22, 3): (
        "**この問題の文法ポイント**\n\n"
        "- 相関係数は $\\rho = \\dfrac{\\mathrm{Cov}(a,b)}{\\sigma_a \\sigma_b}$ で計算。\n"
        "- 共分散を **各々の標準偏差の積** で割ると、$-1 \\le \\rho \\le 1$ にスケールされる。\n"
        "- `np.corrcoef(a, b)` でも同じ結果が得られる。\n\n"
        "**読み方**: 共分散行列の非対角を、対角の平方根の積で割る、と公式を追う。"
    ),
    (22, 4): (
        "**この問題の文法ポイント**\n\n"
        "- シャープレシオ = $\\dfrac{\\mu_p - r_f}{\\sigma_p}$ (超過リターン ÷ ボラティリティ)。\n"
        "- 「リスク 1 単位あたりの超過リターン」を測る業界標準指標。\n"
        "- 月次データから年率化するには **μ は ×12、σ は ×√12**。\n\n"
        "**読み方**: 「超過リターンの平均」を「ボラ」で割る、というシンプルな比率と捉える。"
    ),
    (22, 5): (
        "**この問題の文法ポイント**\n\n"
        "- 情報比率 (IR) = $\\dfrac{\\mu_a - \\mu_b}{\\sigma(r_a - r_b)}$ (アクティブリターン ÷ トラッキングエラー)。\n"
        "- ベンチマーク **対比** で測るのでアクティブ運用評価の標準指標。\n"
        "- 分母は超過リターン (差分系列) の標準偏差、ボラそのものではない点に注意。\n\n"
        "**読み方**: 「対ベンチの差分系列」の平均と std を取って割る、と読む。"
    ),
    (22, 6): (
        "**この問題の文法ポイント**\n\n"
        "- 等加重ポートフォリオは **全資産を同じ比率で持つ** 最もシンプルな戦略。\n"
        "- `np.ones(n) / n` で n 個の `1/n` のベクトルが作れる (合計は 1)。\n"
        "- Markowitz 最適化の **ベースライン比較** によく使われる。\n\n"
        "**読み方**: 配列の要素数と中身を見て「全部同じ値」になっているか確認。"
    ),
    (22, 7): (
        "**この問題の文法ポイント**\n\n"
        "- ポートフォリオ分散は $\\sigma_p^2 = \\mathbf{w}^\\top \\Sigma \\mathbf{w}$ (重みベクトル × 共分散 × 重みベクトル)。\n"
        "- NumPy では `w @ cov @ w` で 1 行 (`@` は行列積演算子)。\n"
        "- 結果は **スカラー (1 個の数)**、これの平方根がポートフォリオのボラ。\n\n"
        "**読み方**: 行列積を左から順に「w・cov → ベクトル」「そのベクトル・w → スカラー」と追う。"
    ),
    (22, 8): (
        "**この問題の文法ポイント**\n\n"
        "- `np.random.default_rng(seed)` で **乱数生成器** を作る。同じ seed なら結果再現可。\n"
        "- `.standard_normal(n)` で標準正規分布 (μ=0, σ=1) から n 個サンプル。\n"
        "- モンテカルロは「乱数を多数回振って平均を取る」近似法の総称。\n\n"
        "**読み方**: `seed=0` で乱数を固定して、生成された配列の形 (shape) を確認。"
    ),
    (22, 9): (
        "**この問題の文法ポイント**\n\n"
        "- GBM の対数収益は $\\log\\dfrac{S_{t+dt}}{S_t} = (\\mu - \\tfrac{\\sigma^2}{2}) dt + \\sigma\\sqrt{dt}\\,Z$。\n"
        "- ドリフト項に **$-\\sigma^2/2$ の補正** が入る (伊藤の補題から)。これを忘れると価格期待値がずれる。\n"
        "- 累積和を `exp` すると価格パスになる。\n\n"
        "**読み方**: 公式の各項 (ドリフト・分散補正・拡散) を 1 つずつコードと対応付ける。"
    ),
    # ─── Ch26 — Phase D 復習 ────────────────────────────────
    (26, 0): (
        "**この問題の文法ポイント**\n\n"
        "- `ARIMA(series, order=(p, d, q))` の `order` は **AR 次数 p / 差分階数 d / MA 次数 q**。\n"
        "- 例: `(1, 1, 1)` は「1 階差分を取った系列に AR(1) と MA(1) を当てる」。\n"
        "- 株価のように非定常な系列は `d=1` で差分を取ってから当てるのが定石。\n\n"
        "**読み方**: `order` のタプル 3 要素を **p, d, q の順** で読む。"
    ),
    (26, 1): (
        "**この問題の文法ポイント**\n\n"
        "- `Series.pct_change()` は **前期からの変化率** $\\dfrac{P_t - P_{t-1}}{P_{t-1}} = \\dfrac{P_t}{P_{t-1}} - 1$。\n"
        "- 1 行目は前期がないので `NaN`。`.dropna()` で除外するのが定型。\n"
        "- 「価格 → リターン」変換の最頻出メソッド。\n\n"
        "**読み方**: 各時点の値を「前の値で割って 1 を引く」と紙で計算してみる。"
    ),
    (26, 2): (
        "**この問題の文法ポイント**\n\n"
        "- scikit-learn の最頻出パターン: `model.fit(X, y)` → `model.predict(X)`。\n"
        "- `fit` が学習、`predict` が予測。すべてのモデル (LinearRegression / RandomForest / etc.) で **共通 API**。\n"
        "- 結果は学習データに対する予測値の配列。\n\n"
        "**読み方**: 「学習 → 予測」の 2 ステップ、と覚える。"
    ),
    (26, 3): (
        "**この問題の文法ポイント**\n\n"
        "- `train_test_split(X, y, test_size=0.2, random_state=42)` で **訓練・テスト分割**。\n"
        "- `test_size=0.2` → テスト 20%, 訓練 80%。`random_state` で再現可能に。\n"
        "- 返り値の順序は **X_train, X_test, y_train, y_test** (混同注意)。\n\n"
        "**読み方**: 戻り値 4 つを左から「特徴量訓練, 特徴量テスト, 目的変数訓練, 目的変数テスト」と当てる。"
    ),
    (26, 4): (
        "**この問題の文法ポイント**\n\n"
        "- PyTorch 学習ループの **4 ステップ**: ① `pred = model(X)` (forward) → ② `loss = loss_fn(pred, y)` → ③ `loss.backward()` (勾配計算) → ④ `optimizer.step()` (パラメータ更新)。\n"
        "- この順序が定型。`zero_grad()` を ① の前に挟むのも定石。\n\n"
        "**読み方**: 4 行が **forward → loss → backward → step** の順になっているか確認。"
    ),
    (26, 5): (
        "**この問題の文法ポイント**\n\n"
        "- `nn.Sequential(...)` は **層を順に並べる** だけのコンテナ。前の層の出力が次の入力。\n"
        "- `nn.Linear(in, out)` は全結合層 (重み W と バイアス b)。\n"
        "- 活性化関数 (`nn.ReLU()` 等) は層と層の間に挟む。\n\n"
        "**読み方**: 各層の `in/out` 次元を追って、配列の形が整合しているか確認。"
    ),
    # ─── Ch29 — Phase E 復習 ────────────────────────────────
    (29, 0): (
        "**この問題の文法ポイント**\n\n"
        "- `requests.get(url)` で **HTTP GET リクエスト** を送信。`Response` オブジェクトが返る。\n"
        "- `response.text` は **本文を str で**、`response.content` は **バイト列で** 返す。\n"
        "- ステータスコードは `response.status_code` (200 = OK)。\n\n"
        "**読み方**: `.text` と `.content` の違い (str か bytes か) を意識して読む。"
    ),
    (29, 1): (
        "**この問題の文法ポイント**\n\n"
        "- `BeautifulSoup(html, \"html.parser\")` で HTML をパース。\n"
        "- `soup.find_all(\"a\")` で **全 `<a>` 要素** を取得 (list で返る)。\n"
        "- 各要素から `a.get(\"href\")` で href 属性を取り出す。\n\n"
        "**読み方**: 「全 a タグを集めて、各 href を取り出す」というスクレイピングの定型と読む。"
    ),
    (29, 2): (
        "**この問題の文法ポイント**\n\n"
        "- `OpenAI()` のインスタンス化は **引数省略可**。その場合は環境変数 `OPENAI_API_KEY` が自動的に使われる。\n"
        "- 明示するなら `OpenAI(api_key=\"sk-...\")` だが、コードに直書きはセキュリティ事故の元。\n"
        "- API キーは `.env` ファイルや OS の環境変数で管理するのが業界標準。\n\n"
        "**読み方**: 引数省略 ≈ 環境変数を読む、と理解。"
    ),
    (29, 3): (
        "**この問題の文法ポイント**\n\n"
        "- `client.chat.completions.create(model=..., messages=[...])` が Chat 系の **基本呼び出し形式**。\n"
        "- `messages` は dict のリスト。各 dict は `{\"role\": \"system\"/\"user\"/\"assistant\", \"content\": \"...\"}`。\n"
        "- 戻り値の `response.choices[0].message.content` に応答テキストが入る。\n\n"
        "**読み方**: messages の role と content を 1 ペアずつ確認、応答の取り出しパスを辿る。"
    ),
    # ─── Ch32 — Phase F 復習 ────────────────────────────────
    (32, 0): (
        "**この問題の文法ポイント**\n\n"
        "- Streamlit は **Python スクリプトをそのまま Web アプリ化** するフレームワーク。\n"
        "- `st.title(...)` で見出し、`st.write(...)` で任意のオブジェクト (文字列・DataFrame・図) を描画。\n"
        "- 起動は `streamlit run script.py`。ファイル保存で自動リロード。\n\n"
        "**読み方**: `st.xxx(...)` 1 行 = ブラウザ上の 1 要素、と対応付け。"
    ),
    (32, 1): (
        "**この問題の文法ポイント**\n\n"
        "- `st.slider(label, min, max, default)` は **ユーザーが現在選んでいる値そのもの** を返す。\n"
        "- 範囲を float で渡すと戻り値も float、int で渡すと int。\n"
        "- スライダーが動くたびにスクリプト全体が再実行される (Streamlit の再実行モデル)。\n\n"
        "**読み方**: 戻り値は **その時点で選択中の値**、と直感的に。"
    ),
    (32, 2): (
        "**この問題の文法ポイント**\n\n"
        "- `pyautogui.moveTo(x, y, duration=t)` は **マウスカーソルを (x, y) へ t 秒かけて移動** する関数。\n"
        "- 座標は画面の左上が (0, 0)。`duration=0` で瞬間移動。\n"
        "- 暴走対策: `pyautogui.FAILSAFE = True` (画面左上にカーソルを動かすと例外で停止)。\n\n"
        "**読み方**: 関数名 `moveTo` を見たら **絶対座標への移動**、と判定。"
    ),
    (32, 3): (
        "**この問題の文法ポイント**\n\n"
        "- Playwright は **ブラウザを Python から操作** するライブラリ。`with sync_playwright()` でリソース管理。\n"
        "- `p.chromium.launch(headless=True)` で Chromium を **画面非表示** で起動 (バッチ用)。\n"
        "- `page.goto(url)` でアクセス、`page.content()` で HTML 取得、`page.close()` / `browser.close()` で終了。\n\n"
        "**読み方**: with ブロック内で browser → page → 操作 → close、の流れを追う。"
    ),
}


class LiteralBlock(str):
    pass


def literal_repr(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlock, literal_repr)


def coerce(node):
    if isinstance(node, dict):
        return {k: coerce(v) for k, v in node.items()}
    if isinstance(node, list):
        return [coerce(v) for v in node]
    if isinstance(node, str) and "\n" in node:
        return LiteralBlock(node)
    return node


def expand_chapter(ch_id: int, path: Path) -> int:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    n_changed = 0
    q_idx = 0
    for page in raw.get("pages", []):
        if page.get("kind") != "reading":
            continue
        guide = GUIDES.get((ch_id, q_idx))
        q_idx += 1
        if guide is None:
            continue
        prompt = (page.get("prompt") or "").lstrip()
        if prompt.startswith(MARKER):
            continue  # already expanded
        new_prompt = guide + "\n\n---\n\n" + prompt
        page["prompt"] = new_prompt
        n_changed += 1
    path.write_text(
        yaml.dump(
            coerce(raw),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    return n_changed


def main() -> None:
    total = 0
    for ch_id in (11, 16, 22, 26, 29, 32):
        path = next(CHAPTERS_DIR.glob(f"{ch_id:02d}_*.yaml"))
        n = expand_chapter(ch_id, path)
        print(f"  [OK] {path.name}: +{n} prompts expanded")
        total += n
    expected = len(GUIDES)
    print(f"\nTotal expansions: {total} (defined guides: {expected})")


if __name__ == "__main__":
    main()
