"""
paper_signals.csv 초기 시드 — 과거 3년치 h500_40_MKT 신호로 채움.

목적: paper_tracker.py 가 즉시 의미 있는 결과 (CAGR, MDD 등) 를 보여줄 수 있도록
      과거 신호 누적 데이터를 만든다.
"""

import os
import csv
import config
from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_with_filters import HighWithFiltersStrategy

SIGNALS_CSV = "./paper_signals.csv"


def main():
    if os.path.exists(SIGNALS_CSV):
        ans = input(f"{SIGNALS_CSV} 이미 있음. 덮어쓸까요? [y/N]: ")
        if ans.lower() != "y":
            print("취소.")
            return

    print("=== Paper Signals 시드 (과거 3년치) ===")
    df = load_macro_daily()
    print(f"[data] {df['code'].nunique()} 종목, {df['date'].nunique()} 영업일")

    strat = HighWithFiltersStrategy(
        lookback_days=500, holding_days=40,
        use_market_filter=True, use_volume_filter=False,
        name="high_500d_h40_MKT",
    )
    trades = strat.backtest(df, default_costs())
    print(f"[signals] 누적 신호: {len(trades)} 건")

    # 종목명 lookup
    code_name = df.groupby("code")["name"].first().to_dict() if "name" in df.columns else {}

    fields = ["signal_date", "code", "name", "entry_price_close",
              "target_exit_date", "lookback_high", "market_strong"]
    with open(SIGNALS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in trades:
            # signal_date 는 entry_date 의 직전 영업일이지만, 단순화로 entry_date 사용
            writer.writerow({
                "signal_date": t.entry_date,  # 약간 단순화
                "code": t.code,
                "name": code_name.get(t.code, ""),
                "entry_price_close": t.entry_price,
                "target_exit_date": t.exit_date,
                "lookback_high": 0,
                "market_strong": True,
            })
    print(f"[saved] {len(trades)} 건 → {SIGNALS_CSV}")


if __name__ == "__main__":
    main()
