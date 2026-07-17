"""
AI PICKS for the Hits model.

Qualification: adj_prob (P(1+ hits)) > 0.65, best_odds <= +200, bat_order <= 6.
Composite score: adj_prob*5 + (batting_avg_15-0.250)*8 + (contact_rate_15-0.75)*3 + bat_order_bonus

Usage:
    python scripts/log_ai_picks_hits.py              # today
    python scripts/log_ai_picks_hits.py 2026-06-07   # specific date
"""
import os
import sys
from datetime import date as date_cls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
from scripts.shared_ai_picks import bat_order_bonus, write_picks, now_utc, _f, _i, _s

TABLE = 'hits_ai_picks_log'
MIN_ADJ_PROB = 0.65
MAX_ODDS = 200
MAX_BAT_ORDER = 6


def run(date_str=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()

    path = f'data/outputs/hits_fair_odds_{date_str}.csv'
    if not os.path.exists(path):
        print(f"  No {path} -- skipping AI picks.")
        return
    df = pd.read_csv(path)

    captured_at = now_utc()
    picks = []
    for _, row in df.iterrows():
        adj_prob = _f(row.get('p_hit_1plus'))
        best_odds = _i(row.get('primary_best_odds'))
        bat_order = _i(row.get('bat_order'))

        if adj_prob is None or adj_prob <= MIN_ADJ_PROB:
            continue
        if best_odds is None or best_odds > MAX_ODDS:
            continue
        if bat_order is None or bat_order > MAX_BAT_ORDER:
            continue

        batting_avg = _f(row.get('batting_avg_15')) or 0.0
        contact_rate = _f(row.get('contact_rate_15')) or 0.0
        score = (adj_prob * 5
                 + (batting_avg - 0.250) * 8
                 + (contact_rate - 0.75) * 3
                 + bat_order_bonus(bat_order))

        picks.append({
            'game_date': date_str, 'captured_at': captured_at,
            'batter': int(row['batter']), 'player_name': _s(row.get('player_name')),
            'team_abbr': _s(row.get('team_abbr')), 'bat_order': bat_order,
            'best_odds': best_odds, 'best_book': _s(row.get('primary_best_book')),
            'edge': _f(row.get('primary_edge')), 'adj_prob': adj_prob,
            'book_line': _f(row.get('primary_line')), 'book_side': 'over',
            'composite_score': float(score),
        })

    picks.sort(key=lambda p: p['composite_score'], reverse=True)
    write_picks(TABLE, picks)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
