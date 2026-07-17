"""
Assembles the shared training dataset for the Hits / Total Bases / Batter Ks
models: one row per batter-game with all rolling features, the opposing
(primary) pitcher's rolling features, bat_order, team K-rate context, and
all 6 targets (hit_1plus/2plus, tb_1plus/2plus, k_1plus/2plus).

bat_order and opp_k_pct_15 are DERIVED from data already in the Statcast
PA-outcome store rather than requiring a new historical API backfill:
  - bat_order: within a (game_pk, team), rank each batter by the at_bat_number
    of their FIRST plate appearance that game. This reconstructs the actual
    batting order for that specific historical game for free.
  - opp_k_pct_15: rolling L15 team-level K rate for the batter's own team
    (i.e. how strikeout-prone this offense has been recently), aggregated
    from the same PA-outcome store.

At prediction time (today's games), bat_order instead comes from the real
confirmed lineup via predict/shared_mlb.fetch_lineups_by_game -- this
derivation is a training-data-only substitute (no live lineup exists yet
for a game that already happened).

Output: data/processed/batter_props_training_dataset.parquet
"""
import pandas as pd
import numpy as np
import os

STORE        = 'data/raw/statcast_batted_balls.parquet'
BATTER       = 'data/processed/batter_pa_features.parquet'
PITCHER      = 'data/processed/pitcher_pa_features.parquet'
PITCHER_LOG  = 'data/processed/pitcher_game_log_features.parquet'
PLATOON      = 'data/processed/batter_platoon_pa_features.parquet'
WEATHER      = 'data/processed/weather.parquet'
PARK_TB      = 'data/processed/park_tb_factor.csv'
OUT          = 'data/processed/batter_props_training_dataset.parquet'


def derive_team_and_bat_order(store):
    """
    Returns a DataFrame: batter, game_pk, team, is_home, bat_order
    derived purely from at_bat_number ordering (see module docstring).
    """
    pa = store[['batter', 'game_pk', 'game_date', 'at_bat_number',
                'inning_topbot', 'home_team', 'away_team']].copy()

    # Batter's team for this game = away team while batting in the top of an
    # inning, home team while batting in the bottom.
    pa['team']    = pa['home_team'].where(pa['inning_topbot'] == 'Bot', pa['away_team'])
    pa['is_home'] = (pa['inning_topbot'] == 'Bot').astype(int)

    first_pa = (pa.groupby(['batter', 'game_pk'])
                .agg(team=('team', 'first'),
                     is_home=('is_home', 'first'),
                     first_ab=('at_bat_number', 'min'))
                .reset_index())

    first_pa['bat_order'] = (
        first_pa.groupby(['game_pk', 'team'])['first_ab']
        .rank(method='first').astype(int)
    )
    # Only 1-9 are real starting-lineup slots; later "orders" are pinch
    # hitters/substitutes batting for the first time later in the game.
    first_pa.loc[first_pa['bat_order'] > 9, 'bat_order'] = 9

    return first_pa[['batter', 'game_pk', 'team', 'is_home', 'bat_order']]


def compute_team_k_rate(store, batter_team_map):
    """Rolling L15 team-level K rate, keyed by (team, game_date)."""
    pa = store[['batter', 'game_pk', 'game_date', 'events']].copy()
    pa['game_date'] = pd.to_datetime(pa['game_date'])
    pa = pa.merge(batter_team_map[['batter', 'game_pk', 'team']],
                  on=['batter', 'game_pk'], how='left')

    K_EVENTS = {'strikeout', 'strikeout_double_play'}
    pa['is_k'] = pa['events'].isin(K_EVENTS).astype(int)

    team_game = (pa.groupby(['team', 'game_pk', 'game_date'])
                 .agg(pa_count=('is_k', 'size'), k=('is_k', 'sum'))
                 .reset_index()
                 .sort_values(['team', 'game_date']))

    out = []
    for team, sub in team_game.groupby('team'):
        sub = sub.sort_values('game_date').copy()
        r = sub.shift(1).rolling(15, min_periods=5)
        sub['opp_k_pct_15'] = r['k'].sum() / r['pa_count'].sum()
        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    return result[['team', 'game_pk', 'opp_k_pct_15']]


