"""
키움증권 모의투자 자동 집행기 — 메인 전략(high_500d_h40_MKT) 신호를 모의계좌에 집행.

의존: pip install kiwoom-rest-api   (PyPI 패키지명 주의 — "kiwoom-api" 아님)
인증: .env 의 KIWOOM_MOCK_APP_KEY / KIWOOM_MOCK_APP_SECRET (KIWOOM_ENV=mock)
      → 내부적으로 KIWOOM_API_KEY/KIWOOM_API_SECRET/KIWOOM_USE_SANDBOX 환경변수로 전달

명령:
  python kiwoom_trader.py status   # 예수금·잔고·미체결 출력 (연결 검증용 — 처음에 이걸 먼저)
  python kiwoom_trader.py buy      # 오늘 신호 종목 매수 주문 (시간외단일가, 16:00~18:00)
  python kiwoom_trader.py sell     # 보유 40영업일 도달 종목 매도 주문
  python kiwoom_trader.py daily    # sell → buy → status 순서 일괄 (스케줄러용)

운용 룰 — [2026-06-12 변경] 키움 모의서버는 시간외단일가 미지원(지정가/시장가만)이
확인되어, 백테스트 "원본 모드"(공식 성과 +139.9% 기준 모드)로 운용한다:
  - 매수: 신호 다음 영업일 09:01 시장가 (≈ 시가 체결). 슬롯 최대 10, 예수금/빈슬롯 분배.
  - 매도: 진입일 포함 40영업일째 15:21 시장가 (마감 동시호가 참여 ≈ 종가 체결).
  - 멱등: 같은 날 같은 종목 중복 주문 방지 (db/kiwoom/orders_*.csv 로그 기준).
  - `daily` 명령은 시계로 분기: 12시 이전 → 매수, 이후 → 매도 (스케줄 09:01/15:21 공용).
  ※ paper_tracker 는 X2(시간외) 모드를 계속 추적 → 두 모드를 병행 검증하게 됨.

⚠️ 안전장치: KIWOOM_ENV=prod 면 주문 명령을 거부한다 (조회만 허용).
   실전 전환은 모의 검증 수개월 후 별도 논의 — 그때도 사용자가 직접 결정.

주문유형(trde_tp): 0 지정가 / 3 시장가 (키움 REST 가이드 기준.
  거부 시 로그 확인 후 "03"/"00" 표기로 교체 시도)
"""

import os
import sys
import csv
from datetime import datetime

import pandas as pd

import config

SIGNALS_CSV = "./paper_signals.csv"
ORDERS_DIR = "./db/kiwoom"
HOLDING_DAYS = 40
MAX_CONCURRENT = 10
ORDER_TYPE_BUY = "3"     # 시장가 (모의서버는 지정가/시장가만 지원)
ORDER_TYPE_SELL = "3"    # 시장가 — 15:21 주문 시 마감 동시호가 참여 ≈ 종가 체결
MIN_ORDER_AMOUNT = 100_000   # 슬롯당 이보다 작으면 주문 생략


# ------------------------------------------------------------
# 공용
# ------------------------------------------------------------
class KiwoomBundle:
    """order/account 클라이언트 묶음."""
    def __init__(self, order, acct):
        self.order = order
        self.acct = acct


def get_api():
    if not config.KIWOOM_APP_KEY or not config.KIWOOM_APP_SECRET:
        print("[ERROR] .env 에 KIWOOM_MOCK_APP_KEY / KIWOOM_MOCK_APP_SECRET 없음")
        sys.exit(1)
    # 라이브러리가 import 시점에 환경변수를 읽으므로 import 전에 주입
    os.environ["KIWOOM_API_KEY"] = config.KIWOOM_APP_KEY
    os.environ["KIWOOM_API_SECRET"] = config.KIWOOM_APP_SECRET
    os.environ["KIWOOM_USE_SANDBOX"] = "false" if config.KIWOOM_ENV == "prod" else "true"
    try:
        from kiwoom_rest_api.config import get_base_url
        from kiwoom_rest_api.auth.token import TokenManager
        from kiwoom_rest_api.koreanstock.order import Order
        from kiwoom_rest_api.koreanstock.account import Account
    except ImportError:
        print("[ERROR] kiwoom-rest-api 미설치 → pip install kiwoom-rest-api")
        sys.exit(1)
    base = get_base_url()
    tm = TokenManager()
    tm.get_token()   # 토큰 발급 검증 (실패 시 예외)
    print(f"[kiwoom] 토큰 발급 OK (env={config.KIWOOM_ENV}, {base})")
    return KiwoomBundle(Order(base_url=base, token_manager=tm),
                        Account(base_url=base, token_manager=tm))


