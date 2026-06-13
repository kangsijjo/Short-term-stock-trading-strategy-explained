"""
AI 학습 v2 — 시계열 누수 차단 + 실제 백테스트 데이터로 학습.

기존 ai_trainer.py 의 문제점 수정:
  - train_test_split(random_state=42) 무작위 셔플 → 시계열 누수 위험
    → 날짜 cutoff 분리 (앞 80% train, 뒤 20% test)
  - 랜덤 fallback (trades_history.csv 없으면 np.random) → 차단
    → 없으면 에러 (실제 데이터만 사용)
  - 60% 컷오프 임의
    → ROC 분석 + 여러 threshold 시뮬

추가:
  - XGBoost 없으면 sklearn GradientBoostingClassifier 사용 (샌드박스 호환)
  - Feature importance 출력
  - 컷오프 시뮬레이션 (50/55/60/65/70%) → 매매 수 vs 평균 수익
"""

import os
import sys
import numpy as np
import pandas as pd

# XGBoost or sklearn fallback
try:
    import xgboost as xgb
    _has_xgb = True
    print("[engine] XGBoost")
except (ImportError, Exception):
    from sklearn.ensemble import GradientBoostingClassifier
    _has_xgb = False
    print("[engine] sklearn GradientBoosting (XGBoost 미사용)")

from sklearn.metrics import accuracy_score, roc_auc_score


AI_DIR = "./ai_data"
MODEL_PATH = f"{AI_DIR}/meta_model_v2.json"
FEAT_PATH = f"{AI_DIR}/historical_features.csv"
TRADES_PATH = "./trades_history.csv"

FEATURE_COLS = [
    "kosdaq_return", "kosdaq_disparity", "kosdaq_volatility",
    "kosdaq_foreign_net", "kosdaq_inst_net",
]


def main():
    print("=== AI 학습 v2 ===\n")

    if not os.path.exists(FEAT_PATH):
        print(f"[error] {FEAT_PATH} 없음. historical_feature_builder.py 먼저 실행.")
        return
    if not os.path.exists(TRADES_PATH):
        print(f"[error] {TRADES_PATH} 없음. make_trades_history.py 먼저 실행.")
        return

    df_feat = pd.read_csv(FEAT_PATH)
    df_feat["date"] = df_feat["date"].astype(str)
    df_trades = pd.read_csv(TRADES_PATH)
    df_trades["date"] = df_trades["date"].astype(str)
    print(f"[data] feat={len(df_feat)} 영업일, trades={len(df_trades)} 매매")

    # 라벨링: yield > 0 → 1 (성공), else 0 (실패)
    df_trades["label"] = (df_trades["yield_pct"] > 0).astype(int)

    df = df_trades.merge(df_feat, on="date", how="inner")
    df = df.dropna(subset=FEATURE_COLS + ["label"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"[merged] {len(df)} 표본 ({df['label'].sum()} 승 / {(1-df['label']).sum()} 패)")

    if len(df) < 100:
        print("[error] 표본 부족")
        return

    # 시간순 분리 (앞 80% train, 뒤 20% test)
    cutoff = int(len(df) * 0.8)
    df_train = df.iloc[:cutoff]
    df_test = df.iloc[cutoff:]
    print(f"\n[split] train={len(df_train)} ({df_train['date'].min()}~{df_train['date'].max()})")
    print(f"        test ={len(df_test)} ({df_test['date'].min()}~{df_test['date'].max()})")

    X_train, y_train = df_train[FEATURE_COLS], df_train["label"]
    X_test, y_test = df_test[FEATURE_COLS], df_test["label"]

    # 학습
    print("\n[training] ...")
    if _has_xgb:
        model = xgb.XGBClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=4,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, eval_metric="logloss",
        )
    else:
        model = GradientBoostingClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=4,
            subsample=0.8, random_state=42,
        )
    model.fit(X_train, y_train)

    # 정확도
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    try:
        auc = roc_auc_score(y_test, y_prob)
    except Exception:
        auc = float("nan")

    print(f"\n[검증]")
    print(f"  test 정확도: {acc*100:.2f}%")
    print(f"  test AUC:    {auc:.3f}  (0.5=동전, 0.7+ 의미있음)")
    print(f"  test 기본 승률 (random 비교): {y_test.mean()*100:.2f}%")

    # Feature importance
    if hasattr(model, "feature_importances_"):
        print(f"\n[Feature Importance]")
        for c, imp in zip(FEATURE_COLS, model.feature_importances_):
            print(f"  {c}: {imp*100:.1f}%")

    # 컷오프 시뮬레이션
    df_test = df_test.copy()
    df_test["ai_prob"] = y_prob
    df_test["yield_pct"] = df_trades.iloc[cutoff:]["yield_pct"].values

    print(f"\n[컷오프 시뮬] AI 확률 ≥ N% 매매만 시뮬 → 평균 수익 vs 매매 수")
    print(f"  전체 (필터 없음): n={len(df_test):>4}, 평균 yield={df_test['yield_pct'].mean():+.2f}%")
    for cutoff_pct in [50, 55, 60, 65, 70, 75]:
        sub = df_test[df_test["ai_prob"] >= cutoff_pct / 100]
        if len(sub) > 0:
            print(f"  ≥{cutoff_pct}%:           n={len(sub):>4}, 평균 yield={sub['yield_pct'].mean():+.2f}%")
        else:
            print(f"  ≥{cutoff_pct}%:           n=   0")

    # 모델 저장
    os.makedirs(AI_DIR, exist_ok=True)
    if _has_xgb:
        model.save_model(MODEL_PATH)
    else:
        import joblib
        joblib.dump(model, MODEL_PATH.replace(".json", ".pkl"))
    print(f"\n[saved] 모델 → {MODEL_PATH}")
    print(f"\n주의: 이 모델은 paper_tracker.py 에 통합 안 됨. 학습 결과 분석만 함.")


if __name__ == "__main__":
    main()
