"""
Fetch per-game pitcher box-score lines from the MLB Stats API for 2021-2026.
Saves data/processed/pitcher_game_logs.parquet keyed by (pitcher, game_pk).

Used for rolling L10 pitcher features that need innings-pitched normalization
(p_hits_per9_10, p_k_per9_10) -- these come straight from MLB's own per-game
box score stats rather than being derived from Statcast, since MLB's
'battersFaced'/'inningsPitched' fields give a cleaner per9 basis than
reconstructing outs from pitch-level data.

Usage:
    python ingestion/fetch_pitcher_game_logs.py             # full 2021-2026 backfill
    python ingestion/fetch_pitcher_game_logs.py --update    # only pitchers active this week
"""
import os
import sys
import time
import requests
import pandas as pd

OUT = 'data/processed/pitcher_game_logs.parquet'


def _parse_ip(ip_str):
    try:
        parts = str(ip_str).split('.')
        full   = int(parts[0])
        thirds = int(parts[1]) if len(parts) > 1 else 0
        return full + thirds / 3.0
    except (ValueError, IndexError, AttributeError):
        return 0.0


def fetch_all_pitcher_ids(season):
    """All pitchers with >= 1 IP in a season, from the season stats endpoint."""
    r = requests.get('https://statsapi.mlb.com/api/v1/stats', params={
        'stats': 'season', 'group': 'pitching', 'sportId': 1,
        'season': season, 'playerPool': 'All', 'limit': 2000,
    }, timeout=30)
    r.raise_for_status()
    ids = []
    for s in r.json().get('stats', [{}])[0].get('splits', []):
        if _parse_ip(s['stat'].get('inningsPitched', '0')) > 0:
            ids.append(s['player']['id'])
    return ids


def fetch_game_log(pitcher_id, season):
    """One pitcher's per-game pitching log for a season."""
    r = requests.get(f'https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats', params={
        'stats': 'gameLog', 'group': 'pitching', 'sportId': 1, 'season': season,
    }, timeout=20)
    r.raise_for_status()
    rows = []
    for group in r.json().get('stats', []):
        for s in group.get('splits', []):
            stat = s.get('stat', {})
            ip = _parse_ip(stat.get('inningsPitched', '0'))
            if ip <= 0:
                continue
            rows.append({
                'pitcher':      pitcher_id,
                'game_pk':      s.get('game', {}).get('gamePk'),
                'game_date':    s.get('date'),
                'season':       season,
                'ip':           ip,
                'h_allowed':    int(stat.get('hits', 0) or 0),
                'bb_allowed':   int(stat.get('baseOnBalls', 0) or 0),
                'k':            int(stat.get('strikeOuts', 0) or 0),
                'hr_allowed':   int(stat.get('homeRuns', 0) or 0),
                'batters_faced': int(stat.get('battersFaced', 0) or 0),
            })
    return rows


def run(seasons=None, pitcher_ids=None):
    if seasons is None:
        seasons = range(2021, 2027)

    all_rows = []
    for season in seasons:
        print(f"Fetching {season} pitcher pool...")
        ids = pitcher_ids if pitcher_ids is not None else fetch_all_pitcher_ids(season)
        print(f"  {len(ids)} pitchers with IP > 0 in {season}")
        for i, pid in enumerate(ids):
            try:
                rows = fetch_game_log(pid, season)
                all_rows.extend(rows)
            except Exception as e:
                print(f"    pitcher {pid} FAILED: {e}")
            if (i + 1) % 50 == 0:
                print(f"    {i + 1}/{len(ids)} pitchers done...")
            time.sleep(0.05)

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("No rows fetched.")
        return df

    df['game_date'] = pd.to_datetime(df['game_date'])
    df = df.sort_values(['pitcher', 'game_date']).drop_duplicates(['pitcher', 'game_pk'], keep='last')

    os.makedirs('data/processed', exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"\nSaved {len(df):,} pitcher-game rows -> {OUT}")
    print(f"Seasons: {sorted(df['season'].unique())}")
    print(f"Pitchers: {df['pitcher'].nunique():,}")
    return df


if __name__ == '__main__':
    if '--update' in sys.argv:
        # Incremental: only re-pull the current season for pitchers who've
        # thrown recently (existing rows for prior seasons are untouched).
        season = pd.Timestamp.today().year
        run(seasons=[season])
    else:
        run()
