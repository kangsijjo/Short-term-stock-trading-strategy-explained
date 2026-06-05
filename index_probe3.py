"""
지수 분봉 3차 probe — 현재 시각 근처로 다양한 endpoint/TR_ID 재시도.
"""
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def try_combo(url_path, tr_id, params, label):
    print(f"\n--- {label} ---")
    print(f"  TR_ID={tr_id}  url={url_path}")
    try:
        data = _request_with_retry("GET", BASE_URL+url_path,
            headers=_default_headers(tr_id), params=params, max_retries=1)
        rt = data.get("rt_cd","?")
        msg = data.get("msg1","")
        o2 = data.get("output2", [])
        print(f"  rt_cd={rt}  msg={msg}  output2={len(o2)}")
        if len(o2) > 0:
            # 시각/날짜 다양성 확인
            r = o2[0]
            print(f"  첫 row: {r}")
            if len(o2) > 1:
                print(f"  두번째 row: {o2[1]}")
            # 오늘 분봉만 count + 시각 분포
            today_rows = [x for x in o2
                         if x.get("stck_bsop_date") == "20260605"
                         and x.get("stck_cntg_hour") not in ("888888", "999999")]
            print(f"  6/5 분봉 (정상 시각): {len(today_rows)}개")
            if today_rows:
                ts = sorted(x["stck_cntg_hour"] for x in today_rows)
                print(f"  6/5 시각 분포: {ts[:8]} ... {ts[-3:] if len(ts)>8 else ''}")
    except Exception as e:
        print(f"  ERROR: {e}")


# 1) stock minute endpoint + market_div=U + 현재 시각 근처
for hr in ["100000", "095000", "094000", "093500"]:
    try_combo(
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        "FHKST03010200",
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": hr,
            "FID_PW_DATA_INCU_YN": "Y",
        },
        f"stock minute + U + hour={hr}",
    )

# 2) 같은 endpoint, market_div=J (정규 종목), iscd=0001 (KOSPI 코드)
try_combo(
    "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
    "FHKST03010200",
    {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "093000",
        "FID_PW_DATA_INCU_YN": "Y",
    },
    "stock minute + J + 0001 (KOSPI 코드)",
)

# 3) 알려진 다른 후보들 + INCU_YN=Y 추가
candidates = [
    ("FHKUP02410200", "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice"),
    ("FHPUP02400200", "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice"),
    ("FHKUP03500100", "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice"),
    ("FHPUP02110100", "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice"),
]
for tr, url in candidates:
    try_combo(
        url, tr,
        {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": "0001",
            "FID_INPUT_HOUR_1": "093000",
            "FID_PW_DATA_INCU_YN": "Y",
        },
        f"alt TR_ID={tr}",
    )
