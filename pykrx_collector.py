"""
과거 3년 치 일봉 & 수급 데이터 수집기 (스텔스 & 좀비 모드 패치)
"""

# config 가 .env 로드 (KRX_ID/PW 환경변수) → pykrx 가 그 후 import 되어 인식
import config  # noqa: F401

from pykrx import stock
import pandas as pd
import os
import time
import random
from datetime import datetime, timedelta

DATA_DIR = "./macro_data/daily"
os.makedirs(DATA_DIR, exist_ok=True)

def collect_macro_data(start_date_str, end_date_str, market="KOSDAQ"):
    print(f"[{market}] {start_date_str} ~ {end_date_str} 스텔스 데이터 수집 시작...")
    print("(KRX 로그인 경고문구는 무시하십시오.)\n")
    
    date_range = pd.bdate_range(start=start_date_str, end=end_date_str)
    total_days = len(date_range)
    
    for i, dt in enumerate(date_range):
        date_str = dt.strftime("%Y%m%d")
        save_path = f"{DATA_DIR}/{date_str}.csv"
        
        # 이미 수집된 날짜는 건너뛰기 (중간에 끊겨도 이어받기 가능)
        if os.path.exists(save_path):
            continue
            
        print(f"[{i+1}/{total_days}] {date_str} 수집 시도 중...")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 1. 서버 차단 방지용 랜덤 딜레이 (기계가 아닌 척 위장)
                time.sleep(random.uniform(1.5, 3.5))
                
                # 2. 일봉 데이터 수집
                df_ohlcv = stock.get_market_ohlcv(date_str, market)
                
                # 휴장일(공휴일) 체크: 빈 데이터면 깔끔하게 패스
                if df_ohlcv is None or df_ohlcv.empty:
                    print(f"  -> {date_str} 휴장일(데이터 없음). 건너뜁니다.")
                    break # 다음 날짜로 넘어감
                    
                df_ohlcv = df_ohlcv.reset_index()
                df_ohlcv.rename(columns={'티커': 'code', '시가': 'open', '고가': 'high', '저가': 'low', '종가': 'close', '거래량': 'volume'}, inplace=True)
                
                # 3. 외국인 순매수 (추가 랜덤 딜레이)
                time.sleep(random.uniform(0.5, 1.5))
                df_foreigner = stock.get_market_net_purchases_of_equities_by_ticker(date_str, date_str, market, "외국인")
                if not df_foreigner.empty:
                    df_foreigner = df_foreigner.reset_index()[['티커', '순매수거래대금']]
                    df_foreigner.rename(columns={'티커': 'code', '순매수거래대금': 'foreign_net'}, inplace=True)
                else:
                    df_foreigner = pd.DataFrame(columns=['code', 'foreign_net'])
                
                # 4. 기관 순매수 (추가 랜덤 딜레이)
                time.sleep(random.uniform(0.5, 1.5))
                df_inst = stock.get_market_net_purchases_of_equities_by_ticker(date_str, date_str, market, "기관합계")
                if not df_inst.empty:
                    df_inst = df_inst.reset_index()[['티커', '순매수거래대금']]
                    df_inst.rename(columns={'티커': 'code', '순매수거래대금': 'inst_net'}, inplace=True)
                else:
                    df_inst = pd.DataFrame(columns=['code', 'inst_net'])
                
                # 5. 병합 및 저장
                df_merged = pd.merge(df_ohlcv, df_foreigner, on='code', how='left')
                df_merged = pd.merge(df_merged, df_inst, on='code', how='left')
                df_merged['date'] = date_str
                
                df_merged.to_csv(save_path, index=False, encoding="utf-8-sig")
                print(f"  -> {date_str} 저장 완료.")
                
                break # 성공했으므로 재시도 루프 탈출
                
            except Exception as e:
                error_msg = str(e)
                if "Expecting value" in error_msg or "None of" in error_msg:
                    print(f"  [경고] KRX 서버 방화벽 감지. 15초 은신 후 재시도... ({attempt+1}/{max_retries})")
                    time.sleep(15) # 차단 시 15초간 숨죽이기
                else:
                    print(f"  [오류] 알 수 없는 에러: {e}")
                    break

if __name__ == "__main__":
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=365 * 3)
    collect_macro_data(start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))