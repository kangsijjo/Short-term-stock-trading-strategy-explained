"""
키움 신용·프로그램매매 과거 백필 — AI 학습용 (조회 전용, 주문 없음).

전략: 전 종목·전 기간이 아니라 trades_history_v3.csv 에 등장하는
(종목, 신호일) 지점만 커버 — 종목별로 연속조회(next-key) 페이지를
신호 최소일까지 거슬러 수집. 종목당 파일 저장이라 중단 후 재실행 시 이어받음.

수집:
  ka10013 신용매매동향(융자)  → db/kiwoom_hist/credit/{code}.csv
  ka90013 종목일별 프로그램매매 → db/kiwoom_hist/program/{code}.csv

사용:
  python kiwoom_backfill.py            # credit + program 백필 (수 시간, 재개 가능)
  python kiwoom_backfill.py credit 20  # credit 만, 20종목 테스트
  python kiwoom_backfill.py merge      # 백필 → 학습 피처 생성 (ai_data/kiwoom_hist_features.csv)

백필 완료 후: merge → python make_trades_history_v3.py → python ai_trainer_v4.py

주의: 키움이 과거 몇 년까지 제공하는지는 실행에서 확인됨 (로그의 '도달 최소일' 참조).
상장폐지 종목은 조회 불가일 수 있음 — 피처 결측으로 처리 (라벨 아님 → 학습엔 무해).
"""

import os
import sys
import time
from datetime import datetime

import pandas as pd

import config  # noqa: F401  (.env)
from progress import bar

TRADES_CSV = "./trades_history_v3.csv"
HIST_DIR = "./db/kiwoom_hist"
FEAT_OUT = "./ai_data/kiwoom_hist_features.csv"
MAX_PAGES = 60          # 종목당 페이지 상한 (안전장치)
SLEEP = 0.25            # 호출 간격 (유량 제한)
BUFFER_DAYS = 45        # 신호 최소일보다 이만큼 더 과거까지 (5일 피처 여유)


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("+", "").strip() or 0)
    except Exception:
        return 0.0


def _clients():
    from kiwoom_collector import _clients as c
    return c()


def needed_codes():
    """code → 필요한 최소 날짜 (신호 최소일 - 버퍼)."""
    if not os.path.exists(TRADES_CSV):
        print(f"[error] {TRADES_CSV} 없음 — make_trades_history_v3.py 먼저")
        sys.exit(1)
    t = pd.read_csv(TRADES_CSV, dtype={"code": str, "date": str})
    t["code"] = t["code"].str.zfill(6)
    g = t.groupby("code")["date"].min()
    out = {}
    for code, d in g.items():
        dt = datetime.strptime(str(d), "%Y%m%d") - pd.Timedelta(days=BUFFER_DAYS)
        out[code] = dt.strftime("%Y%m%d")
    return out


def _paginate(call, list_key, min_date):
    """연속조회로 min_date 까지 페이지 수집. (rows, 도달최소일)"""
    rows, cont, nkey = [], "N", ""
    for _ in range(MAX_PAGES):
        r = call(cont, nkey)
        lst = r.get(list_key) or []
        rows.extend(lst)
        time.sleep(SLEEP)
        oldest = min((str(x.get("dt", "9")) for x in lst), default="9")
        if oldest != "9" and oldest <= min_date:
            break
        if str(r.get("cont-yn", "N")).upper() != "Y":
            break
        nkey = r.get("next-key") or ""
        cont = "Y"
        if not nkey:
            break
    return rows


def backfill(kind, limit=None):
    si, mc = _clients()
    targets = needed_codes()
    codes = list(targets.keys())
    if limit:
        codes = codes[:limit]
    sub = "credit" if kind == "credit" else "program"
    out_dir = f"{HIST_DIR}/{sub}"
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.today().strftime("%Y%m%d")

    n_done = n_skip = n_fail = 0
    reached = []
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        path = f"{out_dir}/{code}.csv"
        if os.path.exists(path):
            n_skip += 1
            continue
        min_date = targets[code]
        try:
            if kind == "credit":
                rows = _paginate(
                    lambda c, k: si.credit_trading_trend_request_ka10013(
                        stock_code=code, date=today, query_type="1",
                        cont_yn=c, next_key=k),
                    "crd_trde_trend", min_date)
            else:
                rows = _paginate(
                    lambda c, k: mc.stockwise_program_trading_by_day_request_ka90013(
                        stock_code=code, amount_quantity_type="1", date=today,
                        cont_yn=c, next_key=k),
                    "stk_daly_prm_trde_trnsn", min_date)
            if rows:
                df = pd.DataFrame(rows)
                df["code"] = code
                df.to_csv(path, index=False, encoding="utf-8-sig")
                n_done += 1
                oldest = min(str(x.get("dt", "")) for x in rows)
                reached.append(oldest)
            else:
                n_fail += 1   # 상장폐지 등 — 파일 없음 = merge 때 결측
        except Exception as e:
            n_fail += 1
            if n_fail <= 5:
                print(f"  [warn] {code}: {str(e)[:120]}")
        if i % 25 == 0 or i == len(codes):
            print(f"  [{kind}] " + bar(i, len(codes), t0,
                  extra=f"저장 {n_done} 스킵 {n_skip} 실패 {n_fail}"), flush=True)

    print(f"[{kind}] 완료 — 저장 {n_done}, 기존 {n_skip}, 실패 {n_fail}")
    if reached:
        print(f"  도달 최소일 중앙값: {sorted(reached)[len(reached)//2]} "
              f"(이보다 오래된 신호는 피처 결측)")