def guard_mock_only():
    if config.KIWOOM_ENV == "prod":
        print("[ABORT] KIWOOM_ENV=prod — 실전 계좌 주문은 이 스크립트에서 차단됨.")
        print("        모의 검증 후 실전 전환은 별도로 진행하세요 (KIWOOM_ENV=mock 으로 변경).")
        sys.exit(1)


def _pick(d, *cands, default=None):
    """응답 dict 에서 후보 키 중 존재하는 첫 값을 반환 (스키마 방어)."""
    for k in cands:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _to_int(v, default=0):
    try:
        return int(str(v).replace(",", "").replace("+", "").strip())
    except Exception:
        return default


def log_order(row):
    os.makedirs(ORDERS_DIR, exist_ok=True)
    path = f"{ORDERS_DIR}/orders_{datetime.today():%Y%m%d}.csv"
    exists = os.path.exists(path)
    fields = ["time", "side", "code", "name", "qty", "price", "order_type",
              "ok", "order_no", "msg"]
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow(row)


def today_ordered_codes(side=None):
    path = f"{ORDERS_DIR}/orders_{datetime.today():%Y%m%d}.csv"
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype={"code": str})
    if side:
        df = df[df["side"] == side]
    ok = df["ok"].astype(str).str.lower().isin(("true", "1"))  # CSV 재로드 시 문자열 대응
    return set(df[ok]["code"].astype(str).str.zfill(6))


# ------------------------------------------------------------
# 계좌 조회
# ------------------------------------------------------------
def get_deposit(api):
    """주문가능 예수금 (원). 스키마 모르면 raw 출력. (kt00001, qry_tp 3=추정조회)"""
    try:
        r = api.acct.deposit_detail_status_request_kt00001(qry_tp="3")
    except Exception:
        r = api.acct.deposit_detail_status_request_kt00001(qry_tp="2")
    for key in ("ord_alow_amt", "ord_alowa", "100stk_ord_alow_amt",
                "entr", "prsm_dpst_aset_amt", "pymn_alow_amt"):
        v = _pick(r, key)
        if v is not None:
            return _to_int(v)
    print(f"[warn] 예수금 필드 식별 실패 — raw keys: {list(r.keys())[:25]}")
    return 0


def get_positions(api):
    """보유 종목 dict: code -> {qty, name}. (kt00018) 스키마 방어적 파싱."""
    r = api.acct.account_evaluation_balance_detail_request_kt00018(
        query_type="1", domestic_exchange_type="KRX")
    items = None
    for key in ("acnt_evlt_remn_indv_tot", "stk_acnt_evlt_prst", "output", "list"):
        if isinstance(r, dict) and isinstance(r.get(key), list):
            items = r[key]
            break
    if items is None:
        print(f"[warn] 잔고 리스트 식별 실패 — raw keys: {list(r.keys())[:20]}")
        return {}
    pos = {}
    for it in items:
        code = str(_pick(it, "stk_cd", "stock_code", default="")).replace("A", "").zfill(6)
        qty = _to_int(_pick(it, "rmnd_qty", "hldg_qty", "qty", default=0))
        name = _pick(it, "stk_nm", "stock_name", default="")
        if code and qty > 0:
            pos[code] = {"qty": qty, "name": name}
    return pos


