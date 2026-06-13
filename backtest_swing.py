"""
오버나잇 스윙 전용 백테스트 메인 실행 스크립트.

[전략 룰]
- 진입: 15시 20분 부근, 주가가 5일 이동평균선(MA5) 위에 있고 전일(D-1) 외인 순매수가 양수일 때 시장가 매수
- 청산: 익일 09시 05분 부근, 조건 없이 전량 시장가 매도 (시가 갭 상승/하락분 수익 확정)

실행: python backtest_swing.py
"""

import sys
import os
import pandas as pd
from datetime import datetime

import config
import data_loader
import analyzer
from simulator import Trade  # [수정] analyzer와 완벽 호환되는 Trade 데이터클래스 임포트

class SwingSimulator:
    def __init__(self, code, name):
        self.code = code
        self.name = name
        self.trades = []
        self.entered = False
        self.entry_price = 0
        self.entry_time = None
        self.entry_date = None

    def simulate(self, df, foreign_data_map):
        # 1. 일봉 종가 및 5일 이동평균선(MA5) 계산
        daily_close = df.groupby('date')['close'].last()
        ma5 = daily_close.shift(1).rolling(5).mean()
        df['ma5'] = df['date'].map(ma5)

        for row in df.itertuples():
            date = str(row.date)
            time = str(row.time)
            price = float(row.close)

            # [청산 로직] 익일 09시 05분 부근 전량 매도
            if self.entered and date > self.entry_date and time >= "090500":
                sell_price = price
                
                # [수정] analyzer.py가 인식할 수 있도록 pandas datetime 포맷으로 변환
                entry_dt = pd.to_datetime(self.entry_date + self.entry_time, format="%Y%m%d%H%M%S")
                exit_dt = pd.to_datetime(date + time, format="%Y%m%d%H%M%S")

                # [수정] 딕셔너리 대신 Trade 객체를 생성하여 TypeError 완벽 방지
                t = Trade(
                    mode="SWING",
                    stock_code=self.code,
                    stock_name=self.name,
                    market="KOSDAQ", 
                    entry_time=entry_dt,
                    entry_price=self.entry_price,
                    exit_time=exit_dt,
                    exit_price=sell_price,
                    exit_reason="morning_gap"
                )
                t.finalize()  # 수수료, 세금, 순수익, 보유시간(오버나잇) 자동 계산
                self.trades.append(t)
                
                self.entered = False

            # [진입 로직] 당일 15시 20분 부근 매수 (5일선 위 + 전일 외인 수급)
            if not self.entered and "152000" <= time <= "152500":
                foreign_net = foreign_data_map.get(date, {}).get(self.code, 0)

                # 조건: 전일 외인 순매수 양수 + 단기 추세(MA5) 안착
                if foreign_net > 0 and pd.notna(row.ma5) and price > row.ma5:
                    self.entered = True
                    self.entry_price = price
                    self.entry_date = date
                    self.entry_time = time

        return self.trades


def main():
    print("="*60)
    print(" [오버나잇 스윙 전용 엔진] 대공사 백테스트 시작")
    print("="*60)

    # 1. 모든 수집 날짜 확보
    dates = data_loader.list_available_dates()
    if not dates:
        print("[error] 수집된 분봉 데이터가 없습니다.")
        sys.exit(1)

    print(f"총 {len(dates)}일의 데이터를 종목별 시계열로 이어붙이는 중...")

    # 2. 외국인 수급 데이터 맵핑 — D-1(전일) 데이터를 D-0 키에 매핑
    # [fix] 이전엔 당일(D-0) 종가 후 확정되는 수급을 15:20 진입 조건에 사용 → look-ahead bias.
    #       15:20 시점에 알 수 있는 것은 전일 확정치이므로 하루 밀어서 사용.
    foreign_data_map = {}
    prev_inv = {}
    for d in dates:  # dates 는 오름차순
        foreign_data_map[d] = prev_inv
        inv_data = data_loader.load_investor_for_date(d)
        if inv_data:
            prev_inv = {code: float(row.get('foreign_net_value', 0) or 0)
                        for code, row in inv_data.items()}
        else:
            prev_inv = {}

    # 3. 모든 날짜의 분봉 데이터를 로드하여 연속된 DataFrame으로 묶기
    all_data_by_code = {}
    name_map = {}
    
    for d in dates:
        bars_by_code = data_loader.load_all_for_date(d)
        daily_names = data_loader.get_stock_name_map(d)
        name_map.update(daily_names)

        for code, df in bars_by_code.items():
            df['date'] = d
            df['time'] = df['datetime'].dt.strftime('%H%M%S') 
            
            if code not in all_data_by_code:
                all_data_by_code[code] = []
            all_data_by_code[code].append(df)

    # 4. 시뮬레이션 실행
    all_trades = []
    total_codes = len(all_data_by_code)
    
    for i, (code, dfs) in enumerate(all_data_by_code.items(), 1):
        if i % 10 == 0:
            print(f"  ... 시뮬레이션 진행 중 ({i}/{total_codes})")
            
        continuous_df = pd.concat(dfs, ignore_index=True)
        continuous_df.sort_values(by=['datetime'], inplace=True)
        
        sim = SwingSimulator(code, name_map.get(code, code))
        trades = sim.simulate(continuous_df, foreign_data_map)
        all_trades.extend(trades)

    # 5. 결과 분석 및 리포팅
    period = f"{dates[0]}-{dates[-1]}"
    print("\n[백테스트 완료] 분석 리포트를 생성합니다...\n")
    
    if not all_trades:
        print("[결과] 해당 기간 동안 스윙 진입 조건을 만족하는 종목이 없습니다.")
        sys.exit(0)
        
    summary = analyzer.summarize(all_trades, label="SWING")
    summaries = [summary]
    
    exit_reasons = {"SWING": analyzer.exit_reason_breakdown(all_trades)}
    
    analyzer.print_report(summaries, exit_reasons)
    
    trades_path = f"{config.RESULT_DIR}/trades_SWING_{period}.csv"
    analyzer.save_trades_csv(all_trades, trades_path)
    print(f"\n→ 매매 {len(all_trades)}건 상세 내역 저장 완료: {trades_path}")


if __name__ == "__main__":
    main()