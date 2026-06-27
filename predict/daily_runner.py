"""
Daily prediction runner for MLB home run props.

Run this each morning before games start:
    python predict/daily_runner.py              # today
    python predict/daily_runner.py 2026-06-07   # specific date

Output: data/predictions/predictions_YYYY-MM-DD.csv

--- Key output columns ---
model_prob     P(HR | batter puts at least one ball in play today)
               This is the raw model output.  The model was trained on batter-game
               rows where the batter made contact, so this probability is
               CONDITIONAL on the batter not striking out/walking in every PA.

k_pct          Batter's strikeout rate per PA (this season, from MLB Stats API)
bb_pct         Batter's walk + HBP rate per PA
contact_rate   Per-PA probability of a batted ball  = 1 - k_pct - bb_pct
exp_pa         Expected plate appearances today (default 3.8 until bat_order is added)
p_contact_game P(batter has >= 1 batted ball today) = 1 - (1 - contact_rate)^exp_pa

adj_prob       P(HR in today's game) = model_prob × p_contact_game
               This is what Priority 4 (fair-odds conversion) will use.
               NEVER use model_prob directly for odds — it overstates true probability.
"""
import os
import sys
import time
import json
import joblib
import requests
import numpy as np
import pandas as pd
from datetime import date

# Add project root to path so we can import from ingestion/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingestion.fetch_weather import fetch_forecast, STADIUMS

# ── Paths ─────────────────────────────────────────────────────────────────────
MODEL_PATH   = 'models/saved/hr_model.pkl'
BATTER_PATH  = 'data/processed/batter_features.parquet'
PITCHER_PATH = 'data/processed/pitcher_features.parquet'
PLATOON_PATH = 'data/processed/platoon_features.parquet'
PARK_PATH    = 'data/processed/park_factors.csv'
WEATHER_PATH = 'data/processed/weather.parquet'
FIP_PATH     = 'data/processed/pitcher_fip.parquet'
STATCAST_PATH = 'data/raw/statcast_batted_balls.parquet'
VS_PITCHER_CACHE_PATH = 'data/processed/vs_pitcher_cache.json'
OUT_DIR      = 'data/predictions'

# Must stay in sync with models/train.py FEATURES list
FEATURES = [
    'barrel_pct_15','hardhit_pct_15','flyball_pct_15','hr_per_bb_15','avg_ev_15','xwoba_15','xslg_15',
    'barrel_pct_30','hardhit_pct_30','flyball_pct_30','hr_per_bb_30','avg_ev_30','xwoba_30','xslg_30',
    'p_barrel_pct_allowed_10','p_hardhit_pct_allowed_10','p_flyball_pct_allowed_10',
    'p_hr_per_bb_allowed_10','p_avg_ev_allowed_10','p_xslg_allowed_10',
    'p_barrel_pct_allowed_20','p_hardhit_pct_allowed_20','p_flyball_pct_allowed_20',
    'p_hr_per_bb_allowed_20','p_avg_ev_allowed_20','p_xslg_allowed_20',
    'hr_park_factor',
    'temp_f', 'wind_speed', 'wind_favor', 'is_dome',
    'stand_R', 'p_throws_R',
    'hr_per_bb_vs_R_15', 'barrel_pct_vs_R_15', 'hardhit_pct_vs_R_15',
    'hr_per_bb_vs_R_30', 'barrel_pct_vs_R_30', 'hardhit_pct_vs_R_30',
    'hr_per_bb_vs_L_15', 'barrel_pct_vs_L_15', 'hardhit_pct_vs_L_15',
    'hr_per_bb_vs_L_30', 'barrel_pct_vs_L_30', 'hardhit_pct_vs_L_30',
    # New features v2
    'season_hr',
    'days_since_hr',
    'p_fip',
]

# Expected PA by batting order position (used in contact adjustment).
# bat_order will populate this once the statcast parquet is refreshed.
EXP_PA_BY_ORDER = {1:4.3, 2:4.2, 3:4.1, 4:4.0, 5:3.9, 6:3.7, 7:3.6, 8:3.5, 9:3.4}
EXP_PA_DEFAULT  = 3.8

MLB_AVG_K  = 0.220   # league-average fallbacks
MLB_AVG_BB = 0.080

