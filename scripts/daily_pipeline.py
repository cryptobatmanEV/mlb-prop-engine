"""
Full daily pipeline - run everything in one command.

Usage:
    python scripts/daily_pipeline.py              # today
    python scripts/daily_pipeline.py 2026-06-07   # specific date

Steps (run in order):
    1. update_statcast  -- pull new Statcast batted-ball data through yesterday
    2. daily_runner     -- score today's batters, output predictions CSV
    3. fair_odds        -- filter to confirmed starters, join market lines, compute edge
    4. write_to_db      -- upsert today's fair_odds into Neon PostgreSQL (powers web app)

Output files:
    data/predictions/predictions_{date}.csv   -- raw model scores for all roster players
    data/outputs/fair_odds_{date}.csv         -- confirmed starters only, with edge column

Run log_results.py the next morning to record actual HR outcomes.
"""

import os, sys, time, traceback
from datetime import date as date_cls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _run_step(label, fn, *args):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = fn(*args)
        print(f"  Completed in {time.time()-t0:.1f}s")
        return result, True
    except Exception as e:
        print(f"  FAILED after {time.time()-t0:.1f}s: {e}")
        traceback.print_exc()
        return None, False


def run(date_str=None):
    if date_str is None:
        date_str = date_cls.today().isoformat()

    print(f"\n{'#'*60}")
    print(f"#  Daily Pipeline  --  {date_str}")
    print(f"{'#'*60}")

    # Step 1: update Statcast (non-fatal if it fails)
    from ingestion.update_statcast import update
    _run_step("Step 1/3  Update Statcast", update)
    # Continue even on failure -- predictions still use yesterday's features

    # Step 2: daily runner (fatal if it fails -- nothing to do in step 3)
    from predict.daily_runner import run as runner_run
    preds, ok = _run_step(f"Step 2/3  Daily runner ({date_str})", runner_run, date_str)
    if not ok or preds is None or len(preds) == 0:
        print("\nDaily runner produced no output. Stopping.")
        return

    # Step 3: fair odds (non-fatal -- predictions are already saved)
    from predict.fair_odds import run as odds_run
    _run_step(f"Step 3/4  Fair odds ({date_str})", odds_run, date_str)

    # Step 4: write to Neon DB (non-fatal -- CSV is the source of truth)
    from scripts.write_to_db import run as db_run
    _run_step(f"Step 4/5  Write to DB ({date_str})", db_run, date_str)

    # Step 5: log AI PICKS snapshot (non-fatal)
    from scripts.log_ai_picks import run as ai_picks_run
    _run_step(f"Step 5/5  Log AI picks ({date_str})", ai_picks_run, date_str)

    print(f"\n{'#'*60}")
    print(f"#  Done  --  {date_str}")
    print(f"#  Predictions : data/predictions/predictions_{date_str}.csv")
    print(f"#  Fair odds   : data/outputs/fair_odds_{date_str}.csv")
    print(f"#  Web app     : powered by Neon DB (check your Vercel URL)")
    print(f"#")
    print(f"#  Tomorrow morning, log actual results:")
    print(f"#  python scripts/log_results.py {date_str}")
    print(f"{'#'*60}")


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
