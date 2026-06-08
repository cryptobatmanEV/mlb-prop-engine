import pandas as pd
import os

STORE   = 'data/raw/statcast_batted_balls.parquet'
BATTER  = 'data/processed/batter_features.parquet'
PITCHER = 'data/processed/pitcher_features.parquet'
PARK    = 'data/processed/park_factors.csv'
WEATHER = 'data/processed/weather.parquet'
PLATOON = 'data/processed/platoon_features.parquet'
OUT     = 'data/processed/training_dataset.parquet'

def build():
    print("Loading sources...")
    store = pd.read_parquet(STORE, columns=['batter','pitcher','game_pk','game_date','home_team','stand'])
    store['game_date'] = pd.to_datetime(store['game_date'])
    batter = pd.read_parquet(BATTER)
    pitcher = pd.read_parquet(PITCHER)
    park = pd.read_csv(PARK)

    print("Finding primary opposing pitcher per batter-game...")
    matchup = (store.groupby(['batter','game_pk','pitcher'])
               .size().reset_index(name='n')
               .sort_values('n', ascending=False)
               .drop_duplicates(['batter','game_pk']))
    matchup = matchup[['batter','game_pk','pitcher']]

    print("Finding home_team per game...")
    game_park = store[['game_pk','home_team']].drop_duplicates('game_pk')

    print("Joining batter features...")
    df = batter.merge(matchup, on=['batter','game_pk'], how='left')
    df = df.merge(game_park, on='game_pk', how='left')

    print("Joining opposing pitcher features...")
    pcols = ['pitcher','game_pk'] + [c for c in pitcher.columns if c.startswith('p_')]
    df = df.merge(pitcher[pcols], on=['pitcher','game_pk'], how='left')

    print("Joining park factors (handedness-split)...")
    park_split = park[park['bat_side'] != 'ALL'][['park','bat_side','hr_park_factor']]
    df = df.merge(park_split, left_on=['home_team','stand'],
                  right_on=['park','bat_side'], how='left')

    print("Joining weather features...")
    if os.path.exists(WEATHER):
        weather = pd.read_parquet(WEATHER)
        weather['game_date'] = pd.to_datetime(weather['game_date'])
        df = df.merge(
            weather[['game_date', 'home_team', 'temp_f', 'wind_speed', 'wind_favor', 'is_dome']],
            on=['game_date', 'home_team'], how='left'
        )
        missing = df['temp_f'].isna().sum()
        print(f"  Weather joined. Rows missing weather: {missing:,} ({missing/len(df):.1%})")
    else:
        print("  WARNING: weather.parquet not found — skipping weather features.")
        print("  To add them: python ingestion/fetch_weather.py historical")
        df['temp_f'] = float('nan')
        df['wind_speed'] = float('nan')
        df['wind_favor'] = float('nan')
        df['is_dome'] = float('nan')

    print("Joining platoon split features...")
    if os.path.exists(PLATOON):
        platoon = pd.read_parquet(PLATOON)
        platoon_cols = [c for c in platoon.columns if c not in ('batter', 'game_pk', 'game_date')]
        df = df.merge(platoon[['batter', 'game_pk'] + platoon_cols],
                      on=['batter', 'game_pk'], how='left')
        has_any = df['hr_per_bb_vs_R_15'].notna().sum()
        print(f"  Platoon joined. vs_R_15 populated: {has_any:,} / {len(df):,} rows ({has_any/len(df):.1%})")
    else:
        print("  WARNING: platoon_features.parquet not found — skipping.")
        print("  To add them: python features/platoon_features.py")

    # Binary-encode batter and pitcher handedness so LightGBM can use them
    # stand_R = 1 if right-handed batter, 0 if left-handed
    # p_throws_R = 1 if right-handed pitcher, 0 if left-handed
    df['stand_R']    = (df['stand']    == 'R').astype(int)
    df['p_throws_R'] = (df['p_throws'] == 'R').astype(int)

    df['target_hr'] = (df['hr'] > 0).astype(int)

    df = df[df['barrel_pct_15'].notna() & df['p_barrel_pct_allowed_10'].notna()].copy()

    os.makedirs('data/processed', exist_ok=True)
    df.to_parquet(OUT, index=False)

    print(f"\nSaved {len(df)} training rows to {OUT}")
    print(f"HR rate in dataset: {df['target_hr'].mean():.3%}")
    feat = [c for c in df.columns if '_15' in c or '_30' in c or c.startswith('p_') or c=='hr_park_factor']
    print(f"Feature count: {len(feat)}")
    print("\nColumns:")
    print(list(df.columns))

build()