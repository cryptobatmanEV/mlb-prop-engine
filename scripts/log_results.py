"""
Pull actual HR outcomes for a completed game date and append to the results log.

Run this the morning after predictions were made (once games are final):
    python scripts/log_results.py              # logs yesterday's results
    python scripts/log_results.py 2026-06-07   # logs a specific date

The results log grows over time at data/logs/results_log.csv.
Use it to validate the model: compare predicted adj_prob vs actual HR rate,
and check whether positive-edge plays are actually profitable over time.

Quick calibration query once you have 100+ rows:
    import pandas as pd
    df = pd.read_csv('data/logs/results_log.csv')
    df = df[df['hit_hr'] >= 0]   # drop rows where result is missing
    df['bucket'] = pd.cut(df['adj_prob'], bins=[0,.06,.10,.14,.18,.25,1.0])
    print(df.groupby('bucket')[['adj_prob','hit_hr']].agg(['mean','count']))
"""

import os, sys, time
import requests
import pandas as pd
from datetime import date as date_cls, timedelta
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MLB_BASE = 'https://statsapi.mlb.com/api/v1'
OUTPUTS_DIR = 'data/outputs'
LOG_PATH = 'data/logs/results_log.csv'

# Columns saved to the log.  Prediction columns come from fair_odds CSV;
# hit_hr and actual_hr_count are appended from boxscore results.
LOG_COLUMNS = [
    'log_date',
    'game_date',
    'player_name', 'team_abbr', 'stand',
    'pitcher_name', 'p_throws', 'home_team',
    'lineup_source',
    'adj_prob', 'fair_odds',
    'has_line', 'best_book', 'best_odds', 'book_implied', 'edge',
    'model_prob', 'hr_park_factor', 'temp_f', 'wind_speed', 'wind_favor',
    'game_id', 'batter',
    'hit_hr',           # 1 = hit a HR, 0 = did not, -1 = result not found
    'actual_hr_count',  # exact count (0, 1, 2 ...)
]


def _mlb(path, params=None, timeout=15):
    r = requests.get(f'{MLB_BASE}/{path}', params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_actual_hrs(game_pks):
    """
    For each game_pk, fetch the boxscore and return
    {mlbam_player_id: hr_count} for every batter who appeared.

    A game is considered complete only if it has at least 50 total at-bats
    across both rosters (a full 9-inning game typically has 60-75 AB).
    Games with fewer than 50 AB are skipped with a warning -- they are
    either not started or suspended mid-game.
    """
    hr_counts = {}
    incomplete = []

    for pk in game_pks:
        try:
            data = _mlb(f'game/{pk}/boxscore')

            # Gate: count total AB to confirm game is actually finished
            total_ab = 0
            for side in ('home', 'away'):
                for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                    total_ab += pdata.get('stats', {}).get('batting', {}).get('atBats', 0) or 0

            if total_ab < 50:
                incomplete.append(pk)
                continue

            # Game is complete -- harvest HR counts
            for side in ('home', 'away'):
                for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                    pid = pdata.get('person', {}).get('id')
                    hr = pdata.get('stats', {}).get('batting', {}).get('homeRuns', 0) or 0
                    if pid:
                        hr_counts[int(pid)] = int(hr)

            time.sleep(0.2)

        except Exception as e:
            print(f"  WARNING: boxscore fetch failed for game {pk}: {e}")

    if incomplete:
        print(f"  Skipped {len(incomplete)} game(s) not yet complete "
              f"(< 50 AB in boxscore): {incomplete}")
        print("  Re-run after those games are final.")

    return hr_counts


def load_fair_odds(date_str):
    path = os.path.join(OUTPUTS_DIR, f'fair_odds_{date_str}.csv')
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No fair_odds file found for {date_str}.\n"
            f"Generate it first with:\n"
            f"    python scripts/daily_pipeline.py {date_str}"
        )
    return pd.read_csv(path)


def already_logged(date_str):
    """Return True if this game_date already has rows in the log."""
    if not os.path.exists(LOG_PATH):
        return False
    existing = pd.read_csv(LOG_PATH, usecols=['game_date'])
    return str(date_str) in existing['game_date'].astype(str).values


def append_to_log(records_df):
    os.makedirs('data/logs', exist_ok=True)
    if os.path.exists(LOG_PATH):
        existing = pd.read_csv(LOG_PATH)
        out = pd.concat([existing, records_df], ignore_index=True)
    else:
        out = records_df
    out.to_csv(LOG_PATH, index=False)
    return len(out)


