"""
Total Bases park factor: how many total bases a park produces per plate
appearance relative to league average, recency-weighted (same 3-year
weighting scheme as features/park_factors.py's HR park factor, but computed
directly from total-bases-per-PA rather than an EV/LA expected-value model --
TB includes singles/doubles/triples, not just the "well-struck ball" quality
signal that HR park factor's expected-HR regression captures).

100 = neutral, 110 = 10% more total bases than average at this park.

Usage:
    python features/park_tb_factor.py
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/park_tb_factor.csv'

YEAR_WEIGHTS = {0: 1.0, 1: 0.7, 2: 0.5}

NON_AB_EVENTS = {
    'walk', 'intent_walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt',
    'sac_fly_double_play', 'sac_bunt_double_play', 'catcher_interf', 'truncated_pa',
}
HIT_EVENTS = {'single', 'double', 'triple', 'home_run'}


def compute(reference_year=None):
    print("Loading PA-outcome store...")
    df = pd.read_parquet(STORE_PATH, columns=['game_year', 'home_team', 'events'])

    seasons = sorted(df['game_year'].unique())
    if reference_year is None:
        reference_year = max(seasons)
    use_years = [y for y in seasons if reference_year - 2 <= y <= reference_year]
    print(f"Using seasons: {use_years} (reference {reference_year})")
    df = df[df['game_year'].isin(use_years)].copy()

    is_single = (df['events'] == 'single').astype(int)
    is_double = (df['events'] == 'double').astype(int)
    is_triple = (df['events'] == 'triple').astype(int)
    is_hr     = (df['events'] == 'home_run').astype(int)
    df['total_bases'] = is_single + 2*is_double + 3*is_triple + 4*is_hr
    df['weight'] = df['game_year'].map(lambda y: YEAR_WEIGHTS.get(reference_year - y, 0.3))

    league_avg_tb = np.average(df['total_bases'], weights=df['weight'])
    print(f"League-average TB/PA: {league_avg_tb:.4f}")

    results = []
    for park, grp in df.groupby('home_team'):
        w = grp['weight']
        actual = np.average(grp['total_bases'], weights=w)
        factor = round(100 * actual / league_avg_tb, 1) if league_avg_tb > 0 else 100.0
        results.append({'park': park, 'tb_park_factor': factor, 'pa_count': len(grp)})

    out = pd.DataFrame(results)
    os.makedirs('data/processed', exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"\nSaved {len(out)} park-factor rows to {OUTPUT_PATH}")
    print("\nTop 10 TB parks:")
    print(out.sort_values('tb_park_factor', ascending=False).head(10).to_string(index=False))
    print("\nBottom 5 TB parks:")
    print(out.sort_values('tb_park_factor', ascending=False).tail(5).to_string(index=False))
    return out


if __name__ == '__main__':
    compute()
