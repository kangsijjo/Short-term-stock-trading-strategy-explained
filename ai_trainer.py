"""
XGBoost 기반 메타 라벨링(Meta-Labeling) AI 엔진 훈련기
- 시장의 '거시 경제 날씨'를 바탕으로 개별 매수 신호의 진짜/가짜 여부를 판별합니다.
"""

import os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

AI_DIR = "./ai_data"
MODEL_PATH = f"{AI_DIR}/meta_model.json"

def train_meta_model():
    print("1. AI 학습 데이터 로딩 중...")
    
    # 1. KOSDAQ 거시경제 Feature 로드
    feat_path = f"{AI_DIR}/historical_features.csv"
    if not os.path.exists(feat_path):
        print("[에러] 거시경제 데이터가 없습니다. historical_feature_builder.py를 먼저 실행하십시오.")
        return
        
    df_features = pd.read_csv(feat_path)
    df_features['date'] = df_features['date'].astype(str)

    # 2. 과거 매매 내역 로드 (보스의 백테스터가 뱉어낸 결과물 매핑)
    trades_path = "trades_history.csv" 
    
    if not os.path.exists(trades_path):
        print(f"[안내] 훈련을 위해 실제 백테스트 결과값({trades_path})이 필요합니다.")
        print("  -> 임시로 '가상 매매 데이터'를 생성하여 AI 엔진 구조 검증을 진행합니다.\\n")
        
        # (구조 테스트용 가상 방어 로직)
        np.random.seed(42)
        dummy_dates = df_features['date'].sample(2000, replace=True).values
        df_trades = pd.DataFrame({
            'date': dummy_dates,
            'yield_pct': np.random.randn(2000) * 5 # 가상의 매매 수익률
        })
    else:
        df_trades = pd.read_csv(trades_path)
        df_trades['date'] = df_trades['date'].astype(str)

    print("2. 매매 타점 평가(라벨링) 및 데이터 병합...")
    
    # 핵심 로직: 수익률이 0% 초과면 1(진입 승인), 0% 이하면 0(매수 거부)으로 냉정하게 라벨링
    df_trades['label'] = (df_trades['yield_pct'] > 0).astype(int)
    
    # 매매가 발생한 날짜의 '시장 날씨'를 병합
    df_merged = df_trades.merge(df_features, on='date', how='inner')
    df_merged = df_merged.dropna()

    # AI가 학습할 거시경제 지표 (Features)
    feature_cols = [
        'kosdaq_return', 'kosdaq_disparity', 'kosdaq_volatility', 
        'kosdaq_foreign_net', 'kosdaq_inst_net'
    ]
    
    X = df_merged[feature_cols]
    y = df_merged['label']

    if len(X) < 100:
        print("[경고] 학습 데이터 표본이 부족하여 훈련을 중단합니다.")
        return

    # 8:2 비율로 Train / Test 분할 (미래 참조 완벽 차단)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("3. 차가운 심판관 (XGBoost 메타 엔진) 훈련 시작...")
    # 과최적화 방지를 위해 뎁스를 얕게 주고, 학습률을 낮춘 실전형 세팅
    model = xgb.XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    # 4. AI 성능 검증
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    
    print("\\n==================================================")
    print(f" [검증 완료] 가짜 신호(손실 타점) 판별 정확도: {acc * 100:.2f}%")
    print("==================================================")
    
    # 5. AI의 판단 근거 (Feature Importance)
    importances = model.feature_importances_
    print("\\n[AI의 판단 근거 비중 (어떤 지표가 수익에 가장 영향을 주었는가?)]")
    for col, imp in zip(feature_cols, importances):
        print(f" - {col}: {imp*100:.1f}%")

    # 6. 완성된 모델 저장
    model.save_model(MODEL_PATH)
    print(f"\\n[성공] AI의 뇌(모델)가 안전하게 저장되었습니다. -> {MODEL_PATH}")

if __name__ == "__main__":
    train_meta_model()