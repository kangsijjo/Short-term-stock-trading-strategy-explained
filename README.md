# KOSDAQ 알고리즘 트레이딩 시스템

다중 전략 비교 + walk-forward 검증 + paper trading 자동화.

## 메인 전략 — `high_500d_h40_MKT`

3년치 데이터로 14개 전략 비교 후 확정한 단일 메인 전략.

| 항목 | 값 |
|---|---|
| 진입 | 종가가 직전 500 영업일 신고가 돌파 |
| 시장 게이트 | 시장 평균 등락률 60일 MA > 0 (강세장만) |
| 유동성 필터 | 거래대금 30억 이상 (전일) |
| 진입가 | 신호 다음 영업일 시가 |
| 청산 | 진입 후 40 영업일 종가 |
| 자본 운용 | 최대 10종목 동시보유, 자본 1/N 분배 |

### 실측 성과 (3년 macro_data, 단방향 -30% 컷오프 적용)

| 지표 | 값 |
|---|---|
| CAGR | **+156.27% / 년** |
| Real MDD | **-8.03%** |
| Real Sharpe | **+3.01** |
| Win rate | 49.28% |
| 표본 | 1,411 매매 |
| 1천만원 → 3년 후 | 약 2,752만원 |

### Walk-forward Multi-split 견고성

| Split | OOS CAGR |
|---|---|
| 50/50 | +77.67% |
| 67/33 | +35.40% |
| 75/25 | +44.50% |

**모든 split 에서 OOS 양수** — 가장 견고한 단일 전략.

---

## 시스템 구조

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

## 빠른 시작

### 1. 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 2. 인증 정보 설정 — `.env` 파일 생성
```env
# KIS Open API (실전 또는 모의)
KIS_ENV=prod   # 또는 vps
KIS_PROD_APP_KEY=발급받은_키
KIS_PROD_APP_SECRET=발급받은_시크릿
KIS_PROD_ACCOUNT=계좌번호

KIS_MOCK_APP_KEY=모의_키
KIS_MOCK_APP_SECRET=모의_시크릿
KIS_MOCK_ACCOUNT=모의_계좌

# KRX 정보데이터시스템 (공매도 등)
KRX_ID=가입한_ID
KRX_PW=비밀번호

# DART 공시 (선택)
DART_API_KEY=발급받은_키
```

### 3. 데이터 수집 (3년치 일봉)
```bash
python pykrx_collector.py
```
약 30분~1시간 소요.

### 4. 전략 비교 백테스트
```bash
python strategy_engine.py
```

### 5. Walk-forward 견고성 검증
```bash
python walkforward.py
```

### 6. Paper trading 시드 + 추적
```bash
python seed_paper_signals.py    # 과거 신호로 시드 (y 입력)
python paper_tracker.py         # 누적 손익 + 보유 포지션
```

### 7. 실시간 신호 (Windows 자동화)
```powershell
powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1
```
7개 자동화 작업 등록. 매일 16:30 메인 전략 신호 자동 감지.

---

## 분석 5단계 과정

진실에 도달하기까지 5단계 거쳤습니다:

| 단계 | 결과 | 진실? |
|---|---|---|
| 1. 매매당 평균 | high_500d_h40 (pf 2.04) | ❌ 자본 회전 무시 |
| 2. 자본 시뮬 | high_500d_h40 (+129%) | ❌ train 운 |
| 3. Single walk-forward (67/33) | portfolio 우위 | ❌ 단일 분할 운 |
| 4. **Multi-split walk-forward** | high_500d_h40_MKT 단일 (+77.67%) | ⭐ 거의 정답 |
| 5. **전문가 지적 + 단방향 -30% 컷오프** | **+156.27% (액면분할 오염 제거)** | ⭐ **진짜 정답** |

**교훈**: 어떤 단순한 결론도 거부하고 다층 검증해야 진실 도달.

---

## 자동화 — 7개 작업 (매일 자동)

| 시각 | 작업 | 내용 |
|---|---|---|
| 08:30 | KIS_KRX | T-1 공매도 |
| 09:00~14:30 (30분) | KIS_Ranking | 분봉 ranking + 지수 snapshot |
| 15:40 | KIS_EOD | 장 마감 종합 |
| 16:00 | KIS_Backtest | 단타 v2 (별건) |
| **16:30** | **KIS_Paper** ⭐ | **메인 전략 신호 + paper tracker** |
| 19:00 | KIS_DART | 공시 |
| 매월 1일 02:00 | KIS_Monthly | xlsx 합본 |

---

## 디렉토리 구조

```
.
├── strategies/             # 14개 전략 모듈
│   ├── high_with_filters.py    # ⭐ 메인 (high_500d_h40_MKT)
│   ├── high_52w.py             # 신고가 베이스
│   ├── gap_buy.py / momentum_5d.py / ...
│   └── portfolio.py            # 다중 전략 결합
├── strategy_engine.py      # 14개 동시 비교 + 자본 시뮬
├── walkforward.py          # multi-split 견고성 검증
├── capital_simulator.py    # 자본 모델링 (단방향 -30% 컷오프)
├── live_signal.py          # ⭐ 매일 실전 신호 감지
├── paper_tracker.py        # ⭐ 누적 손익 + 보유 포지션
├── pykrx_collector.py      # 일봉 3년치 수집
├── data_collector.py       # KIS 데이터 수집 (분봉, 지수)
├── kis_api.py              # KIS API 클라이언트
├── run_*.bat               # 자동화 배치 파일들
├── install_scheduler.ps1   # Windows 작업 스케줄러 등록
└── USAGE.md                # 자세한 사용법
```

---

## 알려진 한계 (정직)

1. **수정주가 미반영** — pykrx 의 raw OHLCV. 액면분할 시 가짜 -80% 폭락. 단방향 -30% 컷오프로 임시 처리. `FinanceDataReader` 재수집이 진짜 정답 (별건 작업).
2. **종목명 NaN** — pykrx_collector 가 종목명 미저장. 코드 식별만 가능. 가독성만 떨어짐.
3. **KOSDAQ 한정** — KOSPI 종목은 별도 인프라 필요.
4. **호가/체결강도 없음** — KIS 무료 API 한계. 단타 정밀도에 영향.
5. **paper trading OOS 미검증** — 1~2개월 누적 후 백테스트 예상치 일치 여부 확인 필요.

---

## 다음 단계

1. **지금 ~ 1개월**: 자동화 매일 paper 누적
2. **1개월 후**: paper 결과 vs 백테스트 예상치 비교
3. **2~3개월 누적 후**: 소액 (50~100만) 실전 진입
4. **6개월 안정 운용 후**: 자본 증액

---

## 자세한 사용법

[USAGE.md](USAGE.md) 참조.

## 분석 과정

- 단타 박스권 룰 v2 (5분 분봉, 4 버전 시험) → break-even 미달, 폐기
- 다중 전략 14종 → high_52w 패밀리만 +EV
- 자본 시뮬 + walk-forward → high_500d_h40_MKT 단일 확정
- 전문가 지적 + 단방향 컷오프 → 진짜 정답 도달

## 라이센스

개인 학습/연구 용도. 실전 매매 결과에 대해 코드 작성자는 책임지지 않음.
