import pandas as pd
import numpy as np
import os

STORE_PATH = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/park_factors.csv'

# Recent years weighted more heavily (3-year rolling, recency-biased)
YEAR_WEIGHTS = {0: 1.0, 1: 0.7, 2: 0.5}  # 0 = most recent year, etc.

def compute_park_factors(reference_year=None):
    """
    Compute handedness-split HR park factors from our own Statcast data.
    Method: compare actual HR rate at each park vs expected HR rate
    (based on each batted ball's exit velo + launch angle), controlled
    for batter handedness. 100 = neutral, 115 = 15% HR boost.
    """
    print("Loading batted-ball store...")
    df = pd.read_parquet(STORE_PATH)

    # Determine the 3 most recent seasons to use
    seasons = sorted(df['game_year'].unique())
    if reference_year is None:
        reference_year = max(seasons)
    use_years = [y for y in seasons if reference_year - 2 <= y <= reference_year]
    print(f"Using seasons: {use_years} (reference {reference_year})")

    df = df[df['game_year'].isin(use_years)].copy()

    # Flag actual home runs
    df['is_hr'] = (df['events'] == 'home_run').astype(int)

    # Expected HR probability for each batted ball, from its xSLG/xwOBA signature.
    # We bucket by exit velocity + launch angle and use the league-wide HR rate
    # in that bucket as the "expected" baseline.
    df = df[df['launch_speed'].notna() & df['launch_angle'].notna()]
    df['ev_bucket'] = (df['launch_speed'] // 2 * 2).astype(int)
    df['la_bucket'] = (df['launch_angle'] // 3 * 3).astype(int)

    # League-wide expected HR rate per (handedness, ev_bucket, la_bucket)
    league = df.groupby(['stand', 'ev_bucket', 'la_bucket'])['is_hr'].mean()
    league.name = 'expected_hr'
    df = df.merge(league, on=['stand', 'ev_bucket', 'la_bucket'], how='left')

    # Recency weight per row
    df['weight'] = df['game_year'].map(
        lambda y: YEAR_WEIGHTS.get(reference_year - y, 0.3)
    )

    # Park factor = weighted actual HR / weighted expected HR, by park + handedness
    results = []
    for (park, hand), grp in df.groupby(['home_team', 'stand']):
        w = grp['weight']
        actual = np.average(grp['is_hr'], weights=w)
        expected = np.average(grp['expected_hr'], weights=w)
        if expected > 0:
            factor = round(100 * actual / expected, 1)
        else:
            factor = 100.0
        results.append({
            'park': park,
            'bat_side': hand,
            'hr_park_factor': factor,
            'batted_balls': len(grp),
        })

    out = pd.DataFrame(results)

    # Also compute an overall (both-handed) factor per park
    overall = []
    for park, grp in df.groupby('home_team'):
        w = grp['weight']
        actual = np.average(grp['is_hr'], weights=w)
        expected = np.average(grp['expected_hr'], weights=w)
        factor = round(100 * actual / expected, 1) if expected > 0 else 100.0
        overall.append({'park': park, 'bat_side': 'ALL',
                        'hr_park_factor': factor, 'batted_balls': len(grp)})

    out = pd.concat([out, pd.DataFrame(overall)], ignore_index=True)

    os.makedirs('data/processed', exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"\nSaved {len(out)} park-factor rows to {OUTPUT_PATH}")
    print("\nTop 10 HR parks (both-handed):")
    top = out[out['bat_side'] == 'ALL'].sort_values('hr_park_factor', ascending=False)
    print(top.head(10).to_string(index=False))
    print("\nBottom 5 HR parks (both-handed):")
    print(top.tail(5).to_string(index=False))
    return out

if __name__ == "__main__":
    compute_park_factors()