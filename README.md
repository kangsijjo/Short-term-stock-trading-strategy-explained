# 단타 박스권 매매 백테스트 — Phase 1: 데이터 수집

룰 v2 기반 자동매매 전략의 백테스트를 위한 데이터 수집 모듈입니다.

## 룰 v2 요약

| 항목 | 값 |
|---|---|
| 시장 | KOSPI + KOSDAQ |
| 종목 풀 | 장 시작 시 거래대금 상위 30개 (우선주/ETF/관리종목 제외) |
| 박스 시간 | 5분 |
| 박스 폭 | ±2.0% (단, 0.8% 미만은 제외) |
| 진입 A (박스권) | 박스 하단 + 박스폭의 5% 지점 매수 |
| 진입 B (거래량) | 직전 2~3분 평균 거래량의 2배↑ 발생 시 시장가 매수 |
| 1차 익절 | +0.7%에서 절반 |
| 트레일링 | 고점 대비 -0.4% |
| 시간 청산 | 5분 경과 시 전량 |
| 손절 | -1.8% |

## 환경 설정

### 1. Python 라이브러리 설치

```bash
pip install -r requirements.txt
```

### 2. KIS API 인증 정보 설정

`config.py` 상단의 `KIS_APP_KEY`, `KIS_APP_SECRET`을 본인 값으로 채우거나,
환경변수로 설정합니다 (권장):

```bash
# macOS/Linux
export KIS_APP_KEY="본인_APP_KEY"
export KIS_APP_SECRET="본인_APP_SECRET"

# Windows (PowerShell)
$env:KIS_APP_KEY="본인_APP_KEY"
$env:KIS_APP_SECRET="본인_APP_SECRET"
```

## 사용법

### A. 오늘 시점의 거래대금 상위 30개 종목 저장

```bash
python data_collector.py ranking
```

→ `data/rankings/YYYYMMDD.csv` 생성

### B. 특정 날짜의 분봉 데이터 수집

먼저 해당 날짜의 ranking이 있어야 합니다.

```bash
python data_collector.py minutes 20260515
```

→ `data/minute_bars/CODE_20260515.csv` 30개 생성

### C. 오늘 ranking + 분봉을 한 번에

```bash
python data_collector.py today
```

장 마감 후(15:30 이후) 실행하는 것이 좋습니다.

### D. 여러 날짜 분봉을 한 번에

```bash
python data_collector.py minutes 20260515 20260514 20260513
```

## 운영 팁

### 백테스트용 데이터 누적

KIS API는 분봉을 **최근 30일 정도**까지만 줍니다.
**매일 장 마감 후 자동 실행**하면서 데이터를 누적해야 의미 있는 백테스트가 가능합니다.

cron (macOS/Linux) 예시:
```
30 16 * * 1-5  cd /path/to/project && python data_collector.py today >> collect.log 2>&1
```

평일 16:30에 자동 실행. 1~2개월 모이면 백테스트 표본이 충분해집니다.

### 데이터 양 예상

- ranking 1개: 약 30 row (작음)
- 분봉 1종목 1일: 약 380 row
- 분봉 30종목 1일: 약 11,400 row (CSV 약 500KB)
- 분봉 30종목 × 60일: 약 30MB

### API 호출 부하

- 1종목 1일 분봉 수집: 약 14번 호출 + sleep
- 30종목 1일: 약 420번 호출 + sleep
- 예상 소요 시간: 2~5분

분당 호출 제한에 걸리면 `kis_api.py`의 `sleep` 값을 늘리세요.

## 다음 단계 (Phase 2)

데이터가 모이면 다음 모듈을 작성합니다:

1. **박스권/거래량 신호 감지 모듈** — 5분 박스 + 2배 거래량 급증 탐지
2. **시뮬레이터** — 진입/청산 룰 적용한 가상 매매
3. **결과 분석** — 승률, 손익비, MDD, 수익 분포

데이터 수집을 시작하시면, 1~2일치 분봉 샘플만 받아 형식 확인 후 Phase 2로 진행하시는 것을 권장합니다.

## 파일 구성

```
.
├── config.py              # 룰 v2 파라미터 + KIS 인증
├── kis_api.py             # KIS API 클라이언트
├── data_collector.py      # 데이터 수집 메인
├── requirements.txt       # 의존성
├── README.md              # (이 파일)
├── data/
│   ├── rankings/          # 일별 거래대금 순위
│   └── minute_bars/       # 종목별 분봉
└── results/               # (Phase 2 결과)
```

## 알려진 한계

1. **호가 데이터 없음** — KIS API 분봉은 OHLCV만 제공. "5틱 위 매수"는 박스폭의 5% 지점으로 근사.
2. **30일 한계** — 그 이전 데이터는 못 받음. 누적 필요.
3. **거래량 순위는 현재 시점만** — 과거 시점의 그날 09:00 거래대금 순위는 정확히 재구성 불가. 매일 장중에 수집하는 방식으로 우회.
4. **슬리피지 가정** — 보수적으로 0.05% 가정. 실전은 더 클 수 있음.
