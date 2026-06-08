"""
Compute batter platoon-split rolling features.

A "platoon split" is a batter's performance broken down by whether the opposing
pitcher was right-handed (RHP) or left-handed (LHP).  Most batters hit for more
power against pitchers of the opposite hand — this is one of the strongest
predictors in baseball.

For each batter-game we produce rolling features from the last N games the batter
faced that same pitcher handedness.  Because we use shift(1) before rolling, the
current game is never included in its own features (no data leakage).

Output columns (12 total):
  hr_per_bb_vs_R_15, hr_per_bb_vs_R_30
  barrel_pct_vs_R_15, barrel_pct_vs_R_30
  hardhit_pct_vs_R_15, hardhit_pct_vs_R_30
  hr_per_bb_vs_L_15, hr_per_bb_vs_L_30
  barrel_pct_vs_L_15, barrel_pct_vs_L_30
  hardhit_pct_vs_L_15, hardhit_pct_vs_L_30

For a game vs RHP the vs_R columns are populated and vs_L columns are NaN.
For a game vs LHP the vs_L columns are populated and vs_R columns are NaN.
LightGBM routes NaN values down a separate branch at each split, so it
naturally learns to use vs_R features when p_throws=R and vs_L when p_throws=L.
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/platoon_features.parquet'

HANDS       = ['R', 'L']
WINDOWS     = [15, 30]
MIN_PERIODS = 3   # need at least 3 games vs a handedness to produce a feature


def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()

    df['is_hr']      = (df['events'] == 'home_run').astype(int)
    df['is_barrel']  = (
        (df['launch_speed'] >= 98) &
        (df['launch_angle'] >= 26) &
        (df['launch_angle'] <= 30)
    ).astype(int)
    df['is_hard_hit'] = (df['launch_speed'] >= 95).astype(int)

    # ── Assign each batter-game to the pitcher handedness they saw the most ──
    print("Finding dominant pitcher hand per batter-game...")
    hand_per_game = (
        df.groupby(['batter', 'game_pk', 'p_throws'])
        .size().reset_index(name='n')
        .sort_values('n', ascending=False)
        .drop_duplicates(['batter', 'game_pk'])
    )[['batter', 'game_pk', 'p_throws']]

    # ── Batter-game aggregation ───────────────────────────────────────────────
    print("Aggregating to batter-game level...")
    g = df.groupby(['batter', 'game_pk', 'game_date']).agg(
        batted_balls = ('is_hr',      'size'),
        hr           = ('is_hr',      'sum'),
        barrels      = ('is_barrel',  'sum'),
        hard_hits    = ('is_hard_hit','sum'),
    ).reset_index()

    g = g.merge(hand_per_game, on=['batter', 'game_pk'], how='left')
    g = g.sort_values(['batter', 'game_date'])

    # All output feature column names
    feat_cols = [
        f'{stat}_vs_{hand}_{w}'
        for hand in HANDS
        for w   in WINDOWS
        for stat in ['hr_per_bb', 'barrel_pct', 'hardhit_pct']
    ]

    # ── Rolling window per batter per pitcher-hand ────────────────────────────
    n_batters = g['batter'].nunique()
    print(f"Computing platoon rolling features for {n_batters:,} batters...")

    all_rows = []
    for batter_id, bsub in g.groupby('batter'):
        bsub = bsub.sort_values('game_date').reset_index(drop=True)

        # Pre-fill all platoon columns with NaN
        for col in feat_cols:
            bsub[col] = np.nan

        for hand in HANDS:
            # Positions (in the bsub index) of games vs this pitcher hand
            idx      = bsub.index[bsub['p_throws'] == hand].tolist()
            hand_sub = bsub.loc[idx].copy().reset_index(drop=True)

            if len(hand_sub) < 2:
                continue  # not enough history to roll; columns stay NaN

            for w in WINDOWS:
                r = hand_sub.shift(1).rolling(w, min_periods=MIN_PERIODS)
                hand_sub[f'hr_per_bb_vs_{hand}_{w}']   = r['hr'].sum()       / r['batted_balls'].sum()
                hand_sub[f'barrel_pct_vs_{hand}_{w}']  = r['barrels'].sum()  / r['batted_balls'].sum()
                hand_sub[f'hardhit_pct_vs_{hand}_{w}'] = r['hard_hits'].sum()/ r['batted_balls'].sum()

            # Write computed values back to the correct rows in bsub
            cols_for_hand = [c for c in feat_cols if f'_vs_{hand}_' in c]
            for col in cols_for_hand:
                bsub.loc[idx, col] = hand_sub[col].values

        all_rows.append(bsub[['batter', 'game_pk', 'game_date'] + feat_cols])

    print("Concatenating results...")
    result = pd.concat(all_rows, ignore_index=True)

    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result):,} rows to {OUTPUT_PATH}")

    total  = len(result)
    has_r  = result['hr_per_bb_vs_R_15'].notna().sum()
    has_l  = result['hr_per_bb_vs_L_15'].notna().sum()
    print(f"vs_R features populated: {has_r:,} / {total:,} ({has_r/total:.1%})")
    print(f"vs_L features populated: {has_l:,} / {total:,} ({has_l/total:.1%})")


build()