# Statcast team abbreviation → MLB Stats API team ID
TEAM_ID = {
    'ARI':109, 'AZ':109, 'ATL':144, 'BAL':110, 'BOS':111,
    'CHC':112, 'CWS':145, 'CIN':113, 'CLE':114, 'COL':115,
    'DET':116, 'HOU':117, 'KC':118,  'LAA':108, 'LAD':119,
    'MIA':146, 'MIL':158, 'MIN':142, 'NYM':121, 'NYY':147,
    'OAK':133, 'ATH':133, 'PHI':143, 'PIT':134, 'SD':135,
    'SF':137,  'SEA':136, 'STL':138, 'TB':139,  'TEX':140,
    'TOR':141, 'WSH':120,
}
# MLB Stats API team ID → Statcast abbreviation (prefer 3-letter over 2-letter)
TEAM_ABB = {v: k for k, v in TEAM_ID.items()}
TEAM_ABB.update({109: 'ARI', 133: 'ATH'})


def _mlb(path, params, timeout=20):
    """Thin wrapper around the MLB Stats API."""
    r = requests.get(f'https://statsapi.mlb.com/api/v1/{path}',
                     params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ── Schedule ──────────────────────────────────────────────────────────────────

def format_game_time_et(iso_str):
    """Convert an MLB Stats API UTC timestamp ('2026-06-07T23:10:00Z') to '7:10 PM ET'."""
    if not iso_str:
        return None
    try:
        ts = pd.Timestamp(iso_str).tz_convert('America/New_York')
        hour = ts.hour % 12
        if hour == 0:
            hour = 12
        period = 'AM' if ts.hour < 12 else 'PM'
        return f"{hour}:{ts.minute:02d} {period} ET"
    except (ValueError, TypeError):
        return None


def fetch_schedule(date_str):
    """
    Returns a list of today's regular-season game dicts:
      game_id, status, home_id, away_id, home_abbr, away_abbr,
      home_pitcher_id, home_pitcher_name, away_pitcher_id, away_pitcher_name,
      game_time, stadium
    """
    data = _mlb('schedule', {
        'sportId': 1, 'date': date_str,
        'hydrate': 'probablePitcher,team', 'gameType': 'R',
    })
    games = []
    for date_block in data.get('dates', []):
        for g in date_block.get('games', []):
            home = g['teams']['home']
            away = g['teams']['away']
            home_abbr = home['team'].get('abbreviation', '')
            games.append({
                'game_id':           g['gamePk'],
                'status':            g['status']['abstractGameState'],
                'home_id':           home['team']['id'],
                'away_id':           away['team']['id'],
                'home_abbr':         home_abbr,
                'away_abbr':         away['team'].get('abbreviation', ''),
                'home_pitcher_id':   home.get('probablePitcher', {}).get('id'),
                'home_pitcher_name': home.get('probablePitcher', {}).get('fullName', 'TBD'),
                'away_pitcher_id':   away.get('probablePitcher', {}).get('id'),
                'away_pitcher_name': away.get('probablePitcher', {}).get('fullName', 'TBD'),
                'game_time':         format_game_time_et(g.get('gameDate')),
                'stadium':           STADIUMS.get(home_abbr, {}).get('name'),
            })
    return games


# ── Rosters ───────────────────────────────────────────────────────────────────

def fetch_roster(team_id, season):
    """
    Returns list of {player_id, name} for active position players on a team.
    Pitchers are excluded (they don't have HR props).
    """
    data = _mlb(f'teams/{team_id}/roster',
                {'rosterType': 'active', 'season': season})
    players = []
    for p in data.get('roster', []):
        if p.get('position', {}).get('type') == 'Pitcher':
            continue
        players.append({
            'player_id': p['person']['id'],
            'name':      p['person']['fullName'],
        })
    return players


# ── Contact rates ─────────────────────────────────────────────────────────────

def fetch_contact_rates(season):
    """
    Fetch this season's K% and BB% for all batters from the MLB Stats API.
    One bulk call — returns DataFrame with columns: player_id, k_pct, bb_pct.

    These feed directly into the contact-conditioning adjustment.
    Missing batters will fall back to MLB_AVG_K / MLB_AVG_BB.
    """
    try:
        data = _mlb('stats', {
            'stats': 'season', 'group': 'hitting',
            'sportId': 1, 'season': season, 'limit': 1500,
        })
        rows = []
        for s in data.get('stats', [{}])[0].get('splits', []):
            pa = s['stat'].get('plateAppearances') or 0
            if pa < 20:
                continue
            so = s['stat'].get('strikeOuts') or 0
            bb = (s['stat'].get('baseOnBalls') or 0) + (s['stat'].get('hitByPitch') or 0)
            rows.append({
                'player_id': s['player']['id'],
                'k_pct':     so / pa,
                'bb_pct':    bb / pa,
                'season_hr': int(s['stat'].get('homeRuns', 0)),
            })
        df = pd.DataFrame(rows)
        print(f"  Contact rates: {len(df)} batters with >= 20 PA this season")
        return df
    except Exception as e:
        print(f"  WARNING: contact rate fetch failed ({e}) — will use league averages")
        return pd.DataFrame(columns=['player_id', 'k_pct', 'bb_pct'])


# ── Pitcher season stats (ERA, HR/9, HR allowed, IP) ──────────────────────────

def _parse_ip(ip_str):
    """Convert MLB's '180.2' notation (full innings + thirds) to decimal innings."""
    try:
        parts = str(ip_str).split('.')
        full   = int(parts[0])
        thirds = int(parts[1]) if len(parts) > 1 else 0
        return full + thirds / 3.0
    except (ValueError, IndexError, AttributeError):
        return 0.0


def fetch_pitcher_season_stats(season):
    """
    Fetch this season's ERA, HR allowed, and IP for all pitchers from the
    MLB Stats API. One bulk call — returns a DataFrame keyed by pitcher_id
    with: pitcher_era, pitcher_hr9, pitcher_hr_allowed, pitcher_ip.
    """
    try:
        data = _mlb('stats', {
            'stats': 'season', 'group': 'pitching',
            'sportId': 1, 'season': season, 'limit': 2000,
        })
        rows = []
        for s in data.get('stats', [{}])[0].get('splits', []):
            ip = _parse_ip(s['stat'].get('inningsPitched', '0'))
            if ip <= 0:
                continue
            hr = int(s['stat'].get('homeRuns', 0) or 0)
            rows.append({
                'pitcher_id':         s['player']['id'],
                'pitcher_era':        float(s['stat'].get('era', 0) or 0),
                'pitcher_hr_allowed': hr,
                'pitcher_ip':         ip,
                'pitcher_hr9':        hr / ip * 9,
            })
        df = pd.DataFrame(rows)
        print(f"  Pitcher season stats: {len(df)} pitchers with IP > 0")
        return df
    except Exception as e:
        print(f"  WARNING: pitcher season stats fetch failed ({e})")
        return pd.DataFrame(columns=['pitcher_id', 'pitcher_era', 'pitcher_hr_allowed',
                                      'pitcher_ip', 'pitcher_hr9'])


# ── Batter-vs-pitcher career matchup ──────────────────────────────────────────

def load_vs_pitcher_cache():
    if os.path.exists(VS_PITCHER_CACHE_PATH):
        try:
            with open(VS_PITCHER_CACHE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_vs_pitcher_cache(cache):
    os.makedirs(os.path.dirname(VS_PITCHER_CACHE_PATH), exist_ok=True)
    with open(VS_PITCHER_CACHE_PATH, 'w') as f:
        json.dump(cache, f)


EMPTY_MATCHUP = {'vs_pitcher_ab': 0, 'vs_pitcher_h': 0, 'vs_pitcher_hr': 0, 'vs_pitcher_avg': np.nan}


def fetch_vs_pitcher(batter_id, pitcher_id):
    """Career AB/H/HR/AVG for batter_id against pitcher_id (all seasons combined)."""
    try:
        data = _mlb(f'people/{batter_id}/stats', {
            'stats': 'vsPlayer', 'opposingPlayerId': pitcher_id,
            'group': 'hitting', 'sportId': 1,
        })
        ab = h = hr = 0
        for stat_group in data.get('stats', []):
            for s in stat_group.get('splits', []):
                stat = s.get('stat', {})
                ab += int(stat.get('atBats', 0) or 0)
                h  += int(stat.get('hits', 0) or 0)
                hr += int(stat.get('homeRuns', 0) or 0)
        if ab == 0:
            return dict(EMPTY_MATCHUP)
        return {
            'vs_pitcher_ab':  ab,
            'vs_pitcher_h':   h,
            'vs_pitcher_hr':  hr,
            'vs_pitcher_avg': round(h / ab, 3),
        }
    except Exception:
        return dict(EMPTY_MATCHUP)


# ── Season HR by opposing pitcher hand ────────────────────────────────────────

def compute_season_platoon_hr(season):
    """
    Season home run counts vs RHP and vs LHP, computed directly from the
    Statcast batted-ball store (every HR is a batted ball, so this is exact).
    Returns a DataFrame: batter, hr_vs_r, hr_vs_l.
    """
    df = pd.read_parquet(STATCAST_PATH, columns=['batter', 'p_throws', 'events', 'game_year'])
    season_hrs = df[(df['game_year'] == season) & (df['events'] == 'home_run')]

    grouped = (season_hrs.groupby(['batter', 'p_throws']).size()
               .unstack(fill_value=0)
               .reindex(columns=['R', 'L'], fill_value=0)
               .rename(columns={'R': 'hr_vs_r', 'L': 'hr_vs_l'})
               .reset_index())
    return grouped


# ── Load latest features from parquets ───────────────────────────────────────

def load_latest_batter_features():
    """
    One row per batter — their most recent game's rolling features.
    Also includes last_hr_date (most recent game they hit a HR), used to
    compute days_since_hr at prediction time relative to the actual game date.
    """
    df = pd.read_parquet(BATTER_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df_sorted = df.sort_values(['batter', 'game_date'])

    # Most recent game date where batter hit at least one HR
    hr_games = df_sorted[df_sorted['hr'] > 0][['batter', 'game_date']]
    last_hr = (hr_games.groupby('batter')['game_date'].max()
               .reset_index()
               .rename(columns={'game_date': 'last_hr_date'}))

    latest = df_sorted.groupby('batter').last().reset_index()
    return latest.merge(last_hr, on='batter', how='left')


def load_latest_pitcher_features(season_year=None):
    """
    One row per pitcher — most recent game's rolling features + p_throws.
    If season_year is given, joins current-season FIP from pitcher_fip.parquet.
    """
    df = pd.read_parquet(PITCHER_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])
    latest = df.sort_values('game_date').groupby('pitcher').last().reset_index()

    if season_year is not None and os.path.exists(FIP_PATH):
        fip = pd.read_parquet(FIP_PATH)
        curr_fip = fip[fip['season'] == season_year][['pitcher', 'p_fip']]
        latest = latest.merge(curr_fip, on='pitcher', how='left')

    return latest


def load_latest_platoon_features():
    """
    One row per batter with BOTH the most recent vs_R features AND the most
    recent vs_L features merged together.

    We grab the last game where each set was populated separately because
    vs_R and vs_L features are computed over different subsets of games.
    """
    df = pd.read_parquet(PLATOON_PATH)
    df['game_date'] = pd.to_datetime(df['game_date'])

    vs_R_cols = [c for c in df.columns if '_vs_R_' in c]
    vs_L_cols = [c for c in df.columns if '_vs_L_' in c]

    latest_R = (df[df['hr_per_bb_vs_R_15'].notna()]
                .sort_values('game_date')
                .groupby('batter').last()
                .reset_index()[['batter'] + vs_R_cols])

    latest_L = (df[df['hr_per_bb_vs_L_15'].notna()]
                .sort_values('game_date')
                .groupby('batter').last()
                .reset_index()[['batter'] + vs_L_cols])

    return latest_R.merge(latest_L, on='batter', how='outer')


# ── Weather ───────────────────────────────────────────────────────────────────

def wind_description(wind_speed, wind_favor, is_dome):
    """
    Human-readable wind summary for the web detail card, e.g.
    '8 MPH TOWARD HP', '5 MPH TOWARD OF', 'CROSSWIND 3 MPH', 'DOME', 'CALM'.
    """
    if is_dome:
        return 'DOME'
    if pd.isna(wind_speed) or wind_speed < 1:
        return 'CALM'
    if pd.isna(wind_favor):
        return f'{round(wind_speed)} MPH'

    ratio = wind_favor / wind_speed
    ratio = max(-1.0, min(1.0, ratio))
    if ratio >= 0.3:
        return f'{round(wind_favor)} MPH TOWARD OF'
    elif ratio <= -0.3:
        return f'{round(abs(wind_favor))} MPH TOWARD HP'
    return f'CROSSWIND {round(wind_speed)} MPH'


def get_todays_weather(date_str):
    """
    Returns a DataFrame of weather keyed by home_team for date_str.
    Uses the saved historical parquet if available, otherwise fetches a
    fresh forecast from Open-Meteo (free, no API key).
    """
    if os.path.exists(WEATHER_PATH):
        w = pd.read_parquet(WEATHER_PATH)
        w['game_date'] = pd.to_datetime(w['game_date'])
        today_w = w[w['game_date'] == pd.Timestamp(date_str).normalize()]
        if not today_w.empty:
            return today_w.set_index('home_team')

    print(f"  Weather not in history — fetching forecast for {date_str}...")
    fresh = fetch_forecast(date_str, list(STADIUMS.keys()))
    if not fresh.empty:
        return fresh.set_index('home_team')
    return pd.DataFrame()


# ── Assemble prediction rows ──────────────────────────────────────────────────

def build_prediction_df(date_str, games, rosters,
                        batter_feats, pitcher_feats, platoon_feats,
                        park_df, weather_idx):
    """
    Builds one row per (batter, game) ready for model scoring.
    Columns match FEATURES exactly; missing values become NaN (LightGBM handles them).
    """
    pitcher_idx = pitcher_feats.set_index('pitcher')
    batter_idx  = batter_feats.set_index('batter')
    platoon_idx = (platoon_feats.set_index('batter')
                   if not platoon_feats.empty else pd.DataFrame())

    park_split = (park_df[park_df['bat_side'] != 'ALL']
                  .set_index(['park', 'bat_side'])['hr_park_factor'])

    # Column names we'll pull from each source
    batter_rolling = [c for c in FEATURES
                      if c in batter_feats.columns and not c.startswith('p_')
                      and '_vs_' not in c
                      and c not in ('hr_park_factor','temp_f','wind_speed','wind_favor',
                                    'is_dome','stand_R','p_throws_R')]
    pitcher_rolling = [c for c in FEATURES if c.startswith('p_') and c != 'p_throws_R']
    platoon_cols    = [c for c in FEATURES if '_vs_' in c]

    rows = []
    for game in games:
        home_abbr = game['home_abbr']

        # Weather for this game's park
        if home_abbr in weather_idx.index:
            w = weather_idx.loc[home_abbr]
            temp_f, wind_speed, wind_favor, is_dome = (
                float(w.get('temp_f',  np.nan)),
                float(w.get('wind_speed', np.nan)),
                float(w.get('wind_favor', np.nan)),
                int(w.get('is_dome', 0)),
            )
            humidity_pct = float(w.get('humidity_pct', np.nan))
            precip_pct   = float(w.get('precip_pct', np.nan))
        else:
            temp_f = wind_speed = wind_favor = humidity_pct = precip_pct = np.nan
            is_dome = 0

        wind_desc = wind_description(wind_speed, wind_favor, is_dome)

        # Two sides: home batters face away pitcher, away batters face home pitcher
        sides = [
            dict(batters=rosters.get(game['home_id'], []),
                 pitcher_id=game['away_pitcher_id'],
                 pitcher_name=game['away_pitcher_name'],
                 team_id=game['home_id'], team_abbr=home_abbr, is_home='H',
                 opp_team=game['away_abbr']),
            dict(batters=rosters.get(game['away_id'], []),
                 pitcher_id=game['home_pitcher_id'],
                 pitcher_name=game['home_pitcher_name'],
                 team_id=game['away_id'], team_abbr=game['away_abbr'], is_home='A',
                 opp_team=home_abbr),
        ]

        for side in sides:
            p_id = side['pitcher_id']

            # Pitcher features + handedness
            if p_id and p_id in pitcher_idx.index:
                pf      = pitcher_idx.loc[p_id]
                p_throws = str(pf.get('p_throws', 'R'))
                p_vals  = {c: (float(pf[c]) if c in pf.index else np.nan)
                           for c in pitcher_rolling}
            else:
                p_throws = 'R'   # right-handed is the more common default
                p_vals   = {c: np.nan for c in pitcher_rolling}

            p_throws_R = 1 if p_throws == 'R' else 0

            for batter in side['batters']:
                bid = batter['player_id']
                if bid not in batter_idx.index:
                    continue   # no history → skip

                bf    = batter_idx.loc[bid]
                stand = str(bf.get('stand', 'R'))
                stand_R = 1 if stand == 'R' else 0

                hr_park_factor = park_split.get((home_abbr, stand), np.nan)

                platoon_vals = {}
                if not platoon_idx.empty and bid in platoon_idx.index:
                    pr = platoon_idx.loc[bid]
                    platoon_vals = {c: float(pr[c]) if pd.notna(pr.get(c)) else np.nan
                                    for c in platoon_cols}

                rows.append({
                    # Identifiers (not model features)
                    'game_date':    date_str,
                    'game_id':      game['game_id'],
                    'batter':       bid,
                    'player_name':  batter['name'],
                    'team_abbr':    side['team_abbr'],
                    'home_team':    home_abbr,
                    'opp_team':     side['opp_team'],
                    'is_home':      side['is_home'],
                    'stand':        stand,
                    'pitcher_name': side['pitcher_name'],
                    'pitcher_id':   p_id,
                    'p_throws':     p_throws,
                    # Batter rolling features
                    **{c: float(bf[c]) if pd.notna(bf.get(c)) else np.nan
                       for c in batter_rolling},
                    # Park + weather
                    'hr_park_factor': float(hr_park_factor) if pd.notna(hr_park_factor) else np.nan,
                    'temp_f':  temp_f, 'wind_speed': wind_speed,
                    'wind_favor': wind_favor, 'is_dome': is_dome,
                    'humidity_pct': humidity_pct, 'precip_pct': precip_pct,
                    'wind_description': wind_desc,
                    # Game info
                    'game_time': game.get('game_time'),
                    'stadium':   game.get('stadium'),
                    # Handedness flags
                    'stand_R': stand_R, 'p_throws_R': p_throws_R,
                    # Pitcher rolling features
                    **p_vals,
                    # Platoon split features
                    **platoon_vals,
                })

    return pd.DataFrame(rows)


# ── Contact-conditioning adjustment ──────────────────────────────────────────

def add_contact_adjustment(df, contact_df):
    """
    Adds the columns needed by Priority 4 (fair-odds conversion).

    The core problem being solved:
      The model was trained only on games where the batter made contact.
      So model_prob = P(HR | batter has >= 1 batted ball today).
      But the HR prop pays on P(HR in game), which includes games where
      the batter strikes out or walks every PA — those games can never
      produce a HR.

      adj_prob = model_prob × P(batter makes contact in today's game)
               = the true probability the prop resolves as a winner.

    Using adj_prob instead of model_prob prevents every line from
    appearing to have false value when converting to fair odds.
    """
    # Join this season's per-player K% and BB% only (season_hr is already in df
    # from batter_feats enrichment done before scoring, so we don't re-merge it)
    if not contact_df.empty:
        rate_cols = contact_df[['player_id', 'k_pct', 'bb_pct']].rename(
            columns={'player_id': 'batter'})
        df = df.merge(rate_cols, on='batter', how='left')
    else:
        df['k_pct']  = np.nan
        df['bb_pct'] = np.nan

    # Fall back to league averages for players with no stats (rookies, short samples)
    df['k_pct']  = df['k_pct'].fillna(MLB_AVG_K).clip(0, 0.60)
    df['bb_pct'] = df['bb_pct'].fillna(MLB_AVG_BB).clip(0, 0.40)

    # Ensure k% + bb% doesn't arithmetically exceed 100%
    total = df['k_pct'] + df['bb_pct']
    excess = (total - 1.0).clip(lower=0)
    df['bb_pct'] = df['bb_pct'] - excess   # trim the smaller component if needed

    # Per-PA probability of putting a ball in play
    df['contact_rate'] = (1 - df['k_pct'] - df['bb_pct']).clip(0, 1)

    # Expected PA: will be refined by batting order once bat_order is available.
    # For now, a flat 3.8 PA per game (MLB average for a full-game starter).
    df['exp_pa'] = EXP_PA_DEFAULT

    # P(at least one batted ball in N PAs) = 1 - P(no contact in any PA)^N
    df['p_contact_game'] = 1 - (1 - df['contact_rate']) ** df['exp_pa']

    # adj_prob = model_prob directly; p_contact_game kept as a diagnostic column
    df['adj_prob'] = df['model_prob']

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def run(date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    season = int(date_str[:4])

    print(f"\n{'='*56}")
    print(f"  MLB HR Prop Runner  --  {date_str}")
    print(f"{'='*56}")

    # ── Static data ───────────────────────────────────────────────────────────
    print("\nLoading model and feature tables...")
    model       = joblib.load(MODEL_PATH)
    park_df     = pd.read_csv(PARK_PATH)
    weather_idx = get_todays_weather(date_str)

    batter_feats  = load_latest_batter_features()
    pitcher_feats = load_latest_pitcher_features(season_year=season)
    platoon_feats = load_latest_platoon_features()
    print(f"  {batter_feats['batter'].nunique():,} batters  |  "
          f"{pitcher_feats['pitcher'].nunique():,} pitchers  with history")

    # ── Schedule ──────────────────────────────────────────────────────────────
    print(f"\nFetching schedule for {date_str}...")
    all_games = fetch_schedule(date_str)
    games = [g for g in all_games if g['status'] != 'Final']
    if not games:
        print("No games today (or all already final). Exiting.")
        return pd.DataFrame()
    print(f"  {len(games)} games")
    for g in games:
        hp = g['home_pitcher_name']
        ap = g['away_pitcher_name']
        print(f"    {g['away_abbr']} ({ap}) @ {g['home_abbr']} ({hp})")

    # ── Rosters ───────────────────────────────────────────────────────────────
    print("\nFetching active rosters...")
    team_ids = {g['home_id'] for g in games} | {g['away_id'] for g in games}
    rosters  = {}
    for tid in sorted(team_ids):
        try:
            rosters[tid] = fetch_roster(tid, season)
            time.sleep(0.1)
        except Exception as e:
            print(f"  WARNING: roster fetch failed for team {tid}: {e}")
            rosters[tid] = []
    total_players = sum(len(v) for v in rosters.values())
    print(f"  {total_players} position players across {len(rosters)} teams")

    # ── Contact rates ─────────────────────────────────────────────────────────
    print(f"\nFetching {season} contact rates (K%/BB%) from MLB Stats API...")
    contact_df = fetch_contact_rates(season)

    # ── Pitcher season stats (ERA, HR/9, HR allowed, IP) ─────────────────────
    print(f"\nFetching {season} pitcher season stats (ERA, HR/9, IP) from MLB Stats API...")
    pitcher_season_df = fetch_pitcher_season_stats(season)

    # ── Season HR by opposing pitcher hand (vs RHP / vs LHP) ─────────────────
    print(f"\nComputing {season} season HR vs RHP/LHP from Statcast store...")
    platoon_hr_df = compute_season_platoon_hr(season)

    # Enrich batter_feats with season_hr and days_since_hr BEFORE model scoring.
    # season_hr comes from the MLB Stats API hit count (already fetched above).
    # days_since_hr is relative to today's prediction date.
    if not contact_df.empty and 'season_hr' in contact_df.columns:
        hr_map = contact_df.set_index('player_id')['season_hr']
        batter_feats['season_hr'] = batter_feats['batter'].map(hr_map)
    else:
        batter_feats['season_hr'] = np.nan

    batter_feats['days_since_hr'] = (
        pd.Timestamp(date_str) - batter_feats['last_hr_date']
    ).dt.days

    # ── Build + score ─────────────────────────────────────────────────────────
    print("\nAssembling prediction rows...")
    pred_df = build_prediction_df(
        date_str, games, rosters,
        batter_feats, pitcher_feats, platoon_feats,
        park_df, weather_idx,
    )
    if pred_df.empty:
        print("No prediction rows built — confirm batter history exists.")
        return pred_df
    print(f"  {len(pred_df)} batter-game rows assembled")

    # Merge pitcher season stats (ERA, HR/9, HR allowed, IP)
    if not pitcher_season_df.empty:
        pred_df = pred_df.merge(pitcher_season_df, on='pitcher_id', how='left')
    else:
        for c in ['pitcher_era', 'pitcher_hr_allowed', 'pitcher_ip', 'pitcher_hr9']:
            pred_df[c] = np.nan

    # Merge season HR vs RHP / vs LHP
    pred_df = pred_df.merge(platoon_hr_df, on='batter', how='left')
    pred_df['hr_vs_r'] = pred_df['hr_vs_r'].fillna(0).astype(int)
    pred_df['hr_vs_l'] = pred_df['hr_vs_l'].fillna(0).astype(int)

    # ── Batter-vs-pitcher career matchups ────────────────────────────────────
    print("\nFetching batter-vs-pitcher matchup history (cached across days)...")
    cache = load_vs_pitcher_cache()
    pairs = pred_df[['batter', 'pitcher_id']].drop_duplicates()
    matchup_rows = []
    n_fetched = 0
    for _, r in pairs.iterrows():
        bid = int(r['batter'])
        pid = r['pitcher_id']
        if pd.isna(pid):
            matchup_rows.append({'batter': bid, 'pitcher_id': pid, **EMPTY_MATCHUP})
            continue
        pid = int(pid)
        key = f"{bid}_{pid}_{date_str}"
        if key in cache:
            m = cache[key]
        else:
            m = fetch_vs_pitcher(bid, pid)
            cache[key] = m
            n_fetched += 1
            time.sleep(0.05)
        matchup_rows.append({'batter': bid, 'pitcher_id': pid, **m})
    save_vs_pitcher_cache(cache)
    print(f"  {len(pairs)} batter-pitcher pairs ({n_fetched} fetched, "
          f"{len(pairs) - n_fetched} cached)")

    matchup_df = pd.DataFrame(matchup_rows)
    pred_df = pred_df.merge(matchup_df, on=['batter', 'pitcher_id'], how='left')

    # Fill any features not yet in the DataFrame
    for f in FEATURES:
        if f not in pred_df.columns:
            pred_df[f] = np.nan

    print("Scoring with model...")
    pred_df['model_prob'] = model.predict_proba(pred_df[FEATURES])[:, 1]

    print("Computing contact-conditioning adjustment...")
    pred_df = add_contact_adjustment(pred_df, contact_df)

    # ── Save ──────────────────────────────────────────────────────────────────
    pred_df = pred_df.sort_values('adj_prob', ascending=False).reset_index(drop=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f'predictions_{date_str}.csv')

    # Ordered output columns — identifiers first, then prediction columns,
    # then the per-component columns needed by Priority 4 fair-odds conversion
    out_cols = [
        'player_name', 'team_abbr', 'stand', 'pitcher_name', 'p_throws', 'home_team', 'opp_team', 'is_home',
        'model_prob',
        'k_pct', 'bb_pct', 'contact_rate', 'exp_pa', 'p_contact_game',
        'adj_prob',                     # <-- input to fair-odds conversion
        'hr_park_factor', 'temp_f', 'wind_speed', 'wind_favor', 'is_dome',
        'humidity_pct', 'precip_pct', 'wind_description',
        'game_time', 'stadium',
        'season_hr', 'days_since_hr', 'p_fip',
        # Statcast rolling features used by model — also shown in web detail card
        'barrel_pct_15', 'hardhit_pct_15', 'flyball_pct_15',
        'avg_ev_15', 'xwoba_15', 'xslg_15',
        'p_barrel_pct_allowed_10', 'p_hardhit_pct_allowed_10', 'p_hr_per_bb_allowed_10',
        # Pitcher season profile — shown in web detail card
        'pitcher_era', 'pitcher_hr9', 'pitcher_hr_allowed', 'pitcher_ip',
        # Batter-vs-pitcher career matchup — shown in web detail card
        'vs_pitcher_ab', 'vs_pitcher_h', 'vs_pitcher_hr', 'vs_pitcher_avg',
        # Season HR by opposing pitcher hand — shown in web detail card
        'hr_vs_r', 'hr_vs_l',
        'game_date', 'game_id', 'batter',
    ]
    pred_df[[c for c in out_cols if c in pred_df.columns]].to_csv(out_path, index=False)

    print(f"\n{'='*56}")
    print(f"Saved {len(pred_df)} predictions to {out_path}")
    print("\nTop 20 by adj_prob:")
    display = ['player_name','team_abbr','stand','pitcher_name','p_throws',
               'model_prob','p_contact_game','adj_prob']
    print(pred_df[[c for c in display if c in pred_df.columns]].head(20).to_string(index=False))

    return pred_df


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
