"""
Priority 4: Fair-odds conversion with confirmed-lineup filter.

Usage:
    python predict/fair_odds.py              # today
    python predict/fair_odds.py 2026-06-07   # specific date

Pipeline:
    [1] Load today's adj_prob predictions from the daily runner
    [2] Fetch confirmed starting lineups from the MLB Stats API (hydrate=lineups)
    [3] HARD FILTER — keep only confirmed starters; log every dropped player
    [4] Fetch OddsAPI batter_home_runs lines  (requires a valid ODDSPAPI_KEY in .env)
    [5] Join lines onto confirmed starters by normalized player name
    [6] Compute edge = adj_prob - book_implied_prob
    [7] Print edge distribution for sanity-checking
    [8] Save data/outputs/fair_odds_YYYY-MM-DD.csv

OddsAPI note:
    The ODDSPAPI_KEY in your .env must be a valid key from https://the-odds-api.com
    If the key is invalid or the batter_home_runs market is unavailable on your tier,
    the script will still run — it will show predictions with fair_odds but no edge.
    Get a key at: https://the-odds-api.com  (free tier includes player props).
"""

import os, re, sys, time, unicodedata
import numpy as np
import pandas as pd
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

ODDS_KEY  = os.getenv('ODDS_API_KEY') or os.getenv('ODDSPAPI_KEY')
MLB_BASE  = 'https://statsapi.mlb.com/api/v1'
ODDS_BASE = 'https://api.the-odds-api.com'
PRED_DIR  = 'data/predictions'
OUT_DIR   = 'data/outputs'


# ── Shared utilities ──────────────────────────────────────────────────────────

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

def american_to_implied(odds):
    """American odds → implied probability (vig included, not stripped)."""
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)

def implied_to_american(p):
    """Model probability → fair-value American odds (what we'd price the line at)."""
    if pd.isna(p) or p <= 0 or p >= 1:
        return None
    if p >= 0.5:
        return int(round(-p / (1.0 - p) * 100))
    return int(round((1.0 - p) / p * 100))

def norm_name(name):
    """
    Normalize a player name for fuzzy matching across data sources.
    Strips accents, lowercases, removes non-alpha characters.
    e.g. "José Ramírez" → "jose ramirez"   "Pete O'Brien" → "pete obrien"
    """
    name = unicodedata.normalize('NFKD', str(name))
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return re.sub(r'[^a-z ]', '', name.lower().strip())


# ── [1] Load predictions ──────────────────────────────────────────────────────

def load_predictions(date_str):
    """
    Load the daily_runner output CSV for date_str.
    If the file doesn't exist, calls daily_runner.run() to generate it first.
    """
    path = os.path.join(PRED_DIR, f'predictions_{date_str}.csv')
    if os.path.exists(path):
        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} predictions from {path}")
        return df

    print(f"  No predictions file for {date_str} — running daily_runner first...")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import predict.daily_runner as runner
    runner.run(date_str)
    if not os.path.exists(path):
        raise SystemExit("daily_runner did not produce output — check for errors above.")
    df = pd.read_csv(path)
    print(f"  Generated and loaded {len(df)} predictions.")
    return df


# ── [2] Confirmed starting lineups ───────────────────────────────────────────

