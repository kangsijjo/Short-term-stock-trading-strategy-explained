"""
과거 분봉 백필 스크립트.

KIS API는 분봉을 최근 30일까지만 주지만, 우리가 매일 수집을 시작한 게
2026-05-18 부터라 그 이전 영업일들은 비어 있음. 이 스크립트는:

  1. db/daily/*.csv 의 종목별 60일치 일봉을 모아 union 함
  2. 30일 윈도우 안의 각 과거 영업일에 대해 trading_value 상위 30개를 산정
     (이게 그날의 "추정 TOP 30 ranking")
  3. 그 ranking 을 data/rankings/YYYYMMDD.csv 로 저장 (이미 있으면 skip)
  4. data_collector.save_minutes(date) 호출 → 누락된 종목 분봉만 KIS 에서 가져옴

사용법:
  python backfill_history.py                # 기본: 30일 전부터 어제까지
  python backfill_history.py --days 14      # 14일치만
  python backfill_history.py --dry-run      # API 호출 없이 무엇을 할지만 출력

한계 (정직):
  - 생존자 편향: db/daily 는 최근 스냅숏 기준 TOP 100 의 역사. 5/10 에 TOP 30
    이었지만 5/28 에 TOP 100 밖으로 밀린 종목은 누락. 실제 그날 TOP 30 과 어긋남.
  - db/daily 표본이 작으면 (지금 ~33개) 진짜 TOP 30 재구성에 종목 풀이 부족.
  - KIS rate limit: 30종목 × 14콜/종목 × 25일 ≈ 10,500콜. 1~2시간 예상.
  - 진행 중 끊겨도 멱등 (재실행하면 누락분만 이어서 받음).
"""

import sys
import os
import time
import csv
import glob
from datetime import datetime, timedelta

import pandas as pd

import csv
import config
from data_collector import save_minutes, _is_excluded, _month_dir
from kis_api import get_full_day_historical_minutes, KIS_ENV


def save_minutes_historical(date_str, codes):
    """과거 분봉을 FHKST03010230 으로 받아서 db/minute/ 에 저장.

    save_minutes 와 다른 점:
      - get_full_day_historical_minutes 사용 (1년치 과거 가능, but 실전 키 필수)
      - 종목별 skip-if-exists (멱등)
    """
    minute_day_dir = f"{_month_dir(config.DB_MINUTE_DIR, date_str)}/{date_str}"
    os.makedirs(minute_day_dir, exist_ok=True)

    n_saved = n_skip = n_fail = 0
    total = len(codes)
    for i, item in enumerate(codes, 1):
        code, name = item[0], item[1]
        out_path = f"{minute_day_dir}/{code}.csv"
        legacy_path = f"{config.MINUTE_DIR}/{code}_{date_str}.csv"
        if os.path.exists(out_path) or os.path.exists(legacy_path):
            n_skip += 1
            continue
        try:
            bars = get_full_day_historical_minutes(code, date_str)
        except Exception as e:
            print(f"  [{i:3}/{total}] {code} 실패: {e}")
            n_fail += 1
            continue
        if not bars:
            print(f"  [{i:3}/{total}] {code} {name}: 데이터 없음")
            n_fail += 1
            continue
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=["date","time","open","high","low","close","volume"])
            writer.writeheader()
            for b in bars:
                writer.writerow(b)
        n_saved += 1
        if i <= 3 or i % 10 == 0 or i == total:
            print(f"  [{i:3}/{total}] saved={n_saved} skip={n_skip} fail={n_fail}")
    print(f"  [{date_str}] 완료: 저장 {n_saved}, 이미 있음 {n_skip}, 실패 {n_fail}")


# KIS 분봉 윈도우 (영업일 아닌 달력일 기준, 보수적으로 35일)
KIS_MINUTE_WINDOW_CALENDAR_DAYS = 35

# 호출 간 sleep (초)
SLEEP_BETWEEN_DATES = 1.0


