"""
Backfill result grades for ungraded hr_ai_picks_log rows.

Re-fetches boxscores for past games that were incomplete when log_results.py
originally ran (< 50 AB threshold), then grades any AI picks found in those games.
Also updates hr_predictions.hit_hr for any players that were missed.

Run once:
    python scripts/backfill_ai_picks_grades.py
"""

import os, sys, time
import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MLB_BASE = 'https://statsapi.mlb.com/api/v1'


def _mlb(path, params=None):
    r = requests.get(f'{MLB_BASE}/{path}', params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_hr_counts(game_pk):
    """Return {player_id: hr_count} for a completed game, or {} if still incomplete."""
    try:
        data = _mlb(f'game/{game_pk}/boxscore')
        total_ab = 0
        for side in ('home', 'away'):
            for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                total_ab += pdata.get('stats', {}).get('batting', {}).get('atBats', 0) or 0

        if total_ab < 50:
            print(f'    game {game_pk}: only {total_ab} AB — still incomplete, skipping')
            return {}

        hr_counts = {}
        for side in ('home', 'away'):
            for pdata in data.get('teams', {}).get(side, {}).get('players', {}).values():
                pid = pdata.get('person', {}).get('id')
                hr  = pdata.get('stats', {}).get('batting', {}).get('homeRuns', 0) or 0
                if pid:
                    hr_counts[int(pid)] = int(hr)

        print(f'    game {game_pk}: {total_ab} AB, {len(hr_counts)} players found')
        return hr_counts
    except Exception as e:
        print(f'    game {game_pk}: fetch failed: {e}')
        return {}


def find_game_id_for_batter(game_date, batter_id):
    """
    For a batter with no hr_predictions row, search the MLB schedule for that
    date and scan boxscores until we find the batter.
    """
    try:
        data = _mlb('schedule', {'sportId': 1, 'date': str(game_date)})
        game_pks = []
        for date_block in data.get('dates', []):
            for g in date_block.get('games', []):
                game_pks.append(g['gamePk'])

        for pk in game_pks:
            try:
                counts = fetch_hr_counts(pk)
                if batter_id in counts:
                    print(f'    Found batter {batter_id} in game {pk}')
                    return pk, counts
                time.sleep(0.15)
            except Exception:
                pass
    except Exception as e:
        print(f'    schedule lookup failed for {game_date}: {e}')
    return None, {}


def backfill():
    import psycopg2
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL not set')
        return

    conn = psycopg2.connect(db_url)
    try:
        # Step 1: find all ungraded past (date, game_id) pairs via hr_predictions JOIN
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT al.game_date, hp.game_id
                FROM hr_ai_picks_log al
                JOIN hr_predictions hp
                  ON al.game_date = hp.game_date AND al.batter = hp.batter
                WHERE al.result IS NULL
                  AND al.game_date < CURRENT_DATE
                  AND hp.game_id IS NOT NULL
                ORDER BY al.game_date
            """)
            date_games = cur.fetchall()

            # Step 2: also find batters with no hr_predictions row at all
            cur.execute("""
                SELECT DISTINCT al.game_date, al.batter, al.player_name
                FROM hr_ai_picks_log al
                LEFT JOIN hr_predictions hp
                  ON al.game_date = hp.game_date AND al.batter = hp.batter
                WHERE al.result IS NULL
                  AND al.game_date < CURRENT_DATE
                  AND hp.batter IS NULL
                ORDER BY al.game_date
            """)
            orphan_picks = cur.fetchall()

        print(f'Found {len(date_games)} (date, game_id) pairs to re-fetch')
        print(f'Found {len(orphan_picks)} orphan picks (no hr_predictions row)')

        total_graded = 0

        # Process known game_ids
        for game_date, game_id in date_games:
            print(f'\n  {game_date} — game {game_id}')
            hr_counts = fetch_hr_counts(game_id)
            if not hr_counts:
                continue
            time.sleep(0.2)

            with conn:
                with conn.cursor() as cur:
                    # Update hr_predictions.hit_hr for any NULL-result players in this game
                    cur.execute("""
                        SELECT batter FROM hr_predictions
                        WHERE game_date = %s AND game_id = %s AND hit_hr IS NULL
                    """, (game_date, game_id))
                    null_batters = [r[0] for r in cur.fetchall()]
                    pred_updated = 0
                    for batter in null_batters:
                        if batter in hr_counts:
                            hr = hr_counts[batter]
                            cur.execute("""
                                UPDATE hr_predictions
                                   SET hit_hr = %s, actual_hr_count = %s
                                 WHERE game_date = %s AND batter = %s AND hit_hr IS NULL
                            """, (hr > 0, hr, game_date, batter))
                            pred_updated += cur.rowcount
                    if pred_updated:
                        print(f'    Updated hr_predictions for {pred_updated} player(s)')

                    # Grade ungraded AI picks for batters found in this boxscore
                    cur.execute("""
                        SELECT DISTINCT batter FROM hr_ai_picks_log
                        WHERE game_date = %s AND result IS NULL
                    """, (game_date,))
                    ungraded_batters = [r[0] for r in cur.fetchall()]
                    graded = 0
                    for batter in ungraded_batters:
                        if batter in hr_counts:
                            hr     = hr_counts[batter]
                            result = 'HIT' if hr > 0 else 'MISS'
                            cur.execute("""
                                UPDATE hr_ai_picks_log
                                   SET actual_hr = %s, result = %s
                                 WHERE game_date = %s AND batter = %s AND result IS NULL
                            """, (hr, result, game_date, batter))
                            graded += cur.rowcount
                    if graded:
                        print(f'    Graded {graded} AI pick(s)')
                    total_graded += graded

        # Process orphan picks (batter has no hr_predictions row)
        if orphan_picks:
            print(f'\n--- Orphan picks (searching MLB schedule) ---')
            for game_date, batter_id, player_name in orphan_picks:
                print(f'  {game_date} {player_name} ({batter_id})')
                game_pk, hr_counts = find_game_id_for_batter(game_date, batter_id)
                if game_pk is None:
                    print(f'    Could not find game for {player_name} on {game_date}')
                    continue
                hr    = hr_counts.get(batter_id, -1)
                if hr < 0:
                    print(f'    Batter {batter_id} not in boxscore result')
                    continue
                result = 'HIT' if hr > 0 else 'MISS'
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE hr_ai_picks_log
                               SET actual_hr = %s, result = %s
                             WHERE game_date = %s AND batter = %s AND result IS NULL
                        """, (hr, result, game_date, batter_id))
                        graded = cur.rowcount
                if graded:
                    print(f'    Graded {graded} AI pick(s) — {result} ({hr} HR)')
                    total_graded += graded
                time.sleep(0.3)

        print(f'\n{"="*50}')
        print(f'Backfill complete. Total AI picks graded: {total_graded}')
        print(f'{"="*50}')
    finally:
        conn.close()


if __name__ == '__main__':
    backfill()
