"""
AI 학습셋 v3 — 풀링 전략 + 종목 피처 + stock.db 외부 피처 (뉴스 감성·매크로 레짐).

v2 대비 변경:
  1. 매매 풀링: h500_40_MKT + h252_40 + h500_20 (서로 다른 lookback/holding)
     → 표본 수 확대 + strategy_id 피처로 구분. macro_data 가 깊어질수록 자동 확장.
  2. stock.db (Stock_AI_Project) 피처:
     - news_sentiment_7d / news_count_7d : 신호일 직전 7일 종목 뉴스 감성 평균·건수
     - vix, vix_chg_5d, sox_ret_5d, usdkrw_chg_5d, kospi_ret_20d : 매크로 레짐
     stock.db 없으면 해당 피처 NaN (graceful).
  3. 라벨용 net_pct 그대로 저장 — 라벨링은 트레이너에서 (big-win 등 선택 가능).

저장: ./trades_history_v3.csv
실행: python make_trades_history_v3.py
"""

import os
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from strategies.daily_loader import load_macro_daily, default_costs, filter_universe
from strategies.high_with_filters import HighWithFiltersStrategy
from strategies.high_52w import FiftyTwoWeekHighStrategy
from make_trades_history_v2 import compute_stock_features

OUT = "./trades_history_v3.csv"

STOCK_DB_CANDIDATES = [
    os.getenv("STOCK_DB", ""),
    "../Stock_AI_Project/data/stock.db",
    "C:/fin/Stock_AI_Project/data/stock.db",
]

STRATEGIES = [
    ("h500_40_MKT", HighWithFiltersStrategy(lookback_days=500, holding_days=40,
                     use_market_filter=True, use_volume_filter=False, name="h500_40_MKT")),
    ("h252_40",     FiftyTwoWeekHighStrategy(lookback_days=252, holding_days=40, name="h252_40")),
    ("h500_20",     FiftyTwoWeekHighStrategy(lookback_days=500, holding_days=20, name="h500_20")),
]


def open_stock_db():
    for p in STOCK_DB_CANDIDATES:
        if p and os.path.exists(p):
            try:
                con = sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)
                con.execute("SELECT 1")
                print(f"[stock.db] 연결: {p}")
                return con
            except Exception as e:
                print(f"[stock.db] {p} 열기 실패: {e}")
    print("[stock.db] 없음 — 뉴스/매크로 피처는 NaN 으로 저장")
    return None


def load_news_daily(con):
    """종목·일자별 감성 평균/건수 (전 기간 1회 집계)."""
    q = """SELECT ticker, pubDate AS d, AVG(sentiment) AS sent, COUNT(*) AS n
           FROM news WHERE sentiment IS NOT NULL GROUP BY ticker, pubDate"""
    df = pd.read_sql(q, con)
    df["d"] = df["d"].astype(str).str.replace("-", "").str[:8]
    return df


def load_macro_ind(con):
    """stock.db(과거) + macro_data/indicators.csv(연속 수집분) 병합 — 최신분 우선."""
    parts = []
    if con is not None:
        parts.append(pd.read_sql("SELECT date, indicator, close FROM macro_indicators", con))
    if os.path.exists("./macro_data/indicators.csv"):
        parts.append(pd.read_csv("./macro_data/indicators.csv"))
    if not parts:
        return None
    m = pd.concat(parts, ignore_index=True)
    m["date"] = m["date"].astype(str).str.replace("-", "").str[:8]
    m = m.drop_duplicates(subset=["date", "indicator"], keep="last")
    w = m.pivot_table(index="date", columns="indicator", values="close", aggfunc="last").sort_index()
    out = pd.DataFrame(index=w.index)
    if "VIX" in w:
        out["vix"] = w["VIX"]
        out["vix_chg_5d"] = w["VIX"].pct_change(5) * 100
    if "SOX" in w:
        out["sox_ret_5d"] = w["SOX"].pct_change(5) * 100
    if "KRW_USD" in w:
        out["usdkrw_chg_5d"] = w["KRW_USD"].pct_change(5) * 100
    if "KOSPI" in w:
        out["kospi_ret_20d"] = w["KOSPI"].pct_change(20) * 100
    # 신호일에 매크로 휴장 등으로 값이 없으면 직전값 사용
    out = out.ffill()
    return out.reset_index().rename(columns={"index": "date"})