def fetch_starting_lineups(date_str):
    """
    Returns (starter_id_set, source_label).

    Tries two MLB Stats API sources in order:

    Source 1 — schedule hydrate=lineups
        Pre-game lineups announced by each team (typically 3-4 hours before first pitch).
        Returns exactly 9 home + 9 away players per game when available.

    Source 2 — live game feed battingOrder
        Available once a game's batting order locks / game starts.
        Used as a fallback if hydrate=lineups hasn't populated yet.

    Returns (empty set, 'none') only if both sources have no data for every game.
    The caller will flag all players as unconfirmed in that case.
    """
    starter_ids = set()

    # — Source 1: schedule hydrate=lineups —
    try:
        data = _mlb('schedule', {
            'sportId': 1, 'date': date_str,
            'hydrate': 'lineups,team', 'gameType': 'R',
        })
        for date_block in data.get('dates', []):
            for game in date_block.get('games', []):
                for side in ('homePlayers', 'awayPlayers'):
                    for p in game.get('lineups', {}).get(side, []):
                        # Universal DH means pitchers never appear in batting lineups,
                        # but keep this guard in case the rule ever changes.
                        if p.get('primaryPosition', {}).get('type') != 'Pitcher':
                            starter_ids.add(int(p['id']))
        if starter_ids:
            return starter_ids, 'mlb_schedule'
        print("  hydrate=lineups returned 0 starters — lineups not yet announced.")
    except Exception as e:
        print(f"  hydrate=lineups failed: {e}")

    # — Source 2: live game feed battingOrder —
    # Pull the game PKs from the schedule (without lineup hydration, which already failed)
    try:
        sched = _mlb('schedule', {'sportId': 1, 'date': date_str, 'gameType': 'R'})
        game_pks = [
            g['gamePk']
            for d in sched.get('dates', [])
            for g in d.get('games', [])
        ]
    except Exception:
        game_pks = []

    found_any = False
    for pk in game_pks:
        try:
            r = requests.get(
                f'https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live',
                timeout=10
            )
            r.raise_for_status()
            box = r.json().get('liveData', {}).get('boxscore', {}).get('teams', {})
            for side in ('home', 'away'):
                for pid in box.get(side, {}).get('battingOrder', []):
                    starter_ids.add(int(pid))
                    found_any = True
            time.sleep(0.2)
        except Exception:
            pass

    if found_any:
        return starter_ids, 'live_feed'

    return set(), 'none'


# ── [3] Hard lineup filter ─────────────────────────────────────────────────────

def apply_lineup_filter(pred_df, starter_ids, starter_source):
    """
    The core requirement of Priority 4: only price confirmed starters.

    Every player in pred_df gets a 'lineup_source' label:
        mlb_schedule / live_feed  → confirmed starter, priced
        not_in_lineup             → bench / no confirmation, DROPPED
        unconfirmed               → no lineup data available at all (rare edge case)

    The count and a name sample of dropped players are always printed so
    nothing is silently discarded.

    Returns (starters_df, dropped_df).
    """
    pred_df = pred_df.copy()

    if starter_ids:
        pred_df['in_lineup'] = pred_df['batter'].isin(starter_ids).astype(int)
        pred_df['lineup_source'] = pred_df['in_lineup'].map(
            {1: starter_source, 0: 'not_in_lineup'}
        )
    else:
        pred_df['in_lineup'] = 0
        pred_df['lineup_source'] = 'unconfirmed'

    starters = pred_df[pred_df['in_lineup'] == 1].copy()
    dropped  = pred_df[pred_df['in_lineup'] == 0].copy()

    n_total   = len(pred_df)
    n_kept    = len(starters)
    n_dropped = len(dropped)

    print(f"\n  {'-'*52}")
    print(f"  LINEUP FILTER  (source: {starter_source})")
    print(f"  Scored:  {n_total:4d}  position players from active roster")
    print(f"  Kept:    {n_kept:4d}  confirmed starters  <- will be priced")
    print(f"  DROPPED: {n_dropped:4d}  bench / not in confirmed lineup  <- not priced")
    print(f"  {'-'*52}")

    if n_dropped > 0:
        dropped_names = sorted(dropped['player_name'].tolist())
        if n_dropped <= 20:
            print(f"  Dropped: {dropped_names}")
        else:
            print(f"  Dropped (first 20 of {n_dropped}): {dropped_names[:20]}")

    if n_kept == 0:
        print("\n  WARNING: Zero confirmed starters after filter.")
        if starter_source == 'none':
            print("  Lineups have not been released yet. Re-run after ~3:00 PM ET.")
        else:
            print("  Check that today's predictions use the same MLBAM player IDs as the lineup.")

    return starters, dropped


