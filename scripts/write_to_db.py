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

MIGRATE_HR_PREDICTIONS = [
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS is_home TEXT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS season_hr INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS bat_order INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS game_total FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS recent_hr INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS barrel_pct_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS hardhit_pct_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS flyball_pct_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS avg_ev_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS xwoba_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS xslg_15 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS p_barrel_pct_allowed_10 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS p_hardhit_pct_allowed_10 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS p_hr_per_bb_allowed_10 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS days_since_hr INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS p_fip FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS pitcher_era FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS pitcher_hr9 FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS pitcher_hr_allowed INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS pitcher_ip FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS vs_pitcher_ab INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS vs_pitcher_h INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS vs_pitcher_hr INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS vs_pitcher_avg FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS hr_vs_r INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS hr_vs_l INTEGER",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS humidity_pct FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS precip_pct FLOAT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS wind_description TEXT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS game_time TEXT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS stadium TEXT",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS opp_team TEXT",
    # Results columns — written by log_results.py, never overwritten by the pipeline upsert
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS hit_hr BOOLEAN",
    "ALTER TABLE hr_predictions ADD COLUMN IF NOT EXISTS actual_hr_count INTEGER",
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
    opp_team        TEXT,
    is_home         TEXT,
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
    season_hr       INTEGER,
    bat_order       INTEGER,
    game_total      FLOAT,
    recent_hr       INTEGER,
    barrel_pct_15            FLOAT,
    hardhit_pct_15           FLOAT,
    flyball_pct_15           FLOAT,
    avg_ev_15                FLOAT,
    xwoba_15                 FLOAT,
    xslg_15                  FLOAT,
    p_barrel_pct_allowed_10  FLOAT,
    p_hardhit_pct_allowed_10 FLOAT,
    p_hr_per_bb_allowed_10   FLOAT,
    days_since_hr   INTEGER,
    p_fip           FLOAT,
    pitcher_era        FLOAT,
    pitcher_hr9        FLOAT,
    pitcher_hr_allowed INTEGER,
    pitcher_ip         FLOAT,
    vs_pitcher_ab   INTEGER,
    vs_pitcher_h    INTEGER,
    vs_pitcher_hr   INTEGER,
    vs_pitcher_avg  FLOAT,
    hr_vs_r         INTEGER,
    hr_vs_l         INTEGER,
    humidity_pct    FLOAT,
    precip_pct      FLOAT,
    wind_description TEXT,
    game_time       TEXT,
    stadium         TEXT,
    hit_hr          BOOLEAN,
    actual_hr_count INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (game_date, batter, game_id)
);
"""

UPSERT = """
INSERT INTO hr_predictions (
    game_date, batter, game_id,
    player_name, team_abbr, stand, pitcher_name, p_throws, home_team, opp_team, is_home, lineup_source,
    adj_prob, fair_odds, has_line, best_book, best_odds, book_implied, edge,
    model_prob, hr_park_factor, temp_f, wind_speed, wind_favor, is_dome,
    season_hr, bat_order, game_total, recent_hr,
    barrel_pct_15, hardhit_pct_15, flyball_pct_15,
    avg_ev_15, xwoba_15, xslg_15,
    p_barrel_pct_allowed_10, p_hardhit_pct_allowed_10, p_hr_per_bb_allowed_10,
    days_since_hr, p_fip,
    pitcher_era, pitcher_hr9, pitcher_hr_allowed, pitcher_ip,
    vs_pitcher_ab, vs_pitcher_h, vs_pitcher_hr, vs_pitcher_avg,
    hr_vs_r, hr_vs_l,
    humidity_pct, precip_pct, wind_description, game_time, stadium
) VALUES (
    %(game_date)s, %(batter)s, %(game_id)s,
    %(player_name)s, %(team_abbr)s, %(stand)s, %(pitcher_name)s, %(p_throws)s,
    %(home_team)s, %(opp_team)s, %(is_home)s, %(lineup_source)s,
    %(adj_prob)s, %(fair_odds)s, %(has_line)s, %(best_book)s, %(best_odds)s,
    %(book_implied)s, %(edge)s,
    %(model_prob)s, %(hr_park_factor)s, %(temp_f)s, %(wind_speed)s, %(wind_favor)s, %(is_dome)s,
    %(season_hr)s, %(bat_order)s, %(game_total)s, %(recent_hr)s,
    %(barrel_pct_15)s, %(hardhit_pct_15)s, %(flyball_pct_15)s,
    %(avg_ev_15)s, %(xwoba_15)s, %(xslg_15)s,
    %(p_barrel_pct_allowed_10)s, %(p_hardhit_pct_allowed_10)s, %(p_hr_per_bb_allowed_10)s,
    %(days_since_hr)s, %(p_fip)s,
    %(pitcher_era)s, %(pitcher_hr9)s, %(pitcher_hr_allowed)s, %(pitcher_ip)s,
    %(vs_pitcher_ab)s, %(vs_pitcher_h)s, %(vs_pitcher_hr)s, %(vs_pitcher_avg)s,
    %(hr_vs_r)s, %(hr_vs_l)s,
    %(humidity_pct)s, %(precip_pct)s, %(wind_description)s, %(game_time)s, %(stadium)s
)
ON CONFLICT (game_date, batter, game_id) DO UPDATE SET
    player_name              = EXCLUDED.player_name,
    opp_team                 = EXCLUDED.opp_team,
    is_home                  = EXCLUDED.is_home,
    lineup_source            = EXCLUDED.lineup_source,
    adj_prob                 = EXCLUDED.adj_prob,
    fair_odds                = EXCLUDED.fair_odds,
    has_line     = EXCLUDED.has_line,
    best_book    = CASE WHEN EXCLUDED.has_line IS TRUE THEN EXCLUDED.best_book    ELSE hr_predictions.best_book    END,
    best_odds    = CASE WHEN EXCLUDED.has_line IS TRUE THEN EXCLUDED.best_odds    ELSE hr_predictions.best_odds    END,
    book_implied = CASE WHEN EXCLUDED.has_line IS TRUE THEN EXCLUDED.book_implied ELSE hr_predictions.book_implied END,
    edge         = CASE WHEN EXCLUDED.has_line IS TRUE THEN EXCLUDED.edge         ELSE hr_predictions.edge         END,
    model_prob               = EXCLUDED.model_prob,
    hr_park_factor           = EXCLUDED.hr_park_factor,
    temp_f                   = EXCLUDED.temp_f,
    wind_speed               = EXCLUDED.wind_speed,
    wind_favor               = EXCLUDED.wind_favor,
    is_dome                  = EXCLUDED.is_dome,
    season_hr                = EXCLUDED.season_hr,
    bat_order                = EXCLUDED.bat_order,
    game_total               = EXCLUDED.game_total,
    recent_hr                = EXCLUDED.recent_hr,
    barrel_pct_15            = EXCLUDED.barrel_pct_15,
    hardhit_pct_15           = EXCLUDED.hardhit_pct_15,
    flyball_pct_15           = EXCLUDED.flyball_pct_15,
    avg_ev_15                = EXCLUDED.avg_ev_15,
    xwoba_15                 = EXCLUDED.xwoba_15,
    xslg_15                  = EXCLUDED.xslg_15,
    p_barrel_pct_allowed_10  = EXCLUDED.p_barrel_pct_allowed_10,
    p_hardhit_pct_allowed_10 = EXCLUDED.p_hardhit_pct_allowed_10,
    p_hr_per_bb_allowed_10   = EXCLUDED.p_hr_per_bb_allowed_10,
    days_since_hr            = EXCLUDED.days_since_hr,
    p_fip                    = EXCLUDED.p_fip,
    pitcher_era              = EXCLUDED.pitcher_era,
    pitcher_hr9              = EXCLUDED.pitcher_hr9,
    pitcher_hr_allowed       = EXCLUDED.pitcher_hr_allowed,
    pitcher_ip               = EXCLUDED.pitcher_ip,
    vs_pitcher_ab            = EXCLUDED.vs_pitcher_ab,
    vs_pitcher_h             = EXCLUDED.vs_pitcher_h,
    vs_pitcher_hr            = EXCLUDED.vs_pitcher_hr,
    vs_pitcher_avg           = EXCLUDED.vs_pitcher_avg,
    hr_vs_r                  = EXCLUDED.hr_vs_r,
    hr_vs_l                  = EXCLUDED.hr_vs_l,
    humidity_pct             = EXCLUDED.humidity_pct,
    precip_pct               = EXCLUDED.precip_pct,
    wind_description         = EXCLUDED.wind_description,
    game_time                = EXCLUDED.game_time,
    stadium                  = EXCLUDED.stadium,
    created_at               = NOW();
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
                for stmt in MIGRATE_HR_PREDICTIONS + MIGRATE_TRACKED_BETS:
                    try:
                        cur.execute("SAVEPOINT mig")
                        cur.execute(stmt)
                        cur.execute("RELEASE SAVEPOINT mig")
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT mig")  # keep outer tx alive
                # Sync: delete any today-rows whose game_id is no longer in the CSV.
                # This removes players from postponed/cancelled games that were stripped
                # from the output file since the last pipeline run.
                if not df.empty:
                    csv_game_ids = [int(x) for x in df['game_id'].dropna().unique()]
                    cur.execute(
                        "DELETE FROM hr_predictions WHERE game_date = %s AND game_id != ALL(%s)",
                        (date_str, csv_game_ids),
                    )
                    deleted = cur.rowcount
                    if deleted > 0:
                        print(f"  Removed {deleted} stale row(s) for postponed/cancelled game(s).")

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
                        'opp_team':      _str(row.get('opp_team')),
                        'is_home':       _str(row.get('is_home')),
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
                        'season_hr':     _int(row.get('season_hr')),
                        'bat_order':     _int(row.get('bat_order')),
                        'game_total':    _clean(row.get('game_total')),
                        'recent_hr':     _int(row.get('recent_hr')),
                        'barrel_pct_15':            _clean(row.get('barrel_pct_15')),
                        'hardhit_pct_15':           _clean(row.get('hardhit_pct_15')),
                        'flyball_pct_15':           _clean(row.get('flyball_pct_15')),
                        'avg_ev_15':                _clean(row.get('avg_ev_15')),
                        'xwoba_15':                 _clean(row.get('xwoba_15')),
                        'xslg_15':                  _clean(row.get('xslg_15')),
                        'p_barrel_pct_allowed_10':  _clean(row.get('p_barrel_pct_allowed_10')),
                        'p_hardhit_pct_allowed_10': _clean(row.get('p_hardhit_pct_allowed_10')),
                        'p_hr_per_bb_allowed_10':   _clean(row.get('p_hr_per_bb_allowed_10')),
                        'days_since_hr': _int(row.get('days_since_hr')),
                        'p_fip':         _clean(row.get('p_fip')),
                        'pitcher_era':        _clean(row.get('pitcher_era')),
                        'pitcher_hr9':        _clean(row.get('pitcher_hr9')),
                        'pitcher_hr_allowed': _int(row.get('pitcher_hr_allowed')),
                        'pitcher_ip':         _clean(row.get('pitcher_ip')),
                        'vs_pitcher_ab':  _int(row.get('vs_pitcher_ab')),
                        'vs_pitcher_h':   _int(row.get('vs_pitcher_h')),
                        'vs_pitcher_hr':  _int(row.get('vs_pitcher_hr')),
                        'vs_pitcher_avg': _clean(row.get('vs_pitcher_avg')),
                        'hr_vs_r': _int(row.get('hr_vs_r')),
                        'hr_vs_l': _int(row.get('hr_vs_l')),
                        'humidity_pct':     _clean(row.get('humidity_pct')),
                        'precip_pct':       _clean(row.get('precip_pct')),
                        'wind_description': _str(row.get('wind_description')),
                        'game_time':        _str(row.get('game_time')),
                        'stadium':          _str(row.get('stadium')),
                    })
        print(f"  Done -- {len(df)} rows upserted.")
    finally:
        conn.close()


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
