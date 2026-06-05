"""
지수 분봉 4차 probe — FHKUP03500100 + FID_INPUT_DATE_1.
"""
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def try_combo(params, label):
    print(f"\n--- {label} ---")
    print(f"  params: {params}")
    try:
        data = _request_with_retry(
            "GET",
            BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice",
            headers=_default_headers("FHKUP03500100"),
            params=params,
            max_retries=1,
        )
        rt = data.get("rt_cd","?")
        msg = data.get("msg1","")
        o2 = data.get("output2", [])
        print(f"  rt_cd={rt}  msg={msg}  output2={len(o2)}")
        if len(o2) > 0:
            print(f"  첫 row: {o2[0]}")
            if len(o2) > 1:
                print(f"  두번째 row: {o2[1]}")
            # 시각 분포
            today = [r for r in o2 if r.get("stck_bsop_date")=="20260605"
                     and r.get("stck_cntg_hour") not in ("888888","999999")]
            print(f"  6/5 분봉 정상 시각: {len(today)}개")
            if today:
                ts = sorted(r["stck_cntg_hour"] for r in today)
                print(f"  시각 분포: {ts[:8]} ... {ts[-5:] if len(ts)>8 else ''}")
    except Exception as e:
        print(f"  ERROR: {e}")


# 1) 풀 파라미터 세트
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "093000",
        "FID_INPUT_DATE_1": "20260605",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "FHKUP03500100 + DATE_1=20260605 + HOUR_1=093000 + INCU_YN=Y",
)

# 2) INCU_YN=N
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260605",
        "FID_PW_DATA_INCU_YN": "N",
    },
    "INCU_YN=N + HOUR_1=153000",
)

# 3) 어제 (6/4) 분봉 받기 시도
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260604",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "어제 6/4 분봉 시도",
)

# 4) KOSDAQ
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "1001",
        "FID_INPUT_HOUR_1": "093000",
        "FID_INPUT_DATE_1": "20260605",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "KOSDAQ (1001)",
)
