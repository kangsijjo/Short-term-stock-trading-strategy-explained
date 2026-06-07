"""
기존 paper_signals.csv 의 빈 name 컬럼을 name_cache 로 일회성 채움.

실행:
  python fix_paper_signals_names.py

전 후 비교 출력 + 백업 (paper_signals.csv.bak) 자동 생성.
"""

import os
import shutil
import pandas as pd

from build_name_cache import load_name_cache

CSV = "./paper_signals.csv"
BAK = "./paper_signals.csv.bak"


def main():
    if not os.path.exists(CSV):
        print(f"[error] {CSV} 없음.")
        return

    name_cache = load_name_cache()
    if not name_cache:
        print("[error] name_cache.csv 없음. build_name_cache.py 먼저 실행.")
        return

    df = pd.read_csv(CSV, dtype={"code": str}, encoding="utf-8-sig")
    df["code"] = df["code"].astype(str).str.zfill(6)

    # name 컬럼 빈/NaN 카운트
    before_empty = df["name"].astype(str).str.strip().isin(["", "nan", "None"]).sum()
    print(f"[before] 빈 name: {before_empty} / {len(df)}")

    # 백업
    shutil.copy(CSV, BAK)
    print(f"[backup] {BAK}")

    # 빈 name 만 name_cache 로 채움
    def fill(row):
        nm = str(row["name"]).strip() if pd.notna(row["name"]) else ""
        if nm in ("", "nan", "None"):
            return name_cache.get(row["code"], "")
        return nm

    df["name"] = df.apply(fill, axis=1)

    after_empty = df["name"].astype(str).str.strip().isin(["", "nan", "None"]).sum()
    print(f"[after]  빈 name: {after_empty} / {len(df)}")
    print(f"[filled] {before_empty - after_empty} 건 채움")

    # 원래 컬럼 순서 보존
    df.to_csv(CSV, index=False, encoding="utf-8-sig")
    print(f"[saved] {CSV}")

    # 미해결 코드 (cache 에도 없는 종목 = 상장폐지 가능성) 출력
    still_empty = df[df["name"].astype(str).str.strip().isin(["", "nan", "None"])]["code"].unique()
    if len(still_empty) > 0:
        print(f"\n[still empty] cache 에도 없는 코드 {len(still_empty)} 개 (상장폐지 추정):")
        for c in still_empty[:10]:
            print(f"  {c}")
        if len(still_empty) > 10:
            print(f"  ... {len(still_empty)-10}개 더")


if __name__ == "__main__":
    main()
