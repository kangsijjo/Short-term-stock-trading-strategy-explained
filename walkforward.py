"""
Walk-forward 검증 v2 — Multi-Split + portfolio_v2.

변경:
- 여러 train/OOS 분할 시점 시험 (50/50, 67/33, 75/25)
- portfolio_v2: high_500d_h40 (과적합) 제거, high_500d_h40_MKT (OOS 통과) 추가
- 평균 OOS CAGR + 견고성 점수 산출
"""

import pandas as pd
import config

from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_52w import FiftyTwoWeekHighStrategy
from strategies.high_with_filters import HighWithFiltersStrategy
from strategies.portfolio import PortfolioStrategy

from capital_simulator import simulate_capital


STRATEGIES = [
    # OOS 통과한 개별 전략
    FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="high_252d_h40"),
    FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="high_500d_h20"),
    HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                            use_market_filter=True, use_volume_filter=False,
                            name="high_500d_h40_MKT"),

    # 비교용 (과적합 확인된 베이스)
    FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40, name="high_500d_h40"),

    # 기존 portfolio (h252_40 + h500_20 + h500_40)
    PortfolioStrategy(
        strategies=[
            FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="_h252_40"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="_h500_20"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40, name="_h500_40"),
        ],
        name="portfolio_v1_trend3",
    ),

    # portfolio_v2 — h500_40 → h500_40_MKT 교체
    PortfolioStrategy(
        strategies=[
            FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="_v2_h252_40"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="_v2_h500_20"),
            HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                                    use_market_filter=True, use_volume_filter=False,
                                    name="_v2_h500_40_MKT"),
        ],
        name="portfolio_v2_3way",
    ),

    # portfolio_v3 — multi-split TOP 2 (h500_40_MKT + h252_40) 2-way 결합
    PortfolioStrategy(
        strategies=[
            HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                                    use_market_filter=True, use_volume_filter=False,
                                    name="_v3_h500_40_MKT"),
            FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="_v3_h252_40"),
        ],
        name="portfolio_v3_TOP2",
    ),

    # portfolio_v4 — h500_40 (OOS avg 60%) 까지 합친 3-way (v3 + h500_40)
    PortfolioStrategy(
        strategies=[
            HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                                    use_market_filter=True, use_volume_filter=False,
                                    name="_v4_h500_40_MKT"),
            FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="_v4_h252_40"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40, name="_v4_h500_40"),
        ],
        name="portfolio_v4_TOP3",
    ),
]


def cap_or_empty(trades, max_concurrent=10):
    if not trades:
        return {
            "n_trades": 0, "skipped": 0, "util_avg_pct": 0,
            "total_ret_pct": 0, "cagr_pct": 0,
            "real_mdd_pct": 0, "real_sharpe": 0,
            "final": 10_000_000,
        }
    cap = simulate_capital(trades, initial_capital=10_000_000,
                            max_concurrent=max_concurrent)
    return cap or {
        "n_trades": 0, "skipped": 0, "util_avg_pct": 0,
        "total_ret_pct": 0, "cagr_pct": 0,
        "real_mdd_pct": 0, "real_sharpe": 0,
        "final": 10_000_000,
    }


def main():
    df = load_macro_daily()
    all_dates = sorted(df["date"].unique())
    n = len(all_dates)
    costs = default_costs()

    print(f"=== Multi-Split Walk-Forward ===")
    print(f"  전체 기간: {all_dates[0]} ~ {all_dates[-1]} ({n} 영업일)")

    # 1) 전체 데이터로 모든 전략 백테스트 한 번 (lookback 보장)
    print(f"\n[setup] 모든 전략 전체 백테스트...")
    trades_by_strat = {}
    for strat in STRATEGIES:
        ts = strat.backtest(df, costs)
        trades_by_strat[strat.name] = ts
        print(f"  {strat.name:32s}: {len(ts):,} 매매")

    # 2) 여러 split 시점 시험
    splits = [
        (0.50, "50/50"),
        (0.67, "67/33"),
        (0.75, "75/25"),
    ]
    rows = []
    for ratio, label in splits:
        train_end_idx = int(n * ratio)
        train_end = all_dates[train_end_idx]
        oos_start = all_dates[train_end_idx + 1] if train_end_idx + 1 < n else all_dates[-1]
        print(f"\n=== Split {label} (train_end={train_end}, OOS_start={oos_start}) ===")
        for strat_name, all_trades in trades_by_strat.items():
            train_trades = [t for t in all_trades if str(t.entry_date) <= train_end]
            oos_trades = [t for t in all_trades if str(t.entry_date) > train_end]
            train_cap = cap_or_empty(train_trades)
            oos_cap = cap_or_empty(oos_trades)
            rows.append({
                "split": label,
                "name": strat_name,
                "train_n": train_cap["n_trades"],
                "OOS_n": oos_cap["n_trades"],
                "train_CAGR": train_cap["cagr_pct"],
                "OOS_CAGR": oos_cap["cagr_pct"],
                "OOS_mdd": oos_cap["real_mdd_pct"],
                "OOS_sharpe": oos_cap["real_sharpe"],
            })

    out = pd.DataFrame(rows)

    # 3) 분할별 결과 표
    print("\n" + "=" * 115)
    print(" Multi-Split 결과 (전략 × split)")
    print("=" * 115)
    print(out.to_string(index=False))

    # 4) 전략별 OOS 평균 + 견고성 점수
    print("\n" + "=" * 115)
    print(" 전략별 OOS 견고성 (평균/최소/최대)")
    print("=" * 115)
    grp = out.groupby("name").agg(
        avg_OOS_CAGR=("OOS_CAGR", "mean"),
        min_OOS_CAGR=("OOS_CAGR", "min"),
        max_OOS_CAGR=("OOS_CAGR", "max"),
        avg_train_CAGR=("train_CAGR", "mean"),
        avg_OOS_sharpe=("OOS_sharpe", "mean"),
    ).round(2)
    grp["all_split_positive"] = (grp["min_OOS_CAGR"] > 0)
    # 정렬: 평균 OOS CAGR 큰 순
    grp = grp.sort_values("avg_OOS_CAGR", ascending=False)
    print(grp.to_string())

    print()
    print(" 해석 ⭐:")
    print("  - all_split_positive=True + avg_OOS_CAGR ≥ 30%: 진짜 견고한 +EV 신호")
    print("  - all_split_positive=False: 어떤 split 에선 OOS 적자 — 운에 의존")
    print("  - avg_OOS_CAGR ≪ avg_train_CAGR: 과적합 강함")


if __name__ == "__main__":
    main()
