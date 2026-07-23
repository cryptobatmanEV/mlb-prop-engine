"""
Shared ParlayAPI odds-fetching for the Hits / Total Bases / Batter Ks models.

Mirrors the proven 3-bookmaker-group pattern from predict/fair_odds.py's
fetch_props_parlay_api (HR model), generalized to take a market key + valid
line set. The HR pipeline is untouched and does not import this module.

Verified against the real ParlayAPI response (2026-07-16 slate) before
integration:
  - player_hits: line=0.5 (primary, "1+ hits") and line=1.5 (secondary,
    "2+ hits") both appear under the SAME market_key.
  - player_total_bases: line=0.5 ("1+ TB") and line=1.5 ("2+ TB", the
    dominant/primary line by volume) both appear under the SAME market_key.
    NOTE: this differs from the original spec's "primary 1.5 / secondary 2.5"
    -- real market volume at 2.5 is on the player_total_bases_alt milestone
    market instead, and 1.5/0.5 map cleanly onto tb_2plus/tb_1plus, matching
    the Hits model's pattern. Using 0.5 -> p_tb_1plus, 1.5 -> p_tb_2plus.
  - player_strikeouts: PITCHER strikeouts-thrown and BATTER strikeout props
    share this same market_key (not separate as the spec assumed). They are
    distinguished only by line value: pitcher K props use lines >= 3.5,
    batter K props use lines 0.5/1.5. Filtering to line in (0.5, 1.5) isolates
    batter strikeout props.
"""
import os
import requests
import pandas as pd
import unicodedata
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

PARLAY_KEY  = os.getenv('PARLAY_API_KEY')
PARLAY_BASE = 'https://parlay-api.com/v1'

_BK_GROUPS = [
    'pinnacle,betrivers,novig,betmgm,bet365',
    'draftkings',
    'fanduel',
]


def _parlay_get(path, params=None, timeout=30):
    if not PARLAY_KEY:
        raise ValueError("PARLAY_API_KEY not set in environment")
    r = requests.get(f'{PARLAY_BASE}{path}',
                      headers={'X-API-Key': PARLAY_KEY},
                      params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r, r.json()


def american_to_implied(odds):
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)


def norm_name(name):
    name = unicodedata.normalize('NFKD', str(name))
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return re.sub(r'[^a-z ]', '', name.lower().strip())


