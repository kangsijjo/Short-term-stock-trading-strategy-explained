"""
백테스트 결과를 trades_history.csv 로 저장 — AI 학습용.

컬럼:
  date         : signal_date (T) — 신호 발생일 (entry_date 의 직전 영업일)
  code         : 종목 코드
  entry_date   : 진입일 (T+1)
  exit_date    : 청산일 (T+40)
  yield_pct    : net_pct (수수료 차감 수익률)
  exit_reason  : hold_exit / stop_loss / trailing_stop / time_stop

ai_trainer.py 가 date 컬럼 기준으로 historical_features.csv 와 merge.
"""

import os
import csv

from strategies.daily_loader import load_macro_daily, default_costs, filter_universe
from strategies.high_with_filters import HighWithFiltersStrategy


def main():
    print("=== trades_history.csv 생성 ===\n")
    df = load_macro_daily()
    df = filter_universe(df)
    df["date"] = df["date"].astype(str)
    df["code"] = df["code"].astype(str).str.zfill(6)
    costs = default_costs()

    strat = HighWithFiltersStrategy(
        lookback_days=500, holding_days=40,
        use_market_filter=True, use_volume_filter=False,
        name="h500_40_MKT",
    )
    trades = strat.backtest(df, costs)
    print(f"[backtest] {len(trades)} 매매")

    # 종목별 영업일 리스트 (signal_date = entry_date 직전 영업일 추정용)
    code_dates = {}
    for code, g in df.groupby("code"):
        code_dates[code] = sorted(g["date"].tolist())

    def signal_date_of(code, entry_date):
        dates = code_dates.get(code, [])
        try:
            idx = dates.index(entry_date)
            if idx > 0:
                return dates[idx - 1]
        except ValueError:
            pass
        return entry_date  # fallback

    rows = []
    for t in trades:
        sig_date = signal_date_of(t.code, t.entry_date)
        rows.append({
            "date": sig_date,
            "code": t.code,
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "yield_pct": round(t.net_pct, 4),
            "exit_reason": t.exit_reason,
        })

    out = "./trades_history.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date","code","entry_date","exit_date","yield_pct","exit_reason"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[saved] {out}, {len(rows)} 행")

    # 통계
    wins = sum(1 for r in rows if r["yield_pct"] > 0)
    losses = len(rows) - wins
    print(f"  승: {wins} ({wins/len(rows)*100:.1f}%)")
    print(f"  패: {losses} ({losses/len(rows)*100:.1f}%)")


if __name__ == "__main__":
    main()
