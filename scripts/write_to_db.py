"""
Upsert today's fair_odds predictions into Neon PostgreSQL.

The hr_predictions table is created automatically on first run.
Re-running for the same date is safe -- rows are updated, not duplicated.

Usage:
    python scripts/write_to_db.py              # today
    python scripts/write_to_db.py 2026-06-07   # specific date

Called automatically as Step 4 by scripts/daily_pipeline.py.
"""

import math, os, sys
import pandas as pd
import psycopg2
from datetime import date as date_cls
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATABASE_URL = os.getenv('DATABASE_URL')
OUTPUTS_DIR  = 'data/outputs'

CREATE_TRACKED_BETS = """
CREATE TABLE IF NOT EXISTS tracked_bets (
    id           SERIAL PRIMARY KEY,
    game_date    DATE        NOT NULL,
    batter       BIGINT      NOT NULL,
    player_name  TEXT,
    team_abbr    TEXT,
    adj_prob     FLOAT,
    tracked_odds INTEGER,
    edge         FLOAT,
    stake_units  FLOAT       NOT NULL,
    hit_hr       BOOLEAN     DEFAULT NULL,
    settled      BOOLEAN     NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (game_date, batter)
);
"""

# Migrations for tables created before this schema
MIGRATE_TRACKED_BETS = [
    "ALTER TABLE tracked_bets RENAME COLUMN best_odds TO tracked_odds",
    "ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS tracked_odds INTEGER",
    "ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS settled BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE tracked_bets ADD CONSTRAINT IF NOT EXISTS tracked_bets_date_batter_key UNIQUE (game_date, batter)",
]

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS hr_predictions (
    id              SERIAL PRIMARY KEY,
    game_date       DATE        NOT NULL,
    batter          BIGINT      NOT NULL,
    game_id         BIGINT      NOT NULL,
    player_name     TEXT,
    team_abbr       TEXT,
    stand           TEXT,
    pitcher_name    TEXT,
    p_throws        TEXT,
    home_team       TEXT,
    lineup_source   TEXT,
    adj_prob        FLOAT,
    fair_odds       INTEGER,
    has_line        BOOLEAN,
    best_book       TEXT,
    best_odds       INTEGER,
    book_implied    FLOAT,
    edge            FLOAT,
    model_prob      FLOAT,
    hr_park_factor  FLOAT,
    temp_f          FLOAT,
    wind_speed      FLOAT,
    wind_favor      FLOAT,
    is_dome         BOOLEAN,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (game_date, batter, game_id)
);
"""

UPSERT = """
INSERT INTO hr_predictions (
    game_date, batter, game_id,
    player_name, team_abbr, stand, pitcher_name, p_throws, home_team, lineup_source,
    adj_prob, fair_odds, has_line, best_book, best_odds, book_implied, edge,
    model_prob, hr_park_factor, temp_f, wind_speed, wind_favor, is_dome
) VALUES (
    %(game_date)s, %(batter)s, %(game_id)s,
    %(player_name)s, %(team_abbr)s, %(stand)s, %(pitcher_name)s, %(p_throws)s,
    %(home_team)s, %(lineup_source)s,
    %(adj_prob)s, %(fair_odds)s, %(has_line)s, %(best_book)s, %(best_odds)s,
    %(book_implied)s, %(edge)s,
    %(model_prob)s, %(hr_park_factor)s, %(temp_f)s, %(wind_speed)s, %(wind_favor)s, %(is_dome)s
)
ON CONFLICT (game_date, batter, game_id) DO UPDATE SET
    player_name    = EXCLUDED.player_name,
    lineup_source  = EXCLUDED.lineup_source,
    adj_prob       = EXCLUDED.adj_prob,
    fair_odds      = EXCLUDED.fair_odds,
    has_line       = EXCLUDED.has_line,
    best_book      = EXCLUDED.best_book,
    best_odds      = EXCLUDED.best_odds,
    book_implied   = EXCLUDED.book_implied,
    edge           = EXCLUDED.edge,
    model_prob     = EXCLUDED.model_prob,
    hr_park_factor = EXCLUDED.hr_park_factor,
    temp_f         = EXCLUDED.temp_f,
    wind_speed     = EXCLUDED.wind_speed,
    wind_favor     = EXCLUDED.wind_favor,
    is_dome        = EXCLUDED.is_dome,
    created_at     = NOW();
"""


def _clean(val):
    """Return None for NaN/NA; pass everything else through unchanged."""
    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _bool(val):
    """Convert 0/1/NaN to Python bool or None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return bool(int(val))


def _int(val):
    """Convert numeric-or-NaN to int or None."""
    v = _clean(val)
    return None if v is None else int(v)


def _str(val):
    """Convert a pandas cell to str or None (handles NaN and 'nan' strings)."""
    if val is None:
        return None
    s = str(val)
    return None if s in ('nan', 'None', '') else s


def run(date_str=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()

    if not DATABASE_URL:
        print("  DATABASE_URL not set in .env -- skipping DB write.")
        return

    path = os.path.join(OUTPUTS_DIR, f'fair_odds_{date_str}.csv')
    if not os.path.exists(path):
        print(f"  No fair_odds file for {date_str} -- skipping DB write.")
        return

    df = pd.read_csv(path)
    print(f"  Upserting {len(df)} rows for {date_str} into hr_predictions...")

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE)
                cur.execute(CREATE_TRACKED_BETS)
                for stmt in MIGRATE_TRACKED_BETS:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass  # column / constraint already exists
                for _, row in df.iterrows():
                    cur.execute(UPSERT, {
                        'game_date':     date_str,
                        'batter':        int(row['batter']),
                        'game_id':       int(row['game_id']),
                        'player_name':   _str(row.get('player_name')),
                        'team_abbr':     _str(row.get('team_abbr')),
                        'stand':         _str(row.get('stand')),
                        'pitcher_name':  _str(row.get('pitcher_name')),
                        'p_throws':      _str(row.get('p_throws')),
                        'home_team':     _str(row.get('home_team')),
                        'lineup_source': _str(row.get('lineup_source')),
                        'adj_prob':      _clean(row.get('adj_prob')),
                        'fair_odds':     _int(row.get('fair_odds')),
                        'has_line':      _bool(row.get('has_line')),
                        'best_book':     _str(row.get('best_book')),
                        'best_odds':     _int(row.get('best_odds')),
                        'book_implied':  _clean(row.get('book_implied')),
                        'edge':          _clean(row.get('edge')),
                        'model_prob':    _clean(row.get('model_prob')),
                        'hr_park_factor':_clean(row.get('hr_park_factor')),
                        'temp_f':        _clean(row.get('temp_f')),
                        'wind_speed':    _clean(row.get('wind_speed')),
                        'wind_favor':    _clean(row.get('wind_favor')),
                        'is_dome':       _bool(row.get('is_dome')),
                    })
        print(f"  Done -- {len(df)} rows upserted.")
    finally:
        conn.close()


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
