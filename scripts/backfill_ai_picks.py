"""
One-time backfill: apply the AI PICKS formula to every past date that has a
fair_odds CSV, and INSERT qualifying rows into hr_ai_picks_log.

Sets captured_at to midnight UTC of each game_date so analytics queries can
distinguish backfill rows from live-logged rows by time if needed.

Skips dates already present in the log (safe to re-run).

Usage:
    python scripts/backfill_ai_picks.py
"""

import glob, os, sys
from datetime import date as date_cls, datetime, timezone
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUTPUTS_DIR = 'data/outputs'


def run():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not set -- aborting.")
        return

    from scripts.log_ai_picks import run as log_picks, CREATE_TABLE
    import psycopg2

    # Ensure table exists before querying it
    conn = psycopg2.connect(db_url)
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
    conn.close()

    # Dates already in the log (skip to make the script re-runnable)
    conn = psycopg2.connect(db_url)
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT game_date::text FROM hr_ai_picks_log")
            already_done = {r[0] for r in cur.fetchall()}
    conn.close()

    csv_files = sorted(glob.glob(os.path.join(OUTPUTS_DIR, 'fair_odds_*.csv')))
    processed = 0

    for fpath in csv_files:
        base     = os.path.basename(fpath)
        date_str = base.replace('fair_odds_', '').replace('.csv', '')

        # Skip today's file — the live pipeline handles it going forward
        if date_str == date_cls.today().isoformat():
            continue

        if date_str in already_done:
            print(f"  {date_str}: already logged, skipping.")
            continue

        try:
            d = date_cls.fromisoformat(date_str)
        except ValueError:
            print(f"  {date_str}: could not parse date, skipping.")
            continue

        captured_at = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
        print(f"  Backfilling {date_str}...", end='  ')
        log_picks(date_str, captured_at=captured_at)
        processed += 1

    print(f"\nBackfill complete. Processed {processed} date(s).")


if __name__ == '__main__':
    run()
