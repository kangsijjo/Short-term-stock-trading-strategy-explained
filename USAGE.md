# Stock_AI_Project 파일 사용 가이드

단타 박스권 매매(룰 v2) 시스템. KIS API + KRX + DART → 데이터 수집 → 백테스트 파이프라인.

---

## 1. 자주 쓰는 명령어 (이거 6개만 알면 거의 다 됨)

| 목적 | 명령어 |
|---|---|
| 오늘 데이터 수동 수집 (KIS) | `python data_collector.py today` |
| 신용/공매도 수동 수집 (KRX) | `python krx_collector.py both` |
| 오늘 공시 수동 수집 (DART) | `python dart_collector.py today` |
| 백테스트 실행 (전체 기간) | `python backtest.py` |
| 백테스트 (특정 날짜/모드) | `python backtest.py 20260604 AB` |
| 자동화 상태 확인 | `Get-ScheduledTask -TaskName "KIS_*" \| Get-ScheduledTaskInfo \| Select TaskName, NextRunTime, LastRunTime, LastTaskResult` |

모든 명령은 먼저 `cd C:\fin\outputs` + `.venv\Scripts\Activate.ps1` (또는 `.venv\Scripts\activate`) 후 실행. 그러면 `python` 명령이 venv 의 Python 을 가리켜 pykrx 등 프로젝트 패키지를 정상 인식.

`py -3.11` 사용도 가능하지만 시스템 Python 을 띄우기 때문에 venv 패키지 못 보임. **venv 활성화 후 `python` 사용 권장.**

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
| 매일 평일 08:30 | **KIS_KRX** | run_krx.bat → krx_collector.py both (T-1 신용/공매도) |
| 매일 09:00~14:30 (30분 간격) | KIS_Ranking | run_collector.bat → data_collector.py today (ranking + 지수) |
| 매일 15:40 | KIS_EOD | run_collector.bat → data_collector.py today (장 마감 후 분봉+투자자+일봉+지수분봉) |
| 매일 16:00 | KIS_Backtest | run_backtest.bat → backtest.py |
| 매일 평일 19:00 | **KIS_DART** | run_dart.bat → dart_collector.py today |
| 매월 1일 02:00 | KIS_Monthly | py -3.11 monthly_xlsx_builder.py |

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

| 항목 | 값 |
|---|---|
| 시장 | KOSPI + KOSDAQ |
| 종목 풀 | 거래대금 raw 상위 50 (ETF/우선주는 백테스트에서 제외) |
| 박스 시간 | 직전 5분 (현재 분봉 제외) |
| 박스 폭 | ±2.0% (0.8% 미만 제외) |
| 진입 A | 박스 하단 + 박스폭의 5% |
| 진입 B | 박스 + 거래량 2배↑ + close > box_high (진짜 돌파만) |
| 1차 익절 | +0.7% 에서 절반 |
| 트레일링 | 고점 대비 -0.4% |
| 시간 청산 | 5분 |
| 손절 | -1.8% |
| 비용 가정 | 수수료 0.015%×2 + 거래세(KOSDAQ 0.20%) + 슬리피지 0.05%×2 = 약 0.43% |

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
