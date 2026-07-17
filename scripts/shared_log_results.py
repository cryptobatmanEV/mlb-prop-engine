"""
Shared results-grading logic for the Hits / Total Bases / Batter Ks models,
mirroring scripts/log_results.py's pattern for the HR model. One function
instead of three near-duplicate scripts.

Grades three places per model:
  1. {table} (e.g. hits_predictions) -- result_actual/result_hit_primary/
     result_hit_secondary columns.
  2. tracked_bets -- WHERE stat_type = <model's stat_type>, graded against
     the SPECIFIC line each user tracked (0.5 vs 1.5), not just the primary line.
  3. {ai_picks_table} -- actual_result/result columns (always graded against
     the primary line, since AI Picks always qualifies on the primary line).
"""
import os
import time
import psycopg2
import requests
import pandas as pd
from datetime import date as date_cls, timedelta
from dotenv import load_dotenv

load_dotenv()

MLB_BASE = 'https://statsapi.mlb.com/api/v1'
DATABASE_URL = os.getenv('DATABASE_URL')
OUTPUTS_DIR = 'data/outputs'


def _mlb(path, params=None, timeout=15):
    r = requests.get(f'{MLB_BASE}/{path}', params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_actual_stat(game_pks, stat_field):
    """
    {batter_id: stat_value} for every batter who appeared, for the given
    boxscore batting stat field ('hits' | 'totalBases' | 'strikeOuts').
    Games with < 50 total AB across both rosters are treated as not yet final.
    """
    values = {}
    incomplete = []
    for pk in game_pks:
        try:
            data = _mlb(f'game/{pk}/boxscore')
            total_ab = 0
            for side in ('home', 'away'):
                for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                    total_ab += pdata.get('stats', {}).get('batting', {}).get('atBats', 0) or 0
            if total_ab < 50:
                incomplete.append(pk)
                continue
            for side in ('home', 'away'):
                for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                    pid = pdata.get('person', {}).get('id')
                    val = pdata.get('stats', {}).get('batting', {}).get(stat_field, 0) or 0
                    if pid:
                        values[int(pid)] = int(val)
            time.sleep(0.2)
        except Exception as e:
            print(f"  WARNING: boxscore fetch failed for game {pk}: {e}")

    if incomplete:
        print(f"  Skipped {len(incomplete)} game(s) not yet complete (< 50 AB): {incomplete}")
        print("  Re-run after those games are final.")
    return values


def grade_predictions_table(table, date_str, actual_by_batter, primary_line, secondary_line):
    if not DATABASE_URL or not actual_by_batter:
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for batter_id, actual in actual_by_batter.items():
                    cur.execute(
                        f"""
                        UPDATE {table}
                           SET result_actual        = %s,
                               result_hit_primary    = %s,
                               result_hit_secondary  = %s
                         WHERE game_date = %s AND batter = %s
                        """,
                        (actual, actual > primary_line, actual > secondary_line, date_str, batter_id),
                    )
        print(f"  Updated {len(actual_by_batter)} row(s) in {table}.")
    finally:
        conn.close()


def _ensure_tracked_bets_columns(cur):
    """Defensive migration -- the TS API routes also apply this, but
    --log-only mode never touches those routes, so apply it here too."""
    cur.execute("ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS stat_type TEXT DEFAULT 'home_runs'")
    cur.execute("ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS line FLOAT DEFAULT 0.5")
    cur.execute("ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS side TEXT DEFAULT 'over'")


def backfill_tracked_bets(stat_type, date_str, actual_by_batter):
    """
    Grade each pending tracked bet against the SPECIFIC line AND side it was
    tracked at -- a bet on the under side wins when actual < line, not > line
    (the model can favor either side per player; see predict/shared_fair_odds.py).
    """
    if not DATABASE_URL or not actual_by_batter:
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        updated = 0
        with conn:
            with conn.cursor() as cur:
                _ensure_tracked_bets_columns(cur)
                for batter_id, actual in actual_by_batter.items():
                    cur.execute(
                        """
                        SELECT id, line, COALESCE(side, 'over') FROM tracked_bets
                         WHERE game_date = %s AND batter = %s AND stat_type = %s AND hit_hr IS NULL
                        """,
                        (date_str, batter_id, stat_type),
                    )
                    for bet_id, line, side in cur.fetchall():
                        won = actual < float(line) if side == 'under' else actual > float(line)
                        cur.execute(
                            "UPDATE tracked_bets SET hit_hr = %s, settled = true WHERE id = %s",
                            (won, bet_id),
                        )
                        updated += 1
        if updated:
            print(f"  Backfilled {updated} tracked bet(s) for stat_type={stat_type}.")
        else:
            print(f"  No pending tracked bets for stat_type={stat_type} on {date_str}.")
    finally:
        conn.close()


def grade_ai_picks_log(ai_picks_table, date_str, actual_by_batter):
    """
    Grades each row against its OWN book_line AND book_side columns, not a
    single line/side passed in from the caller -- different models qualify
    AI Picks against different lines (e.g. Total Bases uses its secondary/1.5
    line, Hits and Batter Ks use their primary/0.5 line), and a pick's side
    can be 'under' if that's what the model favored for that specific player.
    """
    if not DATABASE_URL or not actual_by_batter:
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        updated = 0
        with conn:
            with conn.cursor() as cur:
                for batter_id, actual in actual_by_batter.items():
                    cur.execute(
                        f"""
                        UPDATE {ai_picks_table}
                           SET actual_result = %s,
                               result = CASE
                                 WHEN book_side = 'under' THEN
                                   CASE WHEN %s < COALESCE(book_line, 0.5) THEN 'HIT' ELSE 'MISS' END
                                 ELSE
                                   CASE WHEN %s > COALESCE(book_line, 0.5) THEN 'HIT' ELSE 'MISS' END
                               END
                         WHERE game_date = %s AND batter = %s AND result IS NULL
                        """,
                        (actual, actual, actual, date_str, batter_id),
                    )
                    updated += cur.rowcount
        if updated:
            print(f"  Graded {updated} AI pick(s) in {ai_picks_table}.")
        else:
            print(f"  No ungraded AI picks in {ai_picks_table} for {date_str}.")
    finally:
        conn.close()


def already_logged(log_path, date_str):
    if not os.path.exists(log_path):
        return False
    existing = pd.read_csv(log_path, usecols=['game_date'])
    return str(date_str) in existing['game_date'].astype(str).values


def run(model_key, table, ai_picks_table, stat_field, primary_line, secondary_line, date_str=None):
    """
    model_key: 'hits' | 'total_bases' | 'batter_ks' -- matches both the
      {model_key}_fair_odds_{date}.csv filename and the tracked_bets.stat_type
      value used when tracking from that tab.
    """
    if date_str is None:
        date_str = (date_cls.today() - timedelta(days=1)).isoformat()

    print(f"\n{'='*60}")
    print(f"  Log Results -- {model_key} -- {date_str}")
    print(f"{'='*60}")

    log_path = f'data/logs/results_log_{model_key}.csv'

    fair_odds_path = os.path.join(OUTPUTS_DIR, f'{model_key}_fair_odds_{date_str}.csv')
    if not os.path.exists(fair_odds_path):
        print(f"  No {fair_odds_path} -- nothing to grade.")
        return

    if already_logged(log_path, date_str):
        print(f"  {date_str} is already in {log_path}.")
        return

    pred_df = pd.read_csv(fair_odds_path)
    game_ids = pred_df['game_id'].dropna().astype(int).unique().tolist()
    print(f"  Fetching boxscores for {len(game_ids)} game(s)...")
    actual = fetch_actual_stat(game_ids, stat_field)
    if not actual:
        print("  No complete boxscores yet. Re-run after games are final.")
        return
    print(f"  Results retrieved for {len(actual)} player(s).")

    grade_predictions_table(table, date_str, actual, primary_line, secondary_line)
    backfill_tracked_bets(model_key, date_str, actual)
    grade_ai_picks_log(ai_picks_table, date_str, actual)

    rows = pred_df[pred_df['batter'].isin(actual.keys())].copy()
    rows['actual'] = rows['batter'].map(actual)
    rows['hit_primary'] = rows['actual'] > primary_line
    rows['hit_secondary'] = rows['actual'] > secondary_line
    rows['log_date'] = date_cls.today().isoformat()

    os.makedirs('data/logs', exist_ok=True)
    if os.path.exists(log_path):
        existing = pd.read_csv(log_path)
        out = pd.concat([existing, rows], ignore_index=True)
    else:
        out = rows
    out.to_csv(log_path, index=False)
    print(f"  Appended {len(rows)} row(s) to {log_path} ({len(out)} total).")

    n_hit_primary = rows['hit_primary'].sum()
    print(f"\n  {model_key}: {len(rows)} graded, {n_hit_primary} hit the primary line ({primary_line}+).")
