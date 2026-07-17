"""
Daily prediction runner for the Hits / Total Bases / Batter Ks models.

Mirrors predict/daily_runner.py's structure (HR model) but generalized to
score all three new models in one pass, since they share the same batter-
game matchup assembly. The HR pipeline is untouched.

Usage:
    python predict/batter_props_runner.py              # today
    python predict/batter_props_runner.py 2026-06-07   # specific date

Output: data/predictions/{hits,total_bases,batter_ks}_predictions_{date}.csv
"""
import os
import sys
import time
import joblib
import numpy as np
import pandas as pd
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from predict.shared_mlb import (
    fetch_schedule, fetch_roster, fetch_lineups_by_game, TEAM_ID,
)
from predict.daily_runner import get_todays_weather
from features.build_batter_props_dataset import compute_team_k_rate, derive_team_and_bat_order

BATTER_PATH      = 'data/processed/batter_pa_features.parquet'
PITCHER_PATH     = 'data/processed/pitcher_pa_features.parquet'
PITCHER_LOG_PATH = 'data/processed/pitcher_game_log_features.parquet'
PLATOON_PATH     = 'data/processed/batter_platoon_pa_features.parquet'
PARK_TB_PATH     = 'data/processed/park_tb_factor.csv'
STATCAST_PATH    = 'data/raw/statcast_batted_balls.parquet'
OUT_DIR          = 'data/predictions'

# Feature lists mirror exactly what each saved model was trained on (see
# models/saved/{model}_metrics.json 'features' -- feature-pruning during
# training can leave the 1+/2+ sub-models with different feature counts,
# so predict_proba must be called with each model's own exact list, not one
# shared list, or LightGBM raises a shape-mismatch error.
MODEL_CONFIGS = {
    'hits': dict(
        label='Hits',
        primary_features=[
            'batting_avg_15', 'obp_15', 'contact_rate_15', 'hard_hit_pct_15',
            'line_drive_pct_15', 'xba_15', 'babip_15', 'k_rate_15', 'gb_pct_15',
            'batting_avg_vs_R_15', 'batting_avg_vs_L_15', 'batting_avg_last_5',
            'p_hits_per9_10', 'p_babip_allowed_10', 'p_contact_rate_allowed_10',
            'p_k_rate_10', 'p_gb_pct_10',
            'bat_order', 'is_home', 'opp_k_pct_15', 'stand_R', 'p_throws_R', 'is_dome',
        ],
        secondary_features=[
            'batting_avg_15', 'obp_15', 'contact_rate_15', 'hard_hit_pct_15',
            'line_drive_pct_15', 'xba_15', 'babip_15', 'k_rate_15', 'gb_pct_15',
            'batting_avg_vs_R_15', 'batting_avg_vs_L_15', 'batting_avg_last_5',
            'p_hits_per9_10', 'p_babip_allowed_10', 'p_contact_rate_allowed_10',
            'p_k_rate_10', 'p_gb_pct_10',
            'bat_order', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
        ],
        model_paths=('models/saved/hits_1plus_model.pkl', 'models/saved/hits_2plus_model.pkl'),
        prob_cols=('p_hit_1plus', 'p_hit_2plus'),
        pred_col='pred_hits',
        pred_from='batting_avg_15',  # proxy for expected count: avg * expected AB (~4)
    ),
    'total_bases': dict(
        label='Total Bases',
        primary_features=[
            'avg_total_bases_15', 'xslg_15', 'barrel_pct_15', 'hard_hit_pct_15',
            'fly_ball_pct_15', 'iso_15', 'xba_15', 'hr_rate_15', 'doubles_rate_15',
            'slg_vs_R_15', 'slg_vs_L_15', 'xslg_last_5',
            'p_slg_allowed_10', 'p_iso_allowed_10', 'p_barrel_pct_allowed_10',
            'p_fb_pct_10', 'p_hr_per9_10',
            'bat_order', 'stand_R', 'p_throws_R', 'tb_park_factor',
        ],
        secondary_features=[
            'avg_total_bases_15', 'xslg_15', 'barrel_pct_15', 'hard_hit_pct_15',
            'fly_ball_pct_15', 'iso_15', 'xba_15', 'hr_rate_15', 'doubles_rate_15',
            'slg_vs_R_15', 'slg_vs_L_15', 'xslg_last_5',
            'p_slg_allowed_10', 'p_iso_allowed_10', 'p_barrel_pct_allowed_10',
            'p_fb_pct_10', 'p_hr_per9_10',
            'bat_order', 'is_home', 'stand_R', 'p_throws_R', 'tb_park_factor', 'wind_out',
        ],
        model_paths=('models/saved/total_bases_1plus_model.pkl', 'models/saved/total_bases_2plus_model.pkl'),
        prob_cols=('p_tb_1plus', 'p_tb_2plus'),
        pred_col='pred_total_bases',
        pred_from='avg_total_bases_15',
    ),
    'batter_ks': dict(
        label='Batter Ks',
        primary_features=[
            'k_rate_15', 'avg_k_per_game_15', 'k_rate_vs_R_15', 'k_rate_vs_L_15',
            'p_k_per9_10', 'p_k_rate_10',
            'bat_order', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
        ],
        secondary_features=[
            'k_rate_15', 'avg_k_per_game_15', 'k_rate_vs_R_15', 'k_rate_vs_L_15',
            'p_k_per9_10', 'p_k_rate_10',
            'bat_order', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
        ],
        model_paths=('models/saved/batter_ks_1plus_model.pkl', 'models/saved/batter_ks_2plus_model.pkl'),
        prob_cols=('p_k_1plus', 'p_k_2plus'),
        pred_col='pred_ks',
        pred_from='avg_k_per_game_15',
    ),
}


