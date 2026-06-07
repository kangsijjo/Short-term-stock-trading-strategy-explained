"""
앙상블 가능성 검증 — high_500d_h40 와 high_252d_h40 의 신호 관계.

가설: 500일 신고가는 252일 신고가의 부분집합.
검증: (code, entry_date) 기준 교집합 비율.
"""

import config
from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_52w import FiftyTwoWeekHighStrategy


def main():
    df = load_macro_daily()
    costs = default_costs()

    s500 = FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40,
                                      min_trading_value=3_000_000_000,
                                      name="h500_40")
    s252 = FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40,
                                      min_trading_value=3_000_000_000,
                                      name="h252_40")

    t500 = s500.backtest(df, costs)
    t252 = s252.backtest(df, costs)

    keys_500 = set((t.code, t.entry_date) for t in t500)
    keys_252 = set((t.code, t.entry_date) for t in t252)

    print(f"=== 앙상블 신호 관계 검증 ===\n")
    print(f"high_500d_h40 신호: {len(keys_500):,} (n_trades {len(t500):,})")
    print(f"high_252d_h40 신호: {len(keys_252):,} (n_trades {len(t252):,})")
    print()
    print(f"교집합 (둘 다 신호): {len(keys_500 & keys_252):,}")
    print(f"  500 의 몇 % 가 252 에도 있나: "
          f"{len(keys_500 & keys_252) / max(len(keys_500), 1) * 100:.1f}%")
    print(f"  252 의 몇 % 가 500 에도 있나: "
          f"{len(keys_500 & keys_252) / max(len(keys_252), 1) * 100:.1f}%")
    print()
    print(f"500 만 (252 에 없음): {len(keys_500 - keys_252):,}")
    print(f"252 만 (500 에 없음): {len(keys_252 - keys_500):,}")
    print()
    print(f"=== 결론 ===")
    pct = len(keys_500 & keys_252) / max(len(keys_500), 1) * 100
    if pct >= 95:
        print(f"  high_500d_h40 ⊂ high_252d_h40 거의 완전 (>={pct:.0f}%)")
        print(f"  → 앙상블 = high_500d_h40 자체. 새 정보 X.")
    else:
        print(f"  부분 관계 (h500 의 {pct:.0f}% 만 h252 와 겹침)")
        print(f"  → 앙상블 가능성 있음. 결과 다를 수 있음.")


if __name__ == "__main__":
    main()
