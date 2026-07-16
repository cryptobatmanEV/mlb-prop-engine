"""
Rolling L10 innings-pitched-normalized pitcher features from MLB Stats API
game logs (data/processed/pitcher_game_logs.parquet -- see
ingestion/fetch_pitcher_game_logs.py). These need a real innings-pitched
basis (per9 rates), which the Statcast PA-outcome store can't give cleanly
without reconstructing outs from pitch data -- MLB's own box score IP field
is the correct source.

Output: data/processed/pitcher_game_log_features.parquet
  p_hits_per9_10, p_hr_per9_10, p_k_per9_10, p_k_rate_10 (K / battersFaced)
"""
import pandas as pd
import os

STORE_PATH  = 'data/processed/pitcher_game_logs.parquet'
OUTPUT_PATH = 'data/processed/pitcher_game_log_features.parquet'

W = 10
MIN_PERIODS = 4


def build():
    print("Loading pitcher game logs...")
    df = pd.read_parquet(STORE_PATH)
    df = df.sort_values(['pitcher', 'game_date'])

    print("Computing trailing rolling features (shift(1), no leakage)...")
    out = []
    for pid, sub in df.groupby('pitcher'):
        sub = sub.sort_values('game_date').copy()
        r = sub.shift(1).rolling(W, min_periods=MIN_PERIODS)

        sum_ip = r['ip'].sum()
        sub['p_hits_per9_10'] = r['h_allowed'].sum() / sum_ip * 9
        sub['p_hr_per9_10']   = r['hr_allowed'].sum() / sum_ip * 9
        sub['p_k_per9_10']    = r['k'].sum() / sum_ip * 9
        sub['p_k_rate_10']    = r['k'].sum() / r['batters_faced'].sum()

        out.append(sub)

    result = pd.concat(out, ignore_index=True)
    os.makedirs('data/processed', exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(result):,} pitcher-game rows to {OUTPUT_PATH}")

    ready = result[result['p_k_per9_10'].notna()]
    print(f"Rows with full features: {len(ready):,}")
    print(f"p_hits_per9_10 range: {ready['p_hits_per9_10'].min():.2f} - {ready['p_hits_per9_10'].max():.2f}")
    print(f"p_k_per9_10 range:    {ready['p_k_per9_10'].min():.2f} - {ready['p_k_per9_10'].max():.2f}")
    print(f"p_k_rate_10 range:    {ready['p_k_rate_10'].min():.3f} - {ready['p_k_rate_10'].max():.3f}")
    print(ready[['game_date', 'pitcher', 'p_hits_per9_10', 'p_k_per9_10', 'p_k_rate_10']]
          .head(8).to_string(index=False))


if __name__ == '__main__':
    build()
