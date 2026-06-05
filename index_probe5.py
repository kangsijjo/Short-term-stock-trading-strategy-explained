"""
지수 분봉 5차 probe — DATE_1 + DATE_2 (시작/끝 일자 범위).
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
            today = [r for r in o2 if r.get("stck_bsop_date") in ("20260605","20260604")
                     and r.get("stck_cntg_hour") not in ("888888","999999")]
            print(f"  6/4~6/5 분봉 정상 시각: {len(today)}개")
            if today:
                ts = sorted(today, key=lambda r:(r["stck_bsop_date"], r["stck_cntg_hour"]))
                print(f"  처음 5개: {[(r['stck_bsop_date'], r['stck_cntg_hour']) for r in ts[:5]]}")
                print(f"  마지막 5개: {[(r['stck_bsop_date'], r['stck_cntg_hour']) for r in ts[-5:]]}")
    except Exception as e:
        print(f"  ERROR: {e}")


# 1) DATE_1 = DATE_2 = 오늘 (오늘 분봉만)
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "093000",
        "FID_INPUT_DATE_1": "20260605",
        "FID_INPUT_DATE_2": "20260605",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "오늘 분봉만 (DATE_1=DATE_2=20260605)",
)

# 2) DATE_1 = 어제, DATE_2 = 오늘 (이틀 범위)
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260604",
        "FID_INPUT_DATE_2": "20260605",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "이틀 범위 (6/4~6/5)",
)

# 3) 어제만
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260604",
        "FID_INPUT_DATE_2": "20260604",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "어제 분봉만 (6/4)",
)

# 4) 한 달 전 (백필 가능성 테스트)
try_combo(
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260505",
        "FID_INPUT_DATE_2": "20260505",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "5/5 분봉 (한 달 전 백필 테스트)",
)
