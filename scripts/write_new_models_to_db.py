"""
Generic upsert helper for the three new Batter Model tables (hits_predictions,
total_bases_predictions, batter_ks_predictions). Structurally each mirrors
hr_predictions (see scripts/write_to_db.py) but with two probability/line
pairs instead of one. Built as one parameterized function instead of three
near-duplicate ~250-line modules.

Each table gets:
  id, game_date, game_pk, batter, player_name, team_abbr, opp_team,
  bat_order, is_home, game_time, stadium, pitcher_name, p_throws,
  pred_<stat>, p_<stat>_1plus, p_<stat>_2plus, adj_prob,
  primary_line, primary_has_line, primary_best_book, primary_best_odds,
    primary_book_implied, primary_edge,
  secondary_line, secondary_has_line, secondary_best_book, secondary_best_odds,
    secondary_book_implied, secondary_edge,
  pp_line, pp_side, edge_pp, ud_line, ud_side, edge_ud,
  book_markets, result_actual, result_hit_primary, result_hit_secondary,
  created_at

Called by daily_pipeline.py for each of the 3 new models.
"""
import math
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')


def _clean(val):
    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _bool(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return bool(int(val))


def _int(val):
    v = _clean(val)
    return None if v is None else int(v)


def _str(val):
    if val is None:
        return None
    s = str(val)
    return None if s in ('nan', 'None', '') else s


def _ddl(table, stat_prefix):
    """CREATE TABLE IF NOT EXISTS statement for one of the 3 new prediction tables."""
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        id                      SERIAL PRIMARY KEY,
        game_date               DATE        NOT NULL,
        game_pk                 BIGINT      NOT NULL,
        batter                  BIGINT      NOT NULL,
        player_name             TEXT,
        team_abbr               TEXT,
        opp_team                TEXT,
        bat_order               INTEGER,
        is_home                 TEXT,
        game_time               TEXT,
        stadium                 TEXT,
        pitcher_name            TEXT,
        p_throws                TEXT,

        pred_{stat_prefix}      FLOAT,
        p_{stat_prefix}_1plus   FLOAT,
        p_{stat_prefix}_2plus   FLOAT,
        adj_prob                FLOAT,

        primary_line            FLOAT,
        primary_has_line        BOOLEAN,
        primary_side            TEXT,
        primary_best_book       TEXT,
        primary_best_odds       INTEGER,
        primary_book_implied    FLOAT,
        primary_edge            FLOAT,

        secondary_line          FLOAT,
        secondary_has_line      BOOLEAN,
        secondary_side          TEXT,
        secondary_best_book     TEXT,
        secondary_best_odds     INTEGER,
        secondary_book_implied  FLOAT,
        secondary_edge          FLOAT,

        pp_line                 FLOAT,
        pp_side                 TEXT,
        edge_pp                 FLOAT,
        ud_line                 FLOAT,
        ud_side                 TEXT,
        edge_ud                 FLOAT,

        book_markets            TEXT,
        result_actual            INTEGER,
        result_hit_primary       BOOLEAN,
        result_hit_secondary     BOOLEAN,

        created_at              TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (game_date, batter, game_pk)
    );
    """


_AI_PICKS_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id              SERIAL PRIMARY KEY,
    game_date       DATE        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    batter          BIGINT      NOT NULL,
    player_name     TEXT,
    team            TEXT,
    best_odds       INTEGER,
    best_book       TEXT,
    edge            NUMERIC,
    adj_prob        NUMERIC,
    fair_odds       NUMERIC,
    model_prob      NUMERIC,
    composite_score NUMERIC,
    actual_result   INTEGER,
    result          TEXT
);
"""

_ROW_COLS = [
    'game_date', 'game_pk', 'batter', 'player_name', 'team_abbr', 'opp_team',
    'bat_order', 'is_home', 'game_time', 'stadium', 'pitcher_name', 'p_throws',
    'pred_stat', 'p_stat_1plus', 'p_stat_2plus', 'adj_prob',
    'primary_line', 'primary_has_line', 'primary_side', 'primary_best_book', 'primary_best_odds',
    'primary_book_implied', 'primary_edge',
    'secondary_line', 'secondary_has_line', 'secondary_side', 'secondary_best_book', 'secondary_best_odds',
    'secondary_book_implied', 'secondary_edge',
    'pp_line', 'pp_side', 'edge_pp', 'ud_line', 'ud_side', 'edge_ud',
    'book_markets',
]

_MIGRATIONS = [
    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS primary_side TEXT",
    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS secondary_side TEXT",
]


def _upsert_sql(table, stat_prefix):
    real_cols = [c.replace('pred_stat', f'pred_{stat_prefix}')
                  .replace('p_stat_1plus', f'p_{stat_prefix}_1plus')
                  .replace('p_stat_2plus', f'p_{stat_prefix}_2plus')
                 for c in _ROW_COLS]
    col_list = ', '.join(real_cols)
    val_list = ', '.join(f'%({c})s' for c in _ROW_COLS)
    update_list = ', '.join(
        f'{rc} = EXCLUDED.{rc}' for rc, c in zip(real_cols, _ROW_COLS)
        if c not in ('game_date', 'batter', 'game_pk')
    )
    return f"""
    INSERT INTO {table} ({col_list})
    VALUES ({val_list})
    ON CONFLICT (game_date, batter, game_pk) DO UPDATE SET
        {update_list},
        created_at = NOW();
    """


def write_predictions(table, stat_prefix, rows):
    """
    rows: list[dict] keyed by the logical column names in _ROW_COLS
    (game_date, game_pk, batter, ..., pred_stat, p_stat_1plus, p_stat_2plus, ...).
    """
    if not DATABASE_URL:
        print(f"  DATABASE_URL not set -- skipping DB write for {table}.")
        return
    if not rows:
        print(f"  No rows to write for {table}.")
        return

    ai_picks_table = table.replace('_predictions', '_ai_picks_log')

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(_ddl(table, stat_prefix))
                cur.execute(_AI_PICKS_DDL.format(table=ai_picks_table))
                for stmt in _MIGRATIONS:
                    cur.execute(stmt.format(t=table))

                game_date = rows[0]['game_date']
                game_pks = list({int(r['game_pk']) for r in rows if r.get('game_pk') is not None})
                if game_pks:
                    cur.execute(
                        f"DELETE FROM {table} WHERE game_date = %s AND game_pk != ALL(%s)",
                        (game_date, game_pks),
                    )
                    if cur.rowcount:
                        print(f"  Removed {cur.rowcount} stale row(s) for postponed/cancelled game(s).")

                upsert_sql = _upsert_sql(table, stat_prefix)
                for row in rows:
                    params = {}
                    for c in _ROW_COLS:
                        v = row.get(c)
                        if c in ('primary_has_line', 'secondary_has_line'):
                            params[c] = _bool(v)
                        elif c in ('batter', 'game_pk', 'bat_order', 'primary_best_odds', 'secondary_best_odds'):
                            params[c] = _int(v)
                        elif c in ('player_name', 'team_abbr', 'opp_team', 'is_home', 'game_time',
                                   'stadium', 'pitcher_name', 'p_throws', 'primary_side', 'primary_best_book',
                                   'secondary_side', 'secondary_best_book', 'pp_side', 'ud_side',
                                   'book_markets', 'game_date'):
                            params[c] = _str(v)
                        else:
                            params[c] = _clean(v)
                    cur.execute(upsert_sql, params)
        print(f"  Done -- {len(rows)} rows upserted into {table}.")
    finally:
        conn.close()