def cmd_status():
    api = get_api()
    dep = get_deposit(api)
    pos = get_positions(api)
    print(f"\n[예수금(주문가능)] {dep:,} 원")
    print(f"[보유 종목] {len(pos)} / {MAX_CONCURRENT} 슬롯")
    for c, p in pos.items():
        print(f"  {c} {p['name']}: {p['qty']:,}주")

    # 대시보드용 스냅샷 저장
    try:
        import json
        os.makedirs(ORDERS_DIR, exist_ok=True)
        snap = {"date": datetime.today().strftime("%Y%m%d"),
                "time": datetime.now().strftime("%H:%M"),
                "env": config.KIWOOM_ENV,
                "deposit": dep,
                "positions": [{"code": c, "name": p["name"], "qty": p["qty"]}
                              for c, p in pos.items()]}
        with open(f"{ORDERS_DIR}/snapshot.json", "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        hist = f"{ORDERS_DIR}/equity_history.csv"
        new = not os.path.exists(hist)
        with open(hist, "a", newline="", encoding="utf-8-sig") as f:
            if new:
                f.write("date,time,deposit,n_positions\n")
            f.write(f"{snap['date']},{snap['time']},{dep},{len(pos)}\n")
    except Exception as e:
        print(f"[warn] 스냅샷 저장 실패: {e}")
    try:
        unfilled = api.acct.unfilled_orders_request_ka10075(
            all_stk_tp="0", trde_tp="0", stex_tp="0")
        n = len(unfilled.get("oso", unfilled.get("output", []))) if isinstance(unfilled, dict) else 0
        print(f"[미체결] {n} 건")
    except Exception as e:
        print(f"[미체결 조회 실패] {e}")


# ------------------------------------------------------------
# 매수 — 오늘 신호
# ------------------------------------------------------------
def latest_macro_date():
    """macro_data 의 최신 영업일 (09:01 실행 시 = 어제 = 신호일)."""
    import glob as _g
    files = sorted(_g.glob("./macro_data/daily/*.csv"))
    return os.path.basename(files[-1])[:-4] if files else None


def todays_signals():
    """원본 모드: '직전 영업일 신호'를 다음날 아침 매수 — 최신 macro 일자의 신호."""
    if not os.path.exists(SIGNALS_CSV):
        return []
    s = pd.read_csv(SIGNALS_CSV, dtype={"code": str})
    s["signal_date"] = s["signal_date"].astype(str)
    s["code"] = s["code"].astype(str).str.zfill(6)
    target = latest_macro_date()
    if not target:
        return []
    today = datetime.today().strftime("%Y%m%d")
    if target == today:
        # 아침 실행인데 오늘 데이터가 벌써 있을 수는 없음 — 방어
        return []
    print(f"[buy] 신호 기준일: {target}")
    return s[s["signal_date"] == target].to_dict("records")


def cmd_buy():
    guard_mock_only()
    sigs = todays_signals()
    if not sigs:
        print("[buy] 오늘 신호 없음 — 종료")
        return
    api = get_api()
    pos = get_positions(api)
    already = today_ordered_codes("buy")
    dep = get_deposit(api)

    slots_left = MAX_CONCURRENT - len(pos)
    print(f"[buy] 오늘 신호 {len(sigs)}건, 보유 {len(pos)}, 빈 슬롯 {slots_left}, 예수금 {dep:,}원")
    if slots_left <= 0:
        print("[buy] 슬롯 가득 — 주문 없음")
        return

    # 랭킹: 신호일 거래대금 큰 순 (capital_simulator 와 동일 정책)
    tv_map = {}
    sig_csv = f"./macro_data/daily/{latest_macro_date()}.csv"
    if os.path.exists(sig_csv):
        md = pd.read_csv(sig_csv, encoding="utf-8-sig", dtype={"code": str})
        md = md.rename(columns={"거래대금": "trading_value"})
        md["code"] = md["code"].astype(str).str.zfill(6)
        if "trading_value" in md.columns:
            tv_map = dict(zip(md["code"], md["trading_value"]))
    sigs = sorted(sigs, key=lambda r: float(tv_map.get(r["code"], 0) or 0), reverse=True)

    n_placed = 0
    for sig in sigs:
        if slots_left - n_placed <= 0:
            break
        code, name = sig["code"], str(sig.get("name", ""))
        close = float(sig.get("entry_price_close", 0) or 0)
        if code in pos or code in already:
            print(f"  [skip] {code} {name} — 이미 보유/주문됨")
            continue
        if close <= 0:
            continue
        budget = dep / (slots_left - n_placed)
        # 시장가 매수 — 수량은 신호일 종가 기준으로 산정 (시가 갭은 약간의 슬리피지)
        qty = int((budget * 0.97) // close)   # 갭상승 대비 3% 여유
        if qty < 1 or qty * close < MIN_ORDER_AMOUNT:
            print(f"  [skip] {code} {name} — 예산 부족 (budget {budget:,.0f})")
            continue
        try:
            r = api.order.stock_buy_order_request_kt10000(
                dmst_stex_tp="KRX", stk_cd=code, ord_qty=str(qty),
                trde_tp=ORDER_TYPE_BUY,
                ord_uv="",   # 시장가 — 가격 미지정
            )
            ono = _pick(r, "ord_no", "odno", default="")
            print(f"  [매수주문] {code} {name} {qty}주 @ {int(close):,} → 주문번호 {ono}")
            log_order({"time": datetime.now().strftime("%H:%M:%S"), "side": "buy",
                       "code": code, "name": name, "qty": qty, "price": int(close),
                       "order_type": ORDER_TYPE_BUY, "ok": True, "order_no": ono, "msg": ""})
            dep -= qty * close
            n_placed += 1
        except Exception as e:
            print(f"  [실패] {code} {name}: {e}")
            log_order({"time": datetime.now().strftime("%H:%M:%S"), "side": "buy",
                       "code": code, "name": name, "qty": qty, "price": int(close),
                       "order_type": ORDER_TYPE_BUY, "ok": False, "order_no": "",
                       "msg": str(e)[:200]})
    print(f"[buy] 주문 {n_placed}건 완료")


# ------------------------------------------------------------
# 매도 — 40영업일 도달
# ------------------------------------------------------------
def codes_due_for_exit():
    """보유 40영업일째 도달한 신호 종목 (원본 모드: 진입일 = 신호 다음 영업일)."""
    from strategies.daily_loader import load_macro_daily
    if not os.path.exists(SIGNALS_CSV):
        return set()
    s = pd.read_csv(SIGNALS_CSV, dtype={"code": str})
    s["signal_date"] = s["signal_date"].astype(str)
    s["code"] = s["code"].astype(str).str.zfill(6)
    df = load_macro_daily()
    code_dates = {c: sorted(g["date"].astype(str).tolist()) for c, g in df.groupby("code")}
    today = datetime.today().strftime("%Y%m%d")
    due = set()
    for _, r in s.iterrows():
        ds = code_dates.get(r["code"])
        if not ds or r["signal_date"] not in ds:
            continue
        entry_i = ds.index(r["signal_date"]) + 1     # 진입 = 신호 다음 영업일 (시가)
        exit_i = entry_i + HOLDING_DAYS - 1          # 진입일 포함 40영업일째 종가
        if exit_i < len(ds) and ds[exit_i] <= today:
            due.add(r["code"])
    return due


def _today_close_map():
    """당일 종가 맵 (시간외단일가 주문 가격 지정용). 당일 없으면 빈 dict."""
    path = f"./macro_data/daily/{datetime.today():%Y%m%d}.csv"
    if not os.path.exists(path):
        return {}
    md = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    md["code"] = md["code"].astype(str).str.zfill(6)
    return dict(zip(md["code"], md["close"]))


def cmd_sell():
    guard_mock_only()
    api = get_api()
    pos = get_positions(api)
    if not pos:
        print("[sell] 보유 없음")
        return
    due = codes_due_for_exit()
    already = today_ordered_codes("sell")
    targets = [c for c in pos if c in due and c not in already]
    print(f"[sell] 보유 {len(pos)}, 만기 도달 {len(targets)}건")
    for code in targets:
        qty, name = pos[code]["qty"], pos[code]["name"]
        try:
            # 시장가 매도 — 15:21 실행 시 마감 동시호가 참여 ≈ 종가 체결
            r = api.order.stock_sell_order_request_kt10001(
                dmst_stex_tp="KRX", stk_cd=code, ord_qty=str(qty),
                trde_tp=ORDER_TYPE_SELL, ord_uv="",
            )
            ono = _pick(r, "ord_no", "odno", default="")
            print(f"  [매도주문] {code} {name} {qty}주 → 주문번호 {ono}")
            log_order({"time": datetime.now().strftime("%H:%M:%S"), "side": "sell",
                       "code": code, "name": name, "qty": qty, "price": 0,
                       "order_type": ORDER_TYPE_SELL, "ok": True, "order_no": ono, "msg": ""})
        except Exception as e:
            print(f"  [실패] {code} {name}: {e}")
            log_order({"time": datetime.now().strftime("%H:%M:%S"), "side": "sell",
                       "code": code, "name": name, "qty": qty, "price": 0,
                       "order_type": ORDER_TYPE_SELL, "ok": False, "order_no": "",
                       "msg": str(e)[:200]})


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(f"=== 키움 모의투자 집행기 ({cmd}) {datetime.now():%Y-%m-%d %H:%M} ===")
    if cmd == "status":
        cmd_status()
    elif cmd == "buy":
        cmd_buy()
    elif cmd == "sell":
        cmd_sell()
    elif cmd == "daily":
        # 스케줄 공용 진입점: 09:01 실행이면 매수, 15:21 실행이면 매도 (시계로 분기)
        if datetime.now().hour < 12:
            cmd_buy()
        else:
            cmd_sell()
        cmd_status()
    else:
        print("사용법: python kiwoom_trader.py [status|buy|sell|daily]")


if __name__ == "__main__":
    main()
