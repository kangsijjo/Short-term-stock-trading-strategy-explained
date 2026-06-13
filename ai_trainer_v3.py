"""
AI 학습 v3 — 매크로 5개 + 종목별 7개 = 12 feature.

trades_history_v2.csv 사용. 시계열 분리 (앞 80% train, 뒤 20% test).
"""

import os
import sys
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    _has_xgb = True
    print("[engine] XGBoost")
except (ImportError, Exception):
    from sklearn.ensemble import GradientBoostingClassifier
    _has_xgb = False
    print("[engine] sklearn GradientBoosting")

from sklearn.metrics import accuracy_score, roc_auc_score


AI_DIR = "./ai_data"
MODEL_PATH = f"{AI_DIR}/meta_model_v3"
FEAT_PATH = f"{AI_DIR}/historical_features.csv"
TRADES_PATH = "./trades_history_v2.csv"

MACRO_COLS = ["kosdaq_return", "kosdaq_disparity", "kosdaq_volatility",
              "kosdaq_foreign_net", "kosdaq_inst_net"]
STOCK_COLS = ["rsi14", "atr_pct", "vol_ratio", "tv_ratio",
              "for_5d", "ins_5d", "mcap_class"]
ALL_COLS = MACRO_COLS + STOCK_COLS


def main():
    print("=== AI 학습 v3 (매크로 + 종목별) ===\n")

    if not os.path.exists(FEAT_PATH):
        print(f"[error] {FEAT_PATH} 없음.")
        return
    if not os.path.exists(TRADES_PATH):
        print(f"[error] {TRADES_PATH} 없음. make_trades_history_v2.py 먼저.")
        return

    df_feat = pd.read_csv(FEAT_PATH)
    df_feat["date"] = df_feat["date"].astype(str)
    df_trades = pd.read_csv(TRADES_PATH)
    df_trades["date"] = df_trades["date"].astype(str)

    df_trades["label"] = (df_trades["yield_pct"] > 0).astype(int)
    df = df_trades.merge(df_feat[["date"] + MACRO_COLS], on="date", how="inner")
    df = df.dropna(subset=ALL_COLS + ["label"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"[merged] {len(df)} 표본 ({df['label'].sum()} 승 / {(1-df['label']).sum()} 패)")

    cutoff = int(len(df) * 0.8)
    df_train = df.iloc[:cutoff]
    df_test = df.iloc[cutoff:]
    print(f"\n[split] train={len(df_train)} ({df_train['date'].min()}~{df_train['date'].max()})")
    print(f"        test ={len(df_test)} ({df_test['date'].min()}~{df_test['date'].max()})")

    X_train, y_train = df_train[ALL_COLS], df_train["label"]
    X_test, y_test = df_test[ALL_COLS], df_test["label"]

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

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    try:
        auc = roc_auc_score(y_test, y_prob)
    except Exception:
        auc = float("nan")

    print(f"\n[검증]")
    print(f"  test 정확도: {acc*100:.2f}%")
    print(f"  test AUC:    {auc:.3f}  (v2 baseline: 0.563)")
    print(f"  test 승률:   {y_test.mean()*100:.2f}%")

    if hasattr(model, "feature_importances_"):
        print(f"\n[Feature Importance]")
        sorted_feats = sorted(zip(ALL_COLS, model.feature_importances_), key=lambda x: -x[1])
        for c, imp in sorted_feats:
            kind = "매크로" if c in MACRO_COLS else "종목"
            print(f"  [{kind}] {c}: {imp*100:.1f}%")

    df_test = df_test.copy()
    df_test["ai_prob"] = y_prob

    print(f"\n[컷오프 시뮬]")
    print(f"  전체 (필터 없음): n={len(df_test):>4}, 평균 yield={df_test['yield_pct'].mean():+.2f}%")
    for cutoff_pct in [50, 55, 60, 65, 70]:
        sub = df_test[df_test["ai_prob"] >= cutoff_pct / 100]
        if len(sub) > 0:
            print(f"  ≥{cutoff_pct}%:           n={len(sub):>4}, 평균 yield={sub['yield_pct'].mean():+.2f}%")
        else:
            print(f"  ≥{cutoff_pct}%:           n=   0")

    os.makedirs(AI_DIR, exist_ok=True)
    if _has_xgb:
        model.save_model(MODEL_PATH + ".json")
    else:
        import joblib
        joblib.dump(model, MODEL_PATH + ".pkl")
    print(f"\n[saved] 모델 → {MODEL_PATH}")
    print(f"주의: paper_tracker.py 에 통합 안 됨 — 학습 결과 분석만.")


if __name__ == "__main__":
    main()
