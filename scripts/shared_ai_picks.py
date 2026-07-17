"""
Shared AI Picks infrastructure for Hits / Total Bases / Batter Ks: schema
migration + DB writer + batting-order bonus. Each model's qualification
threshold and composite-score formula genuinely differ (per spec), so those
stay in the three model-specific scripts (log_ai_picks_{hits,total_bases,
batter_ks}.py) -- this module only holds what's truly shared.
"""
import os
import math
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')


def bat_order_bonus(bo):
    if bo is None or (isinstance(bo, float) and math.isnan(bo)):
        return 0.0
    bo = int(bo)
    if bo <= 3:
        return 0.15
    if bo <= 5:
        return 0.08
    if bo <= 7:
        return 0.02
    return 0.0


def _f(val):
    if val is None:
        return None
    try:
        v = float(val)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _i(val):
    v = _f(val)
    return None if v is None else int(v)


def _s(val):
    if val is None:
        return None
    s = str(val)
    return None if s in ('nan', 'None', '') else s


def ensure_table(table):
    """
    Create/migrate {table} to the spec'd schema:
      id, game_date, captured_at, batter, player_name, team_abbr, bat_order,
      best_odds, best_book, edge, adj_prob, book_line, book_side,
      composite_score, actual_result, result
    """
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id              SERIAL PRIMARY KEY,
                        game_date       DATE        NOT NULL,
                        captured_at     TIMESTAMPTZ NOT NULL,
                        batter          BIGINT      NOT NULL,
                        player_name     TEXT,
                        team_abbr       TEXT,
                        bat_order       INTEGER,
                        best_odds       INTEGER,
                        best_book       TEXT,
                        edge            NUMERIC,
                        adj_prob        NUMERIC,
                        book_line       NUMERIC,
                        book_side       TEXT,
                        composite_score NUMERIC,
                        actual_result   INTEGER,
                        result          TEXT
                    )
                """)
                # Migrate tables created by the older generic schema (team
                # instead of team_abbr, no bat_order/book_line/book_side).
                for stmt in [
                    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS team_abbr TEXT",
                    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS bat_order INTEGER",
                    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS book_line NUMERIC",
                    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS book_side TEXT",
                ]:
                    try:
                        cur.execute("SAVEPOINT mig")
                        cur.execute(stmt.format(t=table))
                        cur.execute("RELEASE SAVEPOINT mig")
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT mig")
                # Backfill team_abbr from the old `team` column if it exists and is empty.
                try:
                    cur.execute("SAVEPOINT mig2")
                    cur.execute(f"UPDATE {table} SET team_abbr = team WHERE team_abbr IS NULL AND team IS NOT NULL")
                    cur.execute("RELEASE SAVEPOINT mig2")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT mig2")
    finally:
        conn.close()


def write_picks(table, picks):
    """picks: list[dict] with keys matching the columns in ensure_table()."""
    # Always migrate, even with zero picks this run -- grade_ai_picks_log()
    # (in shared_log_results.py) references book_line/team_abbr/bat_order on
    # every graded run regardless of whether today added any new picks.
    ensure_table(table)
    if not DATABASE_URL or not picks:
        print(f"  No AI picks to write for {table}.")
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for p in picks:
                    cur.execute(
                        f"""
                        INSERT INTO {table}
                            (game_date, captured_at, batter, player_name, team_abbr, bat_order,
                             best_odds, best_book, edge, adj_prob, book_line, book_side, composite_score)
                        VALUES
                            (%(game_date)s, %(captured_at)s, %(batter)s, %(player_name)s, %(team_abbr)s, %(bat_order)s,
                             %(best_odds)s, %(best_book)s, %(edge)s, %(adj_prob)s, %(book_line)s, %(book_side)s, %(composite_score)s)
                        """,
                        p,
                    )
        print(f"  Logged {len(picks)} AI PICK(s) into {table}.")
    finally:
        conn.close()


def now_utc():
    return datetime.now(timezone.utc)
