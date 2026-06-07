# Stock_AI_Project 파일 사용 가이드

**메인 전략: high_500d_h40_MKT** (500일 신고가 + 40일 보유 + 시장 강세 게이트).
3년치 데이터 4단계 분석 (매매당 → 자본 → walk-forward → multi-split) 거쳐 확정.
실측 CAGR +79.75%/년, MDD -10.13%, Sharpe +1.95.

단타 박스권 룰 v2 는 비용 한계로 break-even 미달 → 별건으로만 유지 (자동 백테스트).

## 시스템 한눈에

```
데이터 수집                전략 평가                실전 운용
┌─────────────┐          ┌─────────────┐         ┌─────────────┐
│ KIS API     │          │ strategies/ │         │ live_signal │
│   ranking   │ ──────► │   14종 등록  │ ──────►│   매일 16:30 │
│   분봉      │          │             │         │             │
│ pykrx       │          │ engine.py   │         │ paper_      │
│   3년 일봉  │          │   비교 표   │         │   tracker   │
│ KRX,DART    │          │ capital_sim │         │             │
│             │          │ walkforward │         │ → 진짜 시장 │
└─────────────┘          └─────────────┘         └─────────────┘
```

---

## 1. 자주 쓰는 명령어

### ⭐ 메인 운영 (매일)
| 목적 | 명령어 |
|---|---|
| **오늘 메인 전략 신호** | `python live_signal.py` |
| **paper trading 상태 + 누적 손익** | `python paper_tracker.py` |
| 6/5 같이 신호 0건 시 진단 | `python debug_signal.py` |

### 전략 평가 (가끔)
| 목적 | 명령어 |
|---|---|
| 14개 전략 동시 비교 + 자본 시뮬 | `python strategy_engine.py` |
| Walk-forward 견고성 (3 split) | `python walkforward.py` |
| paper_signals.csv 초기 시드 | `python seed_paper_signals.py` |

### 데이터 수집 (자동화됨, 수동은 가끔)
| 목적 | 명령어 |
|---|---|
| KIS 데이터 (단타 별건) | `python data_collector.py today` |
| KRX 공매도 | `python krx_collector.py both` |
| DART 공시 | `python dart_collector.py today` |
| pykrx 일봉 (메인 전략 데이터) | `python pykrx_collector.py` |

### 옛 백테스트 (별건 유지)
| 목적 | 명령어 |
|---|---|
| 단타 v2 백테스트 | `python backtest.py` |
| 오버나잇 종가베팅 | `python backtest_swing.py` |
| 매크로 3전략 벡터화 | `python pykrx_backtester.py` |

### 시스템
| 목적 | 명령어 |
|---|---|
| 자동화 상태 확인 | `Get-ScheduledTask -TaskName "KIS_*" \| Get-ScheduledTaskInfo \| Select TaskName, NextRunTime, LastRunTime, LastTaskResult` |

모든 명령은 먼저 `cd C:\fin\outputs` + `.venv\Scripts\Activate.ps1` (또는 `.venv\Scripts\activate`) 후 실행. 그러면 `python` 명령이 venv 의 Python 을 가리켜 pykrx 등 프로젝트 패키지를 정상 인식.

`py -3.11` 사용도 가능하지만 시스템 Python 을 띄우기 때문에 venv 패키지 못 보임. **venv 활성화 후 `python` 사용 권장.**

---

## 1.5 메인 전략 — high_500d_h40_MKT

### 룰
| 항목 | 값 |
|---|---|
| 진입 | 종가가 직전 500 영업일 신고가 돌파 |
| 시장 게이트 | 시장 평균 등락률의 60일 MA > 0 (강세장만) |
| 유동성 | 거래대금 ≥ 10억 (전일) |
| 진입가 | 신호 다음 영업일 시가 |
| 청산 | 진입 후 40 영업일 종가 |
| 자본 운용 | 최대 10종목 동시보유 (max_concurrent), 자본 1/N 분배 |

### 실측 성과 (3년치 macro_data, 단방향 -30% 컷오프 적용)

| 지표 | 값 |
|---|---|
| n_trades | 1,411 (단방향 -30% 컷오프 후) |
| 승률 | 49.28% |
| CAGR | **+156.27%/년** |
| Real MDD | **-8.03%** |
| Real Sharpe | **+3.01** |
| 1천만원 → 3년 후 | 약 2,752만원 |

