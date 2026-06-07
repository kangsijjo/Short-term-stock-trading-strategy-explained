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


def collect(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    yyyy_mm = f"{date_str[:4]}-{date_str[4:6]}"
    out_dir = f"{US_DIR}/{yyyy_mm}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{date_str}.csv"

    if os.path.exists(out_path):
        print(f"[us_market] 이미 있음, 스킵: {out_path}")
        return

    end = datetime.now()
    start = end - timedelta(days=10)  # 여유분

    rows = []
    for name, ticker in SYMBOLS.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df.empty:
                print(f"  [warn] {ticker}: 빈 데이터")
                continue
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else last
            close = float(last["Close"].iloc[0] if hasattr(last["Close"], "iloc") else last["Close"])
            prev_close = float(prev["Close"].iloc[0] if hasattr(prev["Close"], "iloc") else prev["Close"])
            change_pct = (close / prev_close - 1) * 100
            us_date = str(df.index[-1].date()).replace("-", "")
            rows.append({
                "symbol": name, "ticker": ticker, "date": us_date,
                "close": round(close, 4),
                "prev_close": round(prev_close, 4),
                "change_pct": round(change_pct, 3),
            })
            print(f"  {name:4} {ticker:6}: {change_pct:+.2f}% (close {close:,.2f})")
        except Exception as e:
            print(f"  [warn] {ticker}: {e}")

    if not rows:
        print(f"[us_market] 빈 결과")
        return

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol","ticker","date","close","prev_close","change_pct"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[us_market] {len(rows)} 지표 저장: {out_path}")


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
