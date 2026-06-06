"""
일봉 통합 데이터 로더.

macro_data/daily/YYYYMMDD.csv 파일들을 모두 합쳐 단일 DataFrame 반환.
컬럼 표준화: 한글 컬럼명 → 영문.
"""

import glob
import os
import pandas as pd

DATA_DIR = "./macro_data/daily"


def load_macro_daily(start_date=None, end_date=None) -> pd.DataFrame:
    """
    Returns: DataFrame[code, date, open, high, low, close, volume,
                      trading_value, change_pct, market_cap,
                      foreign_net, inst_net]
    date 는 YYYYMMDD 문자열, 종목/날짜 정렬.
    """
    files = sorted(glob.glob(f"{DATA_DIR}/*.csv"))
    if not files:
        raise FileNotFoundError(f"{DATA_DIR} 에 일봉 데이터 없음. pykrx_collector.py 먼저 실행.")

    dfs = []
    for f in files:
        date_from_name = os.path.basename(f).rsplit(".", 1)[0]
        if start_date and date_from_name < str(start_date):
            continue
        if end_date and date_from_name > str(end_date):
            continue
        df = pd.read_csv(f, encoding="utf-8-sig", dtype={"code": str})
        if "date" not in df.columns:
            df["date"] = date_from_name
        dfs.append(df)

    full = pd.concat(dfs, ignore_index=True)
    full["date"] = full["date"].astype(str)
    full["code"] = full["code"].astype(str).str.zfill(6)

    # 한글 컬럼 → 영문 표준화
    rename = {
        "거래대금": "trading_value",
        "등락률": "change_pct",
        "시가총액": "market_cap",
    }
    full = full.rename(columns=rename)
    # 누락 컬럼 0 채움 (옛 데이터 호환)
    for c in ["trading_value", "change_pct", "market_cap",
              "foreign_net", "inst_net"]:
        if c not in full.columns:
            full[c] = 0.0

    full = full.sort_values(["code", "date"]).reset_index(drop=True)
    return full


def default_costs():
    """KOSDAQ 기준 비용 가정 (단타와 동일)."""
    return {
        "fee_pct":   0.015 * 2,   # 매수+매도
        "tax_pct":   0.20,        # KOSDAQ 거래세
        "slip_pct":  0.05 * 2,    # 슬리피지 매수+매도
        "total_pct": 0.015*2 + 0.20 + 0.05*2,   # = 0.43%
    }
