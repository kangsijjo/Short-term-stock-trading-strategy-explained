"""
전략 #11+ — 추세 (high_lookback) + 시장 컨텍스트 + 거래량 필터.

시장 컨텍스트: 그날 시장 전체 평균 등락률의 60일 이평선 > 0 (강세장)
거래량 필터: 신호 발생일 거래대금 자기 평균의 1.5배 (관심 종목)

기대: high_500d_h40 의 +10.54% 가 +12~15% 로 강화. 표본 감소 trade-off.
"""

import pandas as pd
from .base import BaseStrategy
from ._swing_base import _make_trades_for_signals


class HighWithFiltersStrategy(BaseStrategy):
    name = "high_filtered"
    timeframe = "daily"

    def __init__(self, lookback_days=500, holding_days=40,
                 use_market_filter=True, market_ma_days=60,
                 use_volume_filter=True, vol_mult=1.5,
                 min_trading_value=3_000_000_000, name=None):  # 10억 → 30억 (유동성 강화)
        self.lookback = lookback_days
        self.holding = holding_days
        self.use_mkt = use_market_filter
        self.mkt_ma = market_ma_days
        self.use_vol = use_volume_filter
        self.vol_mult = vol_mult
        self.min_tv = min_trading_value
        if name:
            self.name = name

    def backtest(self, df, costs):
        df = df.sort_values(["code", "date"]).copy()

        # 신고가 신호
        df["prev_high"] = (df.groupby("code")["high"]
                           .shift(1)
                           .rolling(self.lookback, min_periods=self.lookback).max())
        sig = df["close"] > df["prev_high"]

        # 시장 강세 게이트 (그날 시장 평균 change_pct 의 60일 이평)
        if self.use_mkt:
            mkt = df.groupby("date")["change_pct"].mean()
            mkt_ma = mkt.rolling(self.mkt_ma, min_periods=self.mkt_ma).mean()
            mkt_strong = mkt_ma > 0
            df = df.merge(mkt_strong.rename("mkt_strong"), left_on="date",
                          right_index=True, how="left")
            sig = sig & df["mkt_strong"].fillna(False)

        # 거래량 필터 (신호 발생일 거래대금이 자기 30일 평균의 vol_mult 배)
        if self.use_vol:
            df["tv_mean_30"] = (df.groupby("code")["trading_value"]
                                  .rolling(30, min_periods=30).mean()
                                  .reset_index(0, drop=True))
            sig = sig & (df["trading_value"] >= df["tv_mean_30"] * self.vol_mult)

        # 유동성
        sig = sig & (df["trading_value"] >= self.min_tv)

        df["signal"] = sig

        return _make_trades_for_signals(
            df, holding_days=self.holding,
            strategy_name=self.name, costs=costs)
