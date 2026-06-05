"""
NXT (넥스트레이드) 시간외 분봉 KIS API 지원 가능성 검증.

KIS 의 종목 분봉 endpoint 는 시장 구분 코드(FID_COND_MRKT_DIV_CODE)로 시장을 구분:
  - "J" : KRX 일반 (기존, 09:00~15:30 + 동시호가)
  - "NX": NXT 단독 시세
  - "UN": KRX + NXT 통합시세

vps(모의) 환경에서 NX/UN 코드가 동작하는지 확인 후, 결과에 따라
data_collector 에 통합할지 결정.

사용법:
  python nxt_probe.py [YYYYMMDD]
"""

import sys
import os
from datetime import datetime
import requests

import config


# 직접 호출 (kis_api 의 함수를 그대로 쓰지 않고 endpoint/파라미터 변경 가능하게)
from kis_api import _request_with_retry, _default_headers, BASE_URL


def probe_minute(stock_code, target_time, market_div):
    """주식분봉 API 를 다양한 market_div 로 호출."""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    headers = _default_headers("FHKST03010200")
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": market_div,
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_HOUR_1": target_time,
        "FID_PW_DATA_INCU_YN": "Y",
    }
    try:
        data = _request_with_retry("GET", url, headers=headers, params=params,
                                   max_retries=1)
    except Exception as e:
        return {"ok": False, "error": str(e), "n_bars": 0}

    if data.get("rt_cd") != "0":
        return {
            "ok": False,
            "error": f"rt_cd={data.get('rt_cd')} msg={data.get('msg1')}",
            "n_bars": 0,
        }
    bars = data.get("output2", [])
    times = [b.get("stck_cntg_hour", "") for b in bars[:5]]
    return {
        "ok": True,
        "n_bars": len(bars),
        "sample_times": times,
    }


def main():
    stock_code = "005930"  # 삼성전자 (NXT 대상 종목 중 하나)
    target_time = "170000"  # 17:00 — KRX 마감 후, NXT 영역

    print(f"[probe] 종목 {stock_code}, target_time {target_time}")
    print(f"  목적: NXT 애프터마켓 시간대(17:00)의 분봉을 받을 수 있는지 확인\n")

    for market_div in ["J", "NX", "UN"]:
        print(f"  --- market_div = {market_div!r} ---")
        r = probe_minute(stock_code, target_time, market_div)
        if r["ok"]:
            print(f"    OK, {r['n_bars']} 봉. 샘플 time: {r['sample_times']}")
        else:
            print(f"    실패: {r['error']}")
        print()

    print("=" * 60)
    print(" 해석:")
    print("=" * 60)
    print(" - 'J' 만 성공 + 시간이 15:30 이하: KRX 정규장만 지원 (NXT 미지원)")
    print(" - 'NX' 또는 'UN' 성공 + 시간이 17:00 근처: NXT 데이터 받음. 통합 가능!")
    print(" - 'NX'/'UN' 호출 오류 (rt_cd != 0): vps 환경 NXT 미지원 가능성 큼")
    print(" → 결과에 따라 data_collector 통합 여부 결정.")


if __name__ == "__main__":
    main()
