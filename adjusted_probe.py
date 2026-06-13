"""
수정주가 검증 — CA필터(find_corporate_action_dates)가 감지한 기업행위를
pykrx 수정주가(adjusted=True)와 대조해 오탐/미탐 점검.

실행: python adjusted_probe.py [확인할 종목 수, 기본 10]
주 1회 정도 수동 실행 권장. (전 종목 X — 표본 검증)
"""

import sys
import time
from datetime import datetime, timedelta

import config  # noqa: F401
import pandas as pd
from pykrx import stock

from strategies.daily_loader import load_macro_daily
from strategies._swing_base import find_corporate_action_dates


def main():
    n_check = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    df = load_macro_daily()
    ca = find_corporate_action_dates(df)
    if not ca:
        print("감지된 기업행위 없음.")
        return

    # 최근 발생일 순으로 표본 추출
    flat = [(code, d) for code, ds in ca.items() for d in ds]
    flat.sort(key=lambda x: x[1], reverse=True)
    sample = flat[:n_check]
    print(f"기업행위 감지 총 {len(flat)}건 — 최근 {len(sample)}건 대조\n")

    ok, bad = 0, 0
    for code, d in sample:
        try:
            dt = datetime.strptime(d, "%Y%m%d")
            s = (dt - timedelta(days=7)).strftime("%Y%m%d")
            e = (dt + timedelta(days=3)).strftime("%Y%m%d")
            adj = stock.get_market_ohlcv(s, e, code, adjusted=True)
            raw = stock.get_market_ohlcv(s, e, code, adjusted=False)
            time.sleep(0.5)
            if adj.empty or raw.empty:
                print(f"  {code} {d}: 데이터 없음 (상폐 가능)")
                continue
            # 해당일 전후 수정/원시 종가 비율 차이 → 기업행위면 두 시계열이 달라야 함
            diverge = not adj["종가"].equals(raw["종가"])
            mark = "✅ 확인" if diverge else "❌ 오탐 의심"
            if diverge:
                ok += 1
            else:
                bad += 1
            print(f"  {code} {d}: {mark}")
        except Exception as ex:
            print(f"  {code} {d}: 조회 실패 ({ex})")
    print(f"\n결과: 확인 {ok} / 오탐 의심 {bad}")
    if bad > ok:
        print("오탐이 많음 — _swing_base.find_corporate_action_dates 임계값(0.10) 점검 필요")


if __name__ == "__main__":
    main()
