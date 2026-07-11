import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
import joblib
import json
import os

DATA = 'data/processed/training_dataset.parquet'
MODEL_PATH = 'models/saved/hr_model.pkl'
MODEL_PATH_V2 = 'models/saved/hr_model_v2.pkl'
METRICS_PATH = 'models/saved/retrain_metrics.json'

FEATURES = [
    'barrel_pct_15','hardhit_pct_15','flyball_pct_15','hr_per_bb_15','avg_ev_15','xwoba_15','xslg_15',
    'barrel_pct_30','hardhit_pct_30','flyball_pct_30','hr_per_bb_30','avg_ev_30','xwoba_30','xslg_30',
    # p_barrel_pct_allowed_10 and p_hardhit_pct_allowed_10 removed: r≈+0.004/+0.003, zero signal
    'p_flyball_pct_allowed_10','p_hr_per_bb_allowed_10','p_avg_ev_allowed_10','p_xslg_allowed_10',
    'p_barrel_pct_allowed_20','p_hardhit_pct_allowed_20','p_flyball_pct_allowed_20','p_hr_per_bb_allowed_20','p_avg_ev_allowed_20','p_xslg_allowed_20',
    # hr_park_factor removed: r≈+0.014, near-zero signal
    'temp_f', 'wind_speed', 'wind_favor', 'is_dome',
    'stand_R', 'p_throws_R',
    'hr_per_bb_vs_R_15', 'barrel_pct_vs_R_15', 'hardhit_pct_vs_R_15',
    'hr_per_bb_vs_R_30', 'barrel_pct_vs_R_30', 'hardhit_pct_vs_R_30',
    'hr_per_bb_vs_L_15', 'barrel_pct_vs_L_15', 'hardhit_pct_vs_L_15',
    'hr_per_bb_vs_L_30', 'barrel_pct_vs_L_30', 'hardhit_pct_vs_L_30',
    # New features v2
    'season_hr',     # batter's cumulative HRs this season before this game
    'days_since_hr', # days since batter's most recent HR (NaN if none in history)
    'p_fip',         # pitcher's FIP from prior season (NaN for rookies/short samples)
]

def evaluate_existing_model(X_test, y_test):
    """ROC-AUC of the currently-deployed model on this test set, for before/after comparison.

    Returns None if there's no existing model yet, or if it can't be scored
    (e.g. its feature set no longer matches FEATURES) — in that case the new
    model is promoted unconditionally.
    """
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        old_model = joblib.load(MODEL_PATH)
        old_probs = old_model.predict_proba(X_test)[:, 1]
        return roc_auc_score(y_test, old_probs)
    except Exception as e:
        print(f"Could not evaluate existing model ({e}); treating as no baseline.")
        return None

def train():
    print("Loading training data...")
    df = pd.read_parquet(DATA)
    df['game_date'] = pd.to_datetime(df['game_date'])
    # Don't dropna on all features — platoon columns are intentionally NaN for
    # the non-matching pitcher hand, and LightGBM handles NaN natively.
    # build_dataset.py already filters for the core rolling features being present.

    # Time-aware split: train on 2021-2024, test on 2025+
    train_df = df[df['game_date'].dt.year <= 2024]
    test_df = df[df['game_date'].dt.year >= 2025]
    print(f"Train rows: {len(train_df)} (2021-2024)")
    print(f"Test rows:  {len(test_df)} (2025-2026)")

    X_train, y_train = train_df[FEATURES], train_df['target_hr']
    X_test, y_test = test_df[FEATURES], test_df['target_hr']

    # Class imbalance handling
    pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
    print(f"Scale pos weight: {pos_weight:.2f}")

    base = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=5,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=pos_weight,
        random_state=42,
        verbose=-1,
    )

    print("\nTraining LightGBM with calibration...")
    # Calibrate so probabilities are trustworthy (critical for betting)
    model = CalibratedClassifierCV(base, method='isotonic', cv=3)
    model.fit(X_train, y_train)

    print("Evaluating on held-out 2025-2026 data...")
    probs = model.predict_proba(X_test)[:, 1]

    brier = brier_score_loss(y_test, probs)
    ll = log_loss(y_test, probs)
    auc = roc_auc_score(y_test, probs)
    baseline_brier = brier_score_loss(y_test, np.full(len(y_test), y_test.mean()))

    print(f"\n{'='*40}")
    print(f"Brier Score:      {brier:.4f}  (baseline {baseline_brier:.4f})")
    print(f"Log Loss:         {ll:.4f}")
    print(f"ROC-AUC:          {auc:.4f}")
    print(f"{'='*40}")
    print("Lower Brier/LogLoss = better. AUC > 0.5 = better than random.")

    # Calibration check: bucket predictions, compare to actual rates
    print("\nCalibration check:")
    test_df = test_df.copy()
    test_df['pred'] = probs
    test_df['bucket'] = pd.qcut(probs, 10, duplicates='drop')
    cal = test_df.groupby('bucket', observed=True).agg(
        predicted=('pred','mean'), actual=('target_hr','mean'), n=('target_hr','size'))
    print(cal.to_string())

    # Compare against the currently-deployed model on the same held-out data,
    # and only promote the new model if it's at least as good.
    prev_auc = evaluate_existing_model(X_test, y_test)
    promote = prev_auc is None or auc >= prev_auc

    print(f"\n{'='*40}")
    if prev_auc is not None:
        print(f"Previous model AUC: {prev_auc:.4f}")
        print(f"New model AUC:      {auc:.4f}")
    else:
        print(f"New model AUC: {auc:.4f}  (no existing model to compare)")
    print("PROMOTING new model to hr_model.pkl" if promote
          else "KEEPING existing hr_model.pkl (new model did not improve AUC)")
    print(f"{'='*40}")

    os.makedirs('models/saved', exist_ok=True)
    joblib.dump(model, MODEL_PATH_V2)
    if promote:
        joblib.dump(model, MODEL_PATH)

    with open(METRICS_PATH, 'w') as f:
        json.dump({
            'prev_auc': prev_auc,
            'new_auc': auc,
            'brier': brier,
            'log_loss': ll,
            'promoted': promote,
        }, f, indent=2)
    print(f"\nSaved new model to {MODEL_PATH_V2}")
    print(f"Metrics written to {METRICS_PATH}")

train()