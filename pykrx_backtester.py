"""
3대 매크로 전략 동시 백테스터 (벡터화 기반 초고속 연산)
"""

import pandas as pd
import numpy as np
import os
import glob

DATA_DIR = "./macro_data/daily"

def load_and_prep_data():
    print("데이터 로드 및 지표 계산 중 (수 분이 소요될 수 있습니다)...")
    files = sorted(glob.glob(f"{DATA_DIR}/*.csv"))
    if not files:
        print("데이터가 없습니다. pykrx_collector.py를 먼저 실행하세요.")
        return pd.DataFrame()
        
    df_list = [pd.read_csv(f) for f in files]
    df = pd.concat(df_list, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
    df.sort_values(['code', 'date'], inplace=True)
    
    # 지표 계산 (NaN은 자동으로 채워지지 않고 유지됨)
    df['ma20'] = df.groupby('code')['close'].transform(lambda x: x.rolling(20).mean())
    df['high_5d'] = df.groupby('code')['high'].transform(lambda x: x.rolling(5).max())
    
    # RSI 계산 (14일)
    delta = df.groupby('code')['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.groupby(df['code']).transform(lambda x: x.rolling(14).mean())
    avg_loss = loss.groupby(df['code']).transform(lambda x: x.rolling(14).mean())
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 내일의 시가와 종가 (수익률 계산용)
    df['next_open'] = df.groupby('code')['open'].shift(-1)
    df['next_close'] = df.groupby('code')['close'].shift(-1)
    
    return df

def run_strategy_1(df):
    # 전략 1: 쌍끌이 추세추종 (MA20 위 + 외인/기관 양수)
    cond = (df['close'] > df['ma20']) & (df['foreign_net'] > 0) & (df['inst_net'] > 0)
    trades = df[cond].copy()
    # 진입: 당일 종가, 청산: 다음날 종가 (단순화된 1일 보유 스윙)
    trades['gross_pct'] = (trades['next_close'] - trades['close']) / trades['close'] * 100
    return calculate_stats(trades, "1. 쌍끌이 추세추종")

def run_strategy_2(df):
    # 전략 2: 신고가 종가 베팅 (5일 신고가 갱신 + 외인 순매수)
    cond = (df['close'] >= df['high_5d']) & (df['foreign_net'] > 0)
    trades = df[cond].copy()
    # 진입: 당일 종가, 청산: 다음날 시가 (오버나잇 갭만 먹음)
    trades['gross_pct'] = (trades['next_open'] - trades['close']) / trades['close'] * 100
    return calculate_stats(trades, "2. 신고가 종가 베팅")

def run_strategy_3(df):
    # 전략 3: 낙폭과대 반등 (RSI < 30 + 외인 줍줍)
    cond = (df['rsi'] < 30) & (df['foreign_net'] > 0)
    trades = df[cond].copy()
    # 진입: 당일 종가, 청산: 다음날 종가
    trades['gross_pct'] = (trades['next_close'] - trades['close']) / trades['close'] * 100
    return calculate_stats(trades, "3. 낙폭과대 V자 반등")

def calculate_stats(trades, label):
    # 수수료 및 세금 (보수적 0.35%)
    cost_pct = 0.35 
    trades['net_pct'] = trades['gross_pct'] - cost_pct
    trades = trades.dropna(subset=['net_pct']) # 다음날 상장폐지/정지 등으로 데이터가 NaN인 경우 제외
    
    n = len(trades)
    if n == 0:
        return {"전략": label, "매매건수": 0, "승률(%)": 0, "평균수익률(%)": 0, "손익비": 0}
        
    wins = trades[trades['net_pct'] > 0]
    losses = trades[trades['net_pct'] <= 0]
    
    win_rate = len(wins) / n * 100
    avg_net = trades['net_pct'].mean()
    
    total_win = wins['net_pct'].sum()
    total_loss = abs(losses['net_pct'].sum())
    pf = total_win / total_loss if total_loss > 0 else float('inf')
    
    return {
        "전략": label, 
        "매매건수": n, 
        "승률(%)": round(win_rate, 2), 
        "평균수익률(%)": round(avg_net, 3), 
        "손익비": round(pf, 2)
    }

if __name__ == "__main__":
    df = load_and_prep_data()
    if not df.empty:
        res1 = run_strategy_1(df)
        res2 = run_strategy_2(df)
        res3 = run_strategy_3(df)
        
        results_df = pd.DataFrame([res1, res2, res3])
        print("\n" + "="*60)
        print(" [코스닥 3대 매크로 스윙 전략 과거 3년 백테스트 결과]")
        print("="*60)
        print(results_df.to_string(index=False))