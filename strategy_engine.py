"""
다중 전략 일괄 백테스트 + 비교.

실행: python strategy_engine.py

현재 등록된 전략:
  - gap_buy (전략 #4)

후속 전략 추가는 strategies/ 안에 새 클래스 + 아래 STRATEGIES 리스트에 추가.
"""

import config  # .env 로드
import time
import pandas as pd

from strategies.daily_loader import load_macro_daily, default_costs
from strategies.gap_buy import GapBuyStrategy
from strategies.momentum_5d import FiveDayMomentumStrategy
from strategies.breakout_5d import FiveDayBreakoutStrategy
from strategies.rsi_reversal import RsiReversalStrategy
from strategies.high_52w import FiftyTwoWeekHighStrategy
from strategies.volume_surge import VolumeSurgeStrategy
from strategies.high_with_filters import HighWithFiltersStrategy
from strategies.portfolio import PortfolioStrategy
from strategy_report import evaluate, print_comparison
from capital_simulator import simulate_capital


# ============================================================
# 등록 전략들 (각 전략 인스턴스화 + 파라미터 지정)
# ============================================================
STRATEGIES = [
    # 전략 #4 갭상승 매수 (전형적 momentum 가설 — 결과: 실패, mean reversion 신호)
    GapBuyStrategy(gap_min_pct=0.5, gap_max_pct=3.0,
                   min_trading_value=1_000_000_000, universe_top_n=30,
                   name="gap_up_buy"),

    # 전략 #4-B 갭하락 매수 (mean reversion 가설 — 갭상승 결과의 거울상)
    GapBuyStrategy(gap_min_pct=-3.0, gap_max_pct=-0.5,
                   min_trading_value=1_000_000_000, universe_top_n=30,
                   name="gap_down_buy"),

    # 전략 #8 5일 모멘텀
    FiveDayMomentumStrategy(top_n=20, holding_days=5),

    # 전략 #9 5일 신고가 돌파 + 거래량
    FiveDayBreakoutStrategy(lookback=5, vol_mult=2.0, holding_days=5),

    # 전략 #10 RSI 반전 (과매도)
    RsiReversalStrategy(rsi_period=14, rsi_threshold=30, holding_days=5),

    # 전략 #11 추세 패밀리 — high_NNd_holdM (lookback × holding 다양화)
    FiftyTwoWeekHighStrategy(lookback_days=60,  holding_days=10, name="high_60d_h10"),
    FiftyTwoWeekHighStrategy(lookback_days=120, holding_days=10, name="high_120d_h10"),
    FiftyTwoWeekHighStrategy(lookback_days=120, holding_days=20, name="high_120d_h20"),
    FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=10, name="high_252d_h10"),
    FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=20, name="high_252d_h20_base"),  # 기존 = 베이스
    FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="high_252d_h40"),
    FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="high_500d_h20"),
    FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40, name="high_500d_h40"),

    # 강화 변종 — high_500d_h40 베이스 + 시장 컨텍스트 + 거래량 필터
    HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                            use_market_filter=True, use_volume_filter=False,
                            name="high_500d_h40_MKT"),
    HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                            use_market_filter=False, use_volume_filter=True,
                            name="high_500d_h40_VOL"),
    HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                            use_market_filter=True, use_volume_filter=True,
                            name="high_500d_h40_MKT+VOL"),

    # 포트폴리오 결합 — 추세 권좋 3개 합집합
    PortfolioStrategy(
        strategies=[
            FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="_h252_40"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="_h500_20"),
            FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=40, name="_h500_40"),
        ],
        name="portfolio_trend3",
    ),

    # 비교용: 단일 베이스 (best 단일)
    # high_500d_h40 는 이미 위에 등록되어 있으므로 중복 X — 결과 표에서 직접 비교

    # 전략 #12 거래대금 급증
    VolumeSurgeStrategy(baseline_days=30, surge_mult=3.0, holding_days=1),

    # 추가 예정:
    # ClosingBetStrategy(...),           # 전략 #2 종가베팅 (분봉 필요)
    # ForeignChasingStrategy(...),       # 전략 #7
]


def main(start_date=None, end_date=None):
    print(f"=== 다중 전략 백테스트 ===")
    print(f"기간: {start_date or 'ALL'} ~ {end_date or 'ALL'}")
    print()

    # 1. 데이터 로드
    t0 = time.time()
    df = load_macro_daily(start_date=start_date, end_date=end_date)
    print(f"[data] {len(df):,} 행, "
          f"{df['code'].nunique()} 종목, "
          f"{df['date'].nunique()} 영업일 "
          f"({time.time()-t0:.1f}s 소요)")

    costs = default_costs()
    print(f"[cost] 총 비용 가정: {costs['total_pct']:.3f}% (KOSDAQ 기준)")
    print()

    # 2. 각 전략 백테스트
    results = []
    capital_results = []
    all_trades_map = {}
    for strat in STRATEGIES:
        t1 = time.time()
        print(f"[run ] {strat.name} ...", end=" ", flush=True)
        try:
            trades = strat.backtest(df, costs)
            all_trades_map[strat.name] = trades
            metrics = evaluate(trades, label=strat.name)
            results.append(metrics)
            print(f"{metrics['n_trades']:,} 매매 ({time.time()-t1:.1f}s)")
        except Exception as e:
            print(f"FAIL: {e}")

    # 3. 매매 단위 비교 리포트
    if results:
        print_comparison(results)

    # 4. 자본 단위 시뮬레이션 (max_concurrent=10, 초기 1천만원)
    print()
    print("=" * 100)
    print(" 자본 단위 시뮬레이션 (max_concurrent=10, 초기 1천만원)")
    print("=" * 100)
    cap_rows = []
    for strat in STRATEGIES:
        trades = all_trades_map.get(strat.name)
        if not trades:
            continue
        cap = simulate_capital(trades, initial_capital=10_000_000, max_concurrent=10)
        if cap is None:
            continue
        cap["name"] = strat.name
        cap_rows.append(cap)
    if cap_rows:
        cap_df = pd.DataFrame(cap_rows)[
            ["name", "n_trades", "skipped", "util_avg_pct",
             "total_ret_pct", "cagr_pct", "real_mdd_pct", "real_sharpe", "final"]
        ]
        cap_df["final"] = cap_df["final"].apply(lambda v: f"{int(v):,}")
        print(cap_df.to_string(index=False))
        print()
        print(" total_ret/cagr/mdd/sharpe = 진짜 자본 기준. util_avg = 평균 자본 가동률 (%).")
        print(" skipped = 슬롯 부족으로 놓친 신호 수.")


if __name__ == "__main__":
    import sys
    s = sys.argv[1] if len(sys.argv) >= 2 else None
    e = sys.argv[2] if len(sys.argv) >= 3 else None
    main(start_date=s, end_date=e)
