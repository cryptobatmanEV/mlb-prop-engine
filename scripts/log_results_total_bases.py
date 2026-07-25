"""
Grade yesterday's Total Bases predictions against actual boxscore results.

Usage:
    python scripts/log_results_total_bases.py              # yesterday
    python scripts/log_results_total_bases.py 2026-06-07   # specific date

Line semantics: primary=1.5 (2+ TB), secondary=0.5 (1+ TB) -- the reverse of
Hits/Batter Ks (see predict/batter_props_fair_odds.py's LINE_ORDER). Graded
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
        model_key='total_bases',
        table='total_bases_predictions',
        ai_picks_table='total_bases_ai_picks_log',
        stat_field='totalBases',
        date_str=date_arg,
    )
