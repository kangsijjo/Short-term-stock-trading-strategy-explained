"""
지수 분봉 2차 probe — FHKUP03500200 에 FID_PW_DATA_INCU_YN 추가.

1차 probe 에서 FHKUP03500200 가 "FID_PW_DATA_INCU_YN NOT FOUND" 라고 응답.
= TR_ID 자체는 유효, 파라미터만 보강하면 됨.
"""

import sys, json
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def try_combo(tr_id, params, label):
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-tickprice"
    headers = _default_headers(tr_id)
    try:
        data = _request_with_retry("GET", url, headers=headers, params=params, max_retries=1)
        rt = data.get("rt_cd", "?")
        msg = data.get("msg1", "")
        o2 = data.get("output2", [])
        n_o2 = len(o2) if isinstance(o2, list) else 0
        sample = o2[:2] if n_o2 > 0 else None
        print(f"  rt_cd={rt}  msg={msg}  output2={n_o2}")
        if sample:
            print(f"  샘플: {json.dumps(sample, ensure_ascii=False)[:500]}")
        if rt == "0" and n_o2 == 0:
            o = data.get("output", {})
            print(f"  output(단일): {json.dumps(o, ensure_ascii=False)[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def main():
    print("=== 2차 probe: FHKUP03500200 + FID_PW_DATA_INCU_YN 추가 ===\n")

    print("[1] 표준 파라미터 풀세트")
    try_combo(
        "FHKUP03500200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "153000",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        "주식 분봉 파라미터 그대로",
    )

    print("[2] 시각 09:30 변경")
    try_combo(
        "FHKUP03500200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "093000",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        "09:30",
    )

    print("[3] FID_PW_DATA_INCU_YN=N")
    try_combo(
        "FHKUP03500200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "153000",
            "FID_PW_DATA_INCU_YN": "N",
        },
        "INCU_YN=N",
    )

    print("[4] KOSDAQ (1001) 로도 시험")
    try_combo(
        "FHKUP03500200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "1001",
            "FID_INPUT_HOUR_1": "153000",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        "KOSDAQ",
    )

    # 일자 파라미터 추가 시험 (FID_INPUT_DATE_1)
    print("[5] FID_INPUT_DATE_1 추가 (어제 6/4)")
    try_combo(
        "FHKUP03500200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "153000",
            "FID_INPUT_DATE_1": "20260604",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        "DATE_1 = 어제",
    )


if __name__ == "__main__":
    main()
