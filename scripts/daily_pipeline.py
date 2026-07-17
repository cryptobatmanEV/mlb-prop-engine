"""
Full daily pipeline - run everything in one command.

Usage:
    python scripts/daily_pipeline.py              # today
    python scripts/daily_pipeline.py 2026-06-07   # specific date
    python scripts/daily_pipeline.py --log-only [date]  # grade yesterday's
        results for all 4 models (HR + Hits/Total Bases/Batter Ks), no new
        predictions. This is what the 6 AM ET GitHub Actions run uses --
        it gives the prior evening's late games time to finalize.

Steps (run in order):
    1. update_statcast  -- pull new Statcast PA-outcome data through yesterday
                           (all 4 models share this store; HR features filter
                           to batted balls, Hits/TB/Ks use the full PA outcomes)
    2. daily_runner     -- score today's batters (HR), output predictions CSV
    3. fair_odds        -- filter to confirmed starters, join market lines, compute edge (HR)
    4. write_to_db      -- upsert today's fair_odds into Neon PostgreSQL (HR)
    5. log_ai_picks     -- log qualifying HR plays to hr_ai_picks_log
    6. batter_props_fair_odds -- Hits/Total Bases/Batter Ks: predict, join
                           ParlayAPI odds, write to their own DB tables, log
                           AI picks. Independent of steps 2-5 (HR is untouched).

Output files:
    data/predictions/predictions_{date}.csv        -- HR: raw model scores for all roster players
    data/outputs/fair_odds_{date}.csv              -- HR: confirmed starters only, with edge column
    data/predictions/{hits,total_bases,batter_ks}_predictions_{date}.csv
    data/outputs/{hits,total_bases,batter_ks}_fair_odds_{date}.csv

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


def log_results_only(date_str=None):
    """Grade the prior day's results for all 4 models. No new predictions."""
    print(f"\n{'#'*60}")
    print(f"#  Log Results Only  --  {date_str or '(yesterday)'}")
    print(f"{'#'*60}")

    from scripts.log_results import run as hr_results_run
    _run_step("HR results", hr_results_run, date_str)

    from scripts.shared_log_results import run as shared_run
    _run_step("Hits results", shared_run, 'hits', 'hits_predictions', 'hits_ai_picks_log',
              'hits', 0.5, 1.5, date_str)
    _run_step("Total Bases results", shared_run, 'total_bases', 'total_bases_predictions',
              'total_bases_ai_picks_log', 'totalBases', 0.5, 1.5, date_str)
    _run_step("Batter Ks results", shared_run, 'batter_ks', 'batter_ks_predictions',
              'batter_ks_ai_picks_log', 'strikeOuts', 0.5, 1.5, date_str)


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
    _run_step(f"Step 5/6  Log AI picks ({date_str})", ai_picks_run, date_str)

    # Step 6: Hits / Total Bases / Batter Ks -- predictions, odds, DB write,
    # AI picks all happen inside batter_props_fair_odds.run() (non-fatal --
    # the HR pipeline above already succeeded regardless of this step).
    from predict.batter_props_fair_odds import run as batter_props_run
    _run_step(f"Step 6/6  Hits/Total Bases/Batter Ks ({date_str})", batter_props_run, date_str)

    print(f"\n{'#'*60}")
    print(f"#  Done  --  {date_str}")
    print(f"#  Predictions : data/predictions/predictions_{date_str}.csv")
    print(f"#  Fair odds   : data/outputs/fair_odds_{date_str}.csv")
    print(f"#  Web app     : powered by Neon DB (check your Vercel URL)")
    print(f"#")
    print(f"#  Tomorrow morning, log actual results:")
    print(f"#  python scripts/daily_pipeline.py --log-only {date_str}")
    print(f"{'#'*60}")


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--log-only' in args:
        args = [a for a in args if a != '--log-only']
        date_arg = args[0] if args else None
        log_results_only(date_arg)
    else:
        date_arg = args[0] if args else None
        run(date_arg)
