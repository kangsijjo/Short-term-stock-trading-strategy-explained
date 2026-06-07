"""
자본 사이즈 + 동시보유 모델링.

매매당 평균 수익률 → 진짜 자본 수익률로 변환.

설계:
- initial_capital: 시작 자본
- max_concurrent: 매일 최대 보유 종목 수
- 매매 진입 시점에 가용 현금 / 빈 슬롯 수 만큼 자본 분배
- 시그널 N > 빈 슬롯이면 entry_date 순서로 처리 (먼저 온 거 우선, 초과분 skip)

산출:
  - total_return_pct (총 수익률)
  - cagr_pct (연환산 수익률, 진짜)
  - capital_mdd_pct (자본 기준 mdd, 진짜)
  - capital_sharpe (일별 자본 수익률 기준)
  - n_skipped_signals (슬롯 부족으로 놓친 신호)
  - util_pct (자본 가동률 평균)
"""

import math
import pandas as pd
from dataclasses import asdict


def simulate_capital(trades, initial_capital=10_000_000, max_concurrent=10,
                     min_gross_pct=-30.0, max_gross_pct=None):
    """
    Args:
        trades: list[StrategyTrade]
        initial_capital: 시작 자본 (원)
        max_concurrent: 매일 최대 보유 종목
        min_gross_pct: 이 값 미만 gross_pct 매매 제외 (액면분할 폭락 방어).
            기본 -30% — KOSDAQ 상하한가 자연 한계. 그 이하는 99% 권리락/액면분할.
        max_gross_pct: 이 값 초과 gross_pct 매매 제외 (None 이면 보존).
            ±30% 양방향 컷오프는 진짜 익절도 잘라내므로, 음수만 차단이 정석.
            병합으로 +30% 이상 점프 의심되면 +100% 같은 보수적 상한 가능.

    Returns: dict with metrics, 또는 None (매매 없음)
    """
    if not trades:
        return None

    # 액면분할/병합 방어 — 단방향 컷오프 (음수만 기본, 양수는 진짜 익절 보존)
    n_before = len(trades)
    if min_gross_pct is not None:
        trades = [t for t in trades if t.gross_pct >= min_gross_pct]
    if max_gross_pct is not None:
        trades = [t for t in trades if t.gross_pct <= max_gross_pct]
    n_dropped = n_before - len(trades)
    if n_dropped > 0:
        bounds = f"[{min_gross_pct}, {max_gross_pct}]"
        print(f"  [cutoff] gross_pct 범위 {bounds}% 밖 매매 {n_dropped}건 제외 "
              f"(액면분할/병합 의심)")

    # 매매 DataFrame
    df = pd.DataFrame([{
        "entry_date": t.entry_date,
        "exit_date":  t.exit_date,
        "code":       t.code,
        "net_pct":    t.net_pct,
    } for t in trades])
    df["entry_date"] = pd.to_datetime(df["entry_date"], format="%Y%m%d", errors="coerce")
    df["exit_date"]  = pd.to_datetime(df["exit_date"],  format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["entry_date", "exit_date"]).sort_values("entry_date").reset_index(drop=True)

    if df.empty:
        return None

    # 모든 영업일 (모든 entry + exit 의 합집합)
    all_dates = sorted(set(df["entry_date"].tolist() + df["exit_date"].tolist()))

    cash = float(initial_capital)
    positions = []  # list of dict {exit_date, invested_value, net_pct}
    equity_curve = []
    n_skipped = 0
    util_sum = 0.0   # 일별 자본 가동률 누적
    days_recorded = 0

    for date in all_dates:
        # 1. 오늘 청산할 포지션
        remaining = []
        for p in positions:
            if p["exit_date"] <= date:
                cash += p["invested_value"] * (1 + p["net_pct"] / 100)
            else:
                remaining.append(p)
        positions = remaining

        # 2. 오늘 새 진입 (entry_date == date)
        todays = df[df["entry_date"] == date]
        for _, row in todays.iterrows():
            slots_left = max_concurrent - len(positions)
            if slots_left <= 0:
                n_skipped += 1
                continue
            # 자본 분배: 가용 현금 / 빈 슬롯 (보수적 균등 분배)
            invest = cash / slots_left
            if invest <= 0:
                n_skipped += 1
                continue
            positions.append({
                "exit_date": row["exit_date"],
                "invested_value": invest,
                "net_pct": row["net_pct"],
            })
            cash -= invest

        # 3. 일별 equity 기록 (현금 + 미실현 진입가치)
        invested = sum(p["invested_value"] for p in positions)
        equity = cash + invested
        equity_curve.append((date, equity))
        if equity > 0:
            util_sum += invested / equity
            days_recorded += 1

    # 잔여 포지션은 마지막 시점에 미실현 그대로 (보수적)

    eq = pd.DataFrame(equity_curve, columns=["date", "equity"]).sort_values("date")
    eq["daily_return"] = eq["equity"].pct_change()
    final_eq = float(eq["equity"].iloc[-1])

    days_span = (eq["date"].max() - eq["date"].min()).days
    years = max(days_span / 365.25, 1/252)

    total_return = (final_eq / initial_capital - 1) * 100
    cagr = ((final_eq / initial_capital) ** (1/years) - 1) * 100

    peak = eq["equity"].cummax()
    dd = (eq["equity"] - peak) / peak * 100
    capital_mdd = float(dd.min())

    daily = eq["daily_return"].dropna()
    sharpe = (daily.mean() / daily.std() * math.sqrt(252)
              if daily.std() > 0 else 0.0)
    util_avg = (util_sum / days_recorded * 100) if days_recorded else 0.0

    return {
        "initial":         initial_capital,
        "final":           round(final_eq, 0),
        "total_ret_pct":   round(total_return, 2),
        "cagr_pct":        round(cagr, 2),
        "real_mdd_pct":    round(capital_mdd, 2),
        "real_sharpe":     round(sharpe, 2),
        "util_avg_pct":    round(util_avg, 1),
        "skipped":         n_skipped,
        "n_trades":        len(df),
        "years":           round(years, 2),
    }
