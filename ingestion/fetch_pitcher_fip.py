"""
Fetch pitcher season FIP from MLB Stats API for 2020-2026.
Saves data/processed/pitcher_fip.parquet keyed by (pitcher MLBAM ID, season).

FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + 3.10

Used in model training (previous year's FIP) and prediction (current year's FIP).

Usage:
    python ingestion/fetch_pitcher_fip.py
"""

import os
import time
import requests
import pandas as pd

OUT = 'data/processed/pitcher_fip.parquet'
MIN_IP = 10.0  # minimum innings pitched to keep (excludes pure relievers with 1-2 IP)


def _parse_ip(ip_str):
    """Convert MLB's '180.2' notation (full innings + thirds) to decimal innings."""
    try:
        parts = str(ip_str).split('.')
        full   = int(parts[0])
        thirds = int(parts[1]) if len(parts) > 1 else 0
        return full + thirds / 3.0
    except (ValueError, IndexError, AttributeError):
        return 0.0


def fetch_year(year):
    """Fetch all pitcher season stats for one year, return list of row dicts."""
    r = requests.get(
        'https://statsapi.mlb.com/api/v1/stats',
        params={
            'stats':      'season',
            'group':      'pitching',
            'season':     year,
            'playerPool': 'All',
            'sportId':    1,
            'limit':      2000,
        },
        timeout=30,
    )
    r.raise_for_status()

    rows = []
    for entry in r.json().get('stats', [{}])[0].get('splits', []):
        player = entry.get('player', {})
        stat   = entry.get('stat', {})
        pid    = player.get('id')
        ip     = _parse_ip(stat.get('inningsPitched', '0'))
        if not pid or ip < MIN_IP:
            continue
        hr  = int(stat.get('homeRuns',     0) or 0)
        bb  = int(stat.get('baseOnBalls',  0) or 0)
        hbp = int(stat.get('hitByPitch',   0) or 0)
        k   = int(stat.get('strikeOuts',   0) or 0)
        fip = (13 * hr + 3 * (bb + hbp) - 2 * k) / ip + 3.10
        rows.append({'pitcher': int(pid), 'season': year, 'p_fip': round(fip, 3)})
    return rows


def run():
    all_rows = []
    for year in range(2020, 2027):
        print(f"  Fetching {year}...", end=' ', flush=True)
        try:
            rows = fetch_year(year)
            print(f"{len(rows)} pitchers")
            all_rows.extend(rows)
        except Exception as e:
            print(f"FAILED: {e}")
        time.sleep(0.4)

    df = pd.DataFrame(all_rows)
    os.makedirs('data/processed', exist_ok=True)
    df.to_parquet(OUT, index=False)

    print(f"\nSaved {len(df)} pitcher-season rows -> {OUT}")
    if not df.empty:
        print(f"FIP range: {df['p_fip'].min():.2f} – {df['p_fip'].max():.2f}")
        print(f"Seasons:   {sorted(df['season'].unique())}")
    return df


if __name__ == '__main__':
    run()
