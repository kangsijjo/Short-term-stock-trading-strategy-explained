"""
청산 룰 비교 백테스트.

시나리오 4가지:
  A. 원본 (만기만)
  B. + 하드 손절 -15%
  C. + Trailing peak -15% (+10% 도달 후 활성화)
  D. + 둘 다

각 시나리오의 CAGR / MDD / Sharpe / 승률 / 평균 손익 비교.
"""

import time
from collections import Counter

from strategies.daily_loader import load_macro_daily, default_costs
from strategies.high_with_filters import HighWithFiltersStrategy
from capital_simulator import simulate_capital


SCENARIOS = {
    "A. 원본 (만기만)":                dict(),
    "B. + 하드 손절 -15%":             dict(stop_loss_pct=-15.0),
    "C. + Trailing peak -15% (+10%)":  dict(trailing_peak_pct=-15.0, trailing_activate_pct=10.0),
    "D. + 둘 다":                       dict(stop_loss_pct=-15.0, trailing_peak_pct=-15.0, trailing_activate_pct=10.0),
}


def main():
    print("=== 청산 룰 비교 백테스트 ===\n")
    df = load_macro_daily()
    costs = default_costs()
    print(f"[data] {df['code'].nunique()} 종목, {df['date'].nunique()} 영업일\n")

    results = []
    for label, opts in SCENARIOS.items():
        print(f"\n--- {label} ---")
        t0 = time.time()
        strat = HighWithFiltersStrategy(
            lookback_days=500, holding_days=40,
            use_market_filter=True, use_volume_filter=False,
            name=f"h500_40_MKT_{label[0]}",
            **opts,
        )
        trades = strat.backtest(df, costs)
        elapsed = time.time() - t0
        print(f"  trades: {len(trades)} ({elapsed:.1f}s)")

        # exit_reason 분포
        reasons = Counter(t.exit_reason for t in trades)
        print(f"  exit_reasons: {dict(reasons)}")

        cap = simulate_capital(trades, initial_capital=10_000_000,
                                max_concurrent=10)  # [fix] -30 컷오프 제거 — CA필터가 액면분할 처리 or {}
        if not cap:
            print("  [경고] simulate_capital 결과 없음")
            continue

        # 평균 손익
        net_pcts = [t.net_pct for t in trades]
        avg_net = sum(net_pcts) / len(net_pcts) if net_pcts else 0
        wins = [p for p in net_pcts if p > 0]
        losses = [p for p in net_pcts if p <= 0]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        win_rate = len(wins) / len(net_pcts) * 100 if net_pcts else 0

        result = {
            "label": label,
            "n_trades": len(trades),
            "final": cap.get("final"),
            "total_ret_pct": cap.get("total_ret_pct"),
            "cagr_pct": cap.get("cagr_pct"),
            "real_mdd_pct": cap.get("real_mdd_pct"),
            "real_sharpe": cap.get("real_sharpe"),
            "win_rate_pct": win_rate,
            "avg_net_pct": avg_net,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "reasons": dict(reasons),
        }
        results.append(result)

        print(f"  CAGR: {result['cagr_pct']:+.2f}%/년")
        print(f"  MDD:  {result['real_mdd_pct']:.2f}%")
        print(f"  Sharpe: {result['real_sharpe']:.2f}")
        print(f"  승률: {win_rate:.1f}%  평균 수익: {avg_net:+.2f}%  (승 +{avg_win:.2f} / 패 {avg_loss:.2f})")

    # 요약 표
    print("\n\n" + "=" * 90)
    print("                                  CAGR      MDD     Sharpe   승률    평균수익   매매수")
    print("=" * 90)
    for r in results:
        print(f"  {r['label']:<35}{r['cagr_pct']:>+7.2f}%  {r['real_mdd_pct']:>+6.2f}%  {r['real_sharpe']:>5.2f}   {r['win_rate_pct']:>5.1f}%  {r['avg_net_pct']:>+6.2f}%  {r['n_trades']:>5,}")
    print("=" * 90)

    # 베스트 sharpe / 베스트 mdd
    if results:
        best_sharpe = max(results, key=lambda r: r["real_sharpe"])
        best_mdd = min(results, key=lambda r: abs(r["real_mdd_pct"]))
        best_cagr = max(results, key=lambda r: r["cagr_pct"])
        print(f"\n  Best Sharpe: {best_sharpe['label']}  ({best_sharpe['real_sharpe']:.2f})")
        print(f"  Best MDD:    {best_mdd['label']}  ({best_mdd['real_mdd_pct']:.2f}%)")
        print(f"  Best CAGR:   {best_cagr['label']}  ({best_cagr['cagr_pct']:+.2f}%)")


if __name__ == "__main__":
    main()