def news_window_feature(news_by_code, code, sig_date, days=7):
    """신호일 직전 7일(달력일) 감성 평균/건수 — 종목별 사전 인덱스로 고속 조회."""
    if news_by_code is None:
        return np.nan, np.nan
    g = news_by_code.get(code)
    if g is None:
        return np.nan, 0
    d0 = (datetime.strptime(sig_date, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
    import bisect
    lo = bisect.bisect_left(g["d"], d0)
    hi = bisect.bisect_right(g["d"], sig_date)
    if lo >= hi:
        return np.nan, 0
    n = sum(g["n"][lo:hi])
    s = sum(se * nn for se, nn in zip(g["sent"][lo:hi], g["n"][lo:hi]))
    return float(s / n), int(n)


def main():
    print("=== trades_history v3 (풀링 + 외부 피처) ===\n")
    df = load_macro_daily()
    df = filter_universe(df)
    df["date"] = df["date"].astype(str)
    df["code"] = df["code"].astype(str).str.zfill(6)
    costs = default_costs()

    # 1) 풀링 백테스트
    all_trades = []
    for sid, strat in STRATEGIES:
        ts = strat.backtest(df, costs)
        for t in ts:
            all_trades.append((sid, t))
        print(f"  {sid:14s}: {len(ts):,} 매매")
    print(f"[pool] 합계 {len(all_trades):,} 매매")

    # 2) 종목 피처 (v2 재사용)
    stock_feat = compute_stock_features(df)
    stock_feat["date"] = stock_feat["date"].astype(str)
    stock_feat["code"] = stock_feat["code"].astype(str).str.zfill(6)
    sf_map = stock_feat.set_index(["code", "date"]).to_dict("index")

    # 3) 외부 피처 (stock.db)
    con = open_stock_db()
    news_by_code = None
    macro_ind = None
    if con is not None:
        try:
            news = load_news_daily(con)
            print(f"[news] {len(news):,} 종목-일 집계")
            news = news.sort_values(["ticker", "d"])
            news_by_code = {
                t: {"d": g["d"].tolist(), "sent": g["sent"].tolist(), "n": g["n"].tolist()}
                for t, g in news.groupby("ticker")
            }
        except Exception as e:
            print(f"[news] 집계 실패: {e}")
    try:
        mi = load_macro_ind(con)   # stock.db 없어도 indicators.csv 만으로 동작
        if mi is not None:
            macro_ind = mi.set_index("date").to_dict("index")
            print(f"[macro_ind] {len(macro_ind):,} 일")
    except Exception as e:
        print(f"[macro_ind] 실패: {e}")

    # signal_date = entry 직전 영업일
    code_dates = {c: sorted(g["date"].tolist()) for c, g in df.groupby("code")}

    def sig_date_of(code, entry_date):
        ds = code_dates.get(code, [])
        try:
            i = ds.index(entry_date)
            return ds[i - 1] if i > 0 else entry_date
        except ValueError:
            return entry_date

    rows = []
    feat_keys = ["rsi14", "atr_pct", "vol_ratio", "tv_ratio", "for_5d", "ins_5d", "mcap_class"]
    macro_keys = ["vix", "vix_chg_5d", "sox_ret_5d", "usdkrw_chg_5d", "kospi_ret_20d"]
    for sid, t in all_trades:
        sd = sig_date_of(t.code, t.entry_date)
        sf = sf_map.get((t.code, sd), {})
        sent, n_news = news_window_feature(news_by_code, t.code, sd)
        mi = macro_ind.get(sd, {}) if macro_ind else {}
        row = {
            "date": sd, "code": t.code, "strategy": sid,
            "entry_date": t.entry_date, "exit_date": t.exit_date,
            "net_pct": round(t.net_pct, 4), "gross_pct": round(t.gross_pct, 4),
            "score_tv": t.score,
            "news_sent_7d": None if pd.isna(sent) else round(sent, 4),
            "news_cnt_7d": n_news if not pd.isna(n_news) else None,
        }
        for k in feat_keys:
            v = sf.get(k)
            row[k] = None if v is None or pd.isna(v) else round(float(v), 4)
        for k in macro_keys:
            v = mi.get(k)
            row[k] = None if v is None or pd.isna(v) else round(float(v), 4)
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("date")

    # 키움 백필 피처 (신용잔고·프로그램매매) — kiwoom_backfill.py merge 산출물
    KW_FEAT = "./ai_data/kiwoom_hist_features.csv"
    if os.path.exists(KW_FEAT):
        kw = pd.read_csv(KW_FEAT, dtype={"code": str, "date": str})
        kw["code"] = kw["code"].str.zfill(6)
        out = out.merge(kw, on=["code", "date"], how="left")
        cov = out.get("crd_remn_rt")
        if cov is not None:
            print(f"[kiwoom_feat] 병합 — 신용 커버리지 {cov.notna().mean()*100:.0f}%")

    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n[saved] {OUT}, {len(out):,} 행 "
          f"({out['date'].min()} ~ {out['date'].max()})")
    has_news = out["news_sent_7d"].notna().mean() * 100
    print(f"  뉴스 피처 보유율: {has_news:.1f}%")


if __name__ == "__main__":
    main()