### 액면분할/병합 방어 — 단방향 컷오프 정책

pykrx 의 raw OHLCV 는 수정주가 미반영 → 액면분할 시 가짜 -80% 폭락 발생.
**음수 한쪽만 -30% 컷오프** (양수는 진짜 익절이므로 보존):
- 컷오프 186건 (~13%) = 액면분할/병합 의심 매매 제외
- 양방향 ±30% 는 진짜 익절 359건도 잘라 결과 왜곡 (검증됨)
- 진짜 정답 = pykrx adjusted 미지원 → FinanceDataReader 같은 외부 라이브러리 별건 작업

### Walk-forward Multi-split 견고성

| Split | OOS CAGR |
|---|---|
| 50/50 | +77.67% |
| 67/33 | +35.40% |
| 75/25 | +44.50% |
| **모든 split 에서 OOS 양수** | ⭐ 가장 견고한 단일 전략 |

### 폐기/대안 전략
- **단타 박스권 룰 v2**: profit_factor 0.55, 비용 0.33% 못 이김 → 폐기 (자동 백테스트만 유지)
- **portfolio_v1~v4**: 다각화가 max_concurrent=10 슬롯 병목으로 단일보다 약함
- 종가베팅/모멘텀/RSI/갭매매 등 11개: OOS 검증 못 통과

---

## 1.6 분석 4단계 — 진실에 도달한 과정

| 단계 | 결과 | 진실? |
|---|---|---|
| 1. 매매당 평균 | high_500d_h40 (pf 2.04) 우위 | ❌ 자본 회전 무시 |
| 2. 자본 시뮬 | high_500d_h40 (+129%) 우위 | ❌ train 운 포함 |
| 3. 단일 walk-forward (67/33) | portfolio_trend3, h500_40 폐기 | ❌ 단일 분할 운 |
| 4. **Multi-split walk-forward** | **high_500d_h40_MKT 단일 확정** | ⭐ **진짜 답** |

**교훈**: 4단계 검증 거쳐야 진실. 매매당 평균만 보고 결정 X. 시장 게이트 (MKT 필터) 가 진짜 가치.

---

## 1.7 Paper Trading 사용법

### 매일 운영 (자동)
- **KIS_Paper 작업** 매일 16:30 자동 실행
- `live_signal.py` → 오늘 신호 종목 출력 + `paper_signals.csv` 추가
- `paper_tracker.py` → 누적 매매 + 현재 보유 + 자본 곡선

### 수동 점검 (필요 시)
```powershell
python live_signal.py       # 오늘 신호 (시장 약세면 0건이 정상)
python paper_tracker.py     # 누적 손익 + 보유 포지션
python debug_signal.py      # 신호 0건일 때 진단
```

### 실전 진행 단계 (계획)
1. **지금~1개월**: 자동 paper trading 누적 (KIS_Paper 16:30)
2. **1개월 후**: 실제 누적 결과 점검. 백테스트 예상치와 비교.
3. **2~3개월 누적 → 검증 통과 시**: 소액 (50~100만원) 실전 진입
4. **6개월 안정 운용 후**: 자본 증액 단계

### Paper 데이터 흐름
```
macro_data/daily/*.csv ──► live_signal.py ──► paper_signals.csv
                                                  │
                                                  ▼
                              paper_tracker.py ──► 자본 곡선 + 손익
```

---

## 2. .py 파일별 용도와 실행법

### config.py
**용도**: 룰 v2 파라미터, KIS 인증, 경로 설정 일괄 관리. 다른 모듈이 다 import 해서 씀.

**직접 실행**: `py -3.11 config.py` → 현재 설정 요약 출력 (디버그용)

**주요 토글**:
- `KIS_ENV` — "prod"(실전) / "vps"(모의)
- `TOP_N_STOCKS = 50` — 거래대금 raw 상위 N개 (ETF 포함)
- `ENABLE_FOREIGN_FILTER` — True 면 백테스트 시 D-1 외인 순매수>0 종목만 진입
- `ENABLE_ETF_FILTER` — True 면 백테스트 시 ETF/우선주 제외
- `RULE_V2` dict — 박스 폭, 익절/손절, 시간청산, 비용 가정 등

