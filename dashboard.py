"""
Paper Trading Dashboard 생성기.

paper_signals.csv + macro_data 로 인터랙티브 HTML 대시보드 만듦:
- 자본 곡선 (1천만원 시작 → 현재)
- 현재 보유 포지션 + 미실현 손익
- 최근 청산 매매 표
- 보유 종목별 가격 추이 (entry ~ exit/현재)
- 통계 요약 (CAGR, MDD, Sharpe, 승률)

실행: python dashboard.py
출력: dashboard.html (브라우저로 열기)
자동 새로고침: 10분
"""

import os
import json
import math
from datetime import datetime, timedelta
import pandas as pd

import config
from strategies.daily_loader import load_macro_daily

SIGNALS_CSV = "./paper_signals.csv"
OUTPUT_HTML = "./dashboard.html"
INITIAL_CAPITAL = 10_000_000
MAX_CONCURRENT = 10
HOLDING_DAYS = 40
COST_PCT = 0.330
CUTOFF_MIN_GROSS = -30.0   # 액면분할 의심 매매 제외


def build_trades(signals_df, df):
    """매매 데이터 + 보유기간 가격 시계열 생성."""
    code_dates = df.groupby("code")["date"].apply(lambda x: sorted(x.tolist())).to_dict()
    price_map = df.set_index(["code", "date"])[["open", "close", "high", "low"]].to_dict("index")
    name_map = df.set_index("code")["name"].to_dict() if "name" in df.columns else {}

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
        exit_idx = idx + HOLDING_DAYS
        if exit_idx >= len(dates_list):
            exit_date = None
            exit_p = None
            net_pct = None
            status = "open"
            hold_dates = [d for d in dates_list[idx:idx+HOLDING_DAYS+1]]
        else:
            exit_date = dates_list[exit_idx]
            exit_p = price_map.get((code, exit_date), {}).get("close")
            if not exit_p or exit_p <= 0:
                continue
            gross_pct = (exit_p / entry_p - 1) * 100
            if gross_pct < CUTOFF_MIN_GROSS:
                continue
            net_pct = gross_pct - COST_PCT
            status = "closed"
            hold_dates = [d for d in dates_list[idx:exit_idx+1]]

        price_series = []
        for d in hold_dates:
            p = price_map.get((code, d), {}).get("close", 0)
            if p > 0:
                price_series.append({"d": d, "p": float(p)})

        trades.append({
            "code": code,
            "name": str(name_map.get(code, "")),
            "signal_date": sig_date,
            "entry_date": entry_date,
            "entry_price": float(entry_p),
            "exit_date": exit_date,
            "exit_price": float(exit_p) if exit_p else None,
            "net_pct": float(net_pct) if net_pct is not None else None,
            "status": status,
            "price_series": price_series,
        })
    return trades


def simulate_capital(trades, initial=INITIAL_CAPITAL, max_concurrent=MAX_CONCURRENT):
    """자본 시뮬 + 일별 equity curve."""
    closed = [t for t in trades if t["status"] == "closed"]
    if not closed:
        return None

    all_dates = sorted(set([t["entry_date"] for t in closed] + [t["exit_date"] for t in closed]))
    cash = float(initial)
    positions = []   # {exit_date, invested, net_pct, code}
    equity_curve = []
    actual_entries = []   # 진짜 진입한 매매 (슬롯 통과)
    n_skipped = 0

    df_trades = pd.DataFrame(closed).sort_values("entry_date").reset_index(drop=True)

    for date in all_dates:
        # 청산
        remaining = []
        for p in positions:
            if p["exit_date"] <= date:
                cash += p["invested"] * (1 + p["net_pct"] / 100)
            else:
                remaining.append(p)
        positions = remaining

        # 새 진입
        todays = df_trades[df_trades["entry_date"] == date]
        for _, t in todays.iterrows():
            slots_left = max_concurrent - len(positions)
            if slots_left <= 0:
                n_skipped += 1
                continue
            invest = cash / slots_left
            if invest <= 0:
                n_skipped += 1
                continue
            positions.append({
                "exit_date": t["exit_date"],
                "invested": invest,
                "net_pct": t["net_pct"],
                "code": t["code"],
            })
            cash -= invest
            actual_entries.append({
                "entry_date": t["entry_date"],
                "exit_date": t["exit_date"],
                "code": t["code"],
                "name": t["name"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "net_pct": t["net_pct"],
                "invested": invest,
            })

        invested_total = sum(p["invested"] for p in positions)
        equity = cash + invested_total
        equity_curve.append({"d": date, "equity": equity})

    final = equity_curve[-1]["equity"]
    total_return = (final / initial - 1) * 100
    days_span = (datetime.strptime(equity_curve[-1]["d"], "%Y%m%d") -
                 datetime.strptime(equity_curve[0]["d"], "%Y%m%d")).days
    years = max(days_span / 365.25, 1/252)
    cagr = ((final / initial) ** (1/years) - 1) * 100

    eq_vals = [e["equity"] for e in equity_curve]
    peak = eq_vals[0]
    mdd = 0
    for v in eq_vals:
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100
        if dd < mdd:
            mdd = dd

    # Sharpe (일별 수익률)
    eq_series = pd.Series(eq_vals)
    daily_ret = eq_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * math.sqrt(252)
              if daily_ret.std() > 0 else 0)

    # 승률
    wins = sum(1 for t in actual_entries if t["net_pct"] > 0)
    total = len(actual_entries)
    win_rate = wins / total * 100 if total > 0 else 0

    return {
        "initial": initial,
        "final": final,
        "total_return": round(total_return, 2),
        "cagr": round(cagr, 2),
        "mdd": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "win_rate": round(win_rate, 1),
        "n_actual": total,
        "n_skipped": n_skipped,
        "equity_curve": equity_curve,
        "actual_entries": actual_entries,
        "n_signals": len(closed),
    }


