"""
스윙 전략 공통 헬퍼 — 진입가 = signal day+1 의 시가, 청산가 = N일 후 종가.

벡터화 형태로 일괄 처리해서 100배 빠름.
"""

import pandas as pd
from .base import StrategyTrade


def _make_trades_for_signals(df_with_sig, holding_days, strategy_name,
                              costs, sig_col="signal", entry_lag=1):
    """
    공통 로직: signal 행 다음날 시가 매수, N일 후 종가 매도.

    df_with_sig: code/date 정렬 + sig_col(bool) 컬럼 보유. 행마다 한 종목-일.
    entry_lag: 시그널 발생 후 N일째 시가 진입 (보통 1 = 다음 영업일).
    holding_days: 진입 후 N일째 종가 청산 (1 = 진입 당일은 close).
    """
    df = df_with_sig.copy()

    # 코드별로 lag 적용
    df["entry_price"] = df.groupby("code")["open"].shift(-entry_lag)
    df["entry_date_next"] = df.groupby("code")["date"].shift(-entry_lag)
    df["exit_price"] = df.groupby("code")["close"].shift(-(entry_lag + holding_days - 1)
                                                          if holding_days >= 1
                                                          else -entry_lag)
    df["exit_date_next"] = df.groupby("code")["date"].shift(-(entry_lag + holding_days - 1)
                                                              if holding_days >= 1
                                                              else -entry_lag)

    sig = df[df[sig_col] &
             df["entry_price"].notna() &
             df["exit_price"].notna() &
             (df["entry_price"] > 0) &
             (df["exit_price"] > 0)].copy()

    sig["gross_pct"] = (sig["exit_price"] / sig["entry_price"] - 1) * 100
    sig["cost_pct"] = costs["total_pct"]
    sig["net_pct"] = sig["gross_pct"] - sig["cost_pct"]

    trades = [
        StrategyTrade(
            strategy=strategy_name,
            code=str(r["code"]),
            entry_date=str(r["entry_date_next"]),
            entry_price=float(r["entry_price"]),
            exit_date=str(r["exit_date_next"]),
            exit_price=float(r["exit_price"]),
            holding_days=holding_days,
            gross_pct=float(r["gross_pct"]),
            cost_pct=float(r["cost_pct"]),
            net_pct=float(r["net_pct"]),
            exit_reason="hold_exit",
        )
        for _, r in sig.iterrows()
    ]
    return trades
