"""
Fair-odds conversion with confirmed-lineup filter.

INCREMENTAL DESIGN — safe to run multiple times per day:
  Each run only fetches OddsAPI props for games that are:
    (a) in Preview state (not yet started)
    (b) have a confirmed lineup available right now
    (c) not already priced in today's output CSV
  New results are merged with any previously priced games.

  Typical split-slate usage:
    11 AM run  -> prices day games whose lineups are posted (e.g. 4 games)
    4 PM run   -> prices remaining night games (e.g. 11 games)
    Total API credits: ~17 vs ~16 for a single full-slate run

Usage:
    python predict/fair_odds.py              # today
    python predict/fair_odds.py 2026-06-08   # specific date
"""

import os, re, sys, time, unicodedata
import numpy as np
import pandas as pd
import requests
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ODDS_KEY      = os.getenv('ODDS_API_KEY') or os.getenv('ODDSPAPI_KEY')
PARLAY_KEY    = os.getenv('PARLAY_API_KEY')
MLB_BASE      = 'https://statsapi.mlb.com/api/v1'
ODDS_BASE     = 'https://api.the-odds-api.com'
PARLAY_BASE   = 'https://parlay-api.com/v1'
PRED_DIR      = 'data/predictions'
OUT_DIR       = 'data/outputs'

# Feature flag: set ODDS_PROVIDER=parlay_api in .env to switch providers.
# Defaults to odds_api so nothing changes until explicitly flipped.
# ROLLBACK: set ODDS_PROVIDER=odds_api (or delete the var) to revert instantly.
# The old OddsAPI functions (fetch_events_list, fetch_props_for_events) are
# kept intact below so a rollback requires zero code changes.
ODDS_PROVIDER = os.getenv('ODDS_PROVIDER', 'odds_api')  # 'odds_api' | 'parlay_api'

# Keywords (lowercase) in OddsAPI team names that identify each MLB abbreviation.
# Order matters — Cubs/White Sox and Angels/Dodgers must not cross-match.
_TEAM_KEYS = [
    ('AZ',  ['diamondbacks']),
    ('ATL', ['atlanta']),
    ('BAL', ['baltimore']),
    ('BOS', ['boston']),
    ('CHC', ['cubs']),
    ('CWS', ['white sox']),
    ('CIN', ['cincinnati']),
    ('CLE', ['cleveland']),
    ('COL', ['colorado']),
    ('DET', ['detroit']),
    ('HOU', ['houston']),
    ('KC',  ['kansas city']),
    ('LAA', ['angels']),
    ('LAD', ['dodgers']),
    ('MIA', ['miami']),
    ('MIL', ['milwaukee']),
    ('MIN', ['minnesota']),
    ('NYM', ['mets']),
    ('NYY', ['yankees']),
    ('ATH', ['athletics']),
    ('PHI', ['philadelphia']),
    ('PIT', ['pittsburgh']),
    ('SD',  ['san diego', 'padres']),
    ('SEA', ['seattle']),
    ('SF',  ['san francisco', 'giants']),
    ('STL', ['cardinals']),
    ('TB',  ['tampa bay']),
    ('TEX', ['texas', 'rangers']),
    ('TOR', ['toronto']),
    ('WSH', ['washington']),
]
_ABBR_KEYS = {abbr: keys for abbr, keys in _TEAM_KEYS}

# MLB statusCode values that mean the game will not be played as scheduled.
_POSTPONED_CODES = frozenset({
    'DI', 'DO', 'DR', 'DS', 'DV',  # Postponed – various reasons
    'CR', 'CO',                      # Cancelled – Rain / Other
    'SU', 'SI',                      # Suspended – Inclement Weather / Other
})

# Expected PAs by batting order slot (used to refine adj_prob once bat_order is known)
EXP_PA_BY_ORDER = {1: 4.3, 2: 4.2, 3: 4.1, 4: 4.0, 5: 3.9, 6: 3.7, 7: 3.6, 8: 3.5, 9: 3.4}
EXP_PA_DEFAULT  = 3.8


# ── Utilities ─────────────────────────────────────────────────────────────────

def _mlb(path, params=None, timeout=15):
    r = requests.get(f'{MLB_BASE}/{path}', params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _odds_get(path, params=None, timeout=20):
    r = requests.get(f'{ODDS_BASE}{path}',
                     params={**(params or {}), 'apiKey': ODDS_KEY},
                     timeout=timeout)
    r.raise_for_status()
    return r, r.json()

def _parlay_get(path, params=None, timeout=30):
    if not PARLAY_KEY:
        raise ValueError("PARLAY_API_KEY not set in environment")
    r = requests.get(f'{PARLAY_BASE}{path}',
                     headers={'X-API-Key': PARLAY_KEY},
                     params=params or {},
                     timeout=timeout)
    r.raise_for_status()
    return r, r.json()

def american_to_implied(odds):
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)

def implied_to_american(p):
    if pd.isna(p) or p <= 0 or p >= 1:
        return None
    if p >= 0.5:
        return int(round(-p / (1.0 - p) * 100))
    return int(round((1.0 - p) / p * 100))

def norm_name(name):
    name = unicodedata.normalize('NFKD', str(name))
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return re.sub(r'[^a-z ]', '', name.lower().strip())


# ── [1] Load predictions & existing output ────────────────────────────────────

def load_predictions(date_str):
    path = os.path.join(PRED_DIR, f'predictions_{date_str}.csv')
    if os.path.exists(path):
        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} predictions from {path}")
        return df
    print(f"  No predictions file for {date_str} -- running daily_runner first...")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import predict.daily_runner as runner
    runner.run(date_str)
    if not os.path.exists(path):
        raise SystemExit("daily_runner produced no output -- check errors above.")
    df = pd.read_csv(path)
    print(f"  Generated and loaded {len(df)} predictions.")
    return df


def load_existing_output(date_str):
    """
    Load today's fair_odds CSV if it exists.
    Returns (DataFrame, set_of_already_priced_game_pks).
    """
    path = os.path.join(OUT_DIR, f'fair_odds_{date_str}.csv')
    if not os.path.exists(path):
        return pd.DataFrame(), set()
    df = pd.read_csv(path)
    priced_pks = {int(x) for x in df['game_id'].dropna().unique()}
    print(f"  Existing output: {len(df)} players already priced "
          f"across {len(priced_pks)} game(s)")
    return df, priced_pks


