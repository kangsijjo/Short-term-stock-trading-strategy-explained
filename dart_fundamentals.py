"""
DART 재무제표 수집기 — 종목별 매출/영업이익/당기순이익 (퀄리티 필터용).

API (공식 문서 확정 스펙):
  1. corpCode.xml  : https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=KEY
     → zip 안의 CORPCODE.xml 에서 stock_code(6자리) ↔ corp_code(8자리) 매핑
  2. fnlttSinglAcntAll.json : 단일회사 전체 재무제표
     params: crtfc_key, corp_code, bsns_year, reprt_code, fs_div
     reprt_code: 11013(1분기) 11012(반기) 11014(3분기) 11011(사업보고서)
     fs_div: CFS(연결) / OFS(별도)

수집 대상: credit_collector 와 동일 (최근 신호 종목 + 랭킹 상위) — 호출량 절약.
저장:
  db/fundamentals/corp_code_map.csv               (1회성 매핑 캐시)
  db/fundamentals/{종목코드}_{연도}_{보고서}.csv   (원본 계정 전체)
  db/fundamentals/summary.csv                     (종목별 핵심 지표 요약, 누적 갱신)

실행:
  python dart_fundamentals.py            # 대상 종목 최신 보고서 수집
  python dart_fundamentals.py map        # corp_code 매핑만 재생성
"""

import os
import io
import sys
import csv
import time
import zipfile
from datetime import datetime
import xml.etree.ElementTree as ET

import pandas as pd
import requests

import config  # .env 로드

DART_BASE = "https://opendart.fss.or.kr/api"
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
FUND_DIR = "./db/fundamentals"
MAP_CSV = f"{FUND_DIR}/corp_code_map.csv"
SUMMARY_CSV = f"{FUND_DIR}/summary.csv"

# 분기 → (bsns_year, reprt_code) 우선순위: 가장 최근 확정 보고서부터
REPRT_ORDER = ["11014", "11012", "11013", "11011"]  # 3Q, 반기, 1Q, 사업보고서
REPRT_NAME = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "FY"}


def _check_key():
    if not DART_API_KEY:
        print("[ERROR] DART_API_KEY 없음 — .env 확인")
        sys.exit(1)


def build_corp_code_map():
    """corpCode.xml (zip) → stock_code ↔ corp_code 매핑 CSV."""
    print("[map] corpCode.xml 다운로드...")
    r = requests.get(f"{DART_BASE}/corpCode.xml",
                     params={"crtfc_key": DART_API_KEY}, timeout=60)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml_data = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_data)
    rows = []
    for el in root.iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if len(stock) == 6:  # 상장사만
            rows.append({
                "stock_code": stock,
                "corp_code": (el.findtext("corp_code") or "").strip(),
                "corp_name": (el.findtext("corp_name") or "").strip(),
            })
    os.makedirs(FUND_DIR, exist_ok=True)
    pd.DataFrame(rows).to_csv(MAP_CSV, index=False, encoding="utf-8-sig")
    print(f"[map] 상장사 {len(rows)}개 매핑 저장: {MAP_CSV}")


def load_corp_map():
    if not os.path.exists(MAP_CSV):
        build_corp_code_map()
    m = pd.read_csv(MAP_CSV, dtype=str)
    return dict(zip(m["stock_code"].str.zfill(6), m["corp_code"]))


def fetch_financials(corp_code, year, reprt_code):
    """전체 재무제표. 연결(CFS) 우선, 없으면 별도(OFS)."""
    for fs_div in ("CFS", "OFS"):
        params = {
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bsns_year": str(year), "reprt_code": reprt_code, "fs_div": fs_div,
        }
        try:
            r = requests.get(f"{DART_BASE}/fnlttSinglAcntAll.json",
                             params=params, timeout=15)
            data = r.json()
        except Exception as e:
            return None, f"요청 실패: {e}"
        if data.get("status") == "000" and data.get("list"):
            return data["list"], None
        if data.get("status") == "020":     # 사용한도 초과
            return None, "RATE_LIMIT"
    return None, data.get("message", "데이터 없음")


def extract_summary(rows, code, year, reprt):
    """손익계산서에서 매출/영업이익/당기순이익 추출."""
    KEYS = {
        "revenue":   ("ifrs-full_Revenue", "수익(매출액)", "매출액", "영업수익"),
        "op_profit": ("dart_OperatingIncomeLoss", "영업이익", "영업이익(손실)"),
        "net_income": ("ifrs-full_ProfitLoss", "당기순이익", "당기순이익(손실)",
                       "분기순이익", "반기순이익"),
    }
    out = {"code": code, "year": year, "reprt": REPRT_NAME.get(reprt, reprt),
           "collected": datetime.today().strftime("%Y%m%d")}
    for field, names in KEYS.items():
        val = None
        for r in rows:
            sj = r.get("sj_div", "")
            if sj not in ("IS", "CIS"):    # 손익계산서만
                continue
            acc_id = (r.get("account_id") or "").strip()
            acc_nm = (r.get("account_nm") or "").strip()
            if acc_id in names or acc_nm in names:
                raw = (r.get("thstrm_amount") or "").replace(",", "").strip()
                try:
                    val = int(raw)
                except ValueError:
                    continue
                break
        out[field] = val
    return out


def target_codes():
    from credit_collector import target_codes as tc
    return tc()


def main():
    _check_key()
    os.makedirs(FUND_DIR, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == "map":
        build_corp_code_map()
        return

    corp_map = load_corp_map()
    codes = target_codes()
    if not codes:
        print("[fund] 수집 대상 없음")
        return

    # 최근 확정 보고서 추정: 현재 분기 기준 직전 보고서부터 시도
    now = datetime.today()
    tries = []
    for back in range(0, 2):  # 올해, 작년
        y = now.year - back
        for rc in REPRT_ORDER:
            tries.append((y, rc))

    summaries = []
    existing = set()
    if os.path.exists(SUMMARY_CSV):
        old = pd.read_csv(SUMMARY_CSV, dtype=str)
        existing = set(zip(old["code"].str.zfill(6), old["year"], old["reprt"]))

    n_ok, n_skip, n_fail = 0, 0, 0
    for code in codes:
        corp = corp_map.get(code)
        if not corp:
            n_fail += 1
            continue
        got = False
        for year, rc in tries:
            if (code, str(year), REPRT_NAME[rc]) in existing:
                n_skip += 1
                got = True
                break
            rows, err = fetch_financials(corp, year, rc)
            if err == "RATE_LIMIT":
                print("[fund] DART 호출 한도 초과 — 중단 (내일 재시도)")
                got = True
                break
            time.sleep(0.15)
            if rows:
                raw_path = f"{FUND_DIR}/{code}_{year}_{REPRT_NAME[rc]}.csv"
                pd.DataFrame(rows).to_csv(raw_path, index=False, encoding="utf-8-sig")
                summaries.append(extract_summary(rows, code, year, rc))
                n_ok += 1
                got = True
                break
        if not got:
            n_fail += 1

    if summaries:
        new = pd.DataFrame(summaries)
        if os.path.exists(SUMMARY_CSV):
            new = pd.concat([pd.read_csv(SUMMARY_CSV, dtype=str), new.astype(str)],
                            ignore_index=True).drop_duplicates(
                            subset=["code", "year", "reprt"], keep="last")
        new.to_csv(SUMMARY_CSV, index=False, encoding="utf-8-sig")

    print(f"[fund] 신규 {n_ok}, 기존 {n_skip}, 실패 {n_fail} → {SUMMARY_CSV}")
    # 가드 판정용: 신규+기존이 0이면 실패
    if n_ok + n_skip == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
