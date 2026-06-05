"""
KIS 지수 분봉 API TR_ID 정확한 코드 탐색.

추측 후보 여러 개 시험. '없는 서비스 코드' 응답이 아닌 것 = 유효.
"""

import sys
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def try_endpoint(url_path, tr_id, params, label):
    url = f"{BASE_URL}{url_path}"
    headers = _default_headers(tr_id)
    try:
        data = _request_with_retry("GET", url, headers=headers, params=params, max_retries=1)
        rt = data.get("rt_cd", "?")
        msg = data.get("msg1", "")
        n_out = len(data.get("output", [])) if isinstance(data.get("output"), list) else 0
        n_out2 = len(data.get("output2", [])) if isinstance(data.get("output2"), list) else 0
        status = "OK" if rt == "0" else "FAIL"
        print(f"  {status:5} | {label}")
        print(f"        TR_ID={tr_id}  url={url_path}")
        print(f"        rt_cd={rt}  msg={msg}  output={n_out}, output2={n_out2}")
    except Exception as e:
        print(f"  ERROR | {label}: {e}")


def main():
    print("=== 지수 분봉 가능 TR_ID 탐색 (KOSPI 0001) ===\n")

    # 표준 stock minute endpoint, market_div=U (index)
    try_endpoint(
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        "FHKST03010200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "092500",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        "후보 A: stock minute endpoint + market_div=U",
    )
    print()

    # 업종/지수 분봉 추정 endpoint
    for tr in ["FHKUP03500200", "FHPUP02110000", "FHPST02400000",
               "FHKUP02410200", "FHPUP02400200"]:
        try_endpoint(
            "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice",
            tr,
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_HOUR_1": "092500",
            },
            f"후보 (tickprice): TR_ID={tr}",
        )
        print()

    # 다른 endpoint 경로 시도
    for url_p in [
        "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice",
        "/uapi/domestic-stock/v1/quotations/inquire-index-minute-itemchartprice",
        "/uapi/domestic-stock/v1/quotations/inquire-index-time-tickprice",
    ]:
        try_endpoint(
            url_p,
            "FHPUP02100000",  # snapshot 과 같은 TR_ID 시험
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_HOUR_1": "092500",
            },
            f"snapshot TR_ID + 다른 endpoint: {url_p.split('/')[-1]}",
        )
        print()


if __name__ == "__main__":
    main()
