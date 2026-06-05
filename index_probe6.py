"""
지수 분봉 6차 probe — PERIOD_DIV_CODE 다양한 값 시도.

KIS 통상: D=일, W=주, M=월, Y=년. 분봉은 보통 다른 endpoint 이지만,
이 endpoint 가 통합형이면 "1" / "5" / "T" / "m" 같은 값일 수도.
"""
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def try_combo(period_div, label):
    print(f"\n--- {label} (PERIOD_DIV={period_div!r}) ---")
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_HOUR_1": "153000",
        "FID_INPUT_DATE_1": "20260605",
        "FID_INPUT_DATE_2": "20260605",
        "FID_PERIOD_DIV_CODE": period_div,
        "FID_PW_DATA_INCU_YN": "Y",
    }
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
            valid = [r for r in o2 if r.get("stck_cntg_hour") not in ("888888","999999")]
            print(f"  정상 시각 row: {len(valid)}개")
            if valid:
                ts = sorted({(r.get("stck_bsop_date"), r.get("stck_cntg_hour")) for r in valid})
                print(f"  앞 5개: {ts[:5]}")
                print(f"  뒤 5개: {ts[-5:] if len(ts)>5 else ''}")
    except Exception as e:
        print(f"  ERROR: {e}")


# PERIOD_DIV 후보들
for pd in ["D", "W", "M", "Y", "1", "5", "10", "30", "60", "T", "m", ""]:
    try_combo(pd, f"period {pd!r}")
