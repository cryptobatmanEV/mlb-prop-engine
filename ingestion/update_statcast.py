from pybaseball import statcast
import pybaseball
import pandas as pd
import os
from datetime import date, timedelta

pybaseball.cache.enable()

STORE_PATH = 'data/raw/statcast_batted_balls.parquet'

# NOTE: this store holds one row per completed plate appearance (events.notna()),
# not just batted balls -- see fetch_statcast.py for details.
KEEP_COLS = [
    'game_date', 'game_year', 'game_pk', 'at_bat_number',
    'batter', 'pitcher', 'player_name',
    'events', 'description', 'bb_type',
    'launch_speed', 'launch_angle', 'hit_distance_sc',
    'stand', 'p_throws',
    'home_team', 'away_team', 'inning_topbot',
    'estimated_ba_using_speedangle',
    'estimated_woba_using_speedangle', 'estimated_slg_using_speedangle',
    'woba_value', 'babip_value', 'iso_value',
]

def get_last_date():
    """Find the most recent game date already in the store."""
    if not os.path.exists(STORE_PATH):
        print("No store found. Run fetch_statcast.py backfill first.")
        return None
    df = pd.read_parquet(STORE_PATH, columns=['game_date'])
    last = pd.to_datetime(df['game_date']).max().date()
    print(f"Latest game in store: {last}")
    return last

def update():
    """Pull only games since the last update and append them."""
    last = get_last_date()
    if last is None:
        return

    # Start the day after our latest data, end today
    start = (last + timedelta(days=1)).isoformat()
    end = date.today().isoformat()

    if start > end:
        print("Store is already current. Nothing to pull.")
        return

    print(f"Pulling new games: {start} to {end}...")
    df = statcast(start, end)

    if df is None or len(df) == 0:
        print("No new games found.")
        return

    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols]
    df = df[df['events'].notna()]
    print(f"  New plate appearances: {len(df)}")

    existing = pd.read_parquet(STORE_PATH)
    combined = pd.concat([existing, df], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=['game_pk', 'batter', 'at_bat_number'],
        keep='last'
    )
    after = len(combined)
    combined.to_parquet(STORE_PATH, index=False)
    print(f"  Store updated: {after} rows ({after - before + len(df)} genuinely new)")

if __name__ == "__main__":
    update()