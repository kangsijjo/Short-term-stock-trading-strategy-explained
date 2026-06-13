"""
실전 신호 감지 — 메인 전략 high_500d_h40_MKT.

매일 평일 장 마감 후 실행:
  python live_signal.py

기능:
  1. macro_data/daily/ 의 일별 데이터 로드
  2. 가장 최근 영업일 기준 h500_40_MKT 신호 검사:
     - 종가 > 500일 신고가 (lookback=500)
     - 시장 강세 게이트 (전체 평균 change_pct 의 60일 MA > 0)
     - 거래대금 >= 30억 (백테스트와 동일 기준)
     - ETF/우선주/스팩 제외
  3. 신호 발생 종목 → 콘솔 출력 + paper_signals.csv 적재 (멱등)

저장:
  paper_signals.csv : 누적 신호 (signal_date, code, name, entry_price, target_exit_date)

실전 시 사용자가 다음날 시가 매수, 40일 후 종가 매도.
paper_trades.py 가 보유 포지션 평가 + 손익 추적 (별도 모듈).
"""

import os
import sys
import csv
from datetime import datetime
import pandas as pd

import config  # .env

from strategies.daily_loader import load_macro_daily
from strategies.high_with_filters import HighWithFiltersStrategy

try:
    from build_name_cache import load_name_cache
except ImportError:
    def load_name_cache():
        return {}


SIGNALS_CSV = "./paper_signals.csv"          # 메인 (high_500d_h40_MKT)
SIGNALS_CSV_SIMPLE = "./paper_signals_simple.csv"  # 대안 (high_500d_h40 단순)

# ETF/우선주 제외 prefix
ETF_PREFIXES = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "HANARO",
                "SOL ", "ACE ", "PLUS ", "RISE ", "1Q ", "WON ")


def is_excluded(name, code):
    if not name or not code:
        return True
    if name.startswith(ETF_PREFIXES):
        return True
    if name.endswith(("우", "우B")) or "우선주" in name or "스팩" in name:
        return True
    if len(code) == 6 and code.startswith("5"):
        return True
    return False


def load_existing_signals():
    """기존 paper_signals.csv 로 (signal_date, code) 집합 → 멱등성."""
    if not os.path.exists(SIGNALS_CSV):
        return set()
    df = pd.read_csv(SIGNALS_CSV, dtype={"code": str})
    return set(zip(df["signal_date"].astype(str), df["code"].astype(str).str.zfill(6)))


def append_signals(new_rows):
    """신호 행을 paper_signals.csv 에 append (헤더 없으면 생성)."""
    file_exists = os.path.exists(SIGNALS_CSV)
    fields = ["signal_date", "code", "name", "entry_price_close",
              "target_exit_date", "lookback_high", "market_strong"]
    with open(SIGNALS_CSV, "a" if file_exists else "w",
              newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for r in new_rows:
            writer.writerow(r)


def detect_signals_today(df, n_lookback_days=500, n_market_ma=60,
                          min_trading_value=3_000_000_000):
    # [fix] 1_000_000_000(10억) → 3_000_000_000(30억).
    # 백테스트/walk-forward 에서 검증한 전략(high_500d_h40_MKT)은 30억 필터 기준.
    # 10억이면 검증 안 된 더 넓은 유니버스로 운용하게 됨.
    """가장 최근 영업일에 대해 h500_40_MKT 신호 검사.

    Returns: list of dict (signal rows)
    """
    df = df.sort_values(["code", "date"]).copy()

    # 종가가 직전 lookback 일 신고가 돌파?
    df["prev_high"] = (df.groupby("code")["high"]
                       .shift(1).rolling(n_lookback_days,
                                         min_periods=n_lookback_days).max())

    # 시장 강세 게이트 (시장 평균 change_pct 의 N일 MA > 0)
    mkt_avg = df.groupby("date")["change_pct"].mean()
    mkt_ma = mkt_avg.rolling(n_market_ma, min_periods=n_market_ma).mean()
    mkt_strong_map = (mkt_ma > 0).to_dict()
    df["mkt_strong"] = df["date"].map(mkt_strong_map).fillna(False).astype(bool)

    # 가장 최근 영업일만 선별
    last_date = df["date"].max()
    today_df = df[df["date"] == last_date].copy()

    # 종목명 보강: macro_data 의 name 비어있으면 name_cache fallback
    name_cache = load_name_cache()
    def _resolve_name(r):
        nm = str(r.get("name", "") or "").strip()
        if not nm:
            nm = name_cache.get(str(r["code"]).zfill(6), "")
        return nm
    today_df["_name"] = today_df.apply(_resolve_name, axis=1)

    # 신호 조건
    signaled = today_df[
        (today_df["close"] > today_df["prev_high"]) &
        (today_df["mkt_strong"]) &
        (today_df["trading_value"] >= min_trading_value)
    ].copy()

    # ETF/우선주 제외 (보강된 _name 사용)
    signaled = signaled[~signaled.apply(
        lambda r: is_excluded(r["_name"], r["code"]), axis=1)]

    # 40 영업일 후 청산 목표 — 단순화로 60 달력일 더함 (실제 청산일 = 거래일 계산 후)
    rows = []
    for _, r in signaled.iterrows():
        rows.append({
            "signal_date": last_date,
            "code": str(r["code"]).zfill(6),
            "name": r["_name"],
            "entry_price_close": float(r["close"]),  # 다음날 시가가 실제 진입가
            "target_exit_date": "+40 영업일",
            "lookback_high": float(r.get("prev_high", 0) or 0),
            "market_strong": True,
        })
    return rows, last_date


def main():
    print(f"=== Paper Trading 신호 감지 ===")
    print(f"전략: high_500d_h40_MKT (메인)")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    df = load_macro_daily()
    print(f"\n[data] {df['code'].nunique()} 종목, "
          f"{df['date'].nunique()} 영업일, "
          f"최신 {df['date'].max()}")

    signals, today = detect_signals_today(df)

    # 기존 신호와 비교 — 중복 제거
    existing = load_existing_signals()
    new = [s for s in signals
           if (s["signal_date"], s["code"]) not in existing]

    print(f"\n[signal] {today} 신호 종목: {len(signals)} 건")
    print(f"          새 신호 (중복 제외): {len(new)} 건")

    if not signals:
        print("\n  오늘 신호 없음. 시장 약세 또는 신고가 종목 없음.")
        return

    # 콘솔 출력
    print(f"\n{'='*80}")
    print(f"  Code     | Name                       | Close     | 500d High")
    print(f"{'-'*80}")
    for s in signals[:30]:
        print(f"  {s['code']} | {s['name'][:25]:25} | {s['entry_price_close']:>9,.0f} | {s['lookback_high']:>9,.0f}")

    if len(signals) > 30:
        print(f"  ... 외 {len(signals)-30}개")

    # 멱등 append (signal_date + code 중복 제거)
    existing = load_existing_signals()
    new = [s for s in signals
           if (str(s["signal_date"]), str(s["code"]).zfill(6)) not in existing]
    if new:
        append_signals(new)
        print(f"\n  → {len(new)}개 신규 신호 → {SIGNALS_CSV}")
    else:
        print(f"\n  → 모두 기존 신호와 중복 (멱등)")


if __name__ == "__main__":
    main()
