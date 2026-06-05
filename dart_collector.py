"""
DART (전자공시시스템) → 일자별 공시 목록 수집.

API 키 발급 필수:
  1. https://opendart.fss.or.kr/ 가입
  2. "오픈API 신청" → 인증키 받기
  3. .env 에 추가: DART_API_KEY=발급받은_키

호출 시점: 매일 평일 19:00 권장 (당일 공시 마감 후, KIS_DART 작업).

사용법:
  python dart_collector.py today          # 오늘 공시
  python dart_collector.py date 20260604  # 특정 날짜
  python dart_collector.py corp 005930    # 특정 종목 최근 공시

저장: db/dart/YYYY-MM/YYYYMMDD.csv
스키마: code, corp_code, corp_name, report_nm, rcept_dt, rcept_no, flr_nm
"""

import sys
import os
import json
import csv
from datetime import datetime

import requests

import config


DART_BASE = "https://opendart.fss.or.kr/api"
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()


def _month_dir(base_dir, date_str):
    yyyy_mm = f"{date_str[:4]}-{date_str[4:6]}"
    path = f"{base_dir}/{yyyy_mm}"
    os.makedirs(path, exist_ok=True)
    return path


def _check_api_key():
    if not DART_API_KEY:
        print("[ERROR] DART_API_KEY 환경변수가 없습니다.")
        print("        .env 파일에 DART_API_KEY=발급받은_키 추가 후 재시도.")
        sys.exit(1)


def fetch_disclosures(begin_date, end_date=None, corp_code=None, page_count=100, max_pages=10):
    """DART 공시검색 API 호출. 페이징 처리하여 모든 공시 반환.

    Args:
        begin_date / end_date: YYYYMMDD
        corp_code: DART 고유번호 8자리 (없으면 전체)

    Returns: list[dict]
    """
    _check_api_key()
    if end_date is None:
        end_date = begin_date

    results = []
    for page in range(1, max_pages + 1):
        params = {
            "crtfc_key": DART_API_KEY,
            "bgn_de": begin_date,
            "end_de": end_date,
            "page_no": page,
            "page_count": page_count,
        }
        if corp_code:
            params["corp_code"] = corp_code

        try:
            r = requests.get(f"{DART_BASE}/list.json", params=params, timeout=15)
            data = r.json()
        except Exception as e:
            print(f"  [error] DART API 호출 실패 page={page}: {e}")
            break

        status = data.get("status", "")
        if status == "013":  # 조회된 데이터 없음
            break
        if status != "000":
            print(f"  [warn] DART status={status} msg={data.get('message')}")
            break

        items = data.get("list", [])
        results.extend(items)
        total_page = data.get("total_page", 1)
        if page >= total_page:
            break

    return results


def save_dart_for_date(date_str=None):
    """특정 날짜 전체 공시 목록 저장 → db/dart/YYYY-MM/YYYYMMDD.csv"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    out_dir = _month_dir(config.DB_DART_DIR, date_str)
    out_path = f"{out_dir}/{date_str}.csv"
    if os.path.exists(out_path):
        print(f"[dart] 이미 있음, 스킵: {out_path}")
        return

    print(f"[dart] {date_str} 공시 수집 중...")
    items = fetch_disclosures(date_str)
    if not items:
        print(f"  {date_str} 공시 없음 (휴장 또는 미공시)")
        # 빈 파일이라도 만들어서 "확인했다" 마킹
        open(out_path, "w", encoding="utf-8-sig").close()
        return

    # CSV 저장 (DART API 응답 그대로)
    fieldnames = list(items[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for it in items:
            writer.writerow(it)

    print(f"[dart] {len(items)}건 저장: {out_path}")


def save_dart_for_corp(corp_code, date_from, date_to=None):
    """특정 종목 공시 (corp_code 는 DART 고유번호 8자리)."""
    if date_to is None:
        date_to = datetime.now().strftime("%Y%m%d")
    items = fetch_disclosures(date_from, date_to, corp_code=corp_code)
    print(f"[dart_corp] {corp_code}: {date_from}~{date_to}: {len(items)}건")
    for it in items[:20]:
        print(f"  {it.get('rcept_dt')} {it.get('report_nm')}")
    return items


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "today":
        save_dart_for_date()
    elif cmd == "date":
        if len(sys.argv) < 3:
            print("사용법: python dart_collector.py date YYYYMMDD")
            sys.exit(1)
        save_dart_for_date(sys.argv[2])
    elif cmd == "corp":
        if len(sys.argv) < 3:
            print("사용법: python dart_collector.py corp CORP_CODE [DATE_FROM] [DATE_TO]")
            sys.exit(1)
        corp = sys.argv[2]
        df = sys.argv[3] if len(sys.argv) >= 4 else datetime.now().strftime("%Y%m%d")
        dt = sys.argv[4] if len(sys.argv) >= 5 else None
        save_dart_for_corp(corp, df, dt)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