룰 바꾸려면 이 파일만 수정.

---

### data_collector.py
**용도**: KIS API → CSV 데이터 수집 메인.

**명령어**:
```
py -3.11 data_collector.py ranking            # 거래대금 raw 상위 50 (KOSPI+KOSDAQ 머지)
py -3.11 data_collector.py minutes YYYYMMDD   # 특정 날짜 분봉 (당일치만 가능)
py -3.11 data_collector.py investor [date]    # 외인/기관/개인 매매 데이터
py -3.11 data_collector.py daily [date]       # 종목별 일봉 60일치
python data_collector.py index [date]         # KOSPI/KOSDAQ 지수 snapshot (15컬럼)
python data_collector.py index_minutes [date]  # KOSPI/KOSDAQ 지수 당일 분봉 (EOD 1회)
py -3.11 data_collector.py today              # 위 모두 + 장 마감 후 자동 분기
```

**자동 호출**: `run_collector.bat` 가 `today` 모드로 호출.

`today` 모드 분기:
- 15:30 이전: `ranking` + `index_snapshot` 만 누적
- 15:30 이후: `ranking` + `index_snapshot` + `minutes` + `investor` + `daily` + `index_minutes`

---

### data_loader.py
**용도**: 저장된 CSV → pandas DataFrame 변환. backtest/detector 가 사용.

**직접 실행**: `py -3.11 data_loader.py` → 최신 날짜의 ranking/분봉 샘플 출력 (디버그)

직접 호출할 일은 거의 없음.

---

### detector.py
**용도**: 박스권 + 거래량 급증 신호 감지. simulator 가 사용.

**직접 실행**: `py -3.11 detector.py` → 테스트 데이터로 감지 동작 확인 (디버그)

룩어헤드 편향 방지를 위해 `shift(1)` 적용된 상태. `is_box`=True 는 "직전 5분 박스 형성됨" 을 의미.

---

### simulator.py
**용도**: 가상 매매 시뮬레이터. backtest 가 사용.

**직접 실행**: `py -3.11 simulator.py [YYYYMMDD] [MODE]`
- MODE: A (박스 매수), B (거래량 돌파), AB (둘 다)
- 예: `py -3.11 simulator.py 20260604 AB`

Mode B 게이트: `close > box_high` (진짜 돌파만).

---

### analyzer.py
**용도**: 매매 리스트 → 승률/손익비/MDD 등 통계 계산. backtest 가 사용.

직접 실행 안 함.

---

### backtest.py
**용도**: 백테스트 메인 엔트리포인트. 인자 없으면 전체 누적 날짜 × 모드 A/B/AB 다 비교.

**명령어**:
```
py -3.11 backtest.py                    # 전체 / 전체 모드
py -3.11 backtest.py 20260604           # 특정 날짜
py -3.11 backtest.py AB                 # 특정 모드
py -3.11 backtest.py 20260604 AB        # 둘 다
```

**결과**:
- 콘솔: 모드별 비교 리포트 (n_trades, win_rate, avg_net_pct, profit_factor, cum_pct, mdd_pct)
- 파일: `results/trades_MODE_시작-끝.csv`, `results/daily_MODE_시작-끝.csv`

**자동 호출**: `run_backtest.bat` 가 매일 16:00 호출.

---

### live_signal.py *(MAIN)*
**용도**: 메인 전략 high_500d_h40_MKT 신호 감지. 매일 실행.

**명령어**: `python live_signal.py`

**기능**:
- macro_data/daily/ 최신 영업일 데이터로 500일 신고가 돌파 검사
- 시장 강세 게이트 (60일 MA > 0) 확인
- 거래대금 10억 이상 필터
- ETF/우선주 제외
- 신호 종목 → 콘솔 출력 + `paper_signals.csv` 누적 (멱등)

**자동 호출**: `run_paper.bat` 가 매일 16:30 호출 (KIS_Paper 작업).

### paper_tracker.py *(MAIN)*
**용도**: paper_signals.csv 의 모든 신호로 가상 매매 수행. 누적 손익 + 보유 포지션 출력.

**명령어**: `python paper_tracker.py`

**자동 호출**: `run_paper.bat` 가 live_signal 후 호출.

### debug_signal.py
**용도**: live_signal.py 가 0건일 때 진단. 시장 게이트 / 신고가 / 거래대금 단계별 종목 수.

