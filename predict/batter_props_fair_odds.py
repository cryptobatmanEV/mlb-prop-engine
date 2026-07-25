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
from predict.shared_parlay import fetch_batter_props, norm_name
from predict.shared_fair_odds import match_games_to_events, join_odds, _best_side_per_player
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

# Which line is "primary" (shown first, used for AI Picks/tracking) varies
# by real market coverage, not just numeric order. Total Bases' 0.5 line is
# barely offered by any book (~35% coverage); its 1.5 line is the actual
# popular, well-covered market (~70%+ coverage) -- so 1.5 is primary here,
# unlike Hits/Batter Ks where 0.5 genuinely is the dominant line.
LINE_ORDER = {
    'hits':        dict(primary=0.5, secondary=1.5),
    'total_bases': dict(primary=1.5, secondary=0.5),
    'batter_ks':   dict(primary=0.5, secondary=1.5),
}


def _fill_total_bases_hits_fallback(priced, hits_all_df):
    """
    Total Bases' 0.5 line is its SECONDARY line (LINE_ORDER above: primary is
    1.5) and thinly covered -- most books skip pricing "1+ total base" for
    anyone who isn't a fringe hitter. TB >= 1 iff hits >= 1 exactly (any hit
    is worth at least 1 total base; walks/HBP/errors are worth zero to
    either stat), so wherever no book prices a 0.5 TB line, that player's
    0.5 Hits line describes the same underlying event and is a legitimate
    stand-in. Reuses the player_hits odds run() already fetched for the
    Hits model (no extra ParlayAPI calls).

    Writes to secondary_* fields, not primary_* -- primary_line/
    result_hit_primary drive grading, AI Picks qualification, and the
    header W-L record for this model; overwriting primary_* here would
    silently corrupt all of that for just these rows. The UI's "0.5" column
    for Total Bases already reads from secondary_* (see BatterPropsTable.tsx
    orderedLines()), so that's the field this fallback needs to fill.
    """
    priced = priced.copy()
    priced['secondary_is_hits_fallback'] = False
    if hits_all_df is None or hits_all_df.empty:
        return priced

    missing_idx = priced.index[priced['secondary_has_line'] != True]
    if len(missing_idx) == 0:
        return priced

    name_norm = priced['player_name'].apply(norm_name)
    over_best  = {r['name_norm']: r for _, r in _best_side_per_player(hits_all_df, 0.5, 'over').iterrows()}
    under_best = {r['name_norm']: r for _, r in _best_side_per_player(hits_all_df, 0.5, 'under').iterrows()}

    filled = 0
    for idx in missing_idx:
        nn = name_norm.loc[idx]
        if nn in over_best:
            side, r = 'over', over_best[nn]
            odds, implied = r['over_odds'], r['over_implied']
        elif nn in under_best:
            side, r = 'under', under_best[nn]
            odds, implied = r['under_odds'], r['under_implied']
        else:
            continue

        # p_tb_1plus IS the "0.5 total bases" probability -- and since TB>=1
        # iff hits>=1, it's equally valid as the model probability for this
        # borrowed hits line (same event, not an approximation).
        prob = priced.at[idx, 'p_tb_1plus']
        model_prob_for_side = (1 - prob) if side == 'under' else prob
        edge = (round(model_prob_for_side - implied, 4)
                if model_prob_for_side is not None and implied is not None else None)

        priced.at[idx, 'secondary_line']             = 0.5
        priced.at[idx, 'secondary_side']              = side
        priced.at[idx, 'secondary_best_book']          = r['bookmaker']
        priced.at[idx, 'secondary_best_odds']          = odds
        priced.at[idx, 'secondary_book_implied']       = implied
        priced.at[idx, 'secondary_has_line']           = True
        priced.at[idx, 'secondary_edge']               = edge
        priced.at[idx, 'secondary_is_hits_fallback']   = True
        filled += 1

    if filled:
        print(f"  Total Bases: filled {filled} missing 0.5-line player(s) with their 0.5 Hits odds as fallback")
    return priced


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
    hits_all_df = None  # cached from the 'hits' iteration below, reused by Total Bases' 0.5-line fallback
    for model_key, cfg in MODEL_CONFIGS.items():
        mcfg = MARKET_CONFIGS[model_key]
        pred_df = preds[model_key]
        c1, c2 = cfg['prob_cols']

        print(f"\n--- {cfg['label']} ---")
        events, all_df, used, failed, remaining = fetch_batter_props(
            date_str, mcfg['market_key'], {0.5, 1.5})

        if model_key == 'hits':
            hits_all_df = all_df

        order = LINE_ORDER[model_key]
        # prob_col_primary/secondary must match whichever line (0.5 -> c1,
        # 1.5 -> c2) is designated primary/secondary for this model.
        prob_for_line = {0.5: c1, 1.5: c2}
        priced = join_odds(
            pred_df, all_df,
            prob_col_primary=prob_for_line[order['primary']],
            prob_col_secondary=prob_for_line[order['secondary']],
            primary_line=order['primary'], secondary_line=order['secondary'],
        )

        if model_key == 'total_bases':
            priced = _fill_total_bases_hits_fallback(priced, hits_all_df)

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
                'primary_side': r.get('primary_side'),
                'primary_best_book': r.get('primary_best_book'), 'primary_best_odds': r.get('primary_best_odds'),
                'primary_book_implied': r.get('primary_book_implied'), 'primary_edge': r.get('primary_edge'),
                'secondary_line': r.get('secondary_line'), 'secondary_has_line': r.get('secondary_has_line'),
                'secondary_side': r.get('secondary_side'),
                'secondary_best_book': r.get('secondary_best_book'), 'secondary_best_odds': r.get('secondary_best_odds'),
                'secondary_book_implied': r.get('secondary_book_implied'), 'secondary_edge': r.get('secondary_edge'),
                'secondary_is_hits_fallback': bool(r.get('secondary_is_hits_fallback', False)),
                'pp_line': None, 'pp_side': None, 'edge_pp': None,
                'ud_line': None, 'ud_side': None, 'edge_ud': None,
                'book_markets': r.get('book_markets'),
            })

        write_predictions(mcfg['table'], mcfg['stat_prefix'], rows)

        AI_PICKS_RUNNERS[model_key](date_str)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
