"""
모의투자 대시보드 HTML 생성기.

paper_signals.csv + macro_data → dashboard.html
브라우저로 열어서 시각화 확인.

표시:
  - KPI: 자본 / CAGR / MDD / Sharpe / 보유 / 누적 매매
  - 자본 곡선 차트 (Chart.js)
  - 현재 보유 포지션 (entry 가격 + 현재가 + 평가손익)
  - 최근 매매 이력 (최근 50건)
  - 보유 종목의 일별 종가 변동 차트
"""

import os
import json
from datetime import datetime
import pandas as pd

import config
from strategies.daily_loader import load_macro_daily
from capital_simulator import simulate_capital
from strategies.base import StrategyTrade


SIGNALS_CSV = "./paper_signals.csv"
NAME_CACHE_CSV = "./name_cache.csv"
OUT_HTML = "./dashboard.html"
INITIAL_CAPITAL = 10_000_000
MAX_CONCURRENT = 10
HOLDING_DAYS = 40
COST_PCT = 0.330
LOOKBACK_DAYS = 500   # 메인 전략 룩백


def _load_name_cache(path=NAME_CACHE_CSV):
    """code → name dict. 없으면 {}."""
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype={"code": str}, encoding="utf-8-sig")
    df["code"] = df["code"].astype(str).str.zfill(6)
    return dict(zip(df["code"], df["name"]))