def get_current_positions(trades, df, today=None):
    """현재 (마지막 가용 데이터 기준) 미청산 포지션 + 미실현 손익."""
    if today is None:
        today = df["date"].max()
    price_map = df.set_index(["code", "date"])[["close"]].to_dict("index")

    open_pos = []
    for t in trades:
        if t["status"] != "open":
            continue
        # 현재가 (마지막 가격)
        cur_price = price_map.get((t["code"], today), {}).get("close")
        if not cur_price:
            # 마지막 가격 폴백
            cur_price = t["price_series"][-1]["p"] if t["price_series"] else t["entry_price"]
        unreal_pct = (cur_price / t["entry_price"] - 1) * 100 - COST_PCT
        days_held = len(t["price_series"]) - 1 if t["price_series"] else 0
        open_pos.append({
            "code": t["code"],
            "name": t["name"],
            "entry_date": t["entry_date"],
            "entry_price": t["entry_price"],
            "current_price": float(cur_price),
            "unreal_pct": round(unreal_pct, 2),
            "days_held": days_held,
            "days_remaining": HOLDING_DAYS - days_held,
            "price_series": t["price_series"],
        })
    return sorted(open_pos, key=lambda x: x["unreal_pct"], reverse=True)


def render_html(sim, open_pos, df, generated_at):
    """HTML 대시보드 생성."""
    last_data_date = df["date"].max()
    eq_curve_json = json.dumps(sim["equity_curve"]) if sim else "[]"
    open_pos_json = json.dumps(open_pos)

    # 최근 청산 20건 (시간 역순)
    recent_closed = sorted(sim["actual_entries"], key=lambda x: x["exit_date"], reverse=True)[:20] if sim else []

    # CAGR/MDD 색깔
    cagr_color = "text-green-600" if sim and sim["cagr"] > 0 else "text-red-600"
    return_color = "text-green-600" if sim and sim["total_return"] > 0 else "text-red-600"

    sim_str = lambda k: f"{sim[k]:,.0f}" if sim else "0"
    sim_pct = lambda k: f"{sim[k]:+.2f}%" if sim else "0%"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="600">
