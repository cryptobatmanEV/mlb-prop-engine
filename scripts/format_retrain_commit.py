"""
Build the weekly retrain commit message from models/saved/retrain_metrics.json.

Usage (from repo root):
    python scripts/format_retrain_commit.py
"""
import json

with open('models/saved/retrain_metrics.json') as f:
    m = json.load(f)

prev = m['prev_auc']
new = m['new_auc']

if prev is not None:
    header = f"Auto: weekly retrain - AUC {prev:.4f} -> {new:.4f}"
else:
    header = f"Auto: weekly retrain - AUC {new:.4f} (no previous model)"

status = ("Promoted new model to hr_model.pkl" if m['promoted']
          else "Kept existing hr_model.pkl (new model did not improve AUC)")

print(header)
print()
print(status)
print(f"Brier: {m['brier']:.4f}  LogLoss: {m['log_loss']:.4f}")
