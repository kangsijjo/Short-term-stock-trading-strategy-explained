"""
Trailing 세밀 튜닝 — sweet spot 확인.
1) 폭 세밀화: -22, -24, -25, -26, -28 (activate +10 고정)
2) 활성화 임계값: -25% 고정 + activate +5, +15, +20
"""

import time
from collections import Counter

from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_with_filters import HighWithFiltersStrategy
from capital_simulator import simulate_capital


GRID = [
    ("Trail -22% / act +10%", dict(trailing_peak_pct=-22.0, trailing_activate_pct=10.0)),
    ("Trail -24% / act +10%", dict(trailing_peak_pct=-24.0, trailing_activate_pct=10.0)),
    ("Trail -25% / act +10%", dict(trailing_peak_pct=-25.0, trailing_activate_pct=10.0)),
    ("Trail -26% / act +10%", dict(trailing_peak_pct=-26.0, trailing_activate_pct=10.0)),
    ("Trail -28% / act +10%", dict(trailing_peak_pct=-28.0, trailing_activate_pct=10.0)),
    ("Trail -25% / act  +5%", dict(trailing_peak_pct=-25.0, trailing_activate_pct=5.0)),
    ("Trail -25% / act +15%", dict(trailing_peak_pct=-25.0, trailing_activate_pct=15.0)),
    ("Trail -25% / act +20%", dict(trailing_peak_pct=-25.0, trailing_activate_pct=20.0)),
]


def evaluate(label, opts, df, costs):
    t0 = time.time()
    strat = HighWithFiltersStrategy(
        lookback_days=500, holding_days=40,
        use_market_filter=True, use_volume_filter=False,
        name=label, **opts,
    )
    trades = strat.backtest(df, costs)
    cap = simulate_capital(trades, initial_capital=10_000_000,
                            max_concurrent=10)  # [fix] -30 컷오프 제거 — CA필터가 액면분할 처리 or {}
    if not cap:
        return None
    return {
        "label": label, "n_trades": len(trades),
        "elapsed": time.time() - t0,
        "cagr": cap.get("cagr_pct"),
        "mdd": cap.get("real_mdd_pct"),
        "sharpe": cap.get("real_sharpe"),
    }


def main():
    print("=== Trailing 세밀 튜닝 ===\n", flush=True)
    df = load_macro_daily()
    costs = default_costs()
    print(f"[data] {df['code'].nunique()} 종목\n", flush=True)

    results = []
    for label, opts in GRID:
        r = evaluate(label, opts, df, costs)
        if r:
            results.append(r)
            print(f"  {label:<24} → CAGR={r['cagr']:>+7.2f}%, MDD={r['mdd']:>+6.2f}%, "
                  f"Sharpe={r['sharpe']:>5.2f} ({r['elapsed']:.0f}s)", flush=True)

    print("\n" + "=" * 70)
    for r in sorted(results, key=lambda x: -x["sharpe"]):
        print(f"  {r['label']:<24} CAGR {r['cagr']:>+7.2f}%  MDD {r['mdd']:>+6.2f}%  Sharpe {r['sharpe']:>5.2f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
