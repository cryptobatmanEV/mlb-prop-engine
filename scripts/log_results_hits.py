"""
Grade yesterday's Hits predictions against actual boxscore results.

Usage:
    python scripts/log_results_hits.py              # yesterday
    python scripts/log_results_hits.py 2026-06-07   # specific date

Line semantics: primary=0.5 (1+ hits), secondary=1.5 (2+ hits) -- graded
against each row's own primary_line/secondary_line columns, not hardcoded
here (see scripts/shared_log_results.py).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.shared_log_results import run

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(
        model_key='hits',
        table='hits_predictions',
        ai_picks_table='hits_ai_picks_log',
        stat_field='hits',
        date_str=date_arg,
    )
