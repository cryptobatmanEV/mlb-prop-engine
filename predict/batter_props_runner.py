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
from features.build_batter_props_dataset import compute_team_k_rate, derive_team_and_bat_order

BATTER_PATH      = 'data/processed/batter_pa_features.parquet'
PITCHER_PATH     = 'data/processed/pitcher_pa_features.parquet'
PITCHER_LOG_PATH = 'data/processed/pitcher_game_log_features.parquet'
STATCAST_PATH    = 'data/raw/statcast_batted_balls.parquet'
OUT_DIR          = 'data/predictions'

MODEL_CONFIGS = {
    'hits': dict(
        label='Hits',
        features=[
            'batting_avg_15', 'obp_15', 'contact_rate_15', 'hard_hit_pct_15',
            'line_drive_pct_15', 'xba_15', 'babip_15', 'k_rate_15', 'gb_pct_15',
            'p_hits_per9_10', 'p_babip_allowed_10', 'p_contact_rate_allowed_10',
            'p_k_rate_10', 'p_gb_pct_10',
            'bat_order', 'is_home', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
        ],
        model_paths=('models/saved/hits_1plus_model.pkl', 'models/saved/hits_2plus_model.pkl'),
        prob_cols=('p_hit_1plus', 'p_hit_2plus'),
        pred_col='pred_hits',
        pred_from='batting_avg_15',  # proxy for expected count: avg * expected AB (~4)
    ),
    'total_bases': dict(
        label='Total Bases',
        features=[
            'avg_total_bases_15', 'xslg_15', 'barrel_pct_15', 'hard_hit_pct_15',
            'fly_ball_pct_15', 'iso_15', 'xba_15', 'hr_rate_15', 'doubles_rate_15',
            'p_slg_allowed_10', 'p_iso_allowed_10', 'p_barrel_pct_allowed_10',
            'p_fb_pct_10', 'p_hr_per9_10',
            'bat_order', 'is_home', 'stand_R', 'p_throws_R',
        ],
        model_paths=('models/saved/total_bases_1plus_model.pkl', 'models/saved/total_bases_2plus_model.pkl'),
        prob_cols=('p_tb_1plus', 'p_tb_2plus'),
        pred_col='pred_total_bases',
        pred_from='avg_total_bases_15',
    ),
    'batter_ks': dict(
        label='Batter Ks',
        features=[
            'k_rate_15', 'avg_k_per_game_15',
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


def build_matchup_rows(games, rosters, lineups_by_game, batter_idx, pitcher_idx, team_k_idx):
    rows = []
    for game in games:
        home_abbr, away_abbr = game['home_abbr'], game['away_abbr']
        lineup_info = lineups_by_game.get(game['game_id'], {})
        batting_order = lineup_info.get('batting_order', {})
        starters = lineup_info.get('starters', set())

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
    print(f"  {batter_feats['batter'].nunique():,} batters | {pitcher_feats['pitcher'].nunique():,} pitchers")

    print("\nComputing latest team K rate context...")
    team_k_idx = latest_team_k_rate()

    print(f"\nFetching schedule for {date_str}...")
    all_games = fetch_schedule(date_str)
    games = [g for g in all_games if g['status'] != 'Final']
    if not games:
        print("No games today (or all final). Exiting.")
        return {}
    print(f"  {len(games)} games")

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
    df = build_matchup_rows(games, rosters, lineups_by_game, batter_idx, pitcher_idx, team_k_idx)
    if df.empty:
        print("No rows assembled.")
        return {}
    print(f"  {len(df)} batter-game rows")

    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    for model_key, cfg in MODEL_CONFIGS.items():
        print(f"\nScoring {cfg['label']}...")
        X = df.copy()
        for f in cfg['features']:
            if f not in X.columns:
                X[f] = np.nan
        p1_path, p2_path = cfg['model_paths']
        m1, m2 = joblib.load(p1_path), joblib.load(p2_path)
        c1, c2 = cfg['prob_cols']
        X[c1] = m1.predict_proba(X[cfg['features']])[:, 1]
        X[c2] = m2.predict_proba(X[cfg['features']])[:, 1]
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
