"""
Batter platoon-split rolling features (vs RHP / vs LHP) for the Hits / Total
Bases / Batter Ks models, built from the PA-outcome Statcast store. Mirrors
features/platoon_features.py's approach (HR model) but computes batting
average, slugging, and K-rate splits instead of HR-specific rates.

For a game vs RHP the vs_R columns are populated and vs_L columns are NaN
(and vice versa) -- LightGBM routes NaN down a separate branch per split, so
it naturally learns to use the relevant side's features.

Output: data/processed/batter_platoon_pa_features.parquet
  batting_avg_vs_R_15, batting_avg_vs_L_15
  slg_vs_R_15, slg_vs_L_15
  k_rate_vs_R_15, k_rate_vs_L_15
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/batter_platoon_pa_features.parquet'

NON_AB_EVENTS = {
    'walk', 'intent_walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt',
    'sac_fly_double_play', 'sac_bunt_double_play', 'catcher_interf', 'truncated_pa',
}
HIT_EVENTS = {'single', 'double', 'triple', 'home_run'}
K_EVENTS   = {'strikeout', 'strikeout_double_play'}

HANDS = ['R', 'L']
W = 15
MIN_PERIODS = 3


def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH, columns=[
        'batter', 'game_pk', 'game_date', 'p_throws', 'events',
    ])
    df['game_date'] = pd.to_datetime(df['game_date'])

    df['is_ab']  = (~df['events'].isin(NON_AB_EVENTS)).astype(int)
    df['is_hit'] = df['events'].isin(HIT_EVENTS).astype(int)
    is_single = (df['events'] == 'single').astype(int)
    is_double = (df['events'] == 'double').astype(int)
    is_triple = (df['events'] == 'triple').astype(int)
    is_hr     = (df['events'] == 'home_run').astype(int)
    df['total_bases'] = is_single + 2*is_double + 3*is_triple + 4*is_hr
    df['is_k'] = df['events'].isin(K_EVENTS).astype(int)

    print("Finding dominant pitcher hand per batter-game...")
    hand_per_game = (
        df.groupby(['batter', 'game_pk', 'p_throws'])
        .size().reset_index(name='n')
        .sort_values('n', ascending=False)
        .drop_duplicates(['batter', 'game_pk'])
    )[['batter', 'game_pk', 'p_throws']]

    print("Aggregating to batter-game level...")
    g = df.groupby(['batter', 'game_pk', 'game_date']).agg(
        pa=('is_ab', 'size'), ab=('is_ab', 'sum'),
        h=('is_hit', 'sum'), tb=('total_bases', 'sum'), k=('is_k', 'sum'),
    ).reset_index()
    g = g.merge(hand_per_game, on=['batter', 'game_pk'], how='left')
    g = g.sort_values(['batter', 'game_date'])

    feat_cols = [f'{stat}_vs_{hand}_{W}' for hand in HANDS for stat in ('batting_avg', 'slg', 'k_rate')]

    print(f"Computing platoon rolling features for {g['batter'].nunique():,} batters...")
    all_rows = []
    for batter_id, bsub in g.groupby('batter'):
        bsub = bsub.sort_values('game_date').reset_index(drop=True)
        for col in feat_cols:
            bsub[col] = np.nan

        for hand in HANDS:
            idx = bsub.index[bsub['p_throws'] == hand].tolist()
            hand_sub = bsub.loc[idx].copy().reset_index(drop=True)
            if len(hand_sub) < 2:
                continue
            r = hand_sub.shift(1).rolling(W, min_periods=MIN_PERIODS)
            sum_ab, sum_h, sum_tb, sum_pa, sum_k = (
                r['ab'].sum(), r['h'].sum(), r['tb'].sum(), r['pa'].sum(), r['k'].sum())
            hand_sub[f'batting_avg_vs_{hand}_{W}'] = sum_h / sum_ab
            hand_sub[f'slg_vs_{hand}_{W}']         = sum_tb / sum_ab
            hand_sub[f'k_rate_vs_{hand}_{W}']      = sum_k / sum_pa

            cols_for_hand = [c for c in feat_cols if f'_vs_{hand}_' in c]
            for col in cols_for_hand:
                bsub.loc[idx, col] = hand_sub[col].values

        all_rows.append(bsub[['batter', 'game_pk', 'game_date'] + feat_cols])

    result = pd.concat(all_rows, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result):,} rows to {OUTPUT_PATH}")

    total = len(result)
    has_r = result[f'batting_avg_vs_R_{W}'].notna().sum()
    has_l = result[f'batting_avg_vs_L_{W}'].notna().sum()
    print(f"vs_R populated: {has_r:,} / {total:,} ({has_r/total:.1%})")
    print(f"vs_L populated: {has_l:,} / {total:,} ({has_l/total:.1%})")


if __name__ == '__main__':
    build()