def load_union_daily():
    """db/daily/*.csv 전부 합쳐서 (code, bar_date) 중복 제거.

    Returns: DataFrame[bar_date, code, name, trading_value, close, change_pct, volume]
    """
    files = sorted(glob.glob(f"{config.DB_DAILY_DIR}/*/*.csv"))
    if not files:
        print(f"[error] {config.DB_DAILY_DIR} 에 데이터가 없습니다.")
        print("        먼저 `python data_collector.py daily` 로 최소 한 번 수집하세요.")
        sys.exit(1)

    dfs = []
    for f in files:
        df = pd.read_csv(f, encoding="utf-8-sig",
                         dtype={"code": str, "bar_date": str})
        dfs.append(df)
    all_daily = pd.concat(dfs, ignore_index=True)
    all_daily = all_daily.drop_duplicates(subset=["code", "bar_date"], keep="last")
    print(f"[info] db/daily 통합: {len(files)} 파일, "
          f"{all_daily['code'].nunique()} 종목, "
          f"{all_daily['bar_date'].nunique()} 영업일, "
          f"{len(all_daily)} 행")
    return all_daily


def target_business_days(all_daily, days_back):
    """백필 대상 영업일 목록 반환.

    - all_daily 에 존재하는 bar_date 중에서
    - 오늘로부터 days_back 일 이내 (달력일)
    - 오늘은 제외 (오늘 데이터는 EOD 작업이 처리)
    """
    today = datetime.now().strftime("%Y%m%d")
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    dates = sorted(all_daily["bar_date"].unique())
    return [d for d in dates if cutoff <= d < today]


def synthesize_ranking(all_daily, date_str, top_n=None):
    """해당 날짜의 trading_value 상위 N개를 ranking CSV 형식 DataFrame 으로 반환 (raw, ETF 포함).

    ETF/우선주 필터는 백테스트 단계의 ENABLE_ETF_FILTER 에서 처리하므로 여기선 거르지 않음.
    config.TOP_N_STOCKS (현재 50) 기준 raw 슬라이싱.
    """
    top_n = top_n or config.TOP_N_STOCKS
    day = all_daily[all_daily["bar_date"] == date_str].copy()
    if day.empty:
        return None
    day = day.sort_values("trading_value", ascending=False).head(top_n)
    day = day.reset_index(drop=True)
    ranking = pd.DataFrame({
        "snapshot_time": "1530",
        "rank": range(1, len(day) + 1),
        "code": day["code"].apply(lambda c: str(c).zfill(6)),
        "name": day["name"],
        "current_price": day["close"],
        "change_pct": day["change_pct"],
        "volume": day["volume"],
        "trading_value": day["trading_value"],
    })
    return ranking


def write_ranking_csv(ranking_df, date_str):
    """ranking DataFrame 을 data/rankings/{date}.csv 로 저장."""
    out_path = f"{config.RANKING_DIR}/{date_str}.csv"
    os.makedirs(config.RANKING_DIR, exist_ok=True)
    ranking_df.to_csv(out_path, encoding="utf-8-sig", index=False)
    return out_path


def has_complete_minutes(date_str, ranking_codes):
    """ranking 의 모든 종목에 대한 분봉 파일이 이미 있으면 True."""
    yyyy_mm = f"{date_str[:4]}-{date_str[4:6]}"
    minute_dir = f"{config.DB_MINUTE_DIR}/{yyyy_mm}/{date_str}"
    if not os.path.isdir(minute_dir):
        return False
    for code in ranking_codes:
        if not os.path.exists(f"{minute_dir}/{code}.csv"):
            return False
    return True