# ── [4] OddsAPI HR prop lines ─────────────────────────────────────────────────

def fetch_hr_odds(date_str):
    """
    Fetch batter_home_runs (Over 0.5) lines for today's MLB games from OddsAPI.

    On success  → returns (all_df, best_df)
                   all_df  : one row per (player, bookmaker)
                   best_df : one row per player, keeping the most generous
                             (highest payout = highest American odds) line

    On any failure → prints a clear message and returns (empty, empty).

    Typical failure modes:
        401  INVALID_KEY  — key is wrong; get a new one at https://the-odds-api.com
        422              — batter_home_runs market unavailable on your plan tier
        200 but empty    — no games found for date_str in OddsAPI
    """
    if not ODDS_KEY:
        print("  ODDS_API_KEY is not set in .env - skipping market lines.")
        return pd.DataFrame(), pd.DataFrame()

    # Step 4a: get today's event IDs
    try:
        r, events = _odds_get('/v4/sports/baseball_mlb/events',
                              {'dateFormat': 'iso'})
        remaining = r.headers.get('x-requests-remaining', '?')
    except requests.HTTPError as e:
        code = e.response.status_code
        body = e.response.json() if e.response.text else {}
        if code == 401:
            print(f"  OddsAPI: invalid key (401). "
                  f"Get a valid key at https://the-odds-api.com")
            print(f"  Error detail: {body.get('message','')}")
        else:
            print(f"  OddsAPI events failed ({code}): {body}")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        print(f"  OddsAPI events error: {e}")
        return pd.DataFrame(), pd.DataFrame()

    # Accept games whose commence_time falls within the 36-hour window starting at
    # midnight of date_str (UTC). This covers all US time zones: a 7 PM ET game
    # on June 7 has commence_time 2026-06-08T00:31Z, so a naive date-string match
    # would miss it. The 36-hour ceiling (09:00 UTC next-next day) excludes the
    # following day's afternoon games from bleeding into this slate.
    from datetime import datetime, timedelta
    window_start = f"{date_str}T00:00:00Z"
    next_day = (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime('%Y-%m-%d')
    window_end = f"{next_day}T09:00:00Z"
    today_events = [
        e for e in events
        if window_start <= e.get('commence_time', '') < window_end
    ]
    print(f"  {len(today_events)} events in window [{date_str} 00:00Z - {next_day} 09:00Z]"
          f" | {remaining} API calls remaining")
    if not today_events:
        print(f"  No events for {date_str} in OddsAPI window (they may not be listed yet).")
        return pd.DataFrame(), pd.DataFrame()

    # Step 4b: fetch batter_home_runs odds per event
    rows, failed = [], 0
    for ev in today_events:
        try:
            _, data = _odds_get(
                f'/v4/sports/baseball_mlb/events/{ev["id"]}/odds',
                {'regions': 'us,us_ex', 'markets': 'batter_home_runs', 'oddsFormat': 'american'},
            )
            for bm in data.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] != 'batter_home_runs':
                        continue
                    for outcome in mkt.get('outcomes', []):
                        # Only take "Over 0.5 HRs" = standard anytime-HR prop.
                        # Exclude point=1.5 (2+ HRs) and point=2.5 (3+ HRs) —
                        # those are different markets with far higher prices and
                        # would corrupt the edge calculation if mixed in.
                        if outcome.get('name') == 'Over' and outcome.get('point', 0) == 0.5:
                            rows.append({
                                'player_name_raw': outcome.get('description', ''),
                                'bookmaker':       bm['key'],
                                'odds_american':   int(outcome['price']),
                                'event_id':        ev['id'],
                            })
            time.sleep(0.4)
        except requests.HTTPError as e:
            code = e.response.status_code
            if code == 422:
                # Market unavailable — likely plan restriction; no point continuing
                print(f"  batter_home_runs market unavailable (422). "
                      f"This market may require a higher OddsAPI tier.")
                return pd.DataFrame(), pd.DataFrame()
            failed += 1
        except Exception:
            failed += 1

    if failed:
        print(f"  {failed}/{len(today_events)} events had errors fetching odds.")

    if not rows:
        print("  No batter_home_runs lines returned. "
              "Verify your OddsAPI key has access to player props.")
        return pd.DataFrame(), pd.DataFrame()

    all_df = pd.DataFrame(rows)
    all_df['implied']    = all_df['odds_american'].apply(american_to_implied)
    all_df['name_norm']  = all_df['player_name_raw'].apply(norm_name)

    # Best line = highest American odds (most favorable payout for the bettor)
    best_df = (all_df
               .sort_values('odds_american', ascending=False)
               .groupby('name_norm', as_index=False)
               .first())

    n_books = all_df['bookmaker'].nunique()
    avg_lines = all_df.groupby('name_norm').size().mean()
    print(f"  {len(best_df)} players with lines | "
          f"{n_books} bookmakers | {avg_lines:.1f} lines/player avg")

    return all_df, best_df


