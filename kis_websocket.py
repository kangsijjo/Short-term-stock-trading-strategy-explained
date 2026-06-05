"""
한국투자증권 실시간 체결 데이터(웹소켓) 수신 테스트 모듈

주의: 
- 웹소켓을 사용하려면 기존 액세스 토큰 외에 '웹소켓 접속키(Approval Key)'가 별도로 필요합니다.
- pip install websockets 가 필요합니다.
"""

import json
import asyncio
import requests
import websockets
from config import KIS_APP_KEY, KIS_APP_SECRET, KIS_ENV

# 환경별 웹소켓 URL 및 REST URL 세팅
if KIS_ENV == "prod":
    REST_BASE_URL = "https://openapi.koreainvestment.com:9443"
    WS_BASE_URL = "ws://ops.koreainvestment.com:21000"
else:
    REST_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    WS_BASE_URL = "ws://ops.koreainvestment.com:31000"

def get_approval_key():
    """웹소켓 연결에 필요한 실시간 접속키(Approval Key)를 발급받습니다."""
    print("[웹소켓] 접속키(Approval Key) 발급 요청 중...")
    url = f"{REST_BASE_URL}/oauth2/Approval"
    headers = {"content-type": "application/json; utf-8"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "secretkey": KIS_APP_SECRET
    }
    
    res = requests.post(url, headers=headers, data=json.dumps(body))
    res.raise_for_status()
    approval_key = res.json().get("approval_key")
    print(f"[웹소켓] 접속키 발급 완료: {approval_key[:10]}...")
    return approval_key

async def connect_websocket(stock_code):
    """지정한 종목의 실시간 체결 데이터를 수신합니다."""
    approval_key = get_approval_key()
    
    # 1. 웹소켓 서버 연결
    async with websockets.connect(WS_BASE_URL, ping_interval=None) as websocket:
        print(f"\n[웹소켓] 서버 연결 성공. [{stock_code}] 실시간 데이터 구독을 시작합니다.")
        
        # 2. 구독 요청 전문 작성 (H0STCNT0: 실시간 체결가)
        # ※ 호가창 구독을 원하면 tr_id를 "H0STASP0"로 변경하면 됩니다.
        subscribe_msg = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",      # 개인(P)
                "tr_type": "1",       # 1: 등록(구독), 2: 해제
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",  # 주식 실시간 체결
                    "tr_key": stock_code  # 구독할 종목코드
                }
            }
        }
        
        # 3. 구독 요청 전송
        await websocket.send(json.dumps(subscribe_msg))
        
        # 4. 실시간 데이터 수신 루프
        while True:
            try:
                data = await websocket.recv()
                
                # 처음 연결 시 오는 json 형태의 응답(구독 성공 메세지) 처리
                if data.startswith('{'):
                    parsed = json.loads(data)
                    if parsed.get("header", {}).get("tr_id") == "PINGPONG":
                        await websocket.send(data) # 핑퐁(연결유지) 응답
                    else:
                        print(f"[시스템 메세지] {parsed}")
                    continue
                
                # 실제 체결 데이터는 '|' 로 구분된 평문 스트링으로 쏟아집니다.
                # 예: 0|H0STCNT0|001|005930^110000^...
                parts = data.split('|')
                if len(parts) >= 4:
                    tr_id = parts[1]
                    # 한국투자증권 명세에 따른 체결 데이터 파싱 (인덱스 1: 체결가, 2: 전일대비, 12: 거래량 등)
                    trade_data = parts[3].split('^')
                    if tr_id == "H0STCNT0":
                        current_price = trade_data[1]
                        volume = trade_data[12]
                        time_str = trade_data[0] # HHMMSS
                        print(f"[{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}] "
                              f"종목: {stock_code} | 체결가: {current_price}원 | 체결량: {volume}주")
                        
            except websockets.exceptions.ConnectionClosed:
                print("[웹소켓] 연결이 끊어졌습니다. 재연결 로직이 필요합니다.")
                break
            except Exception as e:
                print(f"[오류 발생] {e}")
                break

if __name__ == "__main__":
    # 테스트용: 삼성전자(005930) 실시간 감시 시작
    # 장 중에 실행해야 데이터가 폭포수처럼 떨어지는 것을 볼 수 있습니다.
    TARGET_CODE = "005930" 
    
    try:
        asyncio.run(connect_websocket(TARGET_CODE))
    except KeyboardInterrupt:
        print("\n[웹소켓] 수신을 종료합니다.")