def _safe_name(v):
    """NaN/float/None → 빈 문자열."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v)


def _calc_reason_meta(code, sig_date, dates_list, price_map, entry_price_close):
    """매매 근거 메타 즉석 계산 — signal_date 기준 직전 500일 고점, 돌파율, 거래대금."""
    try:
        sig_idx = dates_list.index(sig_date)
    except ValueError:
        return {}
    # 직전 LOOKBACK_DAYS 일의 high 최대값 (signal_date 포함 안 함 = 진짜 직전)
    start = max(0, sig_idx - LOOKBACK_DAYS)
    window = dates_list[start:sig_idx]
    if not window:
        return {}
    prior_high = 0.0
    prior_high_date = None
    for d in window:
        h = price_map.get((code, d), {}).get("high", 0) or 0
        if h > prior_high:
            prior_high = float(h)
            prior_high_date = d
    breakout_pct = ((entry_price_close / prior_high) - 1) * 100 if prior_high > 0 else None
    trading_value = price_map.get((code, sig_date), {}).get("trading_value", 0) or 0
    return {
        "prior_high": round(prior_high, 0) if prior_high else None,
        "prior_high_date": prior_high_date,
        "breakout_pct": round(breakout_pct, 2) if breakout_pct is not None else None,
        "trading_value_eok": round(float(trading_value) / 1e8, 1) if trading_value else None,
    }


def build_trades(signals_df, code_dates, price_map, name_cache=None):
    """signals → 매매 변환."""
    name_cache = name_cache or {}
    trades = []
    for _, sig in signals_df.iterrows():
        code = sig["code"]
        sig_date = sig["signal_date"]
        if code not in code_dates:
            continue
        dates_list = code_dates[code]
        next_dates = [d for d in dates_list if d > sig_date]
        if not next_dates:
            continue
        entry_date = next_dates[0]
        entry_p = price_map.get((code, entry_date), {}).get("open")
        if not entry_p or entry_p <= 0:
            continue
        idx = dates_list.index(entry_date)

        # name: csv → name_cache fallback
        nm = _safe_name(sig.get("name"))
        if not nm and code in name_cache:
            nm = name_cache[code]

        # 신호일 종가
        sig_close = price_map.get((code, sig_date), {}).get("close", entry_p) or entry_p

        # 매매 근거 메타 (즉석 계산)
        reason = _calc_reason_meta(code, sig_date, dates_list, price_map, sig_close)
        try:
            market_strong = str(sig.get("market_strong", "")).strip().lower() in ("true", "1")
        except Exception:
            market_strong = False

        reason["strategy"] = "high_500d_h40_MKT"
        reason["market_strong"] = market_strong
        reason["sig_close"] = round(float(sig_close), 0)

        exit_idx = idx + HOLDING_DAYS
        if exit_idx >= len(dates_list):
            current_p = price_map.get((code, dates_list[-1]), {}).get("close", entry_p)
            mtm_pct = (current_p / entry_p - 1) * 100
            trades.append({
                "code": code, "name": nm,
                "signal_date": sig_date, "entry_date": entry_date,
                "entry_price": float(entry_p),
                "exit_date": None, "exit_price": None,
                "current_price": float(current_p),
                "mtm_pct": float(mtm_pct),
                "net_pct": None, "status": "open",
                "holding_so_far": len(dates_list) - idx - 1,
                "reason": reason,
            })
        else:
            exit_date = dates_list[exit_idx]
            exit_p = price_map.get((code, exit_date), {}).get("close")
            if not exit_p or exit_p <= 0:
                continue
            gross_pct = (exit_p / entry_p - 1) * 100
            net_pct = gross_pct - COST_PCT
            trades.append({
                "code": code, "name": nm,
                "signal_date": sig_date, "entry_date": entry_date,
                "entry_price": float(entry_p),
                "exit_date": exit_date, "exit_price": float(exit_p),
                "current_price": float(exit_p),
                "mtm_pct": float(gross_pct),
                "net_pct": float(net_pct), "status": "closed",
                "holding_so_far": HOLDING_DAYS,
                "reason": reason,
            })
    return trades


def build_equity_curve(closed_trades):
    """청산 매매를 entry_date 순으로 정렬해 누적 net_pct 곡선."""
    rows = sorted(closed_trades, key=lambda t: t["entry_date"])
    points = [{"date": "start", "equity": INITIAL_CAPITAL}]
    cap = INITIAL_CAPITAL
    n_active = 0
    per_slot = INITIAL_CAPITAL / MAX_CONCURRENT  # 단순화 모델
    for t in rows:
        # 단순화: 각 매매 자본 1/N 베팅 가정
        invest = per_slot
        result = invest * (1 + t["net_pct"] / 100)
        cap = cap - invest + result   # 거의 동일 (delta = invest × net_pct/100)
        points.append({
            "date": t["exit_date"],
            "equity": round(cap, 0),
            "code": t["code"],
            "net_pct": round(t["net_pct"], 2),
        })
    return points


def build_holding_history(open_trades, price_map, code_dates):
    """보유 중인 종목의 entry 이후 일별 종가 시계열."""
    result = []
    for t in open_trades[:20]:  # 너무 많으면 자름
        code = t["code"]
        entry_date = t["entry_date"]
        if code not in code_dates:
            continue
        dates_list = code_dates[code]
        try:
            start_idx = dates_list.index(entry_date)
        except ValueError:
            continue
        series = []
        for d in dates_list[start_idx:]:
            close = price_map.get((code, d), {}).get("close")
            if close and close > 0:
                pct = (close / t["entry_price"] - 1) * 100
                series.append({"date": d, "close": float(close), "pct": round(pct, 2)})
        result.append({
            "code": code,
            "name": t["name"],
            "entry_date": entry_date,
            "entry_price": t["entry_price"],
            "series": series,
        })
    return result


def render_html(kpi, equity_pts, open_trades, closed_recent, holdings_hist):
    """HTML 문자열 생성."""
    eq_labels = json.dumps([p["date"] for p in equity_pts])
    eq_values = json.dumps([p["equity"] for p in equity_pts])

    # 보유 포지션 표
    open_rows = ""
    for t in sorted(open_trades, key=lambda x: x["mtm_pct"], reverse=True):
        cls = "win" if t["mtm_pct"] >= 0 else "loss"
        open_rows += f"""
        <tr>
          <td>{t['code']}</td><td>{_safe_name(t['name'])[:15]}</td>
          <td>{t['entry_date']}</td>
          <td>{int(t['entry_price']):,}</td>
          <td>{int(t['current_price']):,}</td>
          <td class="{cls}">{t['mtm_pct']:+.2f}%</td>
          <td>{t['holding_so_far']}일</td>
        </tr>"""

    # 최근 매매 이력 (▼ 클릭 → 근거 row 펼침)
    closed_rows = ""
    for i, t in enumerate(sorted(closed_recent, key=lambda x: x["exit_date"], reverse=True)[:50]):
        cls = "win" if t["net_pct"] >= 0 else "loss"
        r = t.get("reason") or {}
        prior_high = r.get("prior_high")
        breakout = r.get("breakout_pct")
        tv = r.get("trading_value_eok")
        mkt = "✅" if r.get("market_strong") else "❌"
        strat = r.get("strategy", "-")
        sig_close = r.get("sig_close")
        ph_date = r.get("prior_high_date") or "-"
        closed_rows += f"""
        <tr class="trade-row" onclick="toggleReason({i})">
          <td><span class="toggle" id="tg{i}">▶</span></td>
          <td>{t['code']}</td><td>{_safe_name(t['name'])[:15]}</td>
          <td>{t['entry_date']}</td>
          <td>{t['exit_date']}</td>
          <td>{int(t['entry_price']):,}</td>
          <td>{int(t['exit_price']):,}</td>
          <td class="{cls}">{t['net_pct']:+.2f}%</td>
        </tr>
        <tr class="reason-row" id="rs{i}" style="display:none;">
          <td colspan="8">
            <div class="reason-box">
              <div class="reason-grid">
                <div><span class="lbl">전략</span><span class="val">{strat}</span></div>
                <div><span class="lbl">신호일 종가</span><span class="val">{int(sig_close):,}원</span></div>
                <div><span class="lbl">직전 500일 고점</span><span class="val">{int(prior_high):,}원 ({ph_date})</span></div>
                <div><span class="lbl">돌파율</span><span class="val">{breakout:+.2f}% (신호 종가 vs 직전 고점)</span></div>
                <div><span class="lbl">거래대금</span><span class="val">{tv:.1f}억원 (필터 30억 이상)</span></div>
                <div><span class="lbl">시장 게이트</span><span class="val">KOSDAQ MA60 통과 {mkt}</span></div>
              </div>
            </div>
          </td>
        </tr>""" if all(x is not None for x in (prior_high, breakout, tv, sig_close)) else f"""
        <tr class="trade-row" onclick="toggleReason({i})">
          <td><span class="toggle" id="tg{i}">▶</span></td>
          <td>{t['code']}</td><td>{_safe_name(t['name'])[:15]}</td>
          <td>{t['entry_date']}</td>
          <td>{t['exit_date']}</td>
          <td>{int(t['entry_price']):,}</td>
          <td>{int(t['exit_price']):,}</td>
          <td class="{cls}">{t['net_pct']:+.2f}%</td>
        </tr>
        <tr class="reason-row" id="rs{i}" style="display:none;">
          <td colspan="8"><div class="reason-box"><em style="color:#8b939e">근거 메타 부족 (macro_data 범위 밖)</em></div></td>
        </tr>"""

    # 보유 종목 차트 데이터
    holdings_data = json.dumps(holdings_hist)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Paper Trading Dashboard — high_500d_h40_MKT</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: -apple-system, "Malgun Gothic", sans-serif;
            margin: 0; background: #0f1115; color: #e8eaed; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
    h1 {{ font-size: 24px; margin: 0 0 4px 0; }}
    .subtitle {{ color: #8b939e; font-size: 13px; margin-bottom: 20px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(7, 1fr);
                gap: 12px; margin-bottom: 20px; }}
    .kpi {{ background: #1a1e26; padding: 14px; border-radius: 8px;
            border-left: 3px solid #4a9eff; }}
    .kpi h3 {{ font-size: 11px; color: #8b939e; margin: 0 0 4px 0;
              text-transform: uppercase; letter-spacing: 0.5px; }}
    .kpi p {{ font-size: 18px; font-weight: 600; margin: 0; }}
    .card {{ background: #1a1e26; padding: 20px; border-radius: 8px;
            margin-bottom: 20px; }}
    .card h2 {{ font-size: 16px; margin: 0 0 14px 0; color: #e8eaed; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ text-align: left; padding: 8px; color: #8b939e;
          border-bottom: 1px solid #2a2f3a; font-weight: 500; }}
    td {{ padding: 8px; border-bottom: 1px solid #2a2f3a; }}
    .win {{ color: #4ade80; }}
    .loss {{ color: #f87171; }}
    .chart-wrap {{ height: 320px; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .trade-row {{ cursor: pointer; }}
    .trade-row:hover {{ background: #20242e; }}
    .toggle {{ display: inline-block; transition: transform 0.15s;
              color: #8b939e; font-size: 10px; user-select: none; }}
    .toggle.open {{ transform: rotate(90deg); }}
    .reason-row td {{ padding: 0; background: #0f1115; border-bottom: 1px solid #2a2f3a; }}
    .reason-box {{ padding: 12px 14px; }}
    .reason-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }}
    .reason-grid .lbl {{ color: #8b939e; font-size: 11px; margin-right: 8px;
                         text-transform: uppercase; letter-spacing: 0.3px; }}
    .reason-grid .val {{ color: #e8eaed; font-size: 13px; font-weight: 500; }}
    @media (max-width: 1000px) {{
      .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
      .grid2 {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>📊 Paper Trading Dashboard</h1>
    <div class="subtitle">메인 전략: high_500d_h40_MKT · 자본: 1,000만원 · 마지막 업데이트: {now}</div>

    <div class="kpi-grid">
      <div class="kpi"><h3>최종 자본</h3><p>{int(kpi.get('final', INITIAL_CAPITAL)):,}원</p></div>
      <div class="kpi"><h3>총 수익률</h3><p class="{'win' if kpi.get('total_ret_pct',0)>=0 else 'loss'}">{kpi.get('total_ret_pct', 0):+.2f}%</p></div>
      <div class="kpi"><h3>CAGR</h3><p>{kpi.get('cagr_pct', 0):+.2f}%/년</p></div>
      <div class="kpi"><h3>Real MDD</h3><p class="loss">{kpi.get('real_mdd_pct', 0):.2f}%</p></div>
      <div class="kpi"><h3>Sharpe</h3><p>{kpi.get('real_sharpe', 0):.2f}</p></div>
      <div class="kpi"><h3>보유 중</h3><p>{len(open_trades)}/{MAX_CONCURRENT}</p></div>
      <div class="kpi"><h3>누적 매매</h3><p>{len(closed_recent):,}건</p></div>
    </div>

    <div class="card">
      <h2>💰 자본 곡선</h2>
      <div class="chart-wrap"><canvas id="equityChart"></canvas></div>
    </div>

    <div class="grid2">
      <div class="card">
        <h2>📈 현재 보유 포지션 ({len(open_trades)}건)</h2>
        <table>
          <thead><tr>
            <th>코드</th><th>종목</th><th>진입일</th>
            <th>진입가</th><th>현재가</th><th>평가손익</th><th>보유</th>
          </tr></thead>
          <tbody>{open_rows or '<tr><td colspan="7" style="text-align:center; color:#666;">보유 없음</td></tr>'}</tbody>
        </table>
      </div>

      <div class="card">
        <h2>📜 최근 매매 이력 (최근 50건) <span style="font-size:11px; color:#8b939e; font-weight:normal;">— 행 클릭 시 근거 펼침</span></h2>
        <table>
          <thead><tr>
            <th style="width:24px;"></th>
            <th>코드</th><th>종목</th><th>진입</th><th>청산</th>
            <th>매수</th><th>매도</th><th>손익</th>
          </tr></thead>
          <tbody>{closed_rows}</tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>📉 보유 종목 변동 추이 (entry 이후 일별)</h2>
      <div class="chart-wrap"><canvas id="holdingsChart"></canvas></div>
    </div>
  </div>

  <script>
    function toggleReason(i) {{
      const row = document.getElementById('rs' + i);
      const tg = document.getElementById('tg' + i);
      if (!row) return;
      const open = row.style.display !== 'none';
      row.style.display = open ? 'none' : 'table-row';
      if (tg) tg.classList.toggle('open', !open);
    }}

    const eqCtx = document.getElementById('equityChart').getContext('2d');
    new Chart(eqCtx, {{
      type: 'line',
      data: {{
        labels: {eq_labels},
        datasets: [{{
          label: '자본 (원)',
          data: {eq_values},
          borderColor: '#4a9eff',
          backgroundColor: 'rgba(74,158,255,0.1)',
          fill: true, tension: 0.1, pointRadius: 0,
        }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#e8eaed' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#8b939e', maxTicksLimit: 20 }}, grid: {{ color: '#2a2f3a' }} }},
          y: {{ ticks: {{ color: '#8b939e', callback: v => (v/10000).toFixed(0)+'만' }},
                grid: {{ color: '#2a2f3a' }} }}
        }}
      }}
    }});

    const holdings = {holdings_data};
    const holdingsCtx = document.getElementById('holdingsChart').getContext('2d');
    const colors = ['#4ade80','#f87171','#fbbf24','#4a9eff','#a78bfa',
                    '#f472b6','#34d399','#fb923c','#60a5fa','#c084fc'];
    new Chart(holdingsCtx, {{
      type: 'line',
      data: {{
        datasets: holdings.slice(0,10).map((h, i) => ({{
          label: h.code + ' ' + h.name,
          data: h.series.map(s => ({{x: s.date, y: s.pct}})),
          borderColor: colors[i % colors.length],
          backgroundColor: 'transparent',
          tension: 0.1, pointRadius: 1, borderWidth: 1.5,
        }}))
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#e8eaed', font: {{size:10}} }} }} }},
        scales: {{
          x: {{ type: 'category', ticks: {{ color: '#8b939e', maxTicksLimit: 30 }},
                grid: {{ color: '#2a2f3a' }} }},
          y: {{ ticks: {{ color: '#8b939e', callback: v => v.toFixed(0)+'%' }},
                grid: {{ color: '#2a2f3a' }} }}
        }}
      }}
    }});
  </script>
</body>
</html>"""
    return html