# ── [5] Join odds and compute edge ────────────────────────────────────────────

def join_odds_and_edge(starters_df, best_odds_df):
    """
    Left-join market lines onto confirmed starters by normalized player name.

    New columns added:
        has_line      — 1 if a market line was found, 0 otherwise
        best_book     — bookmaker offering the most generous (highest) line
        best_odds     — American odds for that line  (e.g. +550)
        book_implied  — raw implied probability from that line  (vig included)
        fair_odds     — our model's fair-value American odds derived from adj_prob
        edge          — adj_prob - book_implied
                        Positive = we think this player is MORE likely to HR than
                        the book implies. Negative = we think LESS likely (or vig).

    Note on vig: book_implied_prob INCLUDES the book's margin (~8-15% on player props).
    A true edge requires adj_prob to exceed book_implied by more than the embedded vig.
    As a rough rule of thumb, only edges > +5% are worth investigating further.
    """
    df = starters_df.copy()
    df['name_norm'] = df['player_name'].apply(norm_name)
    df['fair_odds'] = df['adj_prob'].apply(implied_to_american)

    if best_odds_df.empty:
        df['has_line']    = 0
        df['best_book']   = None
        df['best_odds']   = None
        df['book_implied']= None
        df['edge']        = None
        return df.drop(columns=['name_norm'])

    merge_src = best_odds_df[['name_norm', 'bookmaker', 'odds_american', 'implied']].rename(
        columns={'bookmaker': 'best_book', 'odds_american': 'best_odds', 'implied': 'book_implied'}
    )
    df = df.merge(merge_src, on='name_norm', how='left').drop(columns=['name_norm'])

    df['has_line'] = df['best_odds'].notna().astype(int)
    df['edge']     = (df['adj_prob'] - df['book_implied']).where(df['has_line'] == 1).round(4)

    return df


# ── [6 + 7] Edge sanity check ─────────────────────────────────────────────────