def build():
    print("Loading Statcast store...")
    store = pd.read_parquet(STORE, columns=[
        'batter', 'pitcher', 'game_pk', 'game_date', 'home_team', 'away_team',
        'stand', 'p_throws', 'at_bat_number', 'inning_topbot', 'events',
    ])
    store['game_date'] = pd.to_datetime(store['game_date'])

    print("Finding primary opposing pitcher per batter-game...")
    matchup = (store.groupby(['batter', 'game_pk', 'pitcher'])
               .size().reset_index(name='n')
               .sort_values('n', ascending=False)
               .drop_duplicates(['batter', 'game_pk']))[['batter', 'game_pk', 'pitcher']]

    print("Deriving bat_order + team from at_bat_number ordering...")
    team_order = derive_team_and_bat_order(store)

    print("Computing rolling team K rate (opp_k_pct_15)...")
    team_k = compute_team_k_rate(store, team_order)

    print("Loading feature tables...")
    batter  = pd.read_parquet(BATTER)
    pitcher = pd.read_parquet(PITCHER)
    pitcher_log = pd.read_parquet(PITCHER_LOG)
    platoon = pd.read_parquet(PLATOON)

    print("Finding home_team per game (for weather + park factor joins)...")
    game_home = store[['game_pk', 'home_team']].drop_duplicates('game_pk')

    print("Assembling...")
    df = batter.merge(matchup, on=['batter', 'game_pk'], how='left')
    df = df.merge(team_order, on=['batter', 'game_pk'], how='left')
    df = df.merge(team_k, on=['team', 'game_pk'], how='left')
    df = df.merge(game_home, on='game_pk', how='left')

    platoon_cols = ['batter', 'game_pk'] + [c for c in platoon.columns if c not in ('batter', 'game_pk', 'game_date')]
    df = df.merge(platoon[platoon_cols], on=['batter', 'game_pk'], how='left')

    pcols = ['pitcher', 'game_pk'] + [c for c in pitcher.columns if c.startswith('p_')]
    df = df.merge(pitcher[pcols], on=['pitcher', 'game_pk'], how='left')

    plog_cols = ['pitcher', 'game_pk', 'p_hits_per9_10', 'p_hr_per9_10',
                 'p_k_per9_10', 'p_k_rate_10']
    df = df.merge(pitcher_log[plog_cols], on=['pitcher', 'game_pk'], how='left')

    print("Joining weather (is_dome, wind_out) and TB park factor...")
    if os.path.exists(WEATHER):
        weather = pd.read_parquet(WEATHER)
        weather['game_date'] = pd.to_datetime(weather['game_date'])
        df = df.merge(weather[['game_date', 'home_team', 'wind_favor', 'is_dome']],
                      on=['game_date', 'home_team'], how='left')
        # wind_out: wind blowing out toward the outfield by a meaningful margin
        # (matches the ">= 0.3 of wind_speed toward OF" threshold used for the
        # HR model's wind_description labeling in predict/daily_runner.py).
        df['wind_out'] = (df['wind_favor'] >= 3).astype(int)
        df = df.drop(columns=['wind_favor'])
    else:
        print("  WARNING: weather.parquet not found -- skipping is_dome/wind_out.")
        df['is_dome'] = np.nan
        df['wind_out'] = np.nan

    if os.path.exists(PARK_TB):
        park_tb = pd.read_csv(PARK_TB)[['park', 'tb_park_factor']]
        df = df.merge(park_tb, left_on='home_team', right_on='park', how='left').drop(columns=['park'])
    else:
        print("  WARNING: park_tb_factor.csv not found -- skipping tb_park_factor.")
        df['tb_park_factor'] = np.nan

    # p_throws (pitcher handedness) already came in via pitcher[pcols] above
    # (pitcher_pa_features.parquet groups by p_throws).
    df['stand_R']    = (df['stand'] == 'R').astype(int)
    df['p_throws_R'] = (df['p_throws'] == 'R').astype(int)

    # Require the core rolling features to be present (same convention as
    # the HR model's build_dataset.py -- drop cold-start rows with no history).
    df = df[df['batting_avg_15'].notna() & df['p_slg_allowed_10'].notna()].copy()

    os.makedirs('data/processed', exist_ok=True)
    df.to_parquet(OUT, index=False)

    print(f"\nSaved {len(df):,} training rows to {OUT}")
    for t in ['target_hit_1plus', 'target_hit_2plus', 'target_tb_1plus',
              'target_tb_2plus', 'target_k_1plus', 'target_k_2plus']:
        print(f"  {t}: {df[t].mean():.3%}")
    print(f"\nbat_order coverage: {df['bat_order'].notna().mean():.1%}")
    print(f"opp_k_pct_15 coverage: {df['opp_k_pct_15'].notna().mean():.1%}")
    print(f"p_k_per9_10 coverage: {df['p_k_per9_10'].notna().mean():.1%}")
    print(f"batting_avg_last_5 coverage: {df['batting_avg_last_5'].notna().mean():.1%}")
    print(f"batting_avg_vs_R_15/vs_L_15 coverage: {df['batting_avg_vs_R_15'].notna().mean():.1%} / {df['batting_avg_vs_L_15'].notna().mean():.1%}")
    print(f"is_dome coverage: {df['is_dome'].notna().mean():.1%}")
    print(f"tb_park_factor coverage: {df['tb_park_factor'].notna().mean():.1%}")


if __name__ == '__main__':
    build()
