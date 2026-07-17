"""
Batter rolling features for the Hits / Total Bases / Batter Ks models, built
from the full plate-appearance-outcome Statcast store (not just batted balls --
see ingestion/fetch_statcast.py for why this store now includes K/BB/HBP rows).

Output: data/processed/batter_pa_features.parquet, one row per batter-game with:
  - that game's actual outcome counts (h, tb, k, ab, pa, ...) -- used as training
    labels downstream (NOT shifted, this is what actually happened that game)
  - rolling L15 features computed with shift(1) so the current game is never
    included in its own features (no leakage)

This is separate from features/batter_features.py (HR model, batted-balls-only)
and features/platoon_features.py -- neither of those is touched or affected.
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/batter_pa_features.parquet'

NON_AB_EVENTS = {
    'walk', 'intent_walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt',
    'sac_fly_double_play', 'sac_bunt_double_play',
    'catcher_interf', 'truncated_pa',
}
HIT_EVENTS    = {'single', 'double', 'triple', 'home_run'}
K_EVENTS      = {'strikeout', 'strikeout_double_play'}
BB_EVENTS     = {'walk', 'intent_walk'}
SF_EVENTS     = {'sac_fly', 'sac_fly_double_play'}

W = 15  # rolling window (games)
MIN_PERIODS = 5
W5 = 5   # short "hot streak" window
MIN_PERIODS_5 = 2


def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])

    df['is_ab']       = (~df['events'].isin(NON_AB_EVENTS)).astype(int)
    df['is_hit']      = df['events'].isin(HIT_EVENTS).astype(int)
    df['is_single']   = (df['events'] == 'single').astype(int)
    df['is_double']   = (df['events'] == 'double').astype(int)
    df['is_triple']   = (df['events'] == 'triple').astype(int)
    df['is_hr']       = (df['events'] == 'home_run').astype(int)
    df['is_bb']       = df['events'].isin(BB_EVENTS).astype(int)
    df['is_hbp']      = (df['events'] == 'hit_by_pitch').astype(int)
    df['is_sf']       = df['events'].isin(SF_EVENTS).astype(int)
    df['is_k']        = df['events'].isin(K_EVENTS).astype(int)
    df['total_bases'] = df['is_single'] + 2*df['is_double'] + 3*df['is_triple'] + 4*df['is_hr']

    # bb_type is populated for every batted ball even when the launch_speed
    # sensor reading is missing (~3% of batted balls, more common in early
    # seasons) -- using bb_type.notna() avoids undercounting batted balls,
    # which would otherwise let hard_hit/barrel/GB/FB percentages exceed 1.0.
    df['is_batted_ball'] = df['bb_type'].notna().astype(int)
    df['is_barrel']    = ((df['launch_speed'] >= 98) & (df['launch_angle'] >= 26) & (df['launch_angle'] <= 30)).fillna(False).astype(int)
    df['is_hard_hit']  = (df['launch_speed'] >= 95).fillna(False).astype(int)
    df['is_fly_ball']  = (df['bb_type'] == 'fly_ball').fillna(False).astype(int)
    df['is_ground_ball'] = (df['bb_type'] == 'ground_ball').fillna(False).astype(int)
    df['is_line_drive']  = (df['bb_type'] == 'line_drive').fillna(False).astype(int)

    print("Aggregating to batter-game level...")
    g = df.groupby(['batter', 'game_pk', 'game_date', 'stand']).agg(
        pa=('is_ab', 'size'),
        ab=('is_ab', 'sum'),
        h=('is_hit', 'sum'),
        doubles=('is_double', 'sum'),
        triples=('is_triple', 'sum'),
        hr=('is_hr', 'sum'),
        bb=('is_bb', 'sum'),
        hbp=('is_hbp', 'sum'),
        sf=('is_sf', 'sum'),
        k=('is_k', 'sum'),
        tb=('total_bases', 'sum'),
        batted_balls=('is_batted_ball', 'sum'),
        barrels=('is_barrel', 'sum'),
        hard_hits=('is_hard_hit', 'sum'),
        fly_balls=('is_fly_ball', 'sum'),
        ground_balls=('is_ground_ball', 'sum'),
        line_drives=('is_line_drive', 'sum'),
        avg_xba=('estimated_ba_using_speedangle', 'mean'),
        avg_xslg=('estimated_slg_using_speedangle', 'mean'),
    ).reset_index()
    g = g.sort_values(['batter', 'game_date'])

    # Game-level actual outcomes -- used as training TARGETS downstream (not shifted)
    g['target_hit_1plus'] = (g['h'] >= 1).astype(int)
    g['target_hit_2plus'] = (g['h'] >= 2).astype(int)
    g['target_tb_1plus']  = (g['tb'] >= 1).astype(int)
    g['target_tb_2plus']  = (g['tb'] >= 2).astype(int)
    g['target_k_1plus']   = (g['k']  >= 1).astype(int)
    g['target_k_2plus']   = (g['k']  >= 2).astype(int)

    print("Computing trailing rolling features (shift(1), no leakage)...")
    out = []
    for bid, sub in g.groupby('batter'):
        sub = sub.sort_values('game_date').copy()
        r = sub.shift(1).rolling(W, min_periods=MIN_PERIODS)

        sum_ab  = r['ab'].sum()
        sum_pa  = r['pa'].sum()
        sum_h   = r['h'].sum()
        sum_k   = r['k'].sum()
        sum_bb  = r['bb'].sum()
        sum_hbp = r['hbp'].sum()
        sum_sf  = r['sf'].sum()
        sum_hr  = r['hr'].sum()
        sum_tb  = r['tb'].sum()
        sum_bip = r['batted_balls'].sum()
        sum_dbl = r['doubles'].sum()

        sub['batting_avg_15']   = sum_h / sum_ab
        sub['obp_15']           = (sum_h + sum_bb + sum_hbp) / (sum_ab + sum_bb + sum_hbp + sum_sf)
        sub['contact_rate_15']  = (sum_ab - sum_k) / sum_ab
        sub['k_rate_15']        = sum_k / sum_pa
        sub['babip_15']         = (sum_h - sum_hr) / (sum_ab - sum_k - sum_hr + sum_sf)
        sub['iso_15']           = (sum_tb - sum_h) / sum_ab
        sub['hr_rate_15']       = sum_hr / sum_pa
        sub['doubles_rate_15']  = sum_dbl / sum_pa
        sub['avg_total_bases_15'] = r['tb'].mean()
        sub['avg_k_per_game_15']  = r['k'].mean()

        sub['hard_hit_pct_15']   = r['hard_hits'].sum() / sum_bip
        sub['line_drive_pct_15'] = r['line_drives'].sum() / sum_bip
        sub['gb_pct_15']         = r['ground_balls'].sum() / sum_bip
        sub['fly_ball_pct_15']   = r['fly_balls'].sum() / sum_bip
        sub['barrel_pct_15']     = r['barrels'].sum() / sum_bip
        sub['xba_15']            = r['avg_xba'].mean()
        sub['xslg_15']           = r['avg_xslg'].mean()

        # Short "hot streak" window -- captures recent form better than L15.
        # Only applied to the stats where momentum matters most (batting
        # average, K rate, xBA, xSLG), not every L15 feature.
        r5 = sub.shift(1).rolling(W5, min_periods=MIN_PERIODS_5)
        sub['batting_avg_last_5'] = r5['h'].sum() / r5['ab'].sum()
        sub['k_rate_last_5']      = r5['k'].sum() / r5['pa'].sum()
        sub['xba_last_5']         = r5['avg_xba'].mean()
        sub['xslg_last_5']        = r5['avg_xslg'].mean()

        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result):,} batter-game rows to {OUTPUT_PATH}")

    ready = result[result['batting_avg_15'].notna()]
    print(f"Rows with full features: {len(ready):,}")
    print(ready[['game_date', 'batter', 'batting_avg_15', 'k_rate_15', 'avg_total_bases_15']]
          .head(8).to_string(index=False))


if __name__ == '__main__':
    build()
