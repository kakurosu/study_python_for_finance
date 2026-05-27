# ruff: noqa: N806
# Finance convention: capital R / S / T / K denote returns / spot / time / strike.
"""Synthetic CSV generator for Study Python for Finance exercises.

Run this once to (re)produce all the supplementary CSV files used by
the "参考実装" sample pages added in Phase 1 onwards. The data is fully
synthetic — no internet access, no third-party data sources — and
reproducible thanks to ``np.random.seed(0)`` at the top of each
generator function.

Usage:
    cd study_python_finance
    uv run python data/_generate.py

Each function writes one CSV to ``data/`` and prints a one-line summary.
Files are kept under 100 KB and are committed to the repository so that
end-users do not need to run this script themselves.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# 1) stocks_daily.csv — 504 営業日 (2 年) x 4 銘柄
# ---------------------------------------------------------------------------
def gen_stocks_daily() -> None:
    rng = np.random.default_rng(0)
    n = 504  # ~ 2 trading years
    dates = pd.bdate_range("2023-01-02", periods=n)
    # Drift / vol per name (annualised → daily)
    spec = {
        "AAPL_jp": (0.10, 0.22),
        "MSFT_jp": (0.09, 0.20),
        "TOPIX": (0.05, 0.16),
        "JGB10Y": (0.01, 0.03),
    }
    df = pd.DataFrame({"date": dates})
    for name, (mu, sig) in spec.items():
        dt = 1 / 252
        eps = rng.standard_normal(n)
        log_rets = (mu - 0.5 * sig**2) * dt + sig * np.sqrt(dt) * eps
        prices = 100 * np.exp(np.cumsum(log_rets))
        df[name] = np.round(prices, 2)
    out = DATA_DIR / "stocks_daily.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 2) returns_monthly.csv — 60 か月 (5 年) x 6 資産
# ---------------------------------------------------------------------------
def gen_returns_monthly() -> None:
    rng = np.random.default_rng(1)
    n = 60
    months = pd.date_range("2020-01-31", periods=n, freq="ME").strftime("%Y%m").astype(int)
    assets = ["Equity_DM", "Equity_EM", "Bond_DM", "REIT", "Commod", "Cash"]
    # Annualised expected returns and a hand-tuned correlation matrix.
    mu_ann = np.array([0.08, 0.10, 0.03, 0.07, 0.04, 0.01])
    sig_ann = np.array([0.15, 0.22, 0.06, 0.18, 0.20, 0.005])
    corr = np.array(
        [
            [1.00, 0.65, -0.20, 0.55, 0.25, 0.00],
            [0.65, 1.00, -0.10, 0.50, 0.30, 0.00],
            [-0.20, -0.10, 1.00, -0.05, -0.10, 0.10],
            [0.55, 0.50, -0.05, 1.00, 0.20, 0.00],
            [0.25, 0.30, -0.10, 0.20, 1.00, 0.00],
            [0.00, 0.00, 0.10, 0.00, 0.00, 1.00],
        ]
    )
    cov_ann = corr * np.outer(sig_ann, sig_ann)
    # Monthly draws.
    mu_m = mu_ann / 12
    cov_m = cov_ann / 12
    R = rng.multivariate_normal(mu_m, cov_m, size=n)
    df = pd.DataFrame(np.round(R, 6), columns=assets)
    df.insert(0, "YearMonth", months)
    out = DATA_DIR / "returns_monthly.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 3) factors_french.csv — Fama-French 3 因子 月次 120 か月 (10 年)
# ---------------------------------------------------------------------------
def gen_factors_french() -> None:
    rng = np.random.default_rng(2)
    n = 120
    dates = pd.date_range("2015-01-31", periods=n, freq="ME").strftime("%Y-%m-%d")
    # Annualised premia, volatilities (rough empirical scales)
    mu = np.array([0.07, 0.02, 0.03, 0.01]) / 12  # MKT, SMB, HML, RF
    sig = np.array([0.16, 0.10, 0.12, 0.002]) / np.sqrt(12)
    R = rng.standard_normal((n, 4)) * sig + mu
    df = pd.DataFrame(np.round(R, 6), columns=["MKT", "SMB", "HML", "RF"])
    df.insert(0, "date", dates)
    out = DATA_DIR / "factors_french.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 4) options_chain.csv — 単一原資産のオプションチェーン 60 行
# ---------------------------------------------------------------------------
def gen_options_chain() -> None:
    rng = np.random.default_rng(3)
    expiries = ["2025-03-21", "2025-06-20", "2025-09-19"]
    strikes = np.arange(80, 121, 2)  # 21 strikes
    rows = []
    S = 100.0  # spot
    r = 0.02
    sig0 = 0.22
    for exp in expiries:
        T = (pd.Timestamp(exp) - pd.Timestamp("2025-01-15")).days / 365
        for K in strikes:
            # crude vol smile (smile-shaped)
            moneyness = K / S
            iv = sig0 + 0.10 * (moneyness - 1.0) ** 2
            # Black-Scholes (rough; just for plausible bid/ask numbers)
            from math import exp, log, sqrt
            from statistics import NormalDist

            nd = NormalDist()
            d1 = (log(S / K) + (r + 0.5 * iv**2) * T) / (iv * sqrt(T))
            d2 = d1 - iv * sqrt(T)
            call_mid = S * nd.cdf(d1) - K * exp(-r * T) * nd.cdf(d2)
            put_mid = K * exp(-r * T) * nd.cdf(-d2) - S * nd.cdf(-d1)
            spread = max(0.10, 0.05 * max(call_mid, put_mid))
            rows.append(
                {
                    "expiry": exp,
                    "strike": float(K),
                    "call_bid": round(max(0.01, call_mid - spread / 2), 2),
                    "call_ask": round(call_mid + spread / 2, 2),
                    "put_bid": round(max(0.01, put_mid - spread / 2), 2),
                    "put_ask": round(put_mid + spread / 2, 2),
                    "iv": round(float(iv), 4),
                }
            )
    df = pd.DataFrame(rows)
    out = DATA_DIR / "options_chain.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")
    _ = rng  # silence unused; we used numpy.random.default_rng for consistency


# ---------------------------------------------------------------------------
# 5) portfolio_holdings.csv — 30 銘柄の保有データ
# ---------------------------------------------------------------------------
def gen_portfolio_holdings() -> None:
    rng = np.random.default_rng(4)
    n = 30
    tickers = [f"T{i:04d}" for i in range(1, n + 1)]
    sectors = rng.choice(
        ["Tech", "Financials", "Healthcare", "Energy", "Consumer", "Industrials", "Materials"],
        size=n,
        p=[0.30, 0.18, 0.12, 0.10, 0.12, 0.10, 0.08],
    )
    countries = rng.choice(
        ["JP", "US", "EU", "EM"],
        size=n,
        p=[0.40, 0.30, 0.20, 0.10],
    )
    raw_w = rng.dirichlet(np.ones(n) * 1.5)
    df = pd.DataFrame(
        {
            "ticker": tickers,
            "weight": np.round(raw_w, 4),
            "sector": sectors,
            "country": countries,
        }
    )
    out = DATA_DIR / "portfolio_holdings.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 6) macro_indicators.csv — 120 か月 (10 年) のマクロ指標
# ---------------------------------------------------------------------------
def gen_macro_indicators() -> None:
    rng = np.random.default_rng(5)
    n = 120
    dates = pd.date_range("2015-01-31", periods=n, freq="ME").strftime("%Y-%m-%d")
    # Simple AR(1)-ish dynamics around a slow drift.
    gdp = 2.0 + rng.standard_normal(n).cumsum() * 0.05
    gdp = np.clip(gdp, -2.0, 5.0)
    cpi = 1.5 + rng.standard_normal(n).cumsum() * 0.06
    cpi = np.clip(cpi, -1.0, 6.0)
    unemp = 4.0 + (rng.standard_normal(n).cumsum() * 0.04)
    unemp = np.clip(unemp, 2.0, 7.0)
    ff = 0.5 + np.maximum(0, cpi - 2.0) * 0.4 + rng.standard_normal(n) * 0.05
    ff = np.clip(ff, 0.0, 6.0)
    df = pd.DataFrame(
        {
            "date": dates,
            "GDP_yoy": np.round(gdp, 3),
            "CPI_yoy": np.round(cpi, 3),
            "UnempRate": np.round(unemp, 3),
            "FedFunds": np.round(ff, 3),
        }
    )
    out = DATA_DIR / "macro_indicators.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 7) house_prices.csv — 200 行の住宅価格回帰用データ
# ---------------------------------------------------------------------------
def gen_house_prices() -> None:
    rng = np.random.default_rng(6)
    n = 200
    area = rng.uniform(40, 120, n)
    bedrooms = rng.choice([1, 2, 3, 4, 5], n, p=[0.10, 0.25, 0.35, 0.20, 0.10])
    age = rng.integers(0, 50, n)
    station_min = rng.integers(1, 30, n)
    # True log-linear model + noise
    log_price = (
        4.0
        + 0.018 * area
        + 0.12 * bedrooms
        - 0.012 * age
        - 0.025 * station_min
        + rng.standard_normal(n) * 0.10
    )
    price = np.round(np.exp(log_price) * 100, 0).astype(int)  # 万円
    df = pd.DataFrame(
        {
            "area": np.round(area, 1),
            "bedrooms": bedrooms,
            "age": age,
            "station_min": station_min,
            "price": price,
        }
    )
    out = DATA_DIR / "house_prices.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")


# ---------------------------------------------------------------------------
# 8) credit_default.csv — 500 行の信用デフォルト分類データ
# ---------------------------------------------------------------------------
def gen_credit_default() -> None:
    rng = np.random.default_rng(7)
    n = 500
    age = rng.integers(20, 75, n)
    income = np.round(rng.lognormal(mean=6.0, sigma=0.5, size=n), 0)  # 万円相当
    debt_ratio = np.clip(rng.normal(0.35, 0.15, n), 0.0, 1.5)
    n_defaults = rng.poisson(0.2, n)
    # logistic score (higher → more likely default)
    score = (
        -3.0
        + 0.04 * (age - 45)
        - 0.0008 * (income - 600)
        + 2.5 * (debt_ratio - 0.3)
        + 0.6 * n_defaults
        + rng.standard_normal(n) * 0.5
    )
    p_default = 1 / (1 + np.exp(-score))
    default = (rng.uniform(size=n) < p_default).astype(int)
    df = pd.DataFrame(
        {
            "age": age,
            "income": income.astype(int),
            "debt_ratio": np.round(debt_ratio, 3),
            "n_defaults": n_defaults,
            "default": default,
        }
    )
    out = DATA_DIR / "credit_default.csv"
    df.to_csv(out, index=False)
    rate = float(df["default"].mean())
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols  (default rate = {rate:.1%})")


# ---------------------------------------------------------------------------
# 9) sentiment_corpus.csv — 50 行のヘッドラインxsentiment
# ---------------------------------------------------------------------------
def gen_sentiment_corpus() -> None:
    rng = np.random.default_rng(8)
    headlines_pos = [
        "Quarterly earnings beat analyst estimates by wide margin",
        "Central bank signals dovish stance, equities rally",
        "Major contract win lifts industrial group outlook",
        "Dividend hike announced, share buyback expanded",
        "FDA approves new treatment, biotech stock surges",
        "Strong holiday sales drive retail sector higher",
        "Successful product launch boosts consumer confidence",
        "Merger synergies exceed initial guidance",
        "Manufacturing PMI returns to expansion territory",
        "Bond auction sees record demand from foreign buyers",
    ]
    headlines_neg = [
        "Profit warning sparks 20% intraday plunge",
        "Regulator opens probe into accounting practices",
        "Hawkish Fed minutes trigger broad sell-off",
        "Recall of flagship product weighs on guidance",
        "Inflation print surprises sharply to the upside",
        "Geopolitical tensions escalate, oil spikes higher",
        "Yield curve inverts, recession concerns mount",
        "Major data breach disclosed, share price tumbles",
        "Currency depreciation hurts margins, miss expected",
        "Strike action halts production at flagship plant",
    ]
    headlines_neu = [
        "Company announces routine board meeting schedule",
        "Quarterly filing released as scheduled",
        "CEO to speak at industry conference next month",
        "Ratings agency affirms stable outlook",
        "Index rebalancing announced for next quarter",
        "Dividend payment date confirmed",
        "Annual report distributed to shareholders",
        "Trading session ends mixed amid light volumes",
        "ETF inflows broadly in line with expectations",
        "Subsidiary completes scheduled audit",
    ]
    rows = []
    base = pd.Timestamp("2025-01-02")
    for i, (label, pool) in enumerate(
        [("positive", headlines_pos), ("negative", headlines_neg), ("neutral", headlines_neu)]
    ):
        for j, h in enumerate(pool):
            rows.append(
                {
                    "date": (base + pd.Timedelta(days=i * 10 + j * 3)).strftime("%Y-%m-%d"),
                    "headline": h,
                    "sentiment": label,
                }
            )
    df = pd.DataFrame(rows).sample(frac=1, random_state=8).reset_index(drop=True)
    out = DATA_DIR / "sentiment_corpus.csv"
    df.to_csv(out, index=False)
    print(f"  [OK] {out.name}: {len(df)} rows x {df.shape[1]} cols")
    _ = rng


# ---------------------------------------------------------------------------
def main() -> None:
    print(f"Generating supplementary CSVs into {DATA_DIR} ...")
    gen_stocks_daily()
    gen_returns_monthly()
    gen_factors_french()
    gen_options_chain()
    gen_portfolio_holdings()
    gen_macro_indicators()
    gen_house_prices()
    gen_credit_default()
    gen_sentiment_corpus()
    print("Done.")


if __name__ == "__main__":
    main()
