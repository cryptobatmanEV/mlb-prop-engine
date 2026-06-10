# mlb-prop-engine

## Automated workflows (GitHub Actions)

This repo runs three scheduled workflows under `.github/workflows/`:

| Workflow | File | Schedule | What it does |
|---|---|---|---|
| Daily Pipeline | `daily_pipeline.yml` | 15:00 and 20:00 UTC (11 AM and 4 PM ET) every day | Logs yesterday's HR results, generates today's predictions, and writes them to the database. |
| Weekly Model Retrain | `weekly_retrain.yml` | Mondays at 10:00 UTC (6 AM ET) | Pulls fresh Statcast data, rebuilds features, and retrains the model if it improves on the current one. |
| Keepalive | `keepalive.yml` | Sundays at 12:00 UTC | Makes a tiny weekly commit so GitHub doesn't disable the other schedules during quiet periods (see below). |

### Manually running a workflow

GitHub's cron schedules can occasionally be delayed or skipped (this is a known GitHub limitation, not specific to this repo). If a scheduled run is missed, you can trigger any workflow manually:

1. Go to the repo on GitHub and click the **Actions** tab.
2. In the left sidebar, click the workflow you want to run (e.g. **Daily Pipeline**).
3. Click the **Run workflow** dropdown button on the right, then click the green **Run workflow** button.
4. The run will start within a few seconds — click it to watch the logs.

This works at any time, for any of the three workflows above.

### Why the Keepalive workflow exists

GitHub automatically **disables scheduled (cron) workflows after 60 days with no commits pushed to the repo**. During the off-season, the daily pipeline may not produce any commits for long stretches, which could silently turn off the daily/weekly cron schedules. The Keepalive workflow pushes a tiny timestamp update once a week (`.github/keepalive/last_run.txt`) purely to keep the repo "active" so the other schedules keep firing.
