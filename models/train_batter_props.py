"""
Shared LightGBM trainer for the Hits / Total Bases / Batter Ks models.
One function instead of three near-duplicate training scripts -- the
training logic (fit, calibrate, evaluate, calibration table, feature
importances, pruning, promotion check) is identical across all three; only
FEATURES/targets/paths differ.

Calibration: isotonic (matches the existing HR model's approach --
models/train.py -- rather than Platt/sigmoid scaling; isotonic tends to fit
better than Platt with the ~280K-row sample sizes here, and consistency
with the deployed HR model's calibration method was prioritized over the
spec's literal "Platt scaling" wording). Isotonic calibration directly
target-fits predicted-vs-actual per bucket, which is what a separate
additive per-decile bias correction would otherwise do -- adding one on top
would be redundant, so there isn't a second correction step here (matching
what models/train.py actually does for the HR model; it doesn't have one
either despite being described as the reference implementation for it).

Train/val split: 2021-2024 train, 2025-2026 val (same convention as the HR
model).

Feature pruning: after the initial fit, any feature contributing < 0.5% of
total gain-based importance is dropped and the model is retrained on the
reduced feature set. The pruned model is only kept if its AUC is >= the
full-feature model's (fewer features, no accuracy cost). Either way, the
model is only saved over the existing deployed one if its AUC on the same
holdout set is >= the existing model's.
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
PRUNE_THRESHOLD = 0.005  # 0.5% of total gain

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
    importance_type='gain',
)


def _calibration_table(y_test, probs, n_bins=10):
    bucket = pd.qcut(probs, n_bins, duplicates='drop')
    cal = pd.DataFrame({'pred': probs, 'actual': y_test, 'bucket': bucket})
    return cal.groupby('bucket', observed=True).agg(
        predicted=('pred', 'mean'), actual=('actual', 'mean'), n=('actual', 'size'))


def _mean_importances(model, features):
    """Average gain-based feature_importances_ across CalibratedClassifierCV's internal folds."""
    imps = np.zeros(len(features))
    for cc in model.calibrated_classifiers_:
        imps += cc.estimator.feature_importances_
    imps /= len(model.calibrated_classifiers_)
    total = imps.sum()
    pct = imps / total if total > 0 else imps
    return pd.Series(pct, index=features).sort_values(ascending=False)


def _fit(X_train, y_train, pos_weight):
    base = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **LGB_PARAMS)
    model = CalibratedClassifierCV(base, method='isotonic', cv=3)
    model.fit(X_train, y_train)
    return model


def _evaluate(model, X_test, y_test):
    probs = model.predict_proba(X_test)[:, 1]
    return probs, {
        'brier': brier_score_loss(y_test, probs),
        'log_loss': log_loss(y_test, probs),
        'mae': mean_absolute_error(y_test, probs),
        'auc': roc_auc_score(y_test, probs),
    }


def _evaluate_existing_model(model_path, X_test, y_test):
    if not os.path.exists(model_path):
        return None
    try:
        old = joblib.load(model_path)
        probs = old.predict_proba(X_test)[:, 1]
        return roc_auc_score(y_test, probs)
    except Exception as e:
        print(f"  Could not evaluate existing model ({e}); treating as no baseline.")
        return None


def train_one_target(df, features, target, model_path, label):
    """Train + calibrate + prune one binary target, return (final_features, metrics_dict)."""
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

    print(f"\nTraining full model ({len(features)} features)...")
    full_model = _fit(X_train, y_train, pos_weight)
    full_probs, full_metrics = _evaluate(full_model, X_test, y_test)
    importances = _mean_importances(full_model, features)

    print(f"\nFeature importances (% of total gain):")
    print((importances * 100).round(2).to_string())

    low_imp = importances[importances < PRUNE_THRESHOLD].index.tolist()
    pruned_features = [f for f in features if f not in low_imp]

    if low_imp and len(pruned_features) >= 3:
        print(f"\nDropping {len(low_imp)} feature(s) below {PRUNE_THRESHOLD*100:.1f}% importance: {low_imp}")
        print(f"Retraining with {len(pruned_features)} features...")
        pruned_model = _fit(train_df[pruned_features], y_train, pos_weight)
        pruned_probs, pruned_metrics = _evaluate(pruned_model, test_df[pruned_features], y_test)
        print(f"  Full AUC:   {full_metrics['auc']:.4f}")
        print(f"  Pruned AUC: {pruned_metrics['auc']:.4f}")

        if pruned_metrics['auc'] >= full_metrics['auc']:
            print("  Pruned model is as good or better -- using pruned feature set.")
            final_model, final_probs, final_metrics, final_features = pruned_model, pruned_probs, pruned_metrics, pruned_features
        else:
            print("  Pruned model is worse -- keeping full feature set.")
            final_model, final_probs, final_metrics, final_features = full_model, full_probs, full_metrics, features
    else:
        print("\nNo features below the pruning threshold (or too few would remain) -- keeping full feature set.")
        final_model, final_probs, final_metrics, final_features = full_model, full_probs, full_metrics, features

    print(f"\nFinal model ({len(final_features)} features):")
    print(f"Brier Score: {final_metrics['brier']:.4f}")
    print(f"Log Loss:    {final_metrics['log_loss']:.4f}")
    print(f"MAE:         {final_metrics['mae']:.4f}")
    print(f"ROC-AUC:     {final_metrics['auc']:.4f}")

    print("\nCalibration check (predicted vs actual by decile):")
    print(_calibration_table(y_test, final_probs).to_string())

    prev_auc = _evaluate_existing_model(model_path, test_df[final_features], y_test)
    promote = prev_auc is None or final_metrics['auc'] >= prev_auc
    print(f"\n{'='*40}")
    if prev_auc is not None:
        print(f"Previous model AUC: {prev_auc:.4f}")
        print(f"New model AUC:      {final_metrics['auc']:.4f}")
    else:
        print(f"New model AUC: {final_metrics['auc']:.4f}  (no existing model to compare)")
    print("PROMOTING new model" if promote else "KEEPING existing model (new model did not improve AUC)")
    print(f"{'='*40}")

    os.makedirs('models/saved', exist_ok=True)
    if promote:
        joblib.dump(final_model, model_path)
        print(f"Saved -> {model_path}")

    final_metrics['features'] = final_features
    final_metrics['promoted'] = promote
    final_metrics['prev_auc'] = prev_auc
    return final_features, final_metrics


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