<title>Paper Trading Dashboard — high_500d_h40_MKT</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; }}
  .card {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stat-big {{ font-size: 28px; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f3f4f6; font-size: 12px; color: #6b7280; text-transform: uppercase; }}
  td {{ font-size: 13px; }}
  .pct-pos {{ color: #16a34a; font-weight: bold; }}
  .pct-neg {{ color: #dc2626; font-weight: bold; }}
  .mini-chart {{ display: inline-block; vertical-align: middle; margin-right: 8px; }}
</style>
</head>
<body class="bg-gray-100 p-6">
  <div class="max-w-7xl mx-auto">

    <header class="mb-6">
      <h1 class="text-3xl font-bold text-gray-800">Paper Trading Dashboard</h1>
      <p class="text-gray-600 mt-1">메인 전략: <span class="font-mono">high_500d_h40_MKT</span> · 자본: ₩{INITIAL_CAPITAL:,} · 슬롯: {MAX_CONCURRENT} · 보유: {HOLDING_DAYS}일</p>
      <p class="text-sm text-gray-500 mt-1">생성: {generated_at} · 데이터 최신: {last_data_date} · 10분 자동 새로고침</p>
    </header>

    <!-- 통계 요약 (4개 박스) -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">현재 자본</div>
        <div class="stat-big {return_color}">₩{sim_str('final')}</div>
        <div class="text-sm {return_color}">{sim_pct('total_return')}</div>
      </div>
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">CAGR</div>
        <div class="stat-big {cagr_color}">{sim_pct('cagr')}</div>
        <div class="text-sm text-gray-500">연환산</div>
      </div>
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">MDD</div>
        <div class="stat-big text-red-600">{sim_pct('mdd')}</div>
        <div class="text-sm text-gray-500">최대 낙폭</div>
      </div>
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">Sharpe</div>
        <div class="stat-big text-gray-800">{f"{sim['sharpe']:.2f}" if sim else "0"}</div>
        <div class="text-sm text-gray-500">위험조정 수익</div>
      </div>
    </div>

    <!-- 매매 통계 (2개 박스) -->
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">실제 매매</div>
        <div class="stat-big text-gray-800">{sim_str('n_actual')} 건</div>
        <div class="text-sm text-gray-500">신호 {sim['n_signals']} 중 / 슬롯 부족 {sim['n_skipped']} 건 제외</div>
      </div>
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">승률</div>
        <div class="stat-big text-gray-800">{f"{sim['win_rate']}%" if sim else "0%"}</div>
        <div class="text-sm text-gray-500">청산 기준</div>
      </div>
      <div class="card">
        <div class="text-xs text-gray-500 uppercase">현재 보유</div>
        <div class="stat-big text-blue-600">{len(open_pos)} 종목</div>
        <div class="text-sm text-gray-500">미실현</div>
      </div>
    </div>

    <!-- 자본 곡선 -->
    <div class="card mb-6">
      <h2 class="text-lg font-bold mb-3">📈 자본 곡선</h2>
      <canvas id="equityChart" height="100"></canvas>
    </div>

    <!-- 현재 보유 포지션 -->
    <div class="card mb-6">
      <h2 class="text-lg font-bold mb-3">📦 현재 보유 포지션 ({len(open_pos)})</h2>
      <table>
        <thead>
          <tr>
            <th>종목</th><th>진입일</th><th>진입가</th><th>현재가</th>
            <th>미실현 손익</th><th>보유 일수</th><th>가격 추이</th>
          </tr>
        </thead>
        <tbody>
"""

    for i, pos in enumerate(open_pos[:30]):
        pct_cls = "pct-pos" if pos["unreal_pct"] > 0 else "pct-neg"
        chart_id = f"posChart_{i}"
        html += f"""
          <tr>
            <td><span class="font-mono">{pos['code']}</span><br><span class="text-xs text-gray-500">{pos['name'][:20]}</span></td>
            <td>{pos['entry_date'][:4]}-{pos['entry_date'][4:6]}-{pos['entry_date'][6:8]}</td>
            <td>₩{pos['entry_price']:,.0f}</td>
            <td>₩{pos['current_price']:,.0f}</td>
            <td class="{pct_cls}">{pos['unreal_pct']:+.2f}%</td>
            <td>{pos['days_held']}/{HOLDING_DAYS}</td>
            <td><canvas id="{chart_id}" width="120" height="40"></canvas></td>
          </tr>"""

    html += """
        </tbody>
      </table>
    </div>

    <!-- 최근 청산 매매 -->
    <div class="card mb-6">
      <h2 class="text-lg font-bold mb-3">✅ 최근 청산 매매 (20건)</h2>
      <table>
        <thead>
          <tr>
            <th>종목</th><th>진입일</th><th>청산일</th>
            <th>진입가</th><th>청산가</th><th>손익 (Net)</th><th>투자금</th>
          </tr>
        </thead>
        <tbody>
"""

    for t in recent_closed:
        pct_cls = "pct-pos" if t["net_pct"] > 0 else "pct-neg"
        html += f"""
          <tr>
            <td><span class="font-mono">{t['code']}</span><br><span class="text-xs text-gray-500">{t['name'][:20]}</span></td>
            <td>{t['entry_date'][:4]}-{t['entry_date'][4:6]}-{t['entry_date'][6:8]}</td>
            <td>{t['exit_date'][:4]}-{t['exit_date'][4:6]}-{t['exit_date'][6:8]}</td>
            <td>₩{t['entry_price']:,.0f}</td>
            <td>₩{t['exit_price']:,.0f}</td>
            <td class="{pct_cls}">{t['net_pct']:+.2f}%</td>
            <td>₩{t['invested']:,.0f}</td>
          </tr>"""

    html += f"""
        </tbody>
      </table>
    </div>

    <footer class="text-center text-sm text-gray-500 py-4">
      KOSDAQ 알고리즘 트레이딩 시스템 · 백테스트 기간 3년 · ⚠️ Paper trading 결과는 실전과 다를 수 있음
    </footer>

  </div>

<script>
  // 자본 곡선
  const eqData = {eq_curve_json};
  const ctxEq = document.getElementById('equityChart').getContext('2d');
  new Chart(ctxEq, {{
    type: 'line',
    data: {{
      labels: eqData.map(e => e.d),
      datasets: [{{
        label: '자본 (₩)',
        data: eqData.map(e => e.equity),
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.1,
        pointRadius: 0,
      }}]
    }},
    options: {{
      maintainAspectRatio: false,
      responsive: true,
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 12 }} }},
        y: {{ ticks: {{ callback: v => '₩' + v.toLocaleString() }} }}
      }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});

  // 현재 보유 포지션 미니 차트
  const openPositions = {open_pos_json};
  openPositions.slice(0, 30).forEach((pos, i) => {{
    const ctx = document.getElementById('posChart_' + i);
    if (!ctx || !pos.price_series || pos.price_series.length === 0) return;
    const color = pos.unreal_pct >= 0 ? '#16a34a' : '#dc2626';
    new Chart(ctx, {{
      type: 'line',
      data: {{
        labels: pos.price_series.map(p => p.d),
        datasets: [{{
          data: pos.price_series.map(p => p.p),
          borderColor: color,
          backgroundColor: color + '20',
          fill: true,
          tension: 0.1,
          pointRadius: 0,
        }}]
      }},
      options: {{
        responsive: false,
        plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }},
        scales: {{ x: {{ display: false }}, y: {{ display: false }} }}
      }}
    }});
  }});
</script>
</body>
</html>
"""
    return html


def main():
    if not os.path.exists(SIGNALS_CSV):
        print(f"[error] {SIGNALS_CSV} 없음. seed_paper_signals.py 먼저 실행.")
        return

    print("=== Paper Trading Dashboard 생성 ===")
    print(f"자본: ₩{INITIAL_CAPITAL:,} / max_concurrent={MAX_CONCURRENT} / holding={HOLDING_DAYS}일")

    print("\n[1/4] 신호 데이터 로드...")
    signals = pd.read_csv(SIGNALS_CSV, dtype={"code": str})
    signals["code"] = signals["code"].astype(str).str.zfill(6)
    signals["signal_date"] = signals["signal_date"].astype(str)
    print(f"   누적 신호: {len(signals)} 건")

    print("\n[2/4] 가격 데이터 로드...")
    df = load_macro_daily()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = df["date"].astype(str)
    print(f"   {df['code'].nunique()} 종목, {df['date'].nunique()} 영업일, 최신 {df['date'].max()}")

    print("\n[3/4] 매매 시뮬레이션...")
    trades = build_trades(signals, df)
    sim = simulate_capital(trades)
    open_pos = get_current_positions(trades, df)
    print(f"   매매 생성: {len(trades)} (청산 {sum(1 for t in trades if t['status']=='closed')}, 보유 {len(open_pos)})")
    if sim:
        print(f"   자본: ₩{INITIAL_CAPITAL:,} → ₩{sim['final']:,.0f} ({sim['total_return']:+.2f}%)")
        print(f"   CAGR: {sim['cagr']:+.2f}% / MDD: {sim['mdd']:+.2f}% / Sharpe: {sim['sharpe']:.2f}")

    print("\n[4/4] HTML 대시보드 생성...")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_html(sim, open_pos, df, generated_at)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   저장: {OUTPUT_HTML}")
    print(f"\n브라우저로 열기: start {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
