"""
AI PICKS for the Total Bases model.

Qualification: P(2+ TB) > 0.55, best_odds <= +300, bat_order <= 6.
Composite score: p_tb_2plus*5 + (xslg_15-0.400)*4 + (barrel_pct_15-0.08)*3 + bat_order_bonus

NOTE: the qualifying/scored probability is p_tb_2plus (the secondary line),
not p_tb_1plus. Real ParlayAPI Total Bases lines are dominated by 0.5 (see
predict/shared_parlay.py notes) where P(1+ TB) is almost always well above
55% for any real player -- using it as the AI Picks threshold wouldn't be a
meaningful filter. P(2+ TB) > 55% is the selective, "genuinely a good pick"
signal the spec's "(1.5+ TB)" framing describes, so book_line/best_odds/
best_book/edge are all taken from the SECONDARY line.

Usage:
    python scripts/log_ai_picks_total_bases.py              # today
    python scripts/log_ai_picks_total_bases.py 2026-06-07   # specific date
"""
import os
import sys
from datetime import date as date_cls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
from scripts.shared_ai_picks import bat_order_bonus, write_picks, now_utc, _f, _i, _s

TABLE = 'total_bases_ai_picks_log'
MIN_ADJ_PROB = 0.55
MAX_ODDS = 300
MAX_BAT_ORDER = 6


def run(date_str=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()

    path = f'data/outputs/total_bases_fair_odds_{date_str}.csv'
    if not os.path.exists(path):
        print(f"  No {path} -- skipping AI picks.")
        return
    df = pd.read_csv(path)

    captured_at = now_utc()
    picks = []
    for _, row in df.iterrows():
        adj_prob = _f(row.get('p_tb_2plus'))
        best_odds = _i(row.get('secondary_best_odds'))
        bat_order = _i(row.get('bat_order'))

        if adj_prob is None or adj_prob <= MIN_ADJ_PROB:
            continue
        if best_odds is None or best_odds > MAX_ODDS:
            continue
        if bat_order is None or bat_order > MAX_BAT_ORDER:
            continue

        xslg = _f(row.get('xslg_15')) or 0.0
        barrel = _f(row.get('barrel_pct_15')) or 0.0
        score = (adj_prob * 5
                 + (xslg - 0.400) * 4
                 + (barrel - 0.08) * 3
                 + bat_order_bonus(bat_order))

        picks.append({
            'game_date': date_str, 'captured_at': captured_at,
            'batter': int(row['batter']), 'player_name': _s(row.get('player_name')),
            'team_abbr': _s(row.get('team_abbr')), 'bat_order': bat_order,
            'best_odds': best_odds, 'best_book': _s(row.get('secondary_best_book')),
            'edge': _f(row.get('secondary_edge')), 'adj_prob': adj_prob,
            'book_line': _f(row.get('secondary_line')), 'book_side': _s(row.get('secondary_side')) or 'over',
            'composite_score': float(score),
        })

    picks.sort(key=lambda p: p['composite_score'], reverse=True)
    write_picks(TABLE, picks)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
