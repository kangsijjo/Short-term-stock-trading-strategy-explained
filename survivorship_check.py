"""
생존자 편향 검증 — macro_data 에 사라진 종목이 있는지.

pykrx 가 (A) 그 시점 데이터 vs (B) 현재 종목만 주는지 결정.
- 사라진 종목 다수 = (A), 생존자 편향 없음
- 사라진 종목 0~소수 = (B), 생존자 편향 강함
"""

import glob
import pandas as pd

DATA_DIR = "./macro_data/daily"


def main():
    files = sorted(glob.glob(f"{DATA_DIR}/*.csv"))
    print(f"=== 생존자 편향 검증 ===")
    print(f"전체 파일: {len(files)}")
    print(f"기간: {files[0].split('/')[-1]} ~ {files[-1].split('/')[-1]}")

    # 첫 90 영업일 (약 4.5개월) vs 마지막 90 영업일
    first_files = files[:90]
    last_files = files[-90:]

    first_codes = set()
    for f in first_files:
        df = pd.read_csv(f, dtype={"code": str})
        first_codes.update(df["code"].astype(str).str.zfill(6))

    last_codes = set()
    for f in last_files:
        df = pd.read_csv(f, dtype={"code": str})
        last_codes.update(df["code"].astype(str).str.zfill(6))

    disappeared = first_codes - last_codes
    new = last_codes - first_codes
    both = first_codes & last_codes

    print(f"\n[종목 수 분포]")
    print(f"  처음 90일 unique codes: {len(first_codes):,}")
    print(f"  마지막 90일 unique codes: {len(last_codes):,}")
    print(f"  양 구간 다 존재 (공통):  {len(both):,}")
    print(f"  처음에만 (사라진):       {len(disappeared):,}  ← 폐지/거래정지/이전 의심")
    print(f"  마지막에만 (신규 상장):  {len(new):,}")

    # 사라진 종목 샘플
    if disappeared:
        print(f"\n[사라진 종목 샘플 (앞 10개)]")
        for code in sorted(disappeared)[:10]:
            print(f"  {code}")

    # 판단
    pct_disappeared = len(disappeared) / max(len(first_codes), 1) * 100
    print(f"\n=== 결론 ===")
    if pct_disappeared >= 5:
        print(f"  ✅ 생존자 편향 LOW — 사라진 종목 {len(disappeared)}개 ({pct_disappeared:.1f}%)")
        print(f"     pykrx 가 그 시점 KRX 데이터를 받음. 폐지 종목 데이터 포함.")
    elif pct_disappeared >= 1:
        print(f"  ⚠️  생존자 편향 MEDIUM — 사라진 종목 {len(disappeared)}개 ({pct_disappeared:.1f}%)")
        print(f"     부분적 편향 있을 수 있음. 추가 검증 필요.")
    else:
        print(f"  🔴 생존자 편향 HIGH — 사라진 종목 {len(disappeared)}개 ({pct_disappeared:.1f}%)")
        print(f"     pykrx 가 현재 살아있는 종목만 줄 가능성. 메인 전략 결과 의심.")

    # 추가 — 특정 시점 폐지 종목 사례
    print(f"\n[참고: 실제 폐지 종목 (2023~2025년)]")
    known_delisted = [
        # 사용자가 기억하는 폐지/거래정지 종목 ex.
        # "029460", "204210", "008290" 등
    ]
    if known_delisted:
        for code in known_delisted:
            status = "✅ 데이터에 있음" if code in first_codes else "❌ 데이터에 없음"
            print(f"  {code}: {status}")


if __name__ == "__main__":
    main()