def print_results_table(pred_df):
    """Print today's hit/miss table sorted by adj_prob."""
    show = pred_df.sort_values('adj_prob', ascending=False).copy()
    show['adj_prob'] = show['adj_prob'].map('{:.1%}'.format)
    show['edge'] = show['edge'].apply(
        lambda x: f'{float(x):+.1%}' if pd.notna(x) and str(x) != 'nan' else 'N/A'
    )
    show['result'] = show['hit_hr'].map({1: 'HR!', 0: 'no', -1: '?'})
    cols = ['player_name', 'team_abbr', 'adj_prob', 'edge', 'result', 'actual_hr_count']
    print(show[[c for c in cols if c in show.columns]].to_string(index=False))


def print_calibration_summary():
    """Print running calibration stats from the full results log."""
    if not os.path.exists(LOG_PATH):
        return
    log = pd.read_csv(LOG_PATH)
    log = log[log['hit_hr'] >= 0]  # rows where result is known

    n_total = len(log)
    n_days = log['game_date'].nunique() if 'game_date' in log.columns else 0

    print(f"\n{'='*60}")
    print(f"  Running calibration ({n_days} game dates, {n_total} predictions total)")
    print(f"{'='*60}")

    if n_total < 30:
        print(f"  Not enough data yet for reliable calibration (need ~100+ rows).")
        print(f"  Keep logging daily -- this will fill in automatically.")
        return

    log['bucket'] = pd.cut(
        log['adj_prob'],
        bins=[0, .06, .10, .14, .18, .25, 1.0],
        labels=['< 6%', '6-10%', '10-14%', '14-18%', '18-25%', '> 25%'],
    )
    cal = (
        log.groupby('bucket', observed=True)
           .agg(predicted=('adj_prob', 'mean'),
                actual=('hit_hr', 'mean'),
                n=('hit_hr', 'count'))
           .reset_index()
    )
    cal['predicted'] = cal['predicted'].map('{:.1%}'.format)
    cal['actual']    = cal['actual'].map('{:.1%}'.format)
    print(f"\n  Bucket   Predicted   Actual    N")
    for _, row in cal.iterrows():
        print(f"  {row['bucket']:<8}  {row['predicted']:>9}  {row['actual']:>7}  {row['n']:>4}")

    # Positive-edge plays specifically
    log['edge_num'] = pd.to_numeric(log['edge'], errors='coerce')
    pos_edge = log[(log['has_line'] == 1) & (log['edge_num'] > 0)]
    if len(pos_edge) >= 5:
        actual_rate = pos_edge['hit_hr'].mean()
        pred_rate   = pos_edge['adj_prob'].mean()
        print(f"\n  Positive-edge plays: {len(pos_edge)} flagged")
        print(f"    Predicted avg prob: {pred_rate:.1%}")
        print(f"    Actual HR rate:     {actual_rate:.1%}")
        if actual_rate >= pred_rate * 0.8:
            print(f"    Model is tracking well on positive-edge picks.")
        else:
            print(f"    Actual rate is below predicted -- worth investigating.")
    elif log['has_line'].sum() > 0:
        print(f"\n  Need more positive-edge plays to evaluate (have {len(pos_edge)} so far).")


def write_results_to_db(date_str, pred_df):
    """
    Write hit_hr and actual_hr_count back to hr_predictions in Neon so the
    web app can show a green HR indicator on past-date cards.
    Only rows with a known result (hit_hr >= 0) are updated.
    """
    import psycopg2
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        return

    known = pred_df[pred_df['hit_hr'] >= 0][['batter', 'hit_hr', 'actual_hr_count']].copy()
    if known.empty:
        return

    try:
        conn = psycopg2.connect(db_url)
        try:
            with conn:
                with conn.cursor() as cur:
                    for _, row in known.iterrows():
                        cur.execute(
                            """
                            UPDATE hr_predictions
                               SET hit_hr          = %s,
                                   actual_hr_count = %s
                             WHERE game_date = %s
                               AND batter    = %s
                            """,
                            (bool(row['hit_hr']), int(row['actual_hr_count']),
                             date_str, int(row['batter'])),
                        )
            print(f"  Wrote results to hr_predictions for {len(known)} player(s).")
        finally:
            conn.close()
    except Exception as e:
        print(f"  WARNING: hr_predictions result write failed: {e}")