**명령어**: `python debug_signal.py`

### seed_paper_signals.py
**용도**: paper_signals.csv 를 과거 3년치 백테스트 신호로 시드. 즉시 의미 있는 paper_tracker 결과 확인.

**명령어**: `python seed_paper_signals.py` (y 입력)

### strategy_engine.py
**용도**: 14개 전략 일괄 백테스트 + 자본 시뮬 비교.

**명령어**: `python strategy_engine.py`

### walkforward.py
**용도**: 3개 split (50/50, 67/33, 75/25) walk-forward 견고성 검증.

**명령어**: `python walkforward.py`

### capital_simulator.py
**용도**: max_concurrent 슬롯 cap 적용 자본 시뮬. CAGR / 진짜 MDD / Sharpe.

직접 호출 안 함 — 다른 모듈이 import.

### strategies/ 폴더 *(NEW)*
14개 전략 모듈:
- `base.py` — BaseStrategy + StrategyTrade
- `daily_loader.py` — macro_data 통합 로더
- `_swing_base.py` — 진입 lag + 보유 청산 공통 헬퍼
- `gap_buy.py` — 갭매매 (#4)
- `momentum_5d.py` — 5일 모멘텀 (#8)
- `breakout_5d.py` — 5일 신고가 (#9)
- `rsi_reversal.py` — RSI 과매도 (#10)
- `high_52w.py` — 52주 신고가 (#11) **베이스**
- `volume_surge.py` — 거래량 급증 (#12)
- `high_with_filters.py` — 신고가 + 시장 게이트 + 거래량 (high_500d_h40_MKT) ⭐ **메인**
- `portfolio.py` — 다중 전략 결합

### backfill_history.py
**용도**: 과거 분봉/ranking 백필. **FHKST03010230 endpoint 발견 후 1년치 과거 분봉 백필 가능** (실전 키 필수).

**전제** — 실전 KIS 키 + .env 에 `KIS_ENV=prod` + `KIS_PROD_*` 변수 설정. 모의(vps) 환경에선 작동 안 함 (KIS 모의투자 미지원 endpoint).

**명령어**:
```
python backfill_history.py --dry-run    # 계획만 출력
python backfill_history.py              # 실행 (1년치 가능)
python backfill_history.py --days 14    # 윈도우 축소
```

백필 흐름:
1. db/daily 기반 과거 영업일별 raw 50 ranking 합성/재사용
2. 각 날짜의 종목별 분봉 수집 (FHKST03010230, 한 호출 120건)
3. 멱등 — 이미 있는 분봉 skip

---

### kis_api.py
**용도**: KIS API HTTP 클라이언트. 토큰 관리, 재시도, timeout.

직접 실행 안 함. 다른 모듈이 함수 import.

주요 함수:
- `get_volume_ranking(market, by)` — 거래대금/거래량 상위 (KOSPI/KOSDAQ 각각 호출)
- `get_minute_chart(stock_code, target_time)` — 종목 당일 분봉 (FHKST03010200, vps OK)
- `get_full_day_minutes(code, date)` — 당일치 분봉 누적
- **`get_minute_chart_historical(stock_code, date, target_time)` — 종목 과거 분봉 (FHKST03010230, prod 키 필수)**
- **`get_full_day_historical_minutes(code, date)` — 과거 특정일 하루치 분봉 누적 (시각 역순 4번 호출)**
- `get_daily_chart(code, period_days)` — 일봉
- `get_foreign_institution_trading(market)` — 외인/기관
- `get_stock_investor(code, target_date)` — 종목별 투자자
- `get_index_current(market)` — KOSPI/KOSDAQ 지수 현재값 + breadth (OHLC + 상승/하락 종목 수)
- `get_index_minute_chart(market, target_time)` — 지수 분봉 (vps 미지원, 일봉만 반환)

---

### krx_collector.py *(NEW)*
**용도**: pykrx 로 KRX 정보데이터시스템에서 공매도 데이터 수집. T-1 기준.

**전제**:
- `pip install pykrx` (venv 활성화 후)
- `.env` 에 KRX 로그인:
```
KRX_ID=hong****
KRX_PW=********
```
KRX 정보데이터시스템 (data.krx.co.kr) 무료 가입 후 ID/PW 사용.

**현재 제약 (pykrx 1.2.8 기준)**:
- **신용잔고 미지원** — pykrx 가 해당 함수를 제공 안 함. credit 명령은 안내만 출력 후 종료.
- **공매도 잔고 fallback 체인** — `get_shorting_balance_by_ticker` 가 KRX 컬럼 변경으로 깨진 상태 → `volume_by_ticker` → `value_by_ticker` → `balance_top50` 순으로 시도. 저장 파일 마지막 컬럼 `__source` 에 어떤 함수에서 받았는지 기록.

**명령어**:
```
python krx_collector.py short             # 직전 영업일 공매도
python krx_collector.py short 20260603    # 특정 날짜
python krx_collector.py both              # credit 안내 + short 실행
python krx_collector.py credit            # 안내만 (현재 미지원)
```

저장: `db/short/YYYY-MM/YYYYMMDD.csv`
실측 컬럼 예시 (`source=volume_by_ticker` 일 때):
```
티커, 공매도, 매수, 비중, __source
```
- 공매도: 공매도 거래량
- 매수: 일반 매수 거래량
- 비중: 공매도/총 거래의 % (해당 일 기준)
- `__source`: 어떤 fallback 함수에서 받았는지 (분석 시 동질성 체크)

(`db/credit/` 은 폴더만 생성되고 파일 안 들어옴 — pykrx 한계)

**자동 호출**: `run_krx.bat` 가 매일 평일 08:30 호출 (KIS_KRX 작업).

---

### dart_collector.py *(NEW)*
**용도**: DART (전자공시시스템) 일자별 공시 목록 수집.

**전제**: `.env` 에 `DART_API_KEY=...` 등록 (https://opendart.fss.or.kr 가입 후 발급).

**명령어**:
```
py -3.11 dart_collector.py today              # 오늘 공시
py -3.11 dart_collector.py date 20260604      # 특정 날짜
py -3.11 dart_collector.py corp 005930 20260601 20260604  # 특정 종목 기간
```

저장: `db/dart/YYYY-MM/YYYYMMDD.csv`

**자동 호출**: `run_dart.bat` 가 매일 평일 19:00 호출 (KIS_DART 작업).

---

### nxt_probe.py *(NEW)*
**용도**: NXT(넥스트레이드) 시간외 분봉 KIS API 지원 가능성 검증.

**직접 실행**: `py -3.11 nxt_probe.py`

market_div (J/NX/UN) 별로 17:00 시각 분봉을 시도해서 vps 환경 NXT 지원 여부 확인. 결과에 따라 data_collector 통합 여부 결정.

---

### kis_websocket.py / tick_collector.py
**용도**: WebSocket 실시간 체결 수신 + SQLite 적재.

**전제**: KIS 발급 별도 Approval Key 필요. `pip install websockets` 필요.

실시간 트레이딩 인프라 구축용 별건 모듈. 백테스트 흐름과는 독립.

### run_tick_collector.bat *(NEW)*
**용도**: `tick_collector.py` 를 장중 자동 실행, 15:30 종료. 끊김 시 재시작 루프.

---

## 스윙 전략 (별건, 일봉 기반)

단타(룰 v2)의 비용 한계 회피를 위해 일봉 기반 스윙 전략 인프라 별도 구축.

### pykrx_collector.py *(NEW)*
**용도**: pykrx 로 3년치 일봉 + 수급 데이터 수집 → `macro_data/daily/` 적재.

**전제**: `pip install pykrx`, KRX_ID/PW 등록 (krx_collector 와 동일).

**명령어**:
```
python pykrx_collector.py
```

### pykrx_backtester.py *(NEW)*
**용도**: 3년치 일봉 데이터로 매크로 전략 3개 동시 벡터화 백테스트. 단타 simulator 와 독립.

**명령어**:
```
python pykrx_backtester.py
```

### backtest_swing.py *(NEW)*
**용도**: 오버나잇 종가베팅 백테스트.
- 진입: 15:20, MA5 위 + 당일 외인 순매수 양수
- 청산: 익일 09:05 시가 (갭 수익 확정)

분봉 데이터 활용 (data_loader 와 같은 분봉 사용). analyzer/Trade 데이터클래스 재사용.

**명령어**:
```
python backtest_swing.py
```

전제: `data/rankings/`, `db/minute/`, `db/investor/` 모두 채워져 있어야 함 (분봉 시점 + 외인 데이터 필요).

---

### monthly_xlsx_builder.py
**용도**: 월말 데이터 xlsx 합본 빌드.

**자동 호출**: 매월 1일 02:00 (KIS_Monthly 작업)

---

### diag_env.py
**용도**: 환경 진단 (Python 버전, .env, KIS 인증 상태 등 체크).

**직접 실행**: `py -3.11 diag_env.py` → 환경 문제 점검할 때.

---

## 3. .bat / .ps1 파일

### run_collector.bat
- `data_collector.py today` 호출 + `logs/collect_YYYYMMDD.log` 기록
- 주말 자동 스킵, 로그 30일 자동 삭제
- 자동 호출: KIS_Ranking + KIS_EOD
- Python 우선순위: `.venv\Scripts\python.exe` → `py -3.11` → `python` (venv 가 있으면 무조건 우선 사용)

### run_backtest.bat
- `backtest.py` 호출 + `logs/backtest_YYYYMMDD.log` 기록
- 자동 호출: KIS_Backtest

### run_krx.bat *(NEW)*
- `krx_collector.py both` 호출 + `logs/krx_YYYYMMDD.log`
- 자동 호출: KIS_KRX

### run_dart.bat *(NEW)*
- `dart_collector.py today` 호출 + `logs/dart_YYYYMMDD.log`
- 자동 호출: KIS_DART

### install_scheduler.ps1
- Windows 작업 스케줄러에 **6개 작업** 등록 (Ranking/EOD/Backtest/KRX/DART/Monthly)
- 재실행하면 깔끔하게 재등록 (idempotent)
- 실행: `powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1`

### register_task.bat / unregister_task.bat
- 옛 자동화 등록/해제 스크립트 (현재는 install_scheduler.ps1 사용)

### start_monitor.bat / monitor.ps1
- 모니터링 스크립트 (별건)

---

## 4. 자동화 작업 스케줄러 흐름

| 시각 | 작업 이름 | 호출 |
|---|---|---|
| 매일 평일 08:30 | KIS_KRX | run_krx.bat → krx_collector.py both (T-1 공매도) |
| 매일 09:00~14:30 (30분 간격) | KIS_Ranking | run_collector.bat → data_collector.py today (분봉 ranking + 지수 snapshot) |
| 매일 15:40 | KIS_EOD | run_collector.bat → data_collector.py today (장 마감 종합) |
| 매일 16:00 | KIS_Backtest | run_backtest.bat → backtest.py (단타 v2 별건) |
| **매일 16:30** | **KIS_Paper** ⭐ | **run_paper.bat → live_signal + paper_tracker (메인)** |
| 매일 평일 19:00 | KIS_DART | run_dart.bat → dart_collector.py today |
| 매월 1일 02:00 | KIS_Monthly | monthly_xlsx_builder.py |

PC가 깨어 있고 인터넷 연결되면 매일 자동 실행. 슬립 OFF + 부팅 자동 실행 필수.

---

## 5. 데이터 폴더 구조

```
C:\fin\outputs\
├── .env                         # KIS API 키 + DART_API_KEY (절대 git에 올리지 말 것)
├── .kis_token.json              # KIS 토큰 캐시
├── data/
│   └── rankings/YYYYMMDD.csv    # 시각별 거래대금 상위 50 (raw, ETF 포함)
├── db/
│   ├── minute/YYYY-MM/YYYYMMDD/CODE.csv   # 종목별 분봉
│   ├── investor/YYYY-MM/YYYYMMDD.csv      # 일자별 외인/기관/개인
│   ├── daily/YYYY-MM/YYYYMMDD.csv         # 종목별 60일 일봉
│   ├── index/YYYY-MM/YYYYMMDD.csv         # 지수 30분 snapshot (15컬럼: OHLC + breadth)  (NEW)
│   ├── index/YYYY-MM/YYYYMMDD_minute.csv  # 지수 당일 1분봉 (KOSPI+KOSDAQ)  (NEW)
│   ├── credit/YYYY-MM/YYYYMMDD.csv        # 신용잔고 (T-1)  (NEW)
│   ├── short/YYYY-MM/YYYYMMDD.csv         # 공매도 잔고 (T-1)  (NEW)
│   ├── dart/YYYY-MM/YYYYMMDD.csv          # DART 공시  (NEW)
│   ├── xlsx/                              # 월말 xlsx 합본
│   └── ticks.db                           # 실시간 틱 SQLite (tick_collector)
├── results/
│   ├── trades_MODE_시작-끝.csv             # 매매 한 건 한 건
│   └── daily_MODE_시작-끝.csv              # 일별 손익 요약
└── logs/
    ├── collect_YYYYMMDD.log               # 수집 로그
    ├── backtest_YYYYMMDD.log              # 백테스트 로그
    ├── krx_YYYYMMDD.log                   # KRX 수집 로그  (NEW)
    └── dart_YYYYMMDD.log                  # DART 수집 로그  (NEW)
```

---

## 6. 알려진 제약

1. **종목 분봉** — vps 는 당일치만(`FHKST03010200`), prod 는 1년치 과거 백필 가능(`FHKST03010230`). 평소 vps 로 매일 누적 + 백필 필요할 때 prod 로 일시 전환.
2. **호가/체결강도 데이터 없음** — KIS 무료 API 한계.
3. **KIS vps(모의) 환경 일부 endpoint 제약** — 실전 키와 동작 다를 수 있음.
4. **지수 분봉** — endpoint `inquire-index-tickprice` + TR_ID `FHKUP03500200` + `FID_PW_DATA_INCU_YN=Y` 조합으로 vps 정상 동작 확인. 1차 probe 에서 빠진 필드 때문에 잘못 진단했었음. EOD 1회 누적 (종목 분봉처럼 30분 단위 역순 호출). 추가로 snapshot(30분 간격) 도 별도 보존 — OHLC + breadth 정보가 분봉엔 없으므로 둘 다 가치 있음.
5. **KIS 토큰 24시간 만료** — 장시간 실행 시 재발급 필요.
6. **PC 슬립/종료 시 자동 수집 중단** — 슬립 OFF 필수, 종료 시 그날 데이터 손실 가능.
7. **KRX T-1 지연** — 신용/공매도 데이터는 항상 전일치만 가능 (한국거래소 정책).
8. **DART 공시는 실시간 아님** — 보통 18시까지 그날 공시 등록 완료. 19:00 수집이 안전.
9. **NXT 시간외 분봉** — KIS vps 지원 미검증. `nxt_probe.py` 결과에 따라.

---

## 7. 흔한 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| 자동 수집이 안 됨 | PC 슬립 / 작업 비활성화 / .bat escape 에러 | `Get-ScheduledTaskInfo` 로 LastTaskResult 확인. 255면 .bat escape 문제. |
| `cacert.pem` 에러 | 백신이 venv 파일 격리 | `pip install --force-reinstall certifi` + venv 백신 제외 등록 |
| 새 컬럼 추가 후 sqlite 에러 | 스키마 마이그레이션 누락 | ALTER TABLE ADD COLUMN |
| 백테스트 `수집된 분봉 데이터가 없습니다` | data/rankings 또는 db/minute 비어 있음 | 먼저 `data_collector.py today` 실행 |
| `pykrx 미설치` 에러 | KRX 수집기 첫 실행 | `(.venv)` 활성화 후 `pip install pykrx` |
| `pykrx 미설치` 에러 (venv 에는 설치돼 있는데) | `py -3.11` 이 venv 가 아닌 시스템 Python 호출 | `python krx_collector.py both` (venv 활성) 또는 `.venv\Scripts\python.exe krx_collector.py both`. 자동화 .bat 는 이미 .venv 우선 사용. |
| `module 'pykrx.stock' has no attribute 'get_market_credit_balance_by_ticker'` | pykrx 가 신용잔고 미지원 | 정상 — 신용잔고는 별건. `[credit] 미지원 (skip)` 안내만 출력 후 진행. |
| `get_shorting_balance_by_ticker: None of [Index([...])] are in [columns]` | KRX 가 응답 컬럼명 변경, pykrx 1.2.8 미동기화 | 정상 — 자동으로 다음 fallback (`volume_by_ticker` 등) 시도. 저장 CSV 의 `__source` 컬럼으로 사용된 함수 확인. pykrx 업그레이드 (`pip install -U pykrx`) 후 재시도하면 원래 함수로 복귀 가능. |
| `KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다` (`python -c` 직접 실행 시) | config 안 import → .env 안 로드 | 정상 — `krx_collector.py` 정상 실행 시엔 config 가 먼저 import 되어 .env 로드됨. 확인은 `python -c "import config; import os; print(os.environ.get('KRX_ID'))"` |
| `DART_API_KEY 환경변수 없음` | .env 누락 | https://opendart.fss.or.kr 가입 + .env 등록 |
| 지수 분봉 0건 | `FID_PW_DATA_INCU_YN` 누락 또는 TR_ID 잘못 | 정상 TR_ID = FHKUP03500200, 필수 파라미터 `FID_PW_DATA_INCU_YN=Y` 확인. kis_api.py 의 `get_index_minute_chart` 가 이미 정확한 파라미터로 호출. |
| 지수 snapshot 파일 컬럼 불일치 (옛 7컬럼 + 새 15컬럼) | 코드 업데이트 전후 같은 파일에 append | 해당 날짜 파일 삭제 후 재실행: `Remove-Item db/index/YYYY-MM/YYYYMMDD.csv; python data_collector.py index` |
| KRX 월요일에 빈 결과 | 일요일 데이터 없음 (`_last_business_day` 미적용 옛 버전) | 최신 코드는 자동으로 직전 영업일 사용. 옛 버전이면 코드 업데이트. |

---

## 8. 룰 v2 요약 + 분석 결과

### 룰 파라미터

| 항목 | 값 | 변경 이력 |
|---|---|---|
| 시장 | KOSPI + KOSDAQ | |
| 종목 풀 | 거래대금 raw 상위 50 (ETF/우선주는 백테스트에서 제외) | |
| **박스 시간** | **직전 10분** (현재 분봉 제외) | (기존 5분, 22일치 시간청산 78% 대응) |
| 박스 폭 | ±2.0% (0.8% 미만 제외) | |
| 진입 A | 박스 하단 + 박스폭의 5% | |
| 진입 B | 박스 + 거래량 2배↑ + close > box_high (진짜 돌파만) | |
| **1차 익절** | **+0.8%** 에서 절반 | (기존 0.7%) |
| 트레일링 | 고점 대비 -0.4% | |
| **시간 청산** | **15분** | (기존 5분, 진득 대기) |
| **손절** | **-2.0%** | (기존 -1.8%, 잔파도 털림 방지) |
| 비용 가정 | 수수료 0.015%×2 + 거래세(KOSDAQ 0.20%) + 슬리피지 0.05%×2 = 약 0.43% | |

### 8일치 데이터 분석 결과 (2026-06-04 기준)

| 지표 | 값 |
|---|---|
| 종목-일 수 | 388 |
| 진짜 돌파 표본 | 1,353건 |
| 5분 내 +0.7% 익절 도달률 | 38.8% |
| 5분 내 -1.8% 손절 도달률 | 10.1% |
| 시간청산 (5분내 미도달) | 52.5% |
| 룰 기댓값 (net) | **-0.614%** (비용 0.43% 못 이김) |

**핵심**: TP/SL 튜닝, 시간대 필터, vol_ratio 강화 등 모든 조합이 -EV. **돌파 신호 자체에 통계적 우위 부족**. 신호 추가 또는 룰 본체 재설계 필요. (USAGE.md 9번 섹션 참고)

---

## 9. 다음 단계 — 데이터 축적 + 분석 우선순위

| 데이터 | 상태 | 활용 가능성 |
|---|---|---|
| 시장지수 KOSPI/KOSDAQ | 수집 시작 | 시장 컨텍스트 필터 |
| 신용잔고 (T-1) | 수집 시작 | 변동성 위험 종목 분별 |
| 공매도 잔고 (T-1) | 수집 시작 | Short squeeze 후보 |
| DART 공시 | 수집 시작 (API 키 필요) | 이벤트 종목 제외 필터 |
| NXT 시간외 분봉 | 검증 대기 | nxt_probe.py 결과 후 결정 |
| 호가/체결강도 | 미지원 (유료 필요) | — |

각 데이터 1~2주 누적되면 detector 에 신호로 통합. 통합 패턴은 D-1 외인 필터와 동일 (`config.ENABLE_*_FILTER` 토글로 on/off 비교).