def merge():
    """백필 데이터 → (code, date) 피처 CSV."""
    t = pd.read_csv(TRADES_CSV, dtype={"code": str, "date": str})
    t["code"] = t["code"].str.zfill(6)
    pairs = t[["code", "date"]].drop_duplicates()
    print(f"[merge] 대상 {len(pairs):,} (code, date) 지점")

    # 신호일 거래대금 (정규화용) — 캐시 로더
    from strategies.daily_loader import load_macro_daily
    md = load_macro_daily()
    md["date"] = md["date"].astype(str)
    tv_map = {(c, d): v for c, d, v in
              zip(md["code"], md["date"], md["trading_value"])}
    del md

    feats = []
    by_code = {c: g.sort_values("date") for c, g in pairs.groupby("code")}
    for code, g in by_code.items():
        cr_path = f"{HIST_DIR}/credit/{code}.csv"
        pr_path = f"{HIST_DIR}/program/{code}.csv"
        cr = pr = None
        if os.path.exists(cr_path):
            cr = pd.read_csv(cr_path, dtype={"dt": str}).sort_values("dt")
            cr["remn_n"] = cr["remn"].map(_num)
            cr["remn_rt_n"] = cr["remn_rt"].map(_num)
            cr = cr.set_index("dt")
        if os.path.exists(pr_path):
            pr = pd.read_csv(pr_path, dtype={"dt": str}).sort_values("dt")
            pr["net_n"] = pr["prm_netprps_amt"].map(_num)
            pr = pr.set_index("dt")

        for d in g["date"]:
            row = {"code": code, "date": d}
            if cr is not None and len(cr):
                upto = cr.loc[cr.index <= d]
                if len(upto):
                    row["crd_remn_rt"] = float(upto["remn_rt_n"].iloc[-1])
                    if len(upto) >= 6 and upto["remn_n"].iloc[-6] > 0:
                        row["crd_remn_chg_5d"] = float(
                            (upto["remn_n"].iloc[-1] / upto["remn_n"].iloc[-6] - 1) * 100)
            if pr is not None and len(pr):
                upto = pr.loc[pr.index <= d]
                if len(upto):
                    net5 = float(upto["net_n"].tail(5).sum())
                    tv = float(tv_map.get((code, d), 0) or 0)
                    # 프로그램 5일 순매수금액 / 신호일 거래대금 (단위 보정은 모델이 흡수)
                    row["prm_net_5d_ratio"] = net5 / tv if tv > 0 else None
                    row["prm_net_5d_raw"] = net5
            feats.append(row)

    out = pd.DataFrame(feats)
    os.makedirs("./ai_data", exist_ok=True)
    out.to_csv(FEAT_OUT, index=False, encoding="utf-8-sig")
    cov_c = out["crd_remn_rt"].notna().mean() * 100 if "crd_remn_rt" in out else 0
    cov_p = out["prm_net_5d_ratio"].notna().mean() * 100 if "prm_net_5d_ratio" in out else 0
    print(f"[merge] {len(out):,}행 저장 → {FEAT_OUT}")
    print(f"  커버리지: 신용 {cov_c:.0f}% / 프로그램 {cov_p:.0f}%")
    print("다음: python make_trades_history_v3.py && python ai_trainer_v4.py")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "all"
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if cmd == "merge":
        merge()
        return
    if cmd in ("all", "credit"):
        backfill("credit", limit)
    if cmd in ("all", "program"):
        backfill("program", limit)
    print("\n백필 끝 — 피처 생성: python kiwoom_backfill.py merge")


if __name__ == "__main__":
    main()
