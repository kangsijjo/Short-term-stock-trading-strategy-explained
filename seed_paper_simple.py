"""
paper_signals_simple.csv 시드 — high_500d_h40 (단순) 신호로.

옵션 C 병행 실험용: 시장 게이트 없는 단순 신고가 신호 누적.
1~2개월 후 high_500d_h40_MKT 와 비교.
"""

import os
import csv
import config
from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_52w import FiftyTwoWeekHighStrategy

SIGNALS_CSV = "./paper_signals_simple.csv"


def main():
    if os.path.exists(SIGNALS_CSV):
        ans = input(f"{SIGNALS_CSV} 이미 있음. 덮어쓸까요? [y/N]: ")
        if ans.lower() != "y":
            print("취소.")
            return

    print("=== Paper Signals (단순) 시드 ===")
    print("전략: high_500d_h40 (시장 게이트 없는 단순 신고가)")
    df = load_macro_daily()

    strat = FiftyTwoWeekHighStrategy(
        lookback_days=500, holding_days=40,
        min_trading_value=3_000_000_000,  # 30억 유동성 필터
        name="high_500d_h40",
    )
    trades = strat.backtest(df, default_costs())
    print(f"[signals] 누적 신호: {len(trades)} 건")

    code_name = df.groupby("code")["name"].first().to_dict() if "name" in df.columns else {}

    fields = ["signal_date", "code", "name", "entry_price_close",
              "target_exit_date", "lookback_high", "market_strong"]
    with open(SIGNALS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "signal_date": t.entry_date,
                "code": t.code,
                "name": code_name.get(t.code, ""),
                "entry_price_close": t.entry_price,
                "target_exit_date": t.exit_date,
                "lookback_high": 0,
                "market_strong": False,  # 단순 신호 = 시장 게이트 미적용
            })
    print(f"[saved] {len(trades)} 건 → {SIGNALS_CSV}")


if __name__ == "__main__":
    main()
