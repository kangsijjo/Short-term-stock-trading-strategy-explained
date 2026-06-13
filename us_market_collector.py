"""
미국장 영향 분석용 — yfinance 로 미국 지수 + 섹터 ETF 수집.

매일 한국 장 시작 1시간 전 (08:00) 자동 실행.
실시간 X — 전일 마감 데이터. 그게 한국 09:00 매도 결정에 충분.

수집 지표:
  ^GSPC — S&P 500 (전체)
  ^IXIC — Nasdaq Composite (기술주)
  ^SOX  — 필라델피아 반도체 (KOSDAQ 반도체 종목 proxy)
  ^RUT  — Russell 2000 (소형주)
  ^VIX  — 공포지수
  XLK   — 테크 ETF
  XBI   — 바이오테크 ETF
  XLF   — 금융 ETF
  SMH   — 반도체 ETF

저장: db/us_market/YYYY-MM/YYYYMMDD.csv
"""

import os
import sys
import csv
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("[ERROR] yfinance 미설치.")
    print("  설치: pip install yfinance")
    sys.exit(1)

import config

US_DIR = "./db/us_market"
os.makedirs(US_DIR, exist_ok=True)

SYMBOLS = {
    "SPX": "^GSPC",      # S&P 500 — KOSPI/KOSDAQ 전체 proxy
    "NDX": "^IXIC",      # Nasdaq — 기술주
    "SOX": "^SOX",       # 필라델피아 반도체 — 반도체 종목 proxy
    "RUT": "^RUT",       # Russell 2000 — 소형주
    "VIX": "^VIX",       # 공포지수
    "XLK": "XLK",        # 테크 ETF
    "XBI": "XBI",        # 바이오테크 ETF
    "XLF": "XLF",        # 금융 ETF
    "SMH": "SMH",        # 반도체 ETF (대안)
}


def _download_series(days=35):
    """심볼별 일별 종가 시계열 1회 다운로드 → {symbol: [(us_date, close), ...]}"""
    end = datetime.now()
    start = end - timedelta(days=days)
    out = {}
    for name, ticker in SYMBOLS.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df is None or df.empty:
                print(f"  [warn] {ticker}: 빈 데이터")
                continue
            close = df["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            out[name] = [(str(idx.date()).replace("-", ""), float(v))
                         for idx, v in close.items() if v == v]
        except Exception as e:
            print(f"  [warn] {ticker}: {e}")
    return out


def _save_for_date(series, kr_date):
    """KR 날짜 기준 '그 전 미국 마감' 행을 골라 저장. (과거 결측 백필 가능)"""
    out_dir = f"{US_DIR}/{kr_date[:4]}-{kr_date[4:6]}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{kr_date}.csv"
    if os.path.exists(out_path):
        return True
    rows = []
    for name, ser in series.items():
        past = [(d, c) for d, c in ser if d < kr_date]   # KR 일자 이전 미국 세션
        if len(past) < 2:
            continue
        (pd_, pc), (ld, lc) = past[-2], past[-1]
        rows.append({"symbol": name, "ticker": SYMBOLS[name], "date": ld,
                     "close": round(lc, 4), "prev_close": round(pc, 4),
                     "change_pct": round((lc / pc - 1) * 100, 3)})
    if not rows:
        print(f"[us_market] {kr_date}: 데이터 없음")
        return False
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "ticker", "date", "close",
                                          "prev_close", "change_pct"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[us_market] {kr_date}: {len(rows)} 지표 저장 (US {rows[0]['date']} 마감)")
    return True


def collect(date_str=None):
    """[2026-06-13 개편] 결측 우선: 최근 14영업일 결측을 먼저 채우고 오늘분 저장."""
    from gap_scan import recent_missing
    targets = recent_missing(US_DIR, lookback_bdays=14)
    if date_str and date_str not in targets:
        targets.append(date_str)
    if not targets:
        print("[us_market] 결측 없음 — 최신 상태")
        return
    print(f"[us_market] 대상 {len(targets)}일 (결측 우선): {targets}")
    series = _download_series()
    if not series:
        print("[us_market] 다운로드 실패")
        return
    for d in targets:
        _save_for_date(series, d)


def load_latest():
    """가장 최근 수집 결과 dict 반환: {symbol: change_pct}"""
    import glob
    files = sorted(glob.glob(f"{US_DIR}/*/*.csv"))
    if not files:
        return {}
    import pandas as pd
    df = pd.read_csv(files[-1], encoding="utf-8-sig")
    return {row["symbol"]: row["change_pct"] for _, row in df.iterrows()}


if __name__ == "__main__":
    collect()