def print_edge_sanity_check(df):
    """
    Print a distribution summary of the edge column for immediate sanity-checking.

    A HEALTHY distribution looks like:
        - Most players: -15% to +3%  (most lines lose to the vig)
        - A handful:    +3% to +15%  (potential genuine mispricing)
        - Almost none:  > +20%       (suspicious outlier territory)
        - Mean edge:    -8% to +0%   (the vig is eating the average line)

    RED FLAGS:
        - Mean edge > +10%  → model is inflated, or book lines are stale/wrong
        - Median > +8%      → every player looks like value; shouldn't happen
        - Everything < -20% → model is too conservative, or implied probs are stale

    When ODDSPAPI_KEY is invalid, this section is skipped (no edge to analyze).
    """
    lined = df[df['has_line'] == 1].copy()

    print(f"\n{'='*56}")
    print("  EDGE SANITY CHECK")
    print(f"{'='*56}")
    print(f"  Confirmed starters: {len(df)}")
    print(f"  Players with market lines: {len(lined)}")

    if lined.empty:
        print("\n  No market lines available - cannot compute edge.")
        print("  Fix ODDS_API_KEY in .env to enable edge calculation.")
        print("  (Get a key at https://the-odds-api.com - free tier includes player props)")
        return

    unlined = df[df['has_line'] == 0]['player_name'].tolist()
    if unlined:
        print(f"  No line found for: {unlined}")

    e = lined['edge'].dropna()

    print(f"\n  Edge = adj_prob - book_implied  (+ means model says more likely than book)")
    header = f"  {'Min':>8}  {'P25':>8}  {'Median':>8}  {'Mean':>8}  {'P75':>8}  {'Max':>8}"
    values = (f"  {e.min():>8.1%}  {e.quantile(0.25):>8.1%}  {e.median():>8.1%}  "
              f"{e.mean():>8.1%}  {e.quantile(0.75):>8.1%}  {e.max():>8.1%}")
    print(header)
    print(values)

    n_pos = (e > 0).sum()
    n_gt5 = (e > 0.05).sum()
    n_gt10 = (e > 0.10).sum()
    print(f"\n  Edge > 0%:   {n_pos:3d}/{len(e)} ({n_pos/len(e):.0%})  - favor our model over book")
    print(f"  Edge > +5%:  {n_gt5:3d}/{len(e)} ({n_gt5/len(e):.0%})  - potential value bets")
    print(f"  Edge > +10%: {n_gt10:3d}/{len(e)} ({n_gt10/len(e):.0%})  - high-confidence edges (scrutinize carefully)")

    # Calibration verdict
    mean_e = e.mean()
    if mean_e > 0.10:
        print(f"\n  *** RED FLAG: mean edge {mean_e:+.1%} is too high. ***")
        print("  Likely causes: model output is inflated, or book lines are stale.")
        print("  Do NOT bet these edges until the inflation source is identified.")
    elif mean_e > 0.04:
        print(f"\n  CAUTION: mean edge {mean_e:+.1%} is above zero.")
        print("  Typical vig on player props is 8-15%, so mean edge should be slightly negative.")
        print("  This might be fine if lines are fresh; double-check a few manually.")
    elif mean_e < -0.20:
        print(f"\n  CAUTION: mean edge {mean_e:+.1%} is very negative.")
        print("  Model may be too conservative, or lines have moved significantly.")
    else:
        print(f"\n  Looks healthy — mean {mean_e:+.1%} is in the expected -15% to +5% range.")

    # Top edges
    print(f"\n  Top 10 by edge (best potential bets):")
    cols = ['player_name', 'team_abbr', 'adj_prob', 'book_implied', 'edge', 'best_odds', 'best_book']
    top = lined.nlargest(10, 'edge')[cols].copy()
    top['adj_prob']    = top['adj_prob'].map('{:.1%}'.format)
    top['book_implied']= top['book_implied'].map('{:.1%}'.format)
    top['edge']        = top['edge'].map(lambda x: f'{x:+.1%}')
    top['best_odds']   = top['best_odds'].map(lambda x: f'+{int(x)}' if x > 0 else str(int(x)))
    print(top.to_string(index=False))

    # Bottom edges (sanity: shouldn't all be huge negative)
    print(f"\n  Bottom 5 by edge (most expensive to bet, worst value):")
    bot = lined.nsmallest(5, 'edge')[['player_name', 'team_abbr', 'adj_prob',
                                      'book_implied', 'edge', 'best_odds']].copy()
    bot['adj_prob']    = bot['adj_prob'].map('{:.1%}'.format)
    bot['book_implied']= bot['book_implied'].map('{:.1%}'.format)
    bot['edge']        = bot['edge'].map(lambda x: f'{x:+.1%}')
    bot['best_odds']   = bot['best_odds'].map(lambda x: f'+{int(x)}' if x > 0 else str(int(x)))
    print(bot.to_string(index=False))


