"""
Generic AI PICKS logger for the Hits / Total Bases / Batter Ks models.
Simplified composite score vs. the HR model's (no barrel/hard-hit/park terms,
since those diagnostics are HR-specific) -- same qualifying thresholds and
same shape (one *_ai_picks_log table per model, matching hr_ai_picks_log).

Called by daily_pipeline.py after batter_props_fair_odds.py writes each
model's predictions table.
"""
import math
import os
import psycopg2
from datetime import date as date_cls, datetime, timezone
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

MIN_ADJ_PROB = 0.12
MIN_EDGE     = -0.03
MAX_ODDS     = 500


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


def score_row(row):
    if not row.get('primary_has_line'):
        return None
    edge = _f(row.get('primary_edge'))
    adj_prob = _f(row.get('adj_prob'))
    if edge is None or edge <= MIN_EDGE:
        return None
    if adj_prob is None or adj_prob <= MIN_ADJ_PROB:
        return None
    best_odds = _i(row.get('primary_best_odds'))
    if best_odds is None or best_odds > MAX_ODDS:
        return None

    bo = _i(row.get('bat_order'))
    lineup_bonus = (0.25 if bo is not None and bo <= 3 else
                    0.10 if bo is not None and bo <= 5 else
                    0.02 if bo is not None and bo <= 7 else 0.0)
    book_implied = _f(row.get('primary_book_implied')) or 0.0

    return adj_prob * 5 + edge * 2 + lineup_bonus + book_implied * 2


def run(ai_picks_table, priced_df, date_str=None, captured_at=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    if not DATABASE_URL:
        print("  DATABASE_URL not set -- skipping AI picks log.")
        return
    if priced_df is None or priced_df.empty:
        print(f"  No rows to score for {ai_picks_table}.")
        return

    picks = []
    for _, row in priced_df.iterrows():
        score = score_row(row)
        if score is None:
            continue
        picks.append({
            'game_date': date_str, 'captured_at': captured_at,
            'batter': int(row['batter']), 'player_name': _s(row.get('player_name')),
            'team': _s(row.get('team_abbr')),
            'best_odds': _i(row.get('primary_best_odds')), 'best_book': _s(row.get('primary_best_book')),
            'edge': _f(row.get('primary_edge')), 'adj_prob': _f(row.get('adj_prob')),
            'fair_odds': None, 'model_prob': _f(row.get('adj_prob')),
            'composite_score': float(score),
        })

    if not picks:
        print(f"  0 plays qualify for AI PICKS in {ai_picks_table} on {date_str}.")
        return

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.executemany(f"""
                    INSERT INTO {ai_picks_table}
                        (game_date, captured_at, batter, player_name, team,
                         best_odds, best_book, edge, adj_prob, fair_odds,
                         model_prob, composite_score)
                    VALUES
                        (%(game_date)s, %(captured_at)s, %(batter)s, %(player_name)s, %(team)s,
                         %(best_odds)s, %(best_book)s, %(edge)s, %(adj_prob)s, %(fair_odds)s,
                         %(model_prob)s, %(composite_score)s)
                """, picks)
        print(f"  Logged {len(picks)} AI PICK(s) into {ai_picks_table} for {date_str}.")
    finally:
        conn.close()
