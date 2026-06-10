"""
Fetch weather for every MLB game in the training set (historical mode)
or for today's scheduled games (forecast mode).

Uses Open-Meteo — completely free, no account or API key needed.
  Historical archive: https://archive-api.open-meteo.com
  Forecast:          https://api.open-meteo.com

Output: data/processed/weather.parquet
Columns: game_date, home_team, temp_f, wind_speed, wind_favor, is_dome,
         humidity_pct, precip_pct (forecast mode only)

--- What is wind_favor? ---
Weather services report wind direction as where the wind is COMING FROM.
For example, a "south wind" (180°) means air is flowing northward.

cf_bearing is the compass direction from home plate toward center field.
wind_favor = the component of wind blowing OUT toward the outfield (mph).
  Positive = tailwind  → ball carries farther → more home runs
  Negative = headwind  → ball dies at the wall → fewer home runs
  Zero     = crosswind or dome park

For dome parks (HOU, MIA, ARI, TEX, TB) wind is irrelevant,
so wind_speed and wind_favor are set to 0 and is_dome is set to 1.
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

# ── Stadium metadata ─────────────────────────────────────────────────────────
# cf   = compass bearing (degrees) from home plate toward center field
#        0=North, 90=East, 180=South, 270=West
# tz   = IANA timezone name for the stadium's city
# dome = 1 if the roof is almost always closed (weather irrelevant)
# name = stadium display name, shown in the web detail card
STADIUMS = {
    'ARI': {'lat': 33.4453, 'lon': -112.0668, 'cf': 315, 'tz': 'America/Phoenix',     'dome': 1, 'name': 'Chase Field'},
    'AZ':  {'lat': 33.4453, 'lon': -112.0668, 'cf': 315, 'tz': 'America/Phoenix',     'dome': 1, 'name': 'Chase Field'},
    'ATL': {'lat': 33.8908, 'lon':  -84.4678, 'cf':  15, 'tz': 'America/New_York',    'dome': 0, 'name': 'Truist Park'},
    'BAL': {'lat': 39.2838, 'lon':  -76.6217, 'cf':  50, 'tz': 'America/New_York',    'dome': 0, 'name': 'Camden Yards'},
    'BOS': {'lat': 42.3467, 'lon':  -71.0972, 'cf':  65, 'tz': 'America/New_York',    'dome': 0, 'name': 'Fenway Park'},
    'CHC': {'lat': 41.9484, 'lon':  -87.6553, 'cf':  15, 'tz': 'America/Chicago',     'dome': 0, 'name': 'Wrigley Field'},
    'CWS': {'lat': 41.8299, 'lon':  -87.6338, 'cf':   0, 'tz': 'America/Chicago',     'dome': 0, 'name': 'Rate Field'},
    'CIN': {'lat': 39.0979, 'lon':  -84.5075, 'cf':  15, 'tz': 'America/New_York',    'dome': 0, 'name': 'Great American Ball Park'},
    'CLE': {'lat': 41.4962, 'lon':  -81.6852, 'cf': 325, 'tz': 'America/New_York',    'dome': 0, 'name': 'Progressive Field'},
    'COL': {'lat': 39.7559, 'lon': -104.9942, 'cf':   5, 'tz': 'America/Denver',      'dome': 0, 'name': 'Coors Field'},
    'DET': {'lat': 42.3390, 'lon':  -83.0485, 'cf': 345, 'tz': 'America/Detroit',     'dome': 0, 'name': 'Comerica Park'},
    'HOU': {'lat': 29.7573, 'lon':  -95.3554, 'cf': 330, 'tz': 'America/Chicago',     'dome': 1, 'name': 'Daikin Park'},
    'KC':  {'lat': 39.0517, 'lon':  -94.4803, 'cf':   5, 'tz': 'America/Chicago',     'dome': 0, 'name': 'Kauffman Stadium'},
    'LAA': {'lat': 33.8003, 'lon': -117.8827, 'cf': 335, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Angel Stadium'},
    'LAD': {'lat': 34.0739, 'lon': -118.2400, 'cf':   0, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Dodger Stadium'},
    'MIA': {'lat': 25.7781, 'lon':  -80.2197, 'cf':  20, 'tz': 'America/New_York',    'dome': 1, 'name': 'loanDepot Park'},
    'MIL': {'lat': 43.0280, 'lon':  -87.9712, 'cf': 345, 'tz': 'America/Chicago',     'dome': 0, 'name': 'American Family Field'},
    'MIN': {'lat': 44.9817, 'lon':  -93.2784, 'cf': 320, 'tz': 'America/Chicago',     'dome': 0, 'name': 'Target Field'},
    'NYM': {'lat': 40.7571, 'lon':  -73.8458, 'cf':   0, 'tz': 'America/New_York',    'dome': 0, 'name': 'Citi Field'},
    'NYY': {'lat': 40.8296, 'lon':  -73.9262, 'cf':  20, 'tz': 'America/New_York',    'dome': 0, 'name': 'Yankee Stadium'},
    'OAK': {'lat': 37.7516, 'lon': -122.2005, 'cf': 335, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Sutter Health Park'},
    'ATH': {'lat': 38.5802, 'lon': -121.5000, 'cf':   5, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Sutter Health Park'},
    'PHI': {'lat': 39.9056, 'lon':  -75.1666, 'cf':  10, 'tz': 'America/New_York',    'dome': 0, 'name': 'Citizens Bank Park'},
    'PIT': {'lat': 40.4469, 'lon':  -80.0057, 'cf': 355, 'tz': 'America/New_York',    'dome': 0, 'name': 'PNC Park'},
    'SD':  {'lat': 32.7076, 'lon': -117.1570, 'cf': 320, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Petco Park'},
    'SF':  {'lat': 37.7786, 'lon': -122.3893, 'cf':  55, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'Oracle Park'},
    'SEA': {'lat': 47.5914, 'lon': -122.3325, 'cf': 350, 'tz': 'America/Los_Angeles', 'dome': 0, 'name': 'T-Mobile Park'},
    'STL': {'lat': 38.6226, 'lon':  -90.1928, 'cf': 350, 'tz': 'America/Chicago',     'dome': 0, 'name': 'Busch Stadium'},
    'TB':  {'lat': 27.7683, 'lon':  -82.6534, 'cf':  10, 'tz': 'America/New_York',    'dome': 1, 'name': 'Tropicana Field'},
    'TEX': {'lat': 32.7510, 'lon':  -97.0832, 'cf':   5, 'tz': 'America/Chicago',     'dome': 1, 'name': 'Globe Life Field'},
    'TOR': {'lat': 43.6414, 'lon':  -79.3894, 'cf':  30, 'tz': 'America/Toronto',     'dome': 0, 'name': 'Rogers Centre'},
    'WSH': {'lat': 38.8730, 'lon':  -77.0074, 'cf':  40, 'tz': 'America/New_York',    'dome': 0, 'name': 'Nationals Park'},
}


# ── Core math ─────────────────────────────────────────────────────────────────

def calc_wind_favor(wind_speed, wind_dir, cf_bearing):
    """
    Return the component of wind blowing toward the outfield, in mph.

    Works on scalars, numpy arrays, or pandas Series (vectorized).

    wind_speed  : speed in mph
    wind_dir    : where wind is coming FROM, degrees (meteorological convention)
    cf_bearing  : compass direction from home plate toward center field, degrees

    Example: Wrigley Field (cf=15°). South wind (wind_dir=180) → air moves north.
      going_to = 0°, diff vs cf=15° → 15° → cos(15°)=0.97 → nearly full tailwind.
    """
    going_to = (wind_dir + 180) % 360
    diff = np.abs(going_to - cf_bearing)
    diff = np.where(diff > 180, 360 - diff, diff)
    return wind_speed * np.cos(np.radians(diff))


# ── Open-Meteo API call ────────────────────────────────────────────────────────

def _fetch_daily(lat, lon, tz, start_date=None, end_date=None, forecast=False):
    """
    One Open-Meteo call. Returns a DataFrame with daily rows:
      game_date (Timestamp, midnight), temp_f, wind_speed (mph), wind_dir (degrees from),
      humidity_pct (%), precip_pct (% chance of precipitation, forecast mode only)
    """
    if forecast:
        url = 'https://api.open-meteo.com/v1/forecast'
        params = dict(
            latitude=lat, longitude=lon,
            daily='temperature_2m_max,windspeed_10m_max,winddirection_10m_dominant,'
                  'relative_humidity_2m_max,precipitation_probability_max',
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            timezone=tz,
            forecast_days=7,
        )
    else:
        url = 'https://archive-api.open-meteo.com/v1/archive'
        params = dict(
            latitude=lat, longitude=lon,
            start_date=start_date, end_date=end_date,
            daily='temperature_2m_max,windspeed_10m_max,winddirection_10m_dominant',
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            timezone=tz,
        )

    for attempt in range(2):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429 and attempt == 0:
            print("    Rate limited (429) -- waiting 35 seconds then retrying...")
            time.sleep(35)
            continue
        resp.raise_for_status()
        break

    d = resp.json()['daily']

    # pd.to_numeric(..., errors='coerce') turns any null/None values into NaN
    out = pd.DataFrame({
        'game_date':  pd.to_datetime(d['time']).normalize(),
        'temp_f':     pd.to_numeric(d['temperature_2m_max'],          errors='coerce'),
        'wind_speed': pd.to_numeric(d['windspeed_10m_max'],           errors='coerce'),
        'wind_dir':   pd.to_numeric(d['winddirection_10m_dominant'],  errors='coerce'),
    })
    if forecast:
        out['humidity_pct'] = pd.to_numeric(d.get('relative_humidity_2m_max'), errors='coerce')
        out['precip_pct']   = pd.to_numeric(d.get('precipitation_probability_max'), errors='coerce')
    else:
        out['humidity_pct'] = np.nan
        out['precip_pct']   = np.nan
    return out


# ── Public functions ───────────────────────────────────────────────────────────

def fetch_historical(game_team_df):
    """
    Fetch weather for every (game_date, home_team) pair in game_team_df.

    Makes one API call per team (covering its full date range) — about 30 calls
    total, very fast. A 0.25-second polite delay is added between calls.

    Parameters
    ----------
    game_team_df : DataFrame with columns ['game_date', 'home_team']

    Returns
    -------
    DataFrame with columns:
        game_date, home_team, temp_f, wind_speed, wind_favor, is_dome
    """
    OUT = 'data/processed/weather.parquet'
    gdf = game_team_df.copy()
    gdf['game_date'] = pd.to_datetime(gdf['game_date']).dt.normalize()
    teams = sorted(gdf['home_team'].unique())

    # Resume support: skip teams already present in the saved file
    already_done = set()
    existing_df = None
    if os.path.exists(OUT):
        existing_df = pd.read_parquet(OUT)
        already_done = set(existing_df['home_team'].unique())
        print(f"  Resuming: {len(already_done)} teams already saved, skipping them.")

    results = []

    for i, team in enumerate(teams, 1):
        meta = STADIUMS.get(team)
        if meta is None:
            print(f"  [{i}/{len(teams)}] {team}: no stadium entry -- skipping")
            continue

        if team in already_done:
            print(f"  [{i}/{len(teams)}] {team}: already saved -- skipping")
            continue

        dates = gdf.loc[gdf['home_team'] == team, 'game_date']
        start = dates.min().strftime('%Y-%m-%d')
        end   = dates.max().strftime('%Y-%m-%d')
        print(f"  [{i}/{len(teams)}] {team}: {len(dates)} games  {start} -> {end}")

        try:
            daily = _fetch_daily(meta['lat'], meta['lon'], meta['tz'], start, end)

            # Keep only rows that correspond to actual game days
            game_date_set = set(dates)
            daily = daily[daily['game_date'].isin(game_date_set)].copy()

            if meta['dome']:
                # Wind doesn't matter inside a dome
                daily['wind_speed'] = 0.0
                daily['wind_favor'] = 0.0
            else:
                valid = daily['wind_dir'].notna()
                daily.loc[valid, 'wind_favor'] = calc_wind_favor(
                    daily.loc[valid, 'wind_speed'].to_numpy(dtype=float),
                    daily.loc[valid, 'wind_dir'].to_numpy(dtype=float),
                    meta['cf'],
                )
                # If wind direction is missing (rare), treat as no wind effect
                daily.loc[~valid, 'wind_favor'] = 0.0

            daily['is_dome']   = meta['dome']
            daily['home_team'] = team
            results.append(
                daily[['game_date', 'home_team', 'temp_f', 'wind_speed', 'wind_favor', 'is_dome']]
            )

        except Exception as e:
            print(f"    ERROR: {e}")

        time.sleep(1.5)  # polite rate-limiting for the free API

    new_df = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    if existing_df is not None and not new_df.empty:
        return pd.concat([existing_df, new_df], ignore_index=True)
    elif existing_df is not None:
        return existing_df
    return new_df


def fetch_forecast(target_date_str, home_teams):
    """
    Fetch forecast weather for a specific date and list of home teams.

    Called by the daily prediction runner (Priority 3) to get today's
    weather before scoring the model.

    Parameters
    ----------
    target_date_str : str   e.g. '2026-06-07'
    home_teams      : list  e.g. ['NYY', 'BOS', 'LAD']

    Returns
    -------
    DataFrame with columns:
        game_date, home_team, temp_f, wind_speed, wind_favor, is_dome,
        humidity_pct, precip_pct
    """
    target = pd.Timestamp(target_date_str).normalize()
    rows = []

    for team in home_teams:
        meta = STADIUMS.get(team)
        if meta is None:
            print(f"  {team}: no stadium entry — skipping")
            continue
        try:
            daily = _fetch_daily(meta['lat'], meta['lon'], meta['tz'], forecast=True)
            day   = daily[daily['game_date'] == target]
            if day.empty:
                print(f"  {team}: no forecast row for {target_date_str}")
                continue

            r  = day.iloc[0]
            ws = float(r['wind_speed']) if pd.notna(r['wind_speed']) else 0.0
            wd = float(r['wind_dir'])   if pd.notna(r['wind_dir'])   else None
            wf = 0.0 if (meta['dome'] or wd is None) else float(
                calc_wind_favor(ws, wd, meta['cf'])
            )

            rows.append({
                'game_date':  target,
                'home_team':  team,
                'temp_f':     float(r['temp_f']) if pd.notna(r['temp_f']) else np.nan,
                'wind_speed': 0.0 if meta['dome'] else ws,
                'wind_favor': wf,
                'is_dome':    meta['dome'],
                'humidity_pct': float(r['humidity_pct']) if pd.notna(r['humidity_pct']) else np.nan,
                'precip_pct':   float(r['precip_pct'])   if pd.notna(r['precip_pct'])   else np.nan,
            })
        except Exception as e:
            print(f"  {team}: ERROR — {e}")
        time.sleep(0.1)

    return pd.DataFrame(rows)


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    STORE = 'data/raw/statcast_batted_balls.parquet'
    OUT   = 'data/processed/weather.parquet'

    mode = sys.argv[1] if len(sys.argv) > 1 else 'historical'

    if mode == 'historical':
        print("Reading game list from statcast store...")
        store      = pd.read_parquet(STORE, columns=['game_date', 'home_team'])
        game_teams = store[['game_date', 'home_team']].drop_duplicates()
        print(f"Found {len(game_teams):,} unique (game_date, home_team) pairs\n")

        print("Fetching weather from Open-Meteo (free, no API key needed)...")
        print("This makes ~30 API calls, one per team.  Should take under a minute.\n")
        weather = fetch_historical(game_teams)

        os.makedirs('data/processed', exist_ok=True)
        weather.to_parquet(OUT, index=False)
        print(f"\nSaved {len(weather):,} rows to {OUT}")
        print("\nSummary statistics:")
        print(weather[['temp_f', 'wind_speed', 'wind_favor']].describe().round(1).to_string())
        dome_pct = weather['is_dome'].mean() * 100
        print(f"\nDome games: {dome_pct:.1f}% of rows (wind_favor=0 for these)")

    elif mode == 'forecast':
        # Called by the daily runner, e.g.:
        #   python ingestion/fetch_weather.py forecast 2026-06-07 NYY,BOS,LAD
        if len(sys.argv) < 4:
            print("Usage: python ingestion/fetch_weather.py forecast YYYY-MM-DD TEAM1,TEAM2,...")
            sys.exit(1)
        date_str = sys.argv[2]
        teams    = sys.argv[3].split(',')
        print(f"Fetching forecast for {date_str}: {teams}")
        df = fetch_forecast(date_str, teams)
        print(df.to_string(index=False))

    else:
        print(f"Unknown mode: '{mode}'.  Use 'historical' or 'forecast'.")
        sys.exit(1)
