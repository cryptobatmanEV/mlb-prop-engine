import pandas as pd
import os

STORE_PATH = 'data/raw/statcast_batted_balls.parquet'
OUTPUT_PATH = 'data/processed/pitcher_features.parquet'

def build():
    print("Loading store...")
    df = pd.read_parquet(STORE_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()

    df['is_hr'] = (df['events'] == 'home_run').astype(int)
    df['is_barrel'] = ((df['launch_speed'] >= 98) & (df['launch_angle'] >= 26) & (df['launch_angle'] <= 30)).astype(int)
    df['is_hard_hit'] = (df['launch_speed'] >= 95).astype(int)
    df['is_fly_ball'] = (df['bb_type'] == 'fly_ball').astype(int)

    print("Aggregating to pitcher-game level...")
    g = df.groupby(['pitcher', 'game_pk', 'game_date', 'p_throws']).agg(
        batted_balls=('is_hr', 'size'),
        hr_allowed=('is_hr', 'sum'),
        barrels_allowed=('is_barrel', 'sum'),
        hard_hits_allowed=('is_hard_hit', 'sum'),
        fly_balls_allowed=('is_fly_ball', 'sum'),
        avg_ev_allowed=('launch_speed', 'mean'),
        xwoba_allowed=('estimated_woba_using_speedangle', 'mean'),
        xslg_allowed=('estimated_slg_using_speedangle', 'mean'),
    ).reset_index()
    g = g.sort_values(['pitcher', 'game_date'])

    print("Computing trailing rolling features...")
    out = []
    for pid, sub in g.groupby('pitcher'):
        sub = sub.sort_values('game_date').copy()
        for w in [10, 20]:
            r = sub.shift(1).rolling(w, min_periods=4)
            sub[f'p_barrel_pct_allowed_{w}'] = r['barrels_allowed'].sum() / r['batted_balls'].sum()
            sub[f'p_hardhit_pct_allowed_{w}'] = r['hard_hits_allowed'].sum() / r['batted_balls'].sum()
            sub[f'p_flyball_pct_allowed_{w}'] = r['fly_balls_allowed'].sum() / r['batted_balls'].sum()
            sub[f'p_hr_per_bb_allowed_{w}'] = r['hr_allowed'].sum() / r['batted_balls'].sum()
            sub[f'p_avg_ev_allowed_{w}'] = sub['avg_ev_allowed'].shift(1).rolling(w, min_periods=4).mean()
            sub[f'p_xslg_allowed_{w}'] = sub['xslg_allowed'].shift(1).rolling(w, min_periods=4).mean()
        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result)} pitcher-game rows to {OUTPUT_PATH}")
    ready = result[result['p_barrel_pct_allowed_10'].notna()]
    print(f"Rows with full features: {len(ready)}")
    print(ready[['game_date','pitcher','p_barrel_pct_allowed_10','p_hr_per_bb_allowed_20']].head(8).to_string(index=False))

build()