def main():
    if not os.path.exists(SIGNALS_CSV):
        print(f"[error] {SIGNALS_CSV} 없음. seed_paper_signals.py 먼저 실행.")
        return

    print("=== Dashboard 생성 ===")
    signals = pd.read_csv(SIGNALS_CSV, dtype={"code": str})
    signals["signal_date"] = signals["signal_date"].astype(str)
    signals["code"] = signals["code"].astype(str).str.zfill(6)

    df = load_macro_daily()
    df["date"] = df["date"].astype(str)
    df["code"] = df["code"].astype(str).str.zfill(6)
    code_dates = df.groupby("code")[["date"]].apply(lambda x: sorted(x["date"].tolist())).to_dict()
    cols = [c for c in ["open", "high", "low", "close", "trading_value"] if c in df.columns]
    price_map = df.set_index(["code", "date"])[cols].to_dict("index")

    name_cache = _load_name_cache()
    if name_cache:
        print(f"  [name_cache] {len(name_cache):,} 종목명 로드")
    else:
        print(f"  [name_cache] 없음 (build_name_cache.py 실행 권장)")

    trades = build_trades(signals, code_dates, price_map, name_cache=name_cache)
    closed = [t for t in trades if t["status"] == "closed"]
    open_pos = [t for t in trades if t["status"] == "open"]

    sim_trades = [
        StrategyTrade(
            strategy="paper", code=t["code"], entry_date=t["entry_date"],
            entry_price=t["entry_price"], exit_date=t["exit_date"],
            exit_price=t["exit_price"], holding_days=HOLDING_DAYS,
            gross_pct=(t["exit_price"]/t["entry_price"]-1)*100,
            cost_pct=COST_PCT, net_pct=t["net_pct"], exit_reason="hold_exit",
        ) for t in closed
    ]
    cap = simulate_capital(sim_trades, initial_capital=INITIAL_CAPITAL,
                            max_concurrent=MAX_CONCURRENT) or {}

    equity_pts = build_equity_curve(closed)
    holdings_hist = build_holding_history(open_pos, price_map, code_dates)

    html = render_html(cap, equity_pts, open_pos, closed, holdings_hist)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[saved] {OUT_HTML}")
    print(f"\n브라우저에서 열기:")
    print(f"  file:///{os.path.abspath(OUT_HTML).replace(chr(92), '/')}")


if __name__ == "__main__":
    main()