def load_latest(path, key_col):
    df = pd.read_parquet(path)
    df['game_date'] = pd.to_datetime(df['game_date'])
    return df.sort_values('game_date').groupby(key_col).last().reset_index()


def latest_team_k_rate():
    """Each team's most recent opp_k_pct_15 value (rolling team K rate)."""
    store = pd.read_parquet(STATCAST_PATH, columns=[
        'batter', 'game_pk', 'game_date', 'events', 'home_team', 'away_team', 'inning_topbot',
    ])
    store['game_date'] = pd.to_datetime(store['game_date'])
    team_order = derive_team_and_bat_order(pd.read_parquet(STATCAST_PATH, columns=[
        'batter', 'game_pk', 'game_date', 'at_bat_number', 'inning_topbot', 'home_team', 'away_team',
    ]))
    team_k = compute_team_k_rate(store, team_order)
    team_k = team_k.merge(store[['game_pk', 'game_date']].drop_duplicates('game_pk'), on='game_pk', how='left')
    latest = team_k.sort_values('game_date').groupby('team').last().reset_index()
    return latest.set_index('team')['opp_k_pct_15']


def build_matchup_rows(games, rosters, lineups_by_game, batter_idx, pitcher_idx, team_k_idx,
                        weather_idx, park_tb_idx, date_str):
    rows = []
    for game in games:
        home_abbr, away_abbr = game['home_abbr'], game['away_abbr']
        lineup_info = lineups_by_game.get(game['game_id'], {})
        batting_order = lineup_info.get('batting_order', {})
        starters = lineup_info.get('starters', set())

        is_dome = np.nan
        wind_out = np.nan
        if home_abbr in weather_idx.index:
            w = weather_idx.loc[home_abbr]
            is_dome = int(w.get('is_dome', 0))
            wind_favor = w.get('wind_favor', np.nan)
            wind_out = int(wind_favor >= 3) if pd.notna(wind_favor) else 0
        tb_park_factor = park_tb_idx.get(home_abbr, np.nan)

        sides = [
            dict(batters=rosters.get(game['home_id'], []), pitcher_id=game['away_pitcher_id'],
                 pitcher_name=game['away_pitcher_name'], team_abbr=home_abbr, is_home=1, opp_team=away_abbr),
            dict(batters=rosters.get(game['away_id'], []), pitcher_id=game['home_pitcher_id'],
                 pitcher_name=game['home_pitcher_name'], team_abbr=away_abbr, is_home=0, opp_team=home_abbr),
        ]

        for side in sides:
            p_id = side['pitcher_id']
            if p_id and p_id in pitcher_idx.index:
                pf = pitcher_idx.loc[p_id]
                p_throws = str(pf.get('p_throws', 'R'))
            else:
                pf = None
                p_throws = 'R'
            p_throws_R = 1 if p_throws == 'R' else 0

            for batter in side['batters']:
                bid = batter['player_id']
                if bid not in batter_idx.index:
                    continue
                bf = batter_idx.loc[bid]
                stand = str(bf.get('stand', 'R'))

                row = {
                    'batter': bid, 'player_name': batter['name'],
                    'team_abbr': side['team_abbr'], 'opp_team': side['opp_team'],
                    'is_home': side['is_home'],
                    'bat_order': batting_order.get(bid),
                    'in_lineup': int(bid in starters) if starters else None,
                    'pitcher_id': p_id, 'pitcher_name': side['pitcher_name'], 'p_throws': p_throws,
                    'game_id': game['game_id'], 'game_time': game.get('game_time'), 'stadium': game.get('stadium'),
                    'stand_R': 1 if stand == 'R' else 0, 'p_throws_R': p_throws_R,
                    'opp_k_pct_15': team_k_idx.get(side['team_abbr']),
                    # Pin these explicitly -- otherwise the batter-feature
                    # merge below silently overwrites them with the batter's
                    # OWN last-game game_date/game_pk (stale history, not
                    # today's actual game), which broke already_logged()'s
                    # date dedup check in scripts/shared_log_results.py.
                    'game_date': date_str, 'game_pk': game['game_id'],
                    'is_dome': is_dome, 'wind_out': wind_out, 'tb_park_factor': tb_park_factor,
                }
                for c in bf.index:
                    if c not in row:
                        row[c] = bf[c]
                if pf is not None:
                    for c in pf.index:
                        if c not in row and (str(c).startswith('p_')):
                            row[c] = pf[c]
                rows.append(row)
    return pd.DataFrame(rows)


