"""
AI 메타라벨링을 위한 일일 시장 환경(Feature) 수집기
실행: 매일 15:15 자동 실행 권장
"""

import pandas as pd
from pykrx import stock
from datetime import datetime
import os

FEATURE_DIR = "./ai_data"
os.makedirs(FEATURE_DIR, exist_ok=True)

def collect_daily_features():
    today_str = datetime.today().strftime("%Y%m%d")
    print(f"[{today_str}] AI 학습용 거시 경제 Feature 수집 시작...")

    features = {"date": today_str}

    try:
        # 1. 코스닥 지수 흐름 (시장 전체의 추세)
        kosdaq_index = stock.get_index_ohlcv(today_str, today_str, "KOSDAQ")
        if not kosdaq_index.empty:
            open_idx = kosdaq_index['시가'].iloc[0]
            close_idx = kosdaq_index['종가'].iloc[0]
            # 당일 지수 변동률 (양수면 상승장, 음수면 하락장)
            features['kosdaq_intraday_pct'] = round((close_idx - open_idx) / open_idx * 100, 3)
        else:
            features['kosdaq_intraday_pct'] = 0.0

        # 2. 코스닥 전체 투자자별 순매수 동향 (가장 강력한 수급 지표)
        # 시장 전체의 외국인/기관 매수세가 살아있는지 파악
        investor_net = stock.get_market_net_purchases_of_equities_by_ticker(today_str, today_str, "KOSDAQ", "외국인")
        features['kosdaq_foreign_net_sum'] = float(investor_net['순매수거래대금'].sum()) if not investor_net.empty else 0.0

        investor_inst = stock.get_market_net_purchases_of_equities_by_ticker(today_str, today_str, "KOSDAQ", "기관합계")
        features['kosdaq_inst_net_sum'] = float(investor_inst['순매수거래대금'].sum()) if not investor_inst.empty else 0.0

        # 데이터프레임 변환
        df_new = pd.DataFrame([features])
        
        # 기존 데이터에 누적 저장
        file_path = f"{FEATURE_DIR}/market_features.csv"
        if os.path.exists(file_path):
            df_existing = pd.read_csv(file_path)
            # 중복 날짜 방지
            df_existing = df_existing[df_existing['date'] != int(today_str)]
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_final = df_new

        df_final.to_csv(file_path, index=False)
        print(f"→ 수집 완료: 코스닥 지수변동 {features['kosdaq_intraday_pct']}%, 외인 총순매수 {features['kosdaq_foreign_net_sum']}원")

    except Exception as e:
        print(f"[오류] Feature 수집 실패: {e}")

if __name__ == "__main__":
    collect_daily_features()