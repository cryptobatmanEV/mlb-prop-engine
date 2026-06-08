import pandas as pd
import os

STORE_PATH = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/batter_features.parquet'

def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()

    df['is_hr'] = (df['events'] == 'home_run').astype(int)
    df['is_barrel'] = ((df['launch_speed'] >= 98) & (df['launch_angle'] >= 26) & (df['launch_angle'] <= 30)).astype(int)
    df['is_hard_hit'] = (df['launch_speed'] >= 95).astype(int)
    df['is_fly_ball'] = (df['bb_type'] == 'fly_ball').astype(int)

    print("Aggregating to batter-game level...")
    g = df.groupby(['batter', 'game_pk', 'game_date', 'stand']).agg(
        batted_balls=('is_hr', 'size'),
        hr=('is_hr', 'sum'),
        barrels=('is_barrel', 'sum'),
        hard_hits=('is_hard_hit', 'sum'),
        fly_balls=('is_fly_ball', 'sum'),
        avg_ev=('launch_speed', 'mean'),
        xwoba=('estimated_woba_using_speedangle', 'mean'),
        xslg=('estimated_slg_using_speedangle', 'mean'),
    ).reset_index()
    g = g.sort_values(['batter', 'game_date'])

    print("Computing trailing rolling features...")
    out = []
    for bid, sub in g.groupby('batter'):
        sub = sub.sort_values('game_date').copy()
        for w in [15, 30]:
            r = sub.shift(1).rolling(w, min_periods=5)
            sub[f'barrel_pct_{w}'] = r['barrels'].sum() / r['batted_balls'].sum()
            sub[f'hardhit_pct_{w}'] = r['hard_hits'].sum() / r['batted_balls'].sum()
            sub[f'flyball_pct_{w}'] = r['fly_balls'].sum() / r['batted_balls'].sum()
            sub[f'hr_per_bb_{w}'] = r['hr'].sum() / r['batted_balls'].sum()
            sub[f'avg_ev_{w}'] = sub['avg_ev'].shift(1).rolling(w, min_periods=5).mean()
            sub[f'xwoba_{w}'] = sub['xwoba'].shift(1).rolling(w, min_periods=5).mean()
            sub[f'xslg_{w}'] = sub['xslg'].shift(1).rolling(w, min_periods=5).mean()
        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result)} batter-game rows to {OUTPUT_PATH}")
    ready = result[result['barrel_pct_15'].notna()]
    print(f"Rows with full features: {len(ready)}")
    print(ready[['game_date','batter','barrel_pct_15','hardhit_pct_15','hr_per_bb_30']].head(8).to_string(index=False))

build()