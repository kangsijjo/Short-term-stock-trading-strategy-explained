"""
다중 전략 통합 평가 리포트.

각 전략의 StrategyTrade 리스트를 받아 동일 지표 산출:
  - n_trades, win_rate, profit_factor
  - avg_net_pct, cum_pct
  - max drawdown (cumulative net_pct 기준)
  - Sharpe (단순 일평균/일표준편차 √252)
  - 연환산 수익률 (cum_pct / 기간 * 252)
"""

from dataclasses import asdict
import math
import pandas as pd
import numpy as np


def evaluate(trades, label=None):
    """단일 전략 평가."""
    if not trades:
        return {"name": label or "?", "n_trades": 0}

    df = pd.DataFrame([asdict(t) for t in trades])
    df["entry_date"] = pd.to_datetime(df["entry_date"], format="%Y%m%d")
    df = df.sort_values("entry_date").reset_index(drop=True)

    n = len(df)
    wins = df[df["net_pct"] > 0]
    losses = df[df["net_pct"] <= 0]
    win_rate = len(wins) / n * 100
    wins_sum = wins["net_pct"].sum()
    losses_sum = -losses["net_pct"].sum()
    pf = wins_sum / losses_sum if losses_sum > 0 else float("inf")

    avg_net = df["net_pct"].mean()
    cum = df["net_pct"].sum()

    # MDD: cumulative net_pct 의 최대 낙폭
    cum_series = df["net_pct"].cumsum()
    peak = cum_series.cummax()
    drawdown = cum_series - peak
    mdd = drawdown.min()

    # Sharpe (간이): 일별 평균 net_pct / 일별 std × √252
    daily = df.groupby(df["entry_date"].dt.date)["net_pct"].sum()
    sharpe = (daily.mean() / daily.std() * math.sqrt(252)
              if daily.std() > 0 else 0.0)

    # 연환산 수익률 (영업일 252 기준)
    days_span = (df["entry_date"].max() - df["entry_date"].min()).days
    years = max(days_span / 365.25, 1/252)
    annualized = cum / years

    return {
        "name": label or trades[0].strategy,
        "n_trades": n,
        "win_rate_pct": round(win_rate, 2),
        "avg_net_pct": round(avg_net, 3),
        "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
        "cum_pct": round(cum, 2),
        "mdd_pct": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "annual_sum": round(annualized, 2),    # 매매 net_pct 의 연환산 단순합 (자본 X)
    }


# 통과 기준 (포트폴리오 적합도 점수)
PASS_CRITERIA = {
    "profit_factor": 1.5,
    "sharpe":        1.0,
    "win_rate_pct":  45.0,
    "annual_pct":    15.0,
    "mdd_pct":      -25.0,    # 양호: -25% 이상 (덜 깊음)
    "n_trades":      100,
}


def fit_score(metrics):
    """6개 기준 중 통과 개수 / 6."""
    if metrics["n_trades"] < 10:
        return 0.0
    passed = 0
    pf = metrics["profit_factor"]
    if pf != "inf" and pf >= PASS_CRITERIA["profit_factor"]:
        passed += 1
    if pf == "inf":
        passed += 1
    if metrics["sharpe"] >= PASS_CRITERIA["sharpe"]: passed += 1
    if metrics["win_rate_pct"] >= PASS_CRITERIA["win_rate_pct"]: passed += 1
    if metrics["annual_sum"] >= PASS_CRITERIA["annual_pct"]: passed += 1
    if metrics["mdd_pct"] >= PASS_CRITERIA["mdd_pct"]: passed += 1
    if metrics["n_trades"] >= PASS_CRITERIA["n_trades"]: passed += 1
    return passed / 6


def print_comparison(results):
    """여러 전략 결과를 한 표로 출력."""
    rows = []
    for r in results:
        score = fit_score(r) if r["n_trades"] >= 10 else 0
        r2 = {**r, "fit": f"{int(score*6)}/6"}
        rows.append(r2)
    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print(" 전략 비교")
    print("=" * 100)
    print(df.to_string(index=False))
    print()
    print(f" 통과 기준: pf≥{PASS_CRITERIA['profit_factor']}, sharpe≥{PASS_CRITERIA['sharpe']}, "
          f"win≥{PASS_CRITERIA['win_rate_pct']}%, annual≥{PASS_CRITERIA['annual_pct']}%, "
          f"mdd≥{PASS_CRITERIA['mdd_pct']}%, n≥{PASS_CRITERIA['n_trades']}")
