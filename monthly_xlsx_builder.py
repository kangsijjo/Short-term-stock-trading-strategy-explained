"""월말 CSV → xlsx 합본 (시트 = 일자).

대상:
  db/investor/YYYY-MM/*.csv  →  db/xlsx/YYYY-MM_investor.xlsx
  db/daily/YYYY-MM/*.csv     →  db/xlsx/YYYY-MM_daily.xlsx
  (minute 은 데이터 양이 너무 커서 합본 생략)

사용법:
  py -3.11 monthly_xlsx_builder.py                # 전월 자동 (작업 스케줄러용)
  py -3.11 monthly_xlsx_builder.py 2026-05        # 특정 월 지정
  py -3.11 monthly_xlsx_builder.py 2026-05 daily  # 특정 월 + 특정 카테고리

의존성: pandas, openpyxl
"""

import sys
import os
import glob
from datetime import datetime

import config

try:
    import pandas as pd
except ImportError:
    print("[ERROR] pandas 미설치. `py -3.11 -m pip install pandas openpyxl` 실행하세요.")
    sys.exit(1)


CATEGORIES = {
    "investor": config.DB_INVESTOR_DIR,
    "daily":    config.DB_DAILY_DIR,
}


def build_one_category(year_month, category):
    """category: 'investor' or 'daily'"""
    base_dir = CATEGORIES[category]
    month_dir = f"{base_dir}/{year_month}"

    if not os.path.exists(month_dir):
        print(f"[skip] {category}: {month_dir} 폴더 없음")
        return False

    csv_files = sorted(glob.glob(f"{month_dir}/*.csv"))
    if not csv_files:
        print(f"[skip] {category}: CSV 파일 없음 in {month_dir}")
        return False

    os.makedirs(config.DB_XLSX_DIR, exist_ok=True)
    out_path = f"{config.DB_XLSX_DIR}/{year_month}_{category}.xlsx"

    print(f"[{category}] {len(csv_files)}개 CSV → {out_path}")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for f in csv_files:
            date_str = os.path.splitext(os.path.basename(f))[0]  # YYYYMMDD
            sheet_name = date_str  # 시트 이름 = YYYYMMDD (Excel 시트명 31자 한도 OK)
            try:
                df = pd.read_csv(f, encoding="utf-8-sig")
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"  + sheet '{sheet_name}': {len(df)}행")
            except Exception as e:
                print(f"  [error] {f}: {e}")

    return True


def previous_month_str():
    """현재 시각 기준 전월을 'YYYY-MM' 형태로 반환."""
    today = datetime.now()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def main():
    # 인자 파싱
    if len(sys.argv) >= 2:
        year_month = sys.argv[1]
        # 형식 검증 (YYYY-MM)
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError:
            print(f"[ERROR] year_month 형식 오류: '{year_month}' (예: 2026-05)")
            sys.exit(1)
    else:
        year_month = previous_month_str()
        print(f"[info] 대상 월 미지정 → 전월 '{year_month}' 자동 적용")

    if len(sys.argv) >= 3:
        categories = [sys.argv[2]]
        if categories[0] not in CATEGORIES:
            print(f"[ERROR] 알 수 없는 카테고리: '{categories[0]}'. 사용 가능: {list(CATEGORIES)}")
            sys.exit(1)
    else:
        categories = list(CATEGORIES.keys())

    print("=" * 60)
    print(f" 월말 xlsx 합본: {year_month}")
    print(f" 카테고리: {categories}")
    print("=" * 60)

    for cat in categories:
        build_one_category(year_month, cat)

    print("\n[done] 완료. 결과:", config.DB_XLSX_DIR)


if __name__ == "__main__":
    main()