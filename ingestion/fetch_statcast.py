from pybaseball import statcast
import pybaseball
import pandas as pd
import os

pybaseball.cache.enable()

KEEP_COLS = [
    'game_date', 'game_year', 'game_pk',
    'batter', 'pitcher', 'player_name',
    'events', 'description', 'bb_type',
    'launch_speed', 'launch_angle', 'hit_distance_sc',
    'stand', 'p_throws', 'bat_order',
    'home_team', 'away_team', 'inning_topbot',
    'estimated_woba_using_speedangle', 'estimated_slg_using_speedangle',
    'woba_value', 'babip_value', 'iso_value',
]

STORE_PATH = 'data/raw/statcast_batted_balls.parquet'

def pull_range(start, end):
    """Pull batted balls for a date range, trimmed to needed columns."""
    print(f"Pulling {start} to {end}...")
    df = statcast(start, end)
    if df is None or len(df) == 0:
        print("  No data returned.")
        return pd.DataFrame()
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols]
    df = df[df['launch_speed'].notna()]  # batted balls only
    print(f"  Got {len(df)} batted balls")
    return df

def append_and_dedupe(new_df):
    """Append new data to the permanent store, removing duplicates."""
    os.makedirs('data/raw', exist_ok=True)
    if os.path.exists(STORE_PATH):
        existing = pd.read_parquet(STORE_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    before = len(combined)
    # A batted ball is unique by game + batter + the at-bat outcome row
    combined = combined.drop_duplicates(
        subset=['game_pk', 'batter', 'game_date', 'launch_speed', 'launch_angle'],
        keep='last'
    )
    after = len(combined)
    combined.to_parquet(STORE_PATH, index=False)
    print(f"  Store now has {after} rows ({before - after} dupes removed)")
    return combined

def backfill(start_year=2021, end_year=2024):
    """One-time historical load, season by season."""
    for year in range(start_year, end_year + 1):
        df = pull_range(f'{year}-03-20', f'{year}-10-05')
        if not df.empty:
            append_and_dedupe(df)
    final = pd.read_parquet(STORE_PATH)
    print(f"\nBACKFILL DONE. Total: {len(final)} rows, seasons {sorted(final['game_year'].unique())}")

if __name__ == "__main__":
    backfill(2021, 2024)