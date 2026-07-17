"""
Hits park factor: how many hits a park produces per plate appearance
relative to league average, recency-weighted (same 3-year weighting scheme
as features/park_factors.py's HR park factor and features/park_tb_factor.py's
TB park factor).

100 = neutral, 110 = 10% more hits than average at this park.

Usage:
    python features/park_hit_factor.py
"""
import pandas as pd
import numpy as np
import os

STORE_PATH  = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/park_hit_factor.csv'

YEAR_WEIGHTS = {0: 1.0, 1: 0.7, 2: 0.5}

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

    df['is_hit'] = df['events'].isin(HIT_EVENTS).astype(int)
    df['weight'] = df['game_year'].map(lambda y: YEAR_WEIGHTS.get(reference_year - y, 0.3))

    league_avg_hit = np.average(df['is_hit'], weights=df['weight'])
    print(f"League-average H/PA: {league_avg_hit:.4f}")

    results = []
    for park, grp in df.groupby('home_team'):
        w = grp['weight']
        actual = np.average(grp['is_hit'], weights=w)
        factor = round(100 * actual / league_avg_hit, 1) if league_avg_hit > 0 else 100.0
        results.append({'park': park, 'hit_park_factor': factor, 'pa_count': len(grp)})

    out = pd.DataFrame(results)
    os.makedirs('data/processed', exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"\nSaved {len(out)} park-factor rows to {OUTPUT_PATH}")
    print("\nTop 10 Hit parks:")
    print(out.sort_values('hit_park_factor', ascending=False).head(10).to_string(index=False))
    print("\nBottom 5 Hit parks:")
    print(out.sort_values('hit_park_factor', ascending=False).tail(5).to_string(index=False))
    return out


if __name__ == '__main__':
    compute()
