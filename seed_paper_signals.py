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

try:
    from build_name_cache import load_name_cache
except ImportError:
    def load_name_cache():
        return {}

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

    # 종목명 lookup: macro_data 의 name 우선, 비면 name_cache fallback
    code_name = {}
    if "name" in df.columns:
        code_name = {k: v for k, v in
                     df.groupby("code")["name"].first().to_dict().items()
                     if v and str(v).strip()}
    name_cache = load_name_cache()
    print(f"[name] macro_data 채움: {len(code_name)}, cache: {len(name_cache)}")

    def _resolve_name(code):
        return code_name.get(code) or name_cache.get(str(code).zfill(6), "")

    fields = ["signal_date", "code", "name", "entry_price_close",
              "target_exit_date", "lookback_high", "market_strong"]
    with open(SIGNALS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "signal_date": t.entry_date,
                "code": t.code,
                "name": _resolve_name(t.code),
                "entry_price_close": t.entry_price,
                "target_exit_date": t.exit_date,
                "lookback_high": 0,
                "market_strong": True,
            })

    # 통계: 채워진 name 개수
    filled = sum(1 for t in trades if _resolve_name(t.code))
    print(f"[saved] {len(trades)} 건 -> {SIGNALS_CSV}")
    print(f"[name]  name 채워진 신호: {filled} / {len(trades)}")


if __name__ == "__main__":
    main()