# ── [2] Schedule with game states ─────────────────────────────────────────────

def fetch_schedule(date_str):
    """
    Return today's games with their current state.

    Each dict: {
        'game_pk':   int,
        'status':    'preview' | 'live' | 'final',
        'home_abbr': str,  'away_abbr': str,
        'home_full': str,  'away_full': str,
    }

    status meanings for routing decisions:
        preview -> can still bet; lineup may or may not be available yet
        live    -> batting order is locked but props are closed; skip pricing
        final   -> game over; skip pricing
    """
    data = _mlb('schedule', {
        'sportId': 1, 'date': date_str,
        'hydrate': 'team', 'gameType': 'R',
    })
    games = []
    for date_block in data.get('dates', []):
        for g in date_block.get('games', []):
            status_obj  = g.get('status', {})
            raw_state   = status_obj.get('abstractGameState', 'Preview')
            status_code = status_obj.get('statusCode', '')
            state = raw_state.lower()  # 'preview', 'live', 'final'
            if status_code in _POSTPONED_CODES:
                state = 'postponed'
            ht = g.get('teams', {}).get('home', {}).get('team', {})
            at = g.get('teams', {}).get('away', {}).get('team', {})
            games.append({
                'game_pk':   int(g['gamePk']),
                'status':    state,
                'home_abbr': ht.get('abbreviation', ''),
                'away_abbr': at.get('abbreviation', ''),
                'home_full': ht.get('name', ''),
                'away_full': at.get('name', ''),
            })
    return games


# ── [3] Lineup data per game ──────────────────────────────────────────────────

def fetch_lineups_by_game(date_str, schedule_games):
    """
    Returns {game_pk: {'starters': set[int], 'source': str}}
    for every game where a confirmed lineup is available.
    Games with no lineup data are absent from the dict.

    Source 1: schedule hydrate=lineups (pre-game, 9 per side)
    Source 2: live game feed battingOrder (fallback for Live games)
    """
    result = {}

    # Source 1: hydrate=lineups
    try:
        data = _mlb('schedule', {
            'sportId': 1, 'date': date_str,
            'hydrate': 'lineups,team', 'gameType': 'R',
        })
        for date_block in data.get('dates', []):
            for g in date_block.get('games', []):
                pk = int(g['gamePk'])
                ids = set()
                batting_order = {}
                for side in ('homePlayers', 'awayPlayers'):
                    pos = 1
                    for p in g.get('lineups', {}).get(side, []):
                        if p.get('primaryPosition', {}).get('type') != 'Pitcher':
                            pid = int(p['id'])
                            ids.add(pid)
                            batting_order[pid] = pos
                            pos += 1
                if ids:
                    result[pk] = {'starters': ids, 'source': 'mlb_schedule',
                                  'batting_order': batting_order}
    except Exception as e:
        print(f"  hydrate=lineups failed: {e}")

    # Source 2: live feed for any Live games not already found
    live_pks = [g['game_pk'] for g in schedule_games
                if g['status'] == 'live' and g['game_pk'] not in result]
    for pk in live_pks:
        try:
            r = requests.get(
                f'https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live',
                timeout=10
            )
            r.raise_for_status()
            box = r.json().get('liveData', {}).get('boxscore', {}).get('teams', {})
            ids = set()
            batting_order = {}
            for side in ('home', 'away'):
                bo_list = box.get(side, {}).get('battingOrder', [])
                for pos, pid in enumerate(bo_list, 1):
                    ids.add(int(pid))
                    batting_order[int(pid)] = pos
            if ids:
                result[pk] = {'starters': ids, 'source': 'live_feed',
                              'batting_order': batting_order}
            time.sleep(0.2)
        except Exception:
            pass

    return result


# ── [4] Hard lineup filter ────────────────────────────────────────────────────

def apply_lineup_filter(pred_df, starter_ids, starter_source, batting_order=None):
    """Keep only confirmed starters; log every dropped player."""
    pred_df = pred_df.copy()

    if starter_ids:
        pred_df['in_lineup']    = pred_df['batter'].isin(starter_ids).astype(int)
        pred_df['lineup_source'] = pred_df['in_lineup'].map(
            {1: starter_source, 0: 'not_in_lineup'}
        )
    else:
        pred_df['in_lineup']    = 0
        pred_df['lineup_source'] = 'unconfirmed'

    if batting_order:
        pred_df['bat_order'] = pred_df['batter'].map(batting_order)
    else:
        pred_df['bat_order'] = None

    starters = pred_df[pred_df['in_lineup'] == 1].copy()
    dropped  = pred_df[pred_df['in_lineup'] == 0].copy()

    print(f"\n  {'-'*52}")
    print(f"  LINEUP FILTER  (source: {starter_source})")
    print(f"  Scored:  {len(pred_df):4d}  position players from new games")
    print(f"  Kept:    {len(starters):4d}  confirmed starters")
    print(f"  DROPPED: {len(dropped):4d}  bench / not in confirmed lineup")
    print(f"  {'-'*52}")
    if 0 < len(dropped) <= 20:
        print(f"  Dropped: {sorted(dropped['player_name'].tolist())}")
    elif len(dropped) > 20:
        print(f"  Dropped (first 20 of {len(dropped)}): "
              f"{sorted(dropped['player_name'].tolist())[:20]}")

    return starters, dropped


# ── [5] OddsAPI: events list (1 credit) ───────────────────────────────────────