def run(date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()
    season = int(date_str[:4])

    print(f"\n{'='*60}")
    print(f"  Batter Props Runner (Hits/TB/Ks)  --  {date_str}")
    print(f"{'='*60}")

    print("\nLoading latest feature tables...")
    batter_feats = load_latest(BATTER_PATH, 'batter')
    pitcher_feats = load_latest(PITCHER_PATH, 'pitcher')
    pitcher_log_feats = load_latest(PITCHER_LOG_PATH, 'pitcher')
    pitcher_feats = pitcher_feats.merge(
        pitcher_log_feats[['pitcher', 'p_hits_per9_10', 'p_hr_per9_10', 'p_k_per9_10', 'p_k_rate_10']],
        on='pitcher', how='left')

    platoon_feats = load_latest(PLATOON_PATH, 'batter')
    platoon_cols = [c for c in platoon_feats.columns if c not in ('batter', 'game_pk', 'game_date')]
    batter_feats = batter_feats.merge(platoon_feats[['batter'] + platoon_cols], on='batter', how='left')

    print(f"  {batter_feats['batter'].nunique():,} batters | {pitcher_feats['pitcher'].nunique():,} pitchers")

    print("\nComputing latest team K rate context...")
    team_k_idx = latest_team_k_rate()

    print("\nLoading TB park factors...")
    park_tb_idx = (pd.read_csv(PARK_TB_PATH).set_index('park')['tb_park_factor']
                   if os.path.exists(PARK_TB_PATH) else pd.Series(dtype=float))

    print(f"\nFetching schedule for {date_str}...")
    all_games = fetch_schedule(date_str)
    games = [g for g in all_games if g['status'] != 'Final']
    if not games:
        print("No games today (or all final). Exiting.")
        return {}
    print(f"  {len(games)} games")

    print(f"\nFetching weather for {date_str}...")
    weather_idx = get_todays_weather(date_str)

    print("\nFetching active rosters...")
    team_ids = {g['home_id'] for g in games} | {g['away_id'] for g in games}
    rosters = {}
    for tid in sorted(team_ids):
        try:
            rosters[tid] = fetch_roster(tid, season)
            time.sleep(0.1)
        except Exception as e:
            print(f"  WARNING: roster fetch failed for team {tid}: {e}")
            rosters[tid] = []

    print("\nFetching confirmed lineups (bat_order)...")
    lineups_by_game = fetch_lineups_by_game(date_str, games)
    print(f"  {len(lineups_by_game)} / {len(games)} games have confirmed lineups")

    print("\nAssembling matchup rows...")
    batter_idx = batter_feats.set_index('batter')
    pitcher_idx = pitcher_feats.set_index('pitcher')
    df = build_matchup_rows(games, rosters, lineups_by_game, batter_idx, pitcher_idx, team_k_idx,
                            weather_idx, park_tb_idx, date_str)
    if df.empty:
        print("No rows assembled.")
        return {}
    print(f"  {len(df)} batter-game rows")

    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    for model_key, cfg in MODEL_CONFIGS.items():
        print(f"\nScoring {cfg['label']}...")
        X = df.copy()
        all_features = set(cfg['primary_features']) | set(cfg['secondary_features'])
        for f in all_features:
            if f not in X.columns:
                X[f] = np.nan
        # Columns that are all/mostly None (e.g. bat_order before lineups
        # post) can end up as object dtype, which LightGBM rejects outright.
        X[list(all_features)] = X[list(all_features)].apply(pd.to_numeric, errors='coerce')
        p1_path, p2_path = cfg['model_paths']
        m1, m2 = joblib.load(p1_path), joblib.load(p2_path)
        c1, c2 = cfg['prob_cols']
        X[c1] = m1.predict_proba(X[cfg['primary_features']])[:, 1]
        X[c2] = m2.predict_proba(X[cfg['secondary_features']])[:, 1]
        X['adj_prob'] = X[c1]
        X[cfg['pred_col']] = X[cfg['pred_from']]

        out_path = os.path.join(OUT_DIR, f'{model_key}_predictions_{date_str}.csv')
        X.sort_values(c1, ascending=False).to_csv(out_path, index=False)
        print(f"  Saved {len(X)} rows -> {out_path}")
        print(X[['player_name', 'team_abbr', 'pitcher_name', c1, c2]]
              .sort_values(c1, ascending=False).head(10).to_string(index=False))
        results[model_key] = X

    return results


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
