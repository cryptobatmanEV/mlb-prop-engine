"""
Joins today's Hits/Total Bases/Batter Ks predictions (from
predict/batter_props_runner.py) with real ParlayAPI odds, computes edge,
and writes the final per-model CSVs + DB tables.

Usage:
    python predict/batter_props_fair_odds.py              # today
    python predict/batter_props_fair_odds.py 2026-06-07   # specific date
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from predict.shared_mlb import fetch_schedule
from predict.shared_parlay import fetch_batter_props
from predict.shared_fair_odds import match_games_to_events, join_odds
from predict.batter_props_runner import run as run_predictions, MODEL_CONFIGS
from scripts.write_new_models_to_db import write_predictions
from scripts.log_ai_picks_hits import run as log_ai_picks_hits
from scripts.log_ai_picks_total_bases import run as log_ai_picks_total_bases
from scripts.log_ai_picks_batter_ks import run as log_ai_picks_batter_ks

OUT_DIR = 'data/outputs'

AI_PICKS_RUNNERS = {
    'hits': log_ai_picks_hits,
    'total_bases': log_ai_picks_total_bases,
    'batter_ks': log_ai_picks_batter_ks,
}

MARKET_CONFIGS = {
    'hits':        dict(market_key='player_hits', table='hits_predictions', stat_prefix='hits'),
    'total_bases': dict(market_key='player_total_bases', table='total_bases_predictions', stat_prefix='total_bases'),
    'batter_ks':   dict(market_key='player_strikeouts', table='batter_ks_predictions', stat_prefix='batter_ks'),
}


def run(date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    print(f"\n{'#'*60}")
    print(f"#  Batter Props Fair Odds (Hits/TB/Ks)  --  {date_str}")
    print(f"{'#'*60}")

    preds = run_predictions(date_str)
    if not preds:
        print("No predictions produced -- nothing to price.")
        return

    games = [g for g in fetch_schedule(date_str) if g['status'] != 'Final']

    os.makedirs(OUT_DIR, exist_ok=True)
    for model_key, cfg in MODEL_CONFIGS.items():
        mcfg = MARKET_CONFIGS[model_key]
        pred_df = preds[model_key]
        c1, c2 = cfg['prob_cols']

        print(f"\n--- {cfg['label']} ---")
        events, all_df, used, failed, remaining = fetch_batter_props(
            date_str, mcfg['market_key'], {0.5, 1.5})

        priced = join_odds(pred_df, all_df, c1, c2, primary_line=0.5, secondary_line=1.5)

        out_path = os.path.join(OUT_DIR, f'{model_key}_fair_odds_{date_str}.csv')
        priced.to_csv(out_path, index=False)
        print(f"  Saved {len(priced)} rows -> {out_path}")
        n_priced = priced['primary_has_line'].sum() if 'primary_has_line' in priced.columns else 0
        print(f"  {n_priced} / {len(priced)} players have a primary-line market price")

        rows = []
        for _, r in priced.iterrows():
            rows.append({
                'game_date': date_str, 'game_pk': r.get('game_id'), 'batter': r.get('batter'),
                'player_name': r.get('player_name'), 'team_abbr': r.get('team_abbr'),
                'opp_team': r.get('opp_team'), 'bat_order': r.get('bat_order'),
                'is_home': str(r.get('is_home')), 'game_time': r.get('game_time'),
                'stadium': r.get('stadium'), 'pitcher_name': r.get('pitcher_name'),
                'p_throws': r.get('p_throws'),
                'pred_stat': r.get(cfg['pred_col']), 'p_stat_1plus': r.get(c1), 'p_stat_2plus': r.get(c2),
                'adj_prob': r.get('adj_prob'),
                'primary_line': r.get('primary_line'), 'primary_has_line': r.get('primary_has_line'),
                'primary_best_book': r.get('primary_best_book'), 'primary_best_odds': r.get('primary_best_odds'),
                'primary_book_implied': r.get('primary_book_implied'), 'primary_edge': r.get('primary_edge'),
                'secondary_line': r.get('secondary_line'), 'secondary_has_line': r.get('secondary_has_line'),
                'secondary_best_book': r.get('secondary_best_book'), 'secondary_best_odds': r.get('secondary_best_odds'),
                'secondary_book_implied': r.get('secondary_book_implied'), 'secondary_edge': r.get('secondary_edge'),
                'pp_line': None, 'pp_side': None, 'edge_pp': None,
                'ud_line': None, 'ud_side': None, 'edge_ud': None,
                'book_markets': r.get('book_markets'),
            })

        write_predictions(mcfg['table'], mcfg['stat_prefix'], rows)

        AI_PICKS_RUNNERS[model_key](date_str)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