# ── [8] Save ──────────────────────────────────────────────────────────────────

def save_output(df, date_str):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'fair_odds_{date_str}.csv')

    out_cols = [
        # Who / game context
        'player_name', 'team_abbr', 'stand', 'pitcher_name', 'p_throws', 'home_team',
        # Lineup confirmation — the hard filter result
        'lineup_source',
        # Our probability
        'adj_prob', 'fair_odds',
        # Market
        'has_line', 'best_book', 'best_odds', 'book_implied',
        # The key output
        'edge',
        # Probability breakdown (for auditing)
        'model_prob', 'k_pct', 'bb_pct', 'contact_rate', 'p_contact_game',
        # Context features
        'hr_park_factor', 'temp_f', 'wind_speed', 'wind_favor', 'is_dome',
        # IDs
        'game_date', 'game_id', 'batter',
    ]
    save_cols = [c for c in out_cols if c in df.columns]

    # Sort: players with lines first (by edge desc), then no-line players (by adj_prob desc)
    lined   = df[df['has_line'] == 1].sort_values('edge', ascending=False)
    unlined = df[df['has_line'] == 0].sort_values('adj_prob', ascending=False)
    out = pd.concat([lined, unlined], ignore_index=True)

    out[save_cols].to_csv(path, index=False)
    print(f"\n  Saved {len(out)} rows -> {path}")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def run(date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    print(f"\n{'='*56}")
    print(f"  Fair-Odds Conversion  --  {date_str}")
    print(f"{'='*56}")

    # [1] Predictions
    print("\n[1] Loading predictions...")
    pred_df = load_predictions(date_str)

    # [2] Confirmed lineups
    print(f"\n[2] Fetching confirmed starting lineups...")
    starter_ids, starter_source = fetch_starting_lineups(date_str)
    print(f"  {len(starter_ids)} confirmed starters found  (source: {starter_source})")

    # [3] Hard lineup filter
    print("\n[3] Applying lineup filter...")
    starters_df, dropped_df = apply_lineup_filter(pred_df, starter_ids, starter_source)
    if starters_df.empty:
        print("\n  No confirmed starters to price. Exiting.")
        return pd.DataFrame()

    # [4] Market lines
    print("\n[4] Fetching OddsAPI HR prop lines...")
    all_odds_df, best_odds_df = fetch_hr_odds(date_str)

    # [5] Join odds + edge
    print("\n[5] Joining odds and computing edge...")
    result_df = join_odds_and_edge(starters_df, best_odds_df)
    n_lined = result_df['has_line'].sum()
    n_total = len(result_df)
    print(f"  {n_lined}/{n_total} confirmed starters matched to market lines")
    if not best_odds_df.empty and n_lined < n_total:
        unmatched = result_df[result_df['has_line'] == 0]['player_name'].tolist()
        print(f"  Not matched (name may differ between OddsAPI and MLB): {unmatched}")

    # [6+7] Sanity check
    print_edge_sanity_check(result_df)

    # [8] Save
    out_path = save_output(result_df, date_str)

    # Final summary
    print(f"\n{'='*56}")
    if n_lined > 0:
        positive = (result_df['edge'] > 0).sum()
        gt5      = (result_df['edge'] > 0.05).sum()
        print(f"  {n_lined} players priced  |  {positive} with positive edge  |  {gt5} with edge > +5%")
    else:
        print(f"  {n_total} players priced with fair_odds (no market lines to compare)")
        print(f"  To see edge: fix ODDSPAPI_KEY in .env (https://the-odds-api.com)")
    print(f"  Full output: {out_path}")
    print(f"{'='*56}")

    return result_df


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
