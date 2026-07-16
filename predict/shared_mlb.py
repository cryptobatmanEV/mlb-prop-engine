"""
Shared MLB Stats API helpers used by all four Batter Model pipelines
(Home Runs, Hits, Total Bases, Strikeouts).

Extracted from predict/daily_runner.py and predict/fair_odds.py so the new
models reuse the same schedule/roster/lineup-fetching logic instead of each
duplicating it. The existing HR pipeline (daily_runner.py, fair_odds.py) is
left untouched and does NOT import from here -- this module exists purely
for the three new models.
"""
import time
import requests
import pandas as pd

# Statcast team abbreviation -> MLB Stats API team ID
TEAM_ID = {
    'ARI':109, 'AZ':109, 'ATL':144, 'BAL':110, 'BOS':111,
    'CHC':112, 'CWS':145, 'CIN':113, 'CLE':114, 'COL':115,
    'DET':116, 'HOU':117, 'KC':118,  'LAA':108, 'LAD':119,
    'MIA':146, 'MIL':158, 'MIN':142, 'NYM':121, 'NYY':147,
    'OAK':133, 'ATH':133, 'PHI':143, 'PIT':134, 'SD':135,
    'SF':137,  'SEA':136, 'STL':138, 'TB':139,  'TEX':140,
    'TOR':141, 'WSH':120,
}
# MLB Stats API team ID -> Statcast abbreviation (prefer 3-letter over 2-letter)
TEAM_ABB = {v: k for k, v in TEAM_ID.items()}
TEAM_ABB.update({109: 'ARI', 133: 'ATH'})


def _mlb(path, params, timeout=20):
    """Thin wrapper around the MLB Stats API."""
    r = requests.get(f'https://statsapi.mlb.com/api/v1/{path}',
                      params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


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


def fetch_schedule(date_str, stadiums=None):
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
                'stadium':           (stadiums or {}).get(home_abbr, {}).get('name'),
            })
    return games


def fetch_roster(team_id, season):
    """
    Returns list of {player_id, name} for active position players on a team.
    Pitchers are excluded (they don't have batter props).
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


def fetch_lineups_by_game(date_str, schedule_games):
    """
    Returns {game_pk: {'starters': set[int], 'source': str, 'batting_order': {batter_id: 1-9}}}
    for every game where a confirmed lineup is available.
    Games with no lineup data are absent from the dict.

    Source 1: schedule hydrate=lineups (pre-game, 9 per side)
    Source 2: live game feed battingOrder (fallback for Live games)
    """
    result = {}

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

    live_pks = [g['game_id'] for g in schedule_games
                if g['status'] == 'Live' and g['game_id'] not in result]
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


def fetch_pitcher_season_stats(season):
    """
    Fetch this season's ERA, HR allowed, K, IP for all pitchers from the
    MLB Stats API. One bulk call.
    """
    def _parse_ip(ip_str):
        try:
            parts = str(ip_str).split('.')
            full   = int(parts[0])
            thirds = int(parts[1]) if len(parts) > 1 else 0
            return full + thirds / 3.0
        except (ValueError, IndexError, AttributeError):
            return 0.0

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
            k  = int(s['stat'].get('strikeOuts', 0) or 0)
            h  = int(s['stat'].get('hits', 0) or 0)
            bb = int(s['stat'].get('baseOnBalls', 0) or 0)
            rows.append({
                'pitcher_id':         s['player']['id'],
                'pitcher_era':        float(s['stat'].get('era', 0) or 0),
                'pitcher_hr_allowed': hr,
                'pitcher_h_allowed':  h,
                'pitcher_bb_allowed': bb,
                'pitcher_k':          k,
                'pitcher_ip':         ip,
                'pitcher_hr9':        hr / ip * 9,
                'pitcher_h9':         h / ip * 9,
                'pitcher_k9':         k / ip * 9,
            })
        df = pd.DataFrame(rows)
        print(f"  Pitcher season stats: {len(df)} pitchers with IP > 0")
        return df
    except Exception as e:
        print(f"  WARNING: pitcher season stats fetch failed ({e})")
        return pd.DataFrame(columns=['pitcher_id', 'pitcher_era', 'pitcher_hr_allowed',
                                      'pitcher_h_allowed', 'pitcher_bb_allowed', 'pitcher_k',
                                      'pitcher_ip', 'pitcher_hr9', 'pitcher_h9', 'pitcher_k9'])


def fetch_team_k_rate(season):
    """
    Team-level strikeout rate this season (opp_k_pct_15 uses this as a
    slower-moving fallback/context feature). Returns DataFrame: team_id, team_k_pct.
    """
    try:
        rows = []
        team_data = _mlb('teams/stats', {
            'stats': 'season', 'group': 'hitting', 'sportId': 1, 'season': season,
        })
        for s in team_data.get('stats', [{}])[0].get('splits', []):
            pa = s['stat'].get('plateAppearances') or 0
            so = s['stat'].get('strikeOuts') or 0
            team_id = s.get('team', {}).get('id')
            if pa > 0 and team_id:
                rows.append({'team_id': team_id, 'team_k_pct': so / pa})
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"  WARNING: team K rate fetch failed ({e})")
        return pd.DataFrame(columns=['team_id', 'team_k_pct'])