def codes_from_ranking_df(ranking_df):
    """save_minutes 가 요구하는 (code, name, first_seen_at) 튜플 리스트."""
    return [(str(r["code"]).zfill(6), r["name"], "1530")
            for _, r in ranking_df.iterrows()]


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    days_back = KIS_MINUTE_WINDOW_CALENDAR_DAYS
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days_back = int(args[i + 1])

    print(f"=== backfill_history.py ===")
    print(f"days_back: {days_back} (달력일)")
    print(f"dry_run:   {dry_run}")
    print()

    # 1. db/daily 통합
    all_daily = load_union_daily()

    # 2. 대상 날짜 추출
    dates = target_business_days(all_daily, days_back)
    print(f"\n대상 영업일: {len(dates)}개")
    if dates:
        print(f"  범위: {dates[0]} ~ {dates[-1]}")
    print()

    if not dates:
        print("[info] 백필할 날짜 없음")
        return

    # 3. 각 날짜 처리
    total_to_fetch = 0
    for i, date_str in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] {date_str}")

        # ranking 처리
        # - 원본 수집 (multi-snapshot): 보존
        # - 합성 (단일 snapshot=1530) 또는 없음: raw 50 으로 (재)합성
        ranking_path = f"{config.RANKING_DIR}/{date_str}.csv"
        is_synthesized = False
        if os.path.exists(ranking_path):
            existing = pd.read_csv(ranking_path, encoding="utf-8-sig",
                                   dtype={"code": str})
            snaps = existing.get("snapshot_time", pd.Series(dtype=str)).astype(str).unique()
            is_synthesized = (len(snaps) == 1 and snaps[0] in ("1530", "1530.0"))

            if is_synthesized:
                # 옛 합성 ranking → raw 50 으로 재합성 (ETF 포함)
                ranking_df = synthesize_ranking(all_daily, date_str)
                if ranking_df is None or ranking_df.empty:
                    print(f"    [skip] db/daily 에 {date_str} 데이터 없음, 기존 ranking 유지")
                    ranking_df = existing
                else:
                    if not dry_run:
                        write_ranking_csv(ranking_df, date_str)
                    print(f"    합성 ranking → raw {len(ranking_df)} 재합성 "
                          f"(top 5: {list(ranking_df['code'].head(5))})")
            else:
                print(f"    원본 수집 ranking, 그대로 사용: {ranking_path}")
                ranking_df = existing
        else:
            ranking_df = synthesize_ranking(all_daily, date_str)
            if ranking_df is None or ranking_df.empty:
                print(f"    [skip] db/daily 에 {date_str} 데이터 없음")
                continue
            if not dry_run:
                write_ranking_csv(ranking_df, date_str)
            print(f"    ranking 신규 합성: raw {len(ranking_df)} 종목 "
                  f"(top 5: {list(ranking_df['code'].head(5))})")

        codes = codes_from_ranking_df(ranking_df)
        ranking_codes = [c for c, _, _ in codes]

        # 분봉 완전 수집 여부 확인
        if has_complete_minutes(date_str, ranking_codes):
            print(f"    분봉 이미 완전 수집됨, skip")
            continue

        # 분봉 수집 — FHKST03010230 (과거 분봉, prod 키 필수)
        if dry_run:
            print(f"    [dry-run] save_minutes_historical('{date_str}', {len(codes)} 종목)")
            total_to_fetch += len(codes)
        else:
            if KIS_ENV != "prod":
                print(f"    [warn] 현재 KIS_ENV={KIS_ENV}. 과거 분봉은 prod 키 필요. "
                      f".env 에서 KIS_ENV=prod 로 바꾸고 재실행하세요.")
                continue
            print(f"    분봉 백필 시작 ({len(codes)} 종목)...")
            try:
                save_minutes_historical(date_str, codes)
            except Exception as e:
                print(f"    [error] save_minutes_historical 실패: {e}")
                continue
            time.sleep(SLEEP_BETWEEN_DATES)

    print()
    print(f"=== 완료 ===")
    if dry_run:
        print(f"dry-run: 총 {total_to_fetch} 종목 분봉 호출 예상")
    else:
        print(f"실제 수집 완료. db/minute 확인.")


if __name__ == "__main__":
    main()
