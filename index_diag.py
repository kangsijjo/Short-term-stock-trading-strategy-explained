"""
지수 분봉 응답 분포 진단 — 102개 중 오늘 vs 어제 vs 시각 패턴 확인.
"""
import config
from kis_api import _request_with_retry, _default_headers, BASE_URL


def fetch(market, target_hour, with_pw="Y"):
    iscd = "0001" if market == "KOSPI" else "1001"
    data = _request_with_retry(
        "GET",
        BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice",
        headers=_default_headers("FHKUP03500200"),
        params={
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": iscd,
            "FID_INPUT_HOUR_1": target_hour,
            "FID_PW_DATA_INCU_YN": with_pw,
        },
        max_retries=1,
    )
    return data.get("output2", [])


def analyze(label, out2):
    print(f"\n=== {label} ===")
    print(f"총 {len(out2)}개")

    by_date = {}
    for r in out2:
        d = r.get("stck_bsop_date", "?")
        t = r.get("stck_cntg_hour", "?")
        if t == "999999":
            continue
        by_date.setdefault(d, []).append(t)

    for d in sorted(by_date.keys()):
        times = by_date[d]
        print(f"  {d}: {len(times)}개")
        if times:
            print(f"    첫 5개: {times[:5]}")
            print(f"    끝 5개: {times[-5:]}")

    # 분봉 간격 확인 (당일치)
    today_times = sorted(by_date.get("20260605", []))
    if len(today_times) >= 2:
        # HHMMSS → 초로
        def to_sec(t):
            return int(t[:2])*3600 + int(t[2:4])*60 + int(t[4:6])
        gaps = [to_sec(today_times[i+1]) - to_sec(today_times[i]) for i in range(len(today_times)-1)]
        print(f"    분봉 간격 (당일치): 최소 {min(gaps)}초, 평균 {sum(gaps)/len(gaps):.0f}초, 최대 {max(gaps)}초")


# 시나리오: 다른 target_hour 로 시도
for hh in ["153000", "100000", "093000", "090500", "090100"]:
    out = fetch("KOSPI", hh)
    analyze(f"KOSPI target_hour={hh}", out)

# INCU_YN=N 으로 시도 (당일만)
out = fetch("KOSPI", "153000", with_pw="N")
analyze("KOSPI target_hour=153000 INCU_YN=N", out)
