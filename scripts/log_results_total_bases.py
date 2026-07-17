"""
Grade yesterday's Total Bases predictions against actual boxscore results.

Usage:
    python scripts/log_results_total_bases.py              # yesterday
    python scripts/log_results_total_bases.py 2026-06-07   # specific date

Line semantics: primary=0.5 (1+ TB), secondary=1.5 (2+ TB) -- matches the
real ParlayAPI market lines (see predict/shared_parlay.py notes).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.shared_log_results import run

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(
        model_key='total_bases',
        table='total_bases_predictions',
        ai_picks_table='total_bases_ai_picks_log',
        stat_field='totalBases',
        primary_line=0.5,
        secondary_line=1.5,
        date_str=date_arg,
    )