def fetch_batter_props(date_str, market_key, valid_lines):
    """
    Fetch one batter-prop market from ParlayAPI using the 3-bookmaker-group
    call pattern (9 credits total). Returns rows for BOTH lines in
    valid_lines (e.g. {0.5, 1.5}) so the caller can build both display lines.

    Returns:
        events_for_matching  list[dict]
        all_lines_df         DataFrame -- player_name_raw, bookmaker, line,
                                           over_odds, under_odds, event_id,
                                           over_implied, under_implied, name_norm
        credits_used, failed_count, credits_remaining
    """
    if not PARLAY_KEY:
        print("  PARLAY_API_KEY not set -- skipping market lines.")
        return [], pd.DataFrame(), 0, 0, '?'

    window_start = f"{date_str}T00:00:00Z"
    next_day     = (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime('%Y-%m-%d')
    window_end   = f"{next_day}T09:00:00Z"

    all_raw_rows = []
    credits_remaining = '?'
    credits_used = 0
    failed_count = 0

    for bookmakers in _BK_GROUPS:
        try:
            r, raw = _parlay_get('/sports/baseball_mlb/props',
                                  params={'markets': market_key, 'bookmakers': bookmakers})
            credits_remaining = r.headers.get('x-requests-remaining',
                                r.headers.get('x-credits-remaining', '?'))
            credits_used += 3
            chunk = raw if isinstance(raw, list) else raw.get('data', raw.get('results', raw.get('props', [])))
            all_raw_rows.extend(chunk)
        except requests.HTTPError as e:
            code = e.response.status_code
            failed_count += 1
            print(f"  ParlayAPI call failed ({code}) for [{bookmakers}] market={market_key}")
        except Exception as e:
            failed_count += 1
            print(f"  ParlayAPI error for [{bookmakers}] market={market_key}: {e}")

    if not all_raw_rows:
        return [], pd.DataFrame(), credits_used, failed_count, credits_remaining

    # ParlayAPI occasionally returns two rows for the exact same
    # (player, bookmaker, market_key, line) -- observed 2026-07-23 for
    # DraftKings player_hits: a stale/mislabeled "Hits O/U" row (e.g.
    # over +310/under -450) alongside the real current "Hits" price
    # (over -239/under +177) for the same market. Keeping whichever row
    # happened to come first in the raw API array was arbitrary and could
    # (and did) surface the wrong price. Keep whichever row has the later
    # last_update instead; if either timestamp is missing/unparseable,
    # fall back to keeping the first-seen row (previous behavior).
    def _parse_last_update(row):
        ts = row.get('last_update')
        if not ts:
            return None
        try:
            return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None

    best_by_key = {}
    for row in all_raw_rows:
        key = (row.get('player'), row.get('bookmaker'), row.get('market_key'), row.get('line'))
        if key not in best_by_key:
            best_by_key[key] = row
            continue
        existing_ts = _parse_last_update(best_by_key[key])
        new_ts = _parse_last_update(row)
        if new_ts is not None and existing_ts is not None and new_ts > existing_ts:
            best_by_key[key] = row
    deduped = list(best_by_key.values())

    prop_rows, seen_events = [], {}
    for row in deduped:
        ct = row.get('commence_time', '')
        if not (window_start <= ct < window_end):
            continue

        eid = row.get('canonical_event_id', '')
        if eid and eid not in seen_events:
            seen_events[eid] = {
                'id': eid,
                'home_team': row.get('home_team', ''),
                'away_team': row.get('away_team', ''),
                'commence_time': ct,
            }

        if row.get('market_key') != market_key:
            continue
        if row.get('is_dfs_flat_payout'):
            continue
        line = row.get('line')
        if line is None or float(line) not in valid_lines:
            continue
        over_price  = row.get('over_price')
        under_price = row.get('under_price')
        if over_price is None and under_price is None:
            continue
        player = row.get('player', '')
        # Guard against milestone-style rows where 'player' holds a
        # threshold ('1+', '2+') instead of an actual name.
        if not player or player.strip().rstrip('+').isdigit():
            continue

        prop_rows.append({
            'player_name_raw':   player,
            'bookmaker':         row.get('bookmaker', ''),
            'line':              float(line),
            'over_odds':         int(over_price) if over_price is not None else None,
            'under_odds':        int(under_price) if under_price is not None else None,
            'event_id':          eid,
        })

    events_for_matching = list(seen_events.values())
    n_events = len(events_for_matching)

    if not prop_rows:
        print(f"  ParlayAPI: 0 {market_key} lines in today's window across {n_events} event(s) "
              f"| {credits_remaining} credits remaining")
        return events_for_matching, pd.DataFrame(), credits_used, failed_count, credits_remaining

    all_df = pd.DataFrame(prop_rows)
    all_df['over_implied']  = all_df['over_odds'].apply(lambda o: american_to_implied(o) if pd.notna(o) else None)
    all_df['under_implied'] = all_df['under_odds'].apply(lambda o: american_to_implied(o) if pd.notna(o) else None)
    all_df['name_norm'] = all_df['player_name_raw'].apply(norm_name)

    n_players = all_df['name_norm'].nunique()
    n_books   = all_df['bookmaker'].nunique()
    print(f"  ParlayAPI [{market_key}]: {n_players} players | {n_books} book(s) | "
          f"{n_events} event(s) | {credits_remaining} credits remaining")

    return events_for_matching, all_df, credits_used, failed_count, credits_remaining