def backfill_tracked_bets(date_str, pred_df):
    """
    After results are logged, update tracked_bets rows for this date
    that are still pending (hit_hr IS NULL).
    """
    import psycopg2
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("  DATABASE_URL not set -- skipping tracked_bets backfill.")
        return

    # Build lookup: batter_id -> hit_hr (0 or 1; skip -1 = unknown)
    settled = pred_df[pred_df['hit_hr'] >= 0][['batter', 'hit_hr']].copy()
    if settled.empty:
        return

    try:
        conn = psycopg2.connect(db_url)
        try:
            updated = 0
            with conn:
                with conn.cursor() as cur:
                    for _, row in settled.iterrows():
                        cur.execute(
                            """
                            UPDATE tracked_bets
                               SET hit_hr  = %s,
                                   settled = true
                             WHERE game_date = %s
                               AND batter    = %s
                               AND hit_hr IS NULL
                            """,
                            (bool(row['hit_hr']), date_str, int(row['batter'])),
                        )
                        updated += cur.rowcount
            if updated:
                print(f"  Backfilled {updated} tracked bet(s) with results.")
            else:
                print("  No pending tracked bets for this date.")
        finally:
            conn.close()
    except Exception as e:
        print(f"  WARNING: tracked_bets backfill failed: {e}")


def run(date_str=None):
    if date_str is None:
        date_str = (date_cls.today() - timedelta(days=1)).isoformat()

    print(f"\n{'='*60}")
    print(f"  Log Results  --  {date_str}")
    print(f"{'='*60}")

    # Guard against logging the same date twice
    if already_logged(date_str):
        print(f"\n  {date_str} is already in the log. Nothing to do.")
        print_calibration_summary()
        return

    # Load predictions for that date
    print(f"\nLoading predictions for {date_str}...")
    try:
        pred_df = load_fair_odds(date_str)
    except FileNotFoundError as e:
        print(f"  {e}")
        return
    print(f"  {len(pred_df)} confirmed starters loaded")

    # Fetch actual boxscore results
    game_pks = pred_df['game_id'].dropna().astype(int).unique().tolist()
    print(f"\nFetching boxscores for {len(game_pks)} game(s)...")
    hr_counts = fetch_actual_hrs(game_pks)

    if not hr_counts:
        print("\n  No complete boxscores found.")
        print("  Games may not be finished yet. Re-run after the last game is final.")
        return

    print(f"  Batting results retrieved for {len(hr_counts)} players")

    # Join actual results onto predictions
    pred_df = pred_df.copy()
    pred_df['actual_hr_count'] = pred_df['batter'].map(hr_counts)
    # -1 means the player's result wasn't in the boxscore (pinch hitter, DNP, etc.)
    pred_df['actual_hr_count'] = pred_df['actual_hr_count'].fillna(-1).astype(int)
    pred_df['hit_hr'] = pred_df['actual_hr_count'].apply(
        lambda x: 1 if x > 0 else (0 if x == 0 else -1)
    )
    pred_df['log_date'] = date_cls.today().isoformat()

    # Summary counts
    n_found   = (pred_df['hit_hr'] >= 0).sum()
    n_hr      = (pred_df['hit_hr'] == 1).sum()
    n_missing = (pred_df['hit_hr'] == -1).sum()

    print(f"\n  Results matched : {n_found}/{len(pred_df)} players")
    print(f"  Hit a HR        : {n_hr}")
    print(f"  Did not HR      : {n_found - n_hr}")
    print(f"  Result missing  : {n_missing}")
    if n_missing > 0:
        missing_names = pred_df[pred_df['hit_hr'] == -1]['player_name'].tolist()
        print(f"  Missing players : {missing_names}")

    # Results table
    print(f"\n  Today's hit/miss (sorted by adj_prob):")
    print_results_table(pred_df)

    # Save to log
    save_cols = [c for c in LOG_COLUMNS if c in pred_df.columns]
    total_rows = append_to_log(pred_df[save_cols])
    print(f"\n  Appended {len(pred_df)} rows to {LOG_PATH}  ({total_rows} total rows in log)")

    # Write results to Neon (hr_predictions + tracked_bets)
    write_results_to_db(date_str, pred_df)
    backfill_tracked_bets(date_str, pred_df)

    # Running calibration summary
    print_calibration_summary()


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
