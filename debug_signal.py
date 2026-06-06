"""
신호 0건 진단 — 시장 게이트, 신고가, 거래대금 각 단계별로 종목 수 확인.
"""

import config
import pandas as pd
from strategies.daily_loader import load_macro_daily


def main():
    df = load_macro_daily()
    df = df.sort_values(["code", "date"]).copy()
    last_date = df["date"].max()
    print(f"=== 진단: {last_date} ===\n")

    # 1) 시장 평균 등락률 + 60일 MA
    mkt = df.groupby("date")["change_pct"].mean()
    mkt_ma60 = mkt.rolling(60, min_periods=60).mean()
    mkt_today = mkt.iloc[-1] if last_date in mkt.index else None
    mkt_ma_today = mkt_ma60.iloc[-1] if last_date in mkt_ma60.index else None
    print(f"[1] 시장 컨텍스트")
    print(f"    오늘 시장 평균 등락률: {mkt_today:.3f}%" if mkt_today is not None else "    오늘 데이터 없음")
    print(f"    60일 MA 시장 평균:     {mkt_ma_today:.3f}%" if mkt_ma_today is not None else "")
    if mkt_ma_today is not None:
        gate = "✅ ON (강세)" if mkt_ma_today > 0 else "❌ OFF (약세, 게이트로 신호 차단됨)"
        print(f"    시장 강세 게이트:      {gate}")

    # 2) 500일 신고가 돌파 (게이트 무관, raw count)
    df["prev_high"] = df.groupby("code")["high"].shift(1).rolling(500, min_periods=500).max()
    today_df = df[df["date"] == last_date].copy()
    breakouts = today_df[today_df["close"] > today_df["prev_high"]]
    print(f"\n[2] 500일 신고가 돌파 종목 (게이트 OFF, raw): {len(breakouts)} 건")
    if len(breakouts) > 0:
        cols = ["code", "name", "close", "prev_high", "trading_value"]
        print(breakouts[cols].head(10).to_string(index=False))

    # 3) 거래대금 필터
    liquid = breakouts[breakouts["trading_value"] >= 1_000_000_000]
    print(f"\n[3] + 거래대금 10억 이상: {len(liquid)} 건")

    # 4) 최종 (게이트 ON 시)
    if mkt_ma_today is not None and mkt_ma_today > 0:
        print(f"\n[4] 메인 전략 최종 신호 (게이트 + 거래대금): {len(liquid)} 건")
    else:
        print(f"\n[4] 시장 약세로 메인 전략 신호: 0 건 (정상)")

    # 5) 직전 30일 신호 발생 빈도 (참고)
    df["mkt_strong"] = df["date"].map((mkt_ma60 > 0).to_dict()).fillna(False).astype(bool)
    signal_mask = (
        (df["close"] > df["prev_high"]) &
        df["mkt_strong"] &
        (df["trading_value"] >= 1_000_000_000)
    )
    df["signal"] = signal_mask
    daily_counts = df.groupby("date")["signal"].sum().tail(30)
    print(f"\n[5] 직전 30 영업일 신호 발생 분포")
    print(f"    합계: {int(daily_counts.sum())} 건 (일평균 {daily_counts.mean():.1f} 건)")
    print(f"    0건인 날: {int((daily_counts == 0).sum())} / 30")
    nonzero = daily_counts[daily_counts > 0]
    if len(nonzero) > 0:
        print(f"    신호 있는 날 평균: {nonzero.mean():.1f} 건")


if __name__ == "__main__":
    main()
