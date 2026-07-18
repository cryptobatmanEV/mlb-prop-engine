"""
AI PICKS for the Batter Ks model.

Qualification: P(0.5+ Ks) > 0.55, bat_order <= 8 (and not null -- confirmed
starters only, matching Hits/Total Bases' lineup gate; previously this
model had no bat_order gate at all, which let non-starters -- who may get
0-1 PA -- flood the picks list since "will strike out at least once" is a
low bar for almost any batter over a real game's worth of ABs).
Composite score: adj_prob*5 + (k_rate_15-0.22)*4 + pitcher_k_bonus
  pitcher_k_bonus = (p_k_rate_10 - 0.22) * 3 -- analogous to the other two
  models' pitcher-allowed term; not otherwise specified by the spec.

Usage:
    python scripts/log_ai_picks_batter_ks.py              # today
    python scripts/log_ai_picks_batter_ks.py 2026-06-07   # specific date
"""
import os
import sys
from datetime import date as date_cls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
from scripts.shared_ai_picks import bat_order_bonus, write_picks, now_utc, _f, _i, _s

TABLE = 'batter_ks_ai_picks_log'
MIN_ADJ_PROB = 0.55
MAX_BAT_ORDER = 8


def run(date_str=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()

    path = f'data/outputs/batter_ks_fair_odds_{date_str}.csv'
    if not os.path.exists(path):
        print(f"  No {path} -- skipping AI picks.")
        return
    df = pd.read_csv(path)

    captured_at = now_utc()
    picks = []
    for _, row in df.iterrows():
        adj_prob = _f(row.get('p_k_1plus'))
        if adj_prob is None or adj_prob <= MIN_ADJ_PROB:
            continue

        bat_order = _i(row.get('bat_order'))
        if bat_order is None or bat_order > MAX_BAT_ORDER:
            continue

        k_rate = _f(row.get('k_rate_15')) or 0.0
        p_k_rate = _f(row.get('p_k_rate_10')) or 0.0
        pitcher_k_bonus = (p_k_rate - 0.22) * 3
        score = adj_prob * 5 + (k_rate - 0.22) * 4 + pitcher_k_bonus + bat_order_bonus(bat_order)

        picks.append({
            'game_date': date_str, 'captured_at': captured_at,
            'batter': int(row['batter']), 'player_name': _s(row.get('player_name')),
            'team_abbr': _s(row.get('team_abbr')), 'bat_order': bat_order,
            'best_odds': _i(row.get('primary_best_odds')), 'best_book': _s(row.get('primary_best_book')),
            'edge': _f(row.get('primary_edge')), 'adj_prob': adj_prob,
            'book_line': _f(row.get('primary_line')), 'book_side': _s(row.get('primary_side')) or 'over',
            'composite_score': float(score),
        })

    picks.sort(key=lambda p: p['composite_score'], reverse=True)
    write_picks(TABLE, picks)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
