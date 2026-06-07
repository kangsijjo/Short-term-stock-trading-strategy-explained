"""
FinanceDataReader (fdr) 수정주가 확인 — pykrx 와 비교.

목적:
  1. fdr 정상 동작 + 종목 데이터 받기 확인
  2. 액면분할 종목 (카카오 035720, 2021년 5월 1/5 분할) 으로 수정주가 적용 여부 검증
  3. 결과: 3년치 KOSDAQ 전체 재수집 가치 판단

전제: pip install finance-datareader
"""

import sys

try:
    import FinanceDataReader as fdr
except ImportError:
    print("[ERROR] FinanceDataReader 미설치.")
    print("  설치: pip install finance-datareader")
    sys.exit(1)

import pandas as pd


def main():
    print("=" * 70)
    print(" 1. fdr 005930 (삼성전자) 1년 데이터")
    print("=" * 70)
    df_ss = fdr.DataReader("005930", "2025-01-01", "2025-12-31")
    print(df_ss.head(3))
    print(f"  rows: {len(df_ss)}")
    print(f"  columns: {list(df_ss.columns)}")

    # 2. 액면분할 종목 — 카카오 (035720) 2021년 4월 28일 1/5 분할
    print("\n" + "=" * 70)
    print(" 2. fdr 035720 카카오 — 2021/4/28 액면분할 1/5")
    print("=" * 70)
    df_kakao = fdr.DataReader("035720", "2021-04-23", "2021-05-05")
    print(df_kakao)
    print()
    print(" 해석:")
    print("  - 4/26~28 종가 vs 4/29~30 종가 비교")
    print("  - fdr 가 수정주가 적용했다면: 분할 전 가격이 분할 후 가격 수준으로 보정됨")
    print("    예) 분할 전 종가 ~55만원이 ~11만원으로 보정 (5분의 1)")
    print("  - 미적용이면: 분할 전 55만원, 분할 후 11만원 (raw)")

    # 3. KOSDAQ 전종목 마스터
    print("\n" + "=" * 70)
    print(" 3. fdr KOSDAQ 전종목 마스터")
    print("=" * 70)
    kosdaq = fdr.StockListing("KOSDAQ")
    print(f"  KOSDAQ 종목 수: {len(kosdaq)}")
    print(kosdaq.head(3))

    # 4. 결론
    print("\n" + "=" * 70)
    print(" 4. 다음 결정")
    print("=" * 70)
    print(" 2번 카카오 가격이 4/26→27→28 사이 동일 수준 + 4/29 부터 동일 수준 = 수정주가 적용 OK")
    print(" → 3년치 재수집 가치 큼 (단방향 컷오프 불필요해짐)")
    print()
    print(" 재수집 시간 = 종목 수 × 호출 시간:")
    print("   - KOSDAQ 1700개 종목 × ~0.3초 = 약 8.5분")
    print("   - 단 fdr 호출 빈도 제한 있을 수 있어 안전 sleep 시 30분~1시간 예상")


if __name__ == "__main__":
    main()
