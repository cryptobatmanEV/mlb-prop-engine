"""
Apply the AI PICKS formula to today's fair_odds CSV and INSERT all qualifying
plays into hr_ai_picks_log.

Called automatically as Step 5 by daily_pipeline.py after write_to_db.
Can also be run standalone:
    python scripts/log_ai_picks.py              # today
    python scripts/log_ai_picks.py 2026-06-20   # specific date

The formula and thresholds must stay in sync with web/app/components/AiPicks.tsx.
"""

import math, os, sys
import pandas as pd
import psycopg2
from datetime import date as date_cls, datetime, timezone
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATABASE_URL = os.getenv('DATABASE_URL')
OUTPUTS_DIR  = 'data/outputs'

# ── Thresholds — keep in sync with AiPicks.tsx ─────────────────────────────
MIN_ADJ_PROB = 0.12
MIN_EDGE     = -0.03

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS hr_ai_picks_log (
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
    barrel_pct      NUMERIC,
    hard_hit_pct    NUMERIC,
    hr_park_factor  NUMERIC,
    batting_order   INTEGER,
    szn_hr          INTEGER,
    composite_score NUMERIC,
    actual_hr       INTEGER,
    result          TEXT
);
"""


# ── Helpers ─────────────────────────────────────────────────────────────────

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


# ── Scoring — exact mirror of AiPicks.tsx scorePick() ───────────────────────

def score_row(row) -> float | None:
    """
    Returns composite score (float) if the row qualifies for AI PICKS,
    else None.  Logic must stay byte-for-byte identical to the TypeScript.
    """
    # has_line is 1/True in CSV when a market line was found
    try:
        if not int(row.get('has_line', 0)):
            return None
    except (TypeError, ValueError):
        return None

    edge     = _f(row.get('edge'))
    adj_prob = _f(row.get('adj_prob'))

    if edge is None or edge <= MIN_EDGE:
        return None
    if adj_prob is None or adj_prob <= MIN_ADJ_PROB:
        return None

    best_odds = _i(row.get('best_odds'))
    if best_odds is None:
        return None
    break_even = (100 / (best_odds + 100)) if best_odds > 0 else (abs(best_odds) / (abs(best_odds) + 100))
    if adj_prob < break_even + 0.02:
        return None

    barrel  = _f(row.get('barrel_pct_15'))  or 0.0
    hardhit = _f(row.get('hardhit_pct_15')) or 0.0
    bo      = _i(row.get('bat_order'))

    lineup_bonus = (0.15 if bo is not None and bo <= 3 else
                    0.08 if bo is not None and bo <= 5 else
                    0.02 if bo is not None and bo <= 7 else 0.0)

    return (
        adj_prob * 5
        + (barrel  - 0.08) * 2
        + (hardhit - 0.35) * 1
        + lineup_bonus
        + edge * 0.5
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def run(date_str=None, captured_at=None):
    """
    Score today's fair_odds CSV and INSERT all qualifying rows.

    captured_at : datetime (UTC) to stamp rows.  Defaults to now().
                  Pass a specific datetime for backfill runs.
    """
    if date_str is None:
        date_str = date_cls.today().isoformat()
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    if not DATABASE_URL:
        print("  DATABASE_URL not set -- skipping AI picks log.")
        return

    path = os.path.join(OUTPUTS_DIR, f'fair_odds_{date_str}.csv')
    if not os.path.exists(path):
        print(f"  No fair_odds file for {date_str} -- skipping AI picks log.")
        return

    df = pd.read_csv(path)

    picks = []
    for _, row in df.iterrows():
        score = score_row(row)
        if score is None:
            continue
        picks.append({
            'game_date':      date_str,
            'captured_at':    captured_at,
            'batter':         int(row['batter']),
            'player_name':    _s(row.get('player_name')),
            'team':           _s(row.get('team_abbr')),
            'best_odds':      _i(row.get('best_odds')),
            'best_book':      _s(row.get('best_book')),
            'edge':           _f(row.get('edge')),
            'adj_prob':       _f(row.get('adj_prob')),
            'fair_odds':      _f(row.get('fair_odds')),
            'model_prob':     _f(row.get('model_prob')),
            'barrel_pct':     _f(row.get('barrel_pct_15')),
            'hard_hit_pct':   _f(row.get('hardhit_pct_15')),
            'hr_park_factor': _f(row.get('hr_park_factor')),
            'batting_order':  _i(row.get('bat_order')),
            'szn_hr':         _i(row.get('season_hr')),
            'composite_score': float(score),
        })

    if not picks:
        print(f"  0 plays qualify for AI PICKS on {date_str}.")
        return

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE)
                cur.executemany("""
                    INSERT INTO hr_ai_picks_log
                        (game_date, captured_at, batter, player_name, team,
                         best_odds, best_book, edge, adj_prob, fair_odds,
                         model_prob, barrel_pct, hard_hit_pct, hr_park_factor,
                         batting_order, szn_hr, composite_score)
                    VALUES
                        (%(game_date)s, %(captured_at)s, %(batter)s, %(player_name)s, %(team)s,
                         %(best_odds)s, %(best_book)s, %(edge)s, %(adj_prob)s, %(fair_odds)s,
                         %(model_prob)s, %(barrel_pct)s, %(hard_hit_pct)s, %(hr_park_factor)s,
                         %(batting_order)s, %(szn_hr)s, %(composite_score)s)
                """, picks)
        print(f"  Logged {len(picks)} AI PICK(s) for {date_str}.")
    finally:
        conn.close()


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