def fetch_events_list(date_str):
    """
    Fetch all MLB events from OddsAPI and filter to the 36-hour window for date_str.
    Costs 1 API credit.

    The 36-hour window (midnight UTC to 09:00 UTC next day) ensures that late
    evening US games (which appear as next-day UTC) are included without
    bleeding into the following day's slate.

    Returns (events_in_window, credits_remaining_str).
    Both are empty/unknown on error.
    """
    if not ODDS_KEY:
        print("  ODDS_API_KEY not set -- skipping market lines.")
        return [], '?'

    try:
        r, events = _odds_get('/v4/sports/baseball_mlb/events', {'dateFormat': 'iso'})
        remaining = r.headers.get('x-requests-remaining', '?')
    except requests.HTTPError as e:
        code = e.response.status_code
        body = {}
        try:
            body = e.response.json()
        except Exception:
            pass
        if code == 401:
            print("  OddsAPI auth failed (401). Check ODDS_API_KEY in .env.")
        else:
            print(f"  OddsAPI events failed ({code}): {body.get('message', '')}")
        return [], '?'
    except Exception as e:
        print(f"  OddsAPI events error: {e}")
        return [], '?'

    window_start = f"{date_str}T00:00:00Z"
    next_day     = (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime('%Y-%m-%d')
    window_end   = f"{next_day}T09:00:00Z"
    today_events = [
        e for e in events
        if window_start <= e.get('commence_time', '') < window_end
    ]
    print(f"  {len(today_events)} events in OddsAPI window "
          f"[{date_str} 00:00Z - {next_day} 09:00Z] | {remaining} credits remaining")
    return today_events, remaining


# ── [6] Match MLB game_pks -> OddsAPI event IDs ───────────────────────────────

def _team_matches_abbr(abbr, odds_name):
    """Return True if the OddsAPI team name corresponds to the MLB abbreviation."""
    keys = _ABBR_KEYS.get(abbr, [abbr.lower()])
    name_lower = odds_name.lower()
    return any(k in name_lower for k in keys)


def match_games_to_events(schedule_games, events):
    """
    For each schedule game, find its OddsAPI event by matching home+away team names.
    Returns {game_pk: odds_event_id}.
    Unmatched games are absent from the dict (no line available in OddsAPI).
    """
    mapping = {}
    for game in schedule_games:
        for ev in events:
            if (_team_matches_abbr(game['home_abbr'], ev.get('home_team', '')) and
                    _team_matches_abbr(game['away_abbr'], ev.get('away_team', ''))):
                mapping[game['game_pk']] = ev['id']
                break
    return mapping


# ── [7] OddsAPI: props per event (1 credit each) ──────────────────────────────

def fetch_props_for_events(event_ids):
    """
    Fetch batter_home_runs (Over 0.5) lines and game totals for the given OddsAPI event IDs.
    Costs 1 API credit per event ID. totals market is fetched in the same call at no extra cost.

    Returns (all_lines_df, game_totals_dict, credits_used, failed_count, last_remaining_str).
    game_totals_dict maps event_id -> O/U total (float).
    """
    if not event_ids:
        return pd.DataFrame(), {}, 0, 0, '?'

    rows, game_totals, credits_used, failed, last_remaining = [], {}, 0, 0, '?'

    for event_id in event_ids:
        try:
            r, data = _odds_get(
                f'/v4/sports/baseball_mlb/events/{event_id}/odds',
                {'regions': 'us,us_ex', 'markets': 'batter_home_runs,totals',
                 'oddsFormat': 'american'},
            )
            last_remaining = r.headers.get('x-requests-remaining', last_remaining)
            credits_used += 1
            for bm in data.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'batter_home_runs':
                        for outcome in mkt.get('outcomes', []):
                            # Only anytime-HR (Over 0.5). Exclude 1.5+ markets.
                            if outcome.get('name') == 'Over' and outcome.get('point', 0) == 0.5:
                                rows.append({
                                    'player_name_raw': outcome.get('description', ''),
                                    'bookmaker':       bm['key'],
                                    'odds_american':   int(outcome['price']),
                                    'event_id':        event_id,
                                })
                    elif mkt['key'] == 'totals' and event_id not in game_totals:
                        for outcome in mkt.get('outcomes', []):
                            if outcome.get('name') == 'Over' and event_id not in game_totals:
                                game_totals[event_id] = float(outcome.get('point', 0))
            time.sleep(0.4)
        except requests.HTTPError as e:
            code = e.response.status_code
            if code == 422:
                print(f"  batter_home_runs unavailable (422) for event {event_id} "
                      f"-- may need a higher OddsAPI tier.")
            else:
                print(f"  HTTP {code} fetching props for event {event_id}")
            failed += 1
        except Exception as e:
            print(f"  Error fetching props for event {event_id}: {e}")
            failed += 1

    if not rows:
        return pd.DataFrame(), game_totals, credits_used, failed, last_remaining

    all_df = pd.DataFrame(rows)
    all_df['implied']   = all_df['odds_american'].apply(american_to_implied)
    all_df['name_norm'] = all_df['player_name_raw'].apply(norm_name)
    return all_df, game_totals, credits_used, failed, last_remaining


def _best_lines(all_df):
    """One row per player: the bookmaker offering the highest American odds."""
    if all_df.empty:
        return pd.DataFrame()
    return (all_df
            .sort_values('odds_american', ascending=False)
            .groupby('name_norm', as_index=False)
            .first())


# ── [5-7 alt] ParlayAPI: bulk props fetch (3 credits total) ──────────────────

def fetch_props_parlay_api(date_str):
    """
    Fetch ALL MLB HR props from ParlayAPI in one call (3 credits).
    Also extracts game totals (O/U) from the same response when available.

    Returns:
        events_for_matching  list[dict]   — [{id, home_team, away_team, commence_time}, ...]
                                            shaped identically to OddsAPI events so
                                            match_games_to_events() can be reused unchanged.
        all_lines_df         DataFrame    — same schema as fetch_props_for_events output:
                                            player_name_raw, bookmaker, odds_american,
                                            event_id, implied, name_norm
        game_totals          dict         — {canonical_event_id: float} O/U totals
        credits_used         int          — 3
        failed_count         int          — 0 or 1
        credits_remaining    str
    """
    if not PARLAY_KEY:
        print("  PARLAY_API_KEY not set -- skipping market lines.")
        return [], pd.DataFrame(), {}, 0, 0, '?'

    # 36-hour window: midnight UTC to 09:00 UTC next day (matches OddsAPI logic)
    window_start = f"{date_str}T00:00:00Z"
    next_day     = (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime('%Y-%m-%d')
    window_end   = f"{next_day}T09:00:00Z"

    try:
        r, raw = _parlay_get('/sports/baseball_mlb/props',
                              params={'markets': 'player_home_runs,totals'})
        # ParlayAPI uses x-requests-remaining; fall back to x-credits-remaining
        credits_remaining = r.headers.get('x-requests-remaining',
                            r.headers.get('x-credits-remaining', '?'))
    except requests.HTTPError as e:
        code = e.response.status_code
        body = {}
        try:
            body = e.response.json()
        except Exception:
            pass
        if code == 401:
            print("  ParlayAPI auth failed (401). Check PARLAY_API_KEY in .env.")
        elif code == 403:
            print("  ParlayAPI 403 Forbidden. Key may lack access to this endpoint.")
        else:
            print(f"  ParlayAPI props failed ({code}): {body.get('message', str(e))}")
        return [], pd.DataFrame(), {}, 3, 1, '?'
    except Exception as e:
        print(f"  ParlayAPI props error: {e}")
        return [], pd.DataFrame(), {}, 3, 1, '?'

    # Response may be a top-level list or wrapped in a key
    rows = raw if isinstance(raw, list) else raw.get('data', raw.get('results', raw.get('props', [])))

    hr_rows      = []
    game_totals  = {}
    seen_events  = {}  # canonical_event_id -> event dict (for match_games_to_events)

    for row in rows:
        ct = row.get('commence_time', '')
        if not (window_start <= ct < window_end):
            continue

        eid       = row.get('canonical_event_id', '')
        home_team = row.get('home_team', '')
        away_team = row.get('away_team', '')

        # Build event index from whichever rows we encounter
        if eid and eid not in seen_events:
            seen_events[eid] = {
                'id':            eid,
                'home_team':     home_team,
                'away_team':     away_team,
                'commence_time': ct,
            }

        mkt = row.get('market_key', '')

        # --- HR props (anytime: line == 0.5 or no line field) ---
        if mkt == 'player_home_runs':
            # Skip DFS flat-payout platforms (PrizePicks, Underdog, Sleeper).
            # Their normalized +100/-100 prices are not real sportsbook lines.
            if row.get('is_dfs_flat_payout'):
                continue
            over_price = row.get('over_price')
            if over_price is None:
                continue
            line = row.get('line')
            # Only anytime-HR (0.5 line). Skip 2+ HR markets (line=1.5) and
            # any row where line is absent (e.g. Bovada "2+ HR" with line=None).
            if line is None or float(line) != 0.5:
                continue
            player = row.get('player', '')
            if not player:
                continue
            hr_rows.append({
                'player_name_raw': player,
                'bookmaker':       row.get('bookmaker', ''),
                'odds_american':   int(over_price),
                'event_id':        eid,
            })

        # --- Game totals (same call, free) ---
        elif mkt == 'totals' and eid not in game_totals:
            total_line = row.get('line')
            if total_line is not None:
                try:
                    game_totals[eid] = float(total_line)
                except (TypeError, ValueError):
                    pass

    events_for_matching = list(seen_events.values())
    n_events = len(events_for_matching)

    if not hr_rows:
        print(f"  ParlayAPI: 0 HR lines in today's window across {n_events} event(s) "
              f"| {credits_remaining} credits remaining")
        return events_for_matching, pd.DataFrame(), game_totals, 3, 0, credits_remaining

    all_df = pd.DataFrame(hr_rows)
    all_df['implied']   = all_df['odds_american'].apply(american_to_implied)
    all_df['name_norm'] = all_df['player_name_raw'].apply(norm_name)

    n_players = all_df['name_norm'].nunique()
    n_books   = all_df['bookmaker'].nunique()
    avg_lines = all_df.groupby('name_norm').size().mean()
    print(f"  ParlayAPI: {n_players} players | {n_books} book(s) | "
          f"{avg_lines:.1f} lines/player | {n_events} event(s) | "
          f"{credits_remaining} credits remaining")
    if game_totals:
        print(f"  {len(game_totals)} game O/U total(s): {[f'{v}' for v in game_totals.values()]}")

    return events_for_matching, all_df, game_totals, 3, 0, credits_remaining


def refresh_context_columns(existing_df, pred_df, date_str):
    """
    Refresh time-sensitive context columns (season_hr, days_since_hr, recent_hr)
    on already-priced players using today's freshly recomputed predictions.

    Without this, a player priced earlier in the day keeps the days_since_hr /
    recent_hr values from that earlier run even after the Statcast store picks
    up a new HR -- the odds/edge for that player are left untouched (no extra
    OddsAPI credits spent).
    """
    if existing_df.empty:
        return existing_df

    refresh_cols = [c for c in ('season_hr', 'days_since_hr') if c in pred_df.columns]
    if refresh_cols:
        fresh = pred_df[['game_id', 'batter'] + refresh_cols].drop_duplicates(['game_id', 'batter'])
        existing_df = existing_df.drop(columns=refresh_cols, errors='ignore')
        existing_df = existing_df.merge(fresh, on=['game_id', 'batter'], how='left')

    hot = fetch_recent_hr_batters(date_str, set(existing_df['batter']))
    existing_df['recent_hr'] = existing_df['batter'].isin(hot).astype(int)

    return existing_df


def fetch_recent_hr_batters(date_str, batter_ids):
    """
    Returns the subset of batter_ids who hit >= 1 HR in their last 5 games
    before date_str, using data/processed/batter_features.parquet.
    Returns empty set on any failure (graceful degradation).
    """
    feat_path = os.path.join('data', 'processed', 'batter_features.parquet')
    if not os.path.exists(feat_path):
        return set()
    try:
        import pandas as pd
        df = pd.read_parquet(feat_path, columns=['batter', 'game_date', 'hr'])
        df['game_date'] = pd.to_datetime(df['game_date'])
        cutoff = pd.Timestamp(date_str)
        past = df[(df['game_date'] < cutoff) & (df['batter'].isin(batter_ids))]
        if past.empty:
            return set()
        hot = set()
        for bid, grp in past.groupby('batter'):
            last_5_dates = sorted(grp['game_date'].unique())[-5:]
            if grp[grp['game_date'].isin(last_5_dates)]['hr'].sum() > 0:
                hot.add(bid)
        return hot
    except Exception as e:
        print(f"  WARNING: recent HR check failed ({e}) -- skipping HOT badge")
        return set()


# ── [8] Join odds + edge ──────────────────────────────────────────────────────

def join_odds_and_edge(starters_df, best_odds_df):
    """
    Left-join market lines onto confirmed starters by normalized player name.
    Adds: has_line, best_book, best_odds, book_implied, fair_odds, edge.
    edge = adj_prob - book_implied (vig-inclusive; positive = model favors over book).
    """
    df = starters_df.copy()
    df['name_norm'] = df['player_name'].apply(norm_name)
    df['fair_odds'] = df['adj_prob'].apply(implied_to_american)

    if best_odds_df.empty:
        df['has_line']     = 0
        df['best_book']    = None       # string column — None is fine
        df['best_odds']    = np.nan     # keep float dtype for safe pd.concat
        df['book_implied'] = np.nan
        df['edge']         = np.nan
        return df.drop(columns=['name_norm'])

    merge_src = best_odds_df[['name_norm', 'bookmaker', 'odds_american', 'implied']].rename(
        columns={'bookmaker': 'best_book', 'odds_american': 'best_odds', 'implied': 'book_implied'}
    )
    df = df.merge(merge_src, on='name_norm', how='left').drop(columns=['name_norm'])
    df['has_line'] = df['best_odds'].notna().astype(int)
    df['edge']     = (df['adj_prob'] - df['book_implied']).where(df['has_line'] == 1).round(4)
    return df


# ── [9] Edge sanity check ─────────────────────────────────────────────────────

def print_edge_sanity_check(df):
    lined = df[df['has_line'] == 1].copy()

    print(f"\n{'='*56}")
    print("  EDGE SANITY CHECK")
    print(f"{'='*56}")
    print(f"  Confirmed starters (total today): {len(df)}")
    print(f"  Players with market lines: {len(lined)}")

    if lined.empty:
        print("\n  No market lines available -- cannot compute edge.")
        print("  Check ODDS_API_KEY in .env (https://the-odds-api.com).")
        return

    unlined = df[df['has_line'] == 0]['player_name'].tolist()
    if unlined:
        print(f"  No line found for: {unlined}")

    e = lined['edge'].dropna()

    print(f"\n  Edge = adj_prob - book_implied  (+ means model > book)")
    header = f"  {'Min':>8}  {'P25':>8}  {'Median':>8}  {'Mean':>8}  {'P75':>8}  {'Max':>8}"
    values = (f"  {e.min():>8.1%}  {e.quantile(0.25):>8.1%}  {e.median():>8.1%}  "
              f"{e.mean():>8.1%}  {e.quantile(0.75):>8.1%}  {e.max():>8.1%}")
    print(header)
    print(values)

    n_pos  = (e > 0).sum()
    n_gt5  = (e > 0.05).sum()
    n_gt10 = (e > 0.10).sum()
    print(f"\n  Edge > 0%:   {n_pos:3d}/{len(e)} ({n_pos/len(e):.0%})  model favors over book")
    print(f"  Edge > +5%:  {n_gt5:3d}/{len(e)} ({n_gt5/len(e):.0%})  potential value bets")
    print(f"  Edge > +10%: {n_gt10:3d}/{len(e)} ({n_gt10/len(e):.0%})  high-edge plays (scrutinize)")

    mean_e = e.mean()
    if mean_e > 0.10:
        print(f"\n  *** RED FLAG: mean edge {mean_e:+.1%} is too high. ***")
        print("  Likely causes: model output inflated, or book lines stale.")
        print("  Do NOT bet these edges until the source is identified.")
    elif mean_e > 0.04:
        print(f"\n  CAUTION: mean edge {mean_e:+.1%} is above zero.")
        print("  Typical vig on player props is 8-15%; mean should be slightly negative.")
        print("  May be fine if lines are fresh; verify a few manually.")
    elif mean_e < -0.20:
        print(f"\n  CAUTION: mean edge {mean_e:+.1%} is very negative.")
        print("  Model may be too conservative, or lines have moved.")
    else:
        print(f"\n  Looks healthy -- mean {mean_e:+.1%} is in the expected -15% to +5% range.")

    print(f"\n  Top 10 by edge:")
    cols = ['player_name', 'team_abbr', 'adj_prob', 'book_implied', 'edge', 'best_odds', 'best_book']
    top = lined.nlargest(10, 'edge')[cols].copy()
    top['adj_prob']     = top['adj_prob'].map('{:.1%}'.format)
    top['book_implied'] = top['book_implied'].map('{:.1%}'.format)
    top['edge']         = top['edge'].map(lambda x: f'{x:+.1%}')
    top['best_odds']    = top['best_odds'].map(lambda x: f'+{int(x)}' if x > 0 else str(int(x)))
    print(top.to_string(index=False))

    print(f"\n  Bottom 5 by edge:")
    bot = lined.nsmallest(5, 'edge')[['player_name', 'team_abbr', 'adj_prob',
                                      'book_implied', 'edge', 'best_odds']].copy()
    bot['adj_prob']     = bot['adj_prob'].map('{:.1%}'.format)
    bot['book_implied'] = bot['book_implied'].map('{:.1%}'.format)
    bot['edge']         = bot['edge'].map(lambda x: f'{x:+.1%}')
    bot['best_odds']    = bot['best_odds'].map(lambda x: f'+{int(x)}' if x > 0 else str(int(x)))
    print(bot.to_string(index=False))


# ── [10] Save ─────────────────────────────────────────────────────────────────

def save_output(df, date_str):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'fair_odds_{date_str}.csv')

    out_cols = [
        'player_name', 'team_abbr', 'stand', 'pitcher_name', 'p_throws', 'home_team', 'opp_team',
        'is_home', 'lineup_source',
        'adj_prob', 'fair_odds',
        'has_line', 'best_book', 'best_odds', 'book_implied', 'edge',
        'model_prob', 'k_pct', 'bb_pct', 'contact_rate', 'exp_pa', 'p_contact_game',
        'hr_park_factor', 'temp_f', 'wind_speed', 'wind_favor', 'is_dome',
        'humidity_pct', 'precip_pct', 'wind_description',
        'game_time', 'stadium',
        'season_hr', 'bat_order', 'game_total', 'recent_hr',
        'days_since_hr', 'p_fip',
        # Statcast rolling features — passed through for the web detail card
        'barrel_pct_15', 'hardhit_pct_15', 'flyball_pct_15',
        'avg_ev_15', 'xwoba_15', 'xslg_15',
        'p_barrel_pct_allowed_10', 'p_hardhit_pct_allowed_10', 'p_hr_per_bb_allowed_10',
        # Pitcher season profile, batter-vs-pitcher matchup, season HR by hand
        'pitcher_era', 'pitcher_hr9', 'pitcher_hr_allowed', 'pitcher_ip',
        'vs_pitcher_ab', 'vs_pitcher_h', 'vs_pitcher_hr', 'vs_pitcher_avg',
        'hr_vs_r', 'hr_vs_l',
        'game_date', 'game_id', 'batter',
    ]
    save_cols = [c for c in out_cols if c in df.columns]

    # Sort: players with lines first (edge desc), then no-line (adj_prob desc)
    lined   = df[df['has_line'] == 1].sort_values('edge', ascending=False)
    unlined = df[df['has_line'] == 0].sort_values('adj_prob', ascending=False)
    out = pd.concat([lined, unlined], ignore_index=True)
    out[save_cols].to_csv(path, index=False)
    print(f"\n  Saved {len(out)} rows -> {path}")
    return path


# ── Run summary ───────────────────────────────────────────────────────────────

def print_run_summary(schedule_games, lineups_by_game, already_priced_pks,
                      new_games, credits_events, credits_props, failed_count,
                      credits_remaining, total_priced_today):
    print(f"\n{'='*60}")
    print(f"  RUN SUMMARY")
    print(f"{'='*60}")

    # Per-game table
    header = f"  {'Matchup':<18}  {'State':<8}  Action"
    print(header)
    print(f"  {'-'*56}")
    new_pks = {g['game_pk'] for g in new_games}
    for g in schedule_games:
        pk = g['game_pk']
        matchup = f"{g['away_abbr']} @ {g['home_abbr']}"
        state   = g['status'].capitalize()
        if g['status'] == 'postponed':
            action = "Postponed/cancelled -- removed from card"
        elif pk in already_priced_pks:
            action = "Already priced -- skipped"
        elif g['status'] in ('live', 'final'):
            action = "Started/finished -- skipped (props closed)"
        elif pk in new_pks:
            n = len(lineups_by_game[pk]['starters'])
            src = lineups_by_game[pk]['source']
            action = f"Priced now  ({n} starters, source: {src})"
        elif pk in lineups_by_game:
            # Had lineup but was filtered for another reason
            action = "Skipped (lineup available but already priced)"
        else:
            action = "No lineup yet -- re-run after lineups post"
        print(f"  {matchup:<18}  {state:<8}  {action}")

    # Credit accounting
    provider_label = 'ParlayAPI' if ODDS_PROVIDER == 'parlay_api' else 'OddsAPI'
    print(f"\n  {provider_label} credits used this run:")
    total_this_run = credits_events + credits_props
    if total_this_run == 0:
        print(f"    None (no new games to price)")
    elif ODDS_PROVIDER == 'parlay_api':
        print(f"    Bulk props call:      {credits_props} credits")
    else:
        if credits_events > 0:
            print(f"    Events list:          {credits_events} credit")
        print(f"    Game props ({len(new_games)} events): {credits_props} credits")
    print(f"    Total this run:       {total_this_run} credits")
    if failed_count:
        print(f"    Failed calls:         {failed_count}")
    print(f"  Credits remaining: {credits_remaining}")

    # Day-level summary
    total_games = len(schedule_games)
    n_no_lineup = sum(
        1 for g in schedule_games
        if g['game_pk'] not in already_priced_pks
        and g['game_pk'] not in new_pks
        and g['status'] == 'preview'
        and g['game_pk'] not in lineups_by_game
    )
    print(f"\n  Today's card: {total_priced_today} / {total_games} games priced")
    if n_no_lineup > 0:
        print(f"  {n_no_lineup} game(s) still waiting on lineup announcement")
        print(f"  Re-run once those lineups are posted.")
    elif total_priced_today == total_games:
        print(f"  All games priced -- full card is complete.")
    print(f"{'='*60}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    print(f"\n{'='*56}")
    print(f"  Fair-Odds Conversion  --  {date_str}")
    print(f"{'='*56}")

    # [1] Predictions + existing output
    print("\n[1] Loading predictions and existing output...")
    pred_df = load_predictions(date_str)
    existing_df, already_priced_pks = load_existing_output(date_str)
    existing_df = refresh_context_columns(existing_df, pred_df, date_str)

    # Games where every batter was written with has_line=0 failed to get odds
    # (e.g. wrong odds provider, API outage).  Remove them from already_priced_pks
    # so the next run re-prices them rather than skipping them forever.
    force_reprice_pks: set = set()
    if not existing_df.empty and 'has_line' in existing_df.columns:
        lined_pks = set(
            existing_df.loc[existing_df['has_line'] == 1, 'game_id']
            .dropna().astype(int).unique()
        )
        force_reprice_pks = already_priced_pks - lined_pks
        if force_reprice_pks:
            already_priced_pks -= force_reprice_pks
            print(f"  {len(force_reprice_pks)} game(s) had 0 lines last run -- re-queued: "
                  f"{sorted(force_reprice_pks)}")

    # Games with SOME has_line=True but remaining has_line=False players get re-queued
    # so the missing players can pick up odds on the next run.
    partial_odds_pks: set = set()
    if not existing_df.empty and 'has_line' in existing_df.columns:
        for pk in list(already_priced_pks):
            game_rows = existing_df[existing_df['game_id'] == pk]
            if not game_rows.empty:
                if (game_rows['has_line'] == 1).any() and (game_rows['has_line'] == 0).any():
                    partial_odds_pks.add(pk)
        if partial_odds_pks:
            already_priced_pks -= partial_odds_pks
            print(f"  {len(partial_odds_pks)} game(s) have partial lines -- re-queued for top-up: "
                  f"{sorted(partial_odds_pks)}")

    # [2] Schedule with game states
    print("\n[2] Fetching schedule and game states...")
    schedule_games = fetch_schedule(date_str)
    total_games = len(schedule_games)
    print(f"  {total_games} game(s) on slate")

    if not schedule_games:
        print("  No games scheduled. Exiting.")
        return pd.DataFrame()

    # [3] Lineups per game
    print("\n[3] Fetching confirmed lineups by game...")
    lineups_by_game = fetch_lineups_by_game(date_str, schedule_games)
    n_with_lineups = len(lineups_by_game)
    print(f"  {n_with_lineups} / {total_games} games have confirmed lineups")

    # Classify each game
    new_games      = []   # to price this run
    skip_priced    = []   # already in today's CSV
    skip_started   = []   # live or final, not yet priced (props closed)
    skip_no_lineup = []   # preview but lineups not yet posted
    skip_postponed = []   # postponed, cancelled, or suspended
    partial_reprice_pks = set()  # games being re-run to pick up a late-posting lineup

    # Build set of batter IDs already in existing output for partial-game detection
    already_priced_batters = (
        set(existing_df['batter'].dropna().astype(int))
        if not existing_df.empty else set()
    )

    for g in schedule_games:
        pk = g['game_pk']
        if g['status'] == 'postponed':
            skip_postponed.append(g)
        elif pk in already_priced_pks:
            # If this game now has confirmed lineup players absent from the
            # existing output, one team's lineup posted after the last run.
            # Re-process the whole game so both sides get priced.
            if pk in lineups_by_game:
                missing = lineups_by_game[pk]['starters'] - already_priced_batters
                if missing:
                    new_games.append(g)
                    partial_reprice_pks.add(pk)
                else:
                    skip_priced.append(g)
            else:
                skip_priced.append(g)
        elif g['status'] in ('live', 'final'):
            skip_started.append(g)
        elif pk in lineups_by_game:
            new_games.append(g)
        else:
            skip_no_lineup.append(g)

    # Strip rows for postponed/cancelled games so they don't appear on the card
    postponed_pks = {g['game_pk'] for g in skip_postponed}
    if not existing_df.empty and postponed_pks:
        before = len(existing_df)
        existing_df = existing_df[~existing_df['game_id'].isin(postponed_pks)]
        removed = before - len(existing_df)
        if removed:
            labels = [f"{g['away_abbr']}@{g['home_abbr']}" for g in skip_postponed]
            print(f"  Removed {removed} player(s) for postponed/cancelled game(s): {labels}")

    print(f"  Newly priceable:        {len(new_games)}"
          + (f" ({len(partial_reprice_pks)} partial top-up)" if partial_reprice_pks else ""))
    print(f"  Already priced today:   {len(skip_priced)}")
    print(f"  Started / finished:     {len(skip_started)}")
    if skip_postponed:
        labels = [f"{g['away_abbr']}@{g['home_abbr']}" for g in skip_postponed]
        print(f"  Postponed/cancelled:    {len(skip_postponed)}  {labels}")
    print(f"  No lineup yet:          {len(skip_no_lineup)}")

    # Track credits for summary
    credits_events = 0
    credits_props  = 0
    failed_count   = 0
    credits_remaining = '?'
    all_odds_df    = pd.DataFrame()

    if not new_games:
        if existing_df.empty:
            print("\n  No games ready to price yet. Re-run after lineups are posted.")
        else:
            # Merge any pass-through columns that were added to predictions since last run
            passthrough = [
                c for c in pred_df.columns
                if c not in existing_df.columns
                and c not in ('game_date', 'player_name', 'team_abbr', 'stand',
                              'pitcher_name', 'p_throws', 'home_team', 'opp_team', 'lineup_source')
            ]
            if passthrough:
                merge_src = pred_df[['game_id', 'batter'] + passthrough].drop_duplicates(['game_id', 'batter'])
                existing_df = existing_df.merge(merge_src, on=['game_id', 'batter'], how='left')
                # bat_order from already-fetched lineups
                if 'bat_order' not in existing_df.columns:
                    combined_bo = {}
                    for info in lineups_by_game.values():
                        combined_bo.update(info.get('batting_order', {}))
                    existing_df['bat_order'] = existing_df['batter'].map(combined_bo)
                print(f"\n  Enriched existing output with {len(passthrough)} new column(s).")
            else:
                print("\n  No new games to price this run -- refreshed context columns "
                      "(days since HR, recent HR, season HR).")
            save_output(existing_df, date_str)
        print_run_summary(schedule_games, lineups_by_game, already_priced_pks,
                          new_games, credits_events, credits_props, failed_count,
                          credits_remaining, len(already_priced_pks))
        return existing_df

    # [4] Filter predictions to new games + apply lineup filter
    print("\n[4] Applying lineup filter for new games...")
    new_pks = {g['game_pk'] for g in new_games}
    new_pred_df = pred_df[pred_df['game_id'].isin(new_pks)].copy()

    # Combine starter IDs and batting order across all new games
    combined_starter_ids = set()
    combined_batting_order = {}
    source_priority = {'mlb_schedule': 1, 'live_feed': 2}
    best_source = 'mlb_schedule'
    for g in new_games:
        info = lineups_by_game[g['game_pk']]
        combined_starter_ids |= info['starters']
        combined_batting_order.update(info.get('batting_order', {}))
        if source_priority.get(info['source'], 0) > source_priority.get(best_source, 0):
            best_source = info['source']

    new_starters_df, _ = apply_lineup_filter(
        new_pred_df, combined_starter_ids, best_source, combined_batting_order
    )
    if new_starters_df.empty:
        print("  No starters matched predictions for new games -- check player ID alignment.")
        print_run_summary(schedule_games, lineups_by_game, already_priced_pks,
                          new_games, credits_events, credits_props, failed_count,
                          credits_remaining, len(already_priced_pks))
        return existing_df

    # Refine adj_prob using actual batting order (replaces flat EXP_PA_DEFAULT)
    if new_starters_df['bat_order'].notna().any():
        exp_pa = new_starters_df['bat_order'].map(EXP_PA_BY_ORDER).fillna(EXP_PA_DEFAULT)
        cr = new_starters_df.get('contact_rate', None)
        mp = new_starters_df.get('model_prob', None)
        if cr is not None and mp is not None:
            new_starters_df = new_starters_df.copy()
            new_starters_df['exp_pa'] = exp_pa
            new_starters_df['p_contact_game'] = 1 - (1 - new_starters_df['contact_rate'].fillna(0.7)) ** exp_pa
            new_starters_df['adj_prob'] = new_starters_df['model_prob'] * new_starters_df['p_contact_game']
            print(f"  Refined adj_prob using batting order "
                  f"(exp_pa range: {exp_pa.min():.1f}-{exp_pa.max():.1f})")

    # Tag batters with a HR in their last 5 games
    hot_batters = fetch_recent_hr_batters(date_str, set(new_starters_df['batter']))
    new_starters_df = new_starters_df.copy()
    new_starters_df['recent_hr'] = new_starters_df['batter'].isin(hot_batters).astype(int)
    if hot_batters:
        hot_names = new_starters_df.loc[
            new_starters_df['batter'].isin(hot_batters), 'player_name'
        ].tolist()
        print(f"  HOT (HR in last 5 games): {hot_names}")

    # [5-7] Fetch market lines (provider-selected via ODDS_PROVIDER env var)
    game_totals       = {}
    game_to_event     = {}
    all_odds_df       = pd.DataFrame()

    if ODDS_PROVIDER == 'parlay_api':
        # ── ParlayAPI: one bulk call replaces the events-list + per-event calls ──
        print(f"\n[5-7] Fetching HR props from ParlayAPI (bulk call, 3 credits)...")
        (pa_events, all_odds_df, game_totals,
         credits_props, failed_count, credits_remaining) = fetch_props_parlay_api(date_str)

        print(f"\n[6] Matching games to ParlayAPI events...")
        game_to_event = match_games_to_events(new_games, pa_events)
        matched   = [g for g in new_games if g['game_pk'] in game_to_event]
        unmatched = [g for g in new_games if g['game_pk'] not in game_to_event]
        print(f"  Matched: {len(matched)} / {len(new_games)} new games to ParlayAPI events")
        if unmatched:
            labels = [f"{g['away_abbr']}@{g['home_abbr']}" for g in unmatched]
            print(f"  No ParlayAPI event found for: {labels} (will price without lines)")

    else:
        # ── OddsAPI: events list (1 credit) + per-event props (1 credit each) ──
        print("\n[5] Fetching OddsAPI events list...")
        today_events, credits_remaining = fetch_events_list(date_str)
        if today_events:
            credits_events = 1

        print("\n[6] Matching games to OddsAPI events...")
        game_to_event = match_games_to_events(new_games, today_events)
        matched   = [g for g in new_games if g['game_pk'] in game_to_event]
        unmatched = [g for g in new_games if g['game_pk'] not in game_to_event]
        print(f"  Matched: {len(matched)} / {len(new_games)} new games to OddsAPI events")
        if unmatched:
            labels = [f"{g['away_abbr']}@{g['home_abbr']}" for g in unmatched]
            print(f"  No OddsAPI event found for: {labels} (will price without lines)")

        new_event_ids = [game_to_event[g['game_pk']] for g in matched]
        if new_event_ids:
            print(f"\n[7] Fetching HR props for {len(new_event_ids)} new event(s)...")
            all_odds_df, game_totals, credits_props, failed_count, credits_remaining = \
                fetch_props_for_events(new_event_ids)
            if not all_odds_df.empty:
                n_books = all_odds_df['bookmaker'].nunique()
                avg     = all_odds_df.groupby('name_norm').size().mean()
                print(f"  {len(_best_lines(all_odds_df))} players with lines | "
                      f"{n_books} bookmaker(s) | {avg:.1f} lines/player avg")
            if game_totals:
                print(f"  {len(game_totals)} game O/U total(s) fetched: "
                      f"{[f'{v}' for v in game_totals.values()]}")
        else:
            print("\n[7] No new events to fetch odds for.")

    best_odds_df = _best_lines(all_odds_df)

    # [8] Join odds + edge for new starters
    print("\n[8] Joining odds and computing edge...")
    new_result_df = join_odds_and_edge(new_starters_df, best_odds_df)

    # Map event_id -> game_pk -> game_total and attach to each row
    if game_totals:
        event_to_pk = {v: k for k, v in game_to_event.items()}
        game_total_by_pk = {event_to_pk[eid]: total
                            for eid, total in game_totals.items()
                            if eid in event_to_pk}
        new_result_df = new_result_df.copy()
        new_result_df['game_total'] = new_result_df['game_id'].map(game_total_by_pk)
    n_lined = new_result_df['has_line'].sum()
    print(f"  {n_lined} / {len(new_result_df)} new starters matched to market lines")
    if not best_odds_df.empty and n_lined < len(new_result_df):
        unmatched_names = new_result_df[new_result_df['has_line'] == 0]['player_name'].tolist()
        print(f"  Name-match misses: {unmatched_names}")

    # [9] Merge with previously priced players
    # Strip stale rows only for games being actively re-priced this run.
    # Intersect with new_pks so games that ended up skip_started/skip_no_lineup
    # keep their existing rows in the CSV (their DB rows are preserved by upsert).
    all_reprice_pks = (partial_reprice_pks | force_reprice_pks | partial_odds_pks) & new_pks
    if not existing_df.empty and all_reprice_pks:
        existing_df = existing_df[~existing_df['game_id'].isin(all_reprice_pks)]
    if not existing_df.empty:
        combined_df = pd.concat([existing_df, new_result_df], ignore_index=True)
        print(f"\n  Merged: {len(existing_df)} existing + {len(new_result_df)} new "
              f"= {len(combined_df)} total players")
    else:
        combined_df = new_result_df

    # [10] Edge sanity check across full combined output
    print_edge_sanity_check(combined_df)

    # [11] Save combined output
    out_path = save_output(combined_df, date_str)

    # [12] Run summary
    total_priced_pks = already_priced_pks | new_pks
    print_run_summary(schedule_games, lineups_by_game, already_priced_pks,
                      new_games, credits_events, credits_props, failed_count,
                      credits_remaining, len(total_priced_pks))

    return combined_df


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
