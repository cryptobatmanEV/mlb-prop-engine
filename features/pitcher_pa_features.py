"""
Pitcher-allowed rolling features for the Hits / Total Bases / Batter Ks models,
built from the full plate-appearance-outcome Statcast store (see
ingestion/fetch_statcast.py for why this store now includes K/BB/HBP rows).

Output: data/processed/pitcher_pa_features.parquet, one row per pitcher-game.

Note: p_hits_per9_10 and p_k_per9_10 (innings-normalized rates) are NOT
computed here -- those come from ingestion/fetch_pitcher_game_logs.py (MLB
Stats API box scores), which gives a cleaner innings-pitched basis than
reconstructing outs from Statcast pitch data. This module covers the
allowed-contact-quality features (contact rate, BABIP, GB/FB, SLG/ISO allowed)
that DO need Statcast's batted-ball detail.
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/pitcher_pa_features.parquet'

NON_AB_EVENTS = {
    'walk', 'intent_walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt',
    'sac_fly_double_play', 'sac_bunt_double_play',
    'catcher_interf', 'truncated_pa',
}
HIT_EVENTS = {'single', 'double', 'triple', 'home_run'}
K_EVENTS   = {'strikeout', 'strikeout_double_play'}
BB_EVENTS  = {'walk', 'intent_walk'}

W = 10  # rolling window (starts)
MIN_PERIODS = 4


def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])

    df['is_ab']     = (~df['events'].isin(NON_AB_EVENTS)).astype(int)
    df['is_hit']     = df['events'].isin(HIT_EVENTS).astype(int)
    df['is_single']  = (df['events'] == 'single').astype(int)
    df['is_double']  = (df['events'] == 'double').astype(int)
    df['is_triple']  = (df['events'] == 'triple').astype(int)
    df['is_hr']      = (df['events'] == 'home_run').astype(int)
    df['is_k']       = df['events'].isin(K_EVENTS).astype(int)
    df['total_bases'] = df['is_single'] + 2*df['is_double'] + 3*df['is_triple'] + 4*df['is_hr']

    # bb_type is populated for every batted ball even when the launch_speed
    # sensor reading is missing (~3% of batted balls) -- using bb_type.notna()
    # avoids undercounting batted balls, which would otherwise let allowed
    # hard_hit/barrel/GB/FB percentages exceed 1.0.
    df['is_batted_ball'] = df['bb_type'].notna().astype(int)
    df['is_barrel']    = ((df['launch_speed'] >= 98) & (df['launch_angle'] >= 26) & (df['launch_angle'] <= 30)).fillna(False).astype(int)
    df['is_hard_hit']  = (df['launch_speed'] >= 95).fillna(False).astype(int)
    df['is_fly_ball']  = (df['bb_type'] == 'fly_ball').fillna(False).astype(int)
    df['is_ground_ball'] = (df['bb_type'] == 'ground_ball').fillna(False).astype(int)

    print("Aggregating to pitcher-game level...")
    g = df.groupby(['pitcher', 'game_pk', 'game_date', 'p_throws']).agg(
        pa=('is_ab', 'size'),
        ab=('is_ab', 'sum'),
        h=('is_hit', 'sum'),
        hr=('is_hr', 'sum'),
        k=('is_k', 'sum'),
        tb=('total_bases', 'sum'),
        batted_balls=('is_batted_ball', 'sum'),
        barrels=('is_barrel', 'sum'),
        hard_hits=('is_hard_hit', 'sum'),
        fly_balls=('is_fly_ball', 'sum'),
        ground_balls=('is_ground_ball', 'sum'),
    ).reset_index()
    g = g.sort_values(['pitcher', 'game_date'])

    print("Computing trailing rolling features (shift(1), no leakage)...")
    out = []
    for pid, sub in g.groupby('pitcher'):
        sub = sub.sort_values('game_date').copy()
        r = sub.shift(1).rolling(W, min_periods=MIN_PERIODS)

        sum_ab  = r['ab'].sum()
        sum_pa  = r['pa'].sum()
        sum_h   = r['h'].sum()
        sum_hr  = r['hr'].sum()
        sum_tb  = r['tb'].sum()
        sum_bip = r['batted_balls'].sum()

        sub['p_contact_rate_allowed_10'] = r['batted_balls'].sum() / sum_pa
        sub['p_babip_allowed_10']        = (sum_h - sum_hr) / (sum_ab - sum_hr)
        sub['p_slg_allowed_10']          = sum_tb / sum_ab
        sub['p_iso_allowed_10']          = (sum_tb - sum_h) / sum_ab
        sub['p_gb_pct_10']               = r['ground_balls'].sum() / sum_bip
        sub['p_fb_pct_10']               = r['fly_balls'].sum() / sum_bip
        sub['p_barrel_pct_allowed_10']   = r['barrels'].sum() / sum_bip

        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result):,} pitcher-game rows to {OUTPUT_PATH}")

    ready = result[result['p_slg_allowed_10'].notna()]
    print(f"Rows with full features: {len(ready):,}")
    print(ready[['game_date', 'pitcher', 'p_slg_allowed_10', 'p_gb_pct_10']]
          .head(8).to_string(index=False))


if __name__ == '__main__':
    build()
