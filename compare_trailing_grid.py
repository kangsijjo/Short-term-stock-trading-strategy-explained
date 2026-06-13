"""
Trailing stop 폭 그리드 검색.

원본 + 5가지 trailing 폭 비교 (activate=+10% 고정).
"""

import time
from collections import Counter

from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_with_filters import HighWithFiltersStrategy
from capital_simulator import simulate_capital


GRID = [
    ("Trailing -20%",        dict(trailing_peak_pct=-20.0, trailing_activate_pct=10.0)),
    ("Trailing -25%",        dict(trailing_peak_pct=-25.0, trailing_activate_pct=10.0)),
    ("Trailing -30%",        dict(trailing_peak_pct=-30.0, trailing_activate_pct=10.0)),
]


def evaluate(label, opts, df, costs):
    t0 = time.time()
    strat = HighWithFiltersStrategy(
        lookback_days=500, holding_days=40,
        use_market_filter=True, use_volume_filter=False,
        name=f"h500_40_MKT_{label}",
        **opts,
    )
    trades = strat.backtest(df, costs)
    elapsed = time.time() - t0
    cap = simulate_capital(trades, initial_capital=10_000_000,
                            max_concurrent=10)  # [fix] -30 컷오프 제거 — CA필터가 액면분할 처리 or {}
    if not cap:
        return None
    net_pcts = [t.net_pct for t in trades]
    wins = [p for p in net_pcts if p > 0]
    losses = [p for p in net_pcts if p <= 0]
    win_rate = len(wins) / len(net_pcts) * 100 if net_pcts else 0
    avg_net = sum(net_pcts) / len(net_pcts) if net_pcts else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    reasons = Counter(t.exit_reason for t in trades)
    return {
        "label": label, "n_trades": len(trades), "elapsed": elapsed,
        "cagr_pct": cap.get("cagr_pct"),
        "real_mdd_pct": cap.get("real_mdd_pct"),
        "real_sharpe": cap.get("real_sharpe"),
        "win_rate_pct": win_rate, "avg_net_pct": avg_net,
        "avg_win_pct": avg_win, "avg_loss_pct": avg_loss,
        "reasons": dict(reasons),
    }


def main():
    print("=== Trailing 폭 그리드 검색 ===\n")
    df = load_macro_daily()
    costs = default_costs()
    print(f"[data] {df['code'].nunique()} 종목, {df['date'].nunique()} 영업일\n")

    results = []
    for label, opts in GRID:
        r = evaluate(label, opts, df, costs)
        if r:
            results.append(r)
            print(f"  {label:<25} → trades={r['n_trades']:>5,}, CAGR={r['cagr_pct']:>+7.2f}%, "
                  f"MDD={r['real_mdd_pct']:>+6.2f}%, Sharpe={r['real_sharpe']:>5.2f}, "
                  f"승률={r['win_rate_pct']:>5.1f}% ({r['elapsed']:.0f}s)", flush=True)

    print("\n\n" + "=" * 95)
    print("                              CAGR        MDD     Sharpe   승률    평균수익   승평균  패평균  매매수")
    print("=" * 95)
    for r in results:
        print(f"  {r['label']:<22}{r['cagr_pct']:>+8.2f}%  {r['real_mdd_pct']:>+6.2f}%  {r['real_sharpe']:>5.2f}  "
              f"{r['win_rate_pct']:>5.1f}%  {r['avg_net_pct']:>+6.2f}%  "
              f"{r['avg_win_pct']:>+6.2f}  {r['avg_loss_pct']:>+6.2f}  {r['n_trades']:>5,}")
    print("=" * 95)

    if results:
        best_sharpe = max(results, key=lambda r: r["real_sharpe"])
        best_cagr = max(results, key=lambda r: r["cagr_pct"])
        best_mdd = min(results, key=lambda r: abs(r["real_mdd_pct"]))
        print(f"\n  Best Sharpe: {best_sharpe['label']}  ({best_sharpe['real_sharpe']:.2f})")
        print(f"  Best CAGR:   {best_cagr['label']}  ({best_cagr['cagr_pct']:+.2f}%)")
        print(f"  Best MDD:    {best_mdd['label']}  ({best_mdd['real_mdd_pct']:.2f}%)")


if __name__ == "__main__":
    main()
