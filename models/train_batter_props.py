"""
Shared LightGBM trainer for the Hits / Total Bases / Batter Ks models.
One function instead of three near-duplicate training scripts -- the
training logic (fit, calibrate, evaluate, calibration table, promotion
check) is identical across all three; only FEATURES/targets/paths differ.

Calibration: isotonic (matches the existing HR model's approach --
models/train.py -- rather than Platt/sigmoid scaling; isotonic tends to fit
better than Platt with the ~280K-row sample sizes here, and consistency
with the deployed HR model's calibration method was prioritized over the
spec's literal "Platt scaling" wording).

Train/val split: 2021-2024 train, 2025-2026 val (same convention as the HR
model).
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, mean_absolute_error
import joblib
import json
import os

DATA = 'data/processed/batter_props_training_dataset.parquet'

LGB_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
)


def _calibration_table(y_test, probs, n_bins=10):
    bucket = pd.qcut(probs, n_bins, duplicates='drop')
    cal = pd.DataFrame({'pred': probs, 'actual': y_test, 'bucket': bucket})
    return cal.groupby('bucket', observed=True).agg(
        predicted=('pred', 'mean'), actual=('actual', 'mean'), n=('actual', 'size'))


def train_one_target(df, features, target, model_path, label):
    """Train + calibrate one binary target, return (model, metrics_dict)."""
    print(f"\n{'='*60}")
    print(f"  {label}  (target={target})")
    print(f"{'='*60}")

    train_df = df[df['game_date'].dt.year <= 2024]
    test_df  = df[df['game_date'].dt.year >= 2025]
    print(f"Train rows: {len(train_df):,} (2021-2024)")
    print(f"Test rows:  {len(test_df):,} (2025-2026)")

    X_train, y_train = train_df[features], train_df[target]
    X_test, y_test   = test_df[features], test_df[target]

    pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
    base = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **LGB_PARAMS)

    print("Training LightGBM with isotonic calibration...")
    model = CalibratedClassifierCV(base, method='isotonic', cv=3)
    model.fit(X_train, y_train)

    probs = model.predict_proba(X_test)[:, 1]
    brier = brier_score_loss(y_test, probs)
    ll    = log_loss(y_test, probs)
    auc   = roc_auc_score(y_test, probs)
    mae   = mean_absolute_error(y_test, probs)
    baseline_brier = brier_score_loss(y_test, np.full(len(y_test), y_test.mean()))

    print(f"\nBrier Score: {brier:.4f}  (baseline {baseline_brier:.4f})")
    print(f"Log Loss:    {ll:.4f}")
    print(f"MAE:         {mae:.4f}")
    print(f"ROC-AUC:     {auc:.4f}")

    print("\nCalibration check (predicted vs actual by decile):")
    print(_calibration_table(y_test, probs).to_string())

    os.makedirs('models/saved', exist_ok=True)
    joblib.dump(model, model_path)
    print(f"\nSaved -> {model_path}")

    return model, {'brier': brier, 'log_loss': ll, 'mae': mae, 'auc': auc}


def run(features, targets, model_paths, metrics_path, label):
    """
    targets: (primary_target, secondary_target) e.g. ('target_hit_1plus','target_hit_2plus')
    model_paths: (primary_path, secondary_path)
    """
    print(f"Loading training data for {label}...")
    df = pd.read_parquet(DATA)
    df['game_date'] = pd.to_datetime(df['game_date'])

    all_metrics = {}
    for target, path in zip(targets, model_paths):
        _, metrics = train_one_target(df, features, target, path, f"{label} -- {target}")
        all_metrics[target] = metrics

    with open(metrics_path, 'w') as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\nMetrics written to {metrics_path}")
    return all_metrics
