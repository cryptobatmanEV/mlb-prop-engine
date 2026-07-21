# total_bases_2plus_model_v2.pkl -- candidate, NOT deployed

Archived for future reference, not wired into `predict/batter_props_runner.py`
or any other prediction path. Nothing reads this file today.

## What it is

Same features as the deployed `total_bases_2plus_model.pkl` plus one addition:
`extra_base_hit_rate_15` = (2B + 3B + HR) / AB over the trailing 15 games
(added to `features/batter_pa_features.py` alongside this experiment).

## Why it wasn't promoted

Investigated after the audit found `bat_order` carrying ~27-28% of total model
gain -- by far the dominant feature, enough that Shohei Ohtani (.792 xSLG)
was ranking below Nick Gonzales (.445 xSLG) in P(2+ TB) on 2026-07-20.

Two things were tested:
- Removing `bat_order` entirely: AUC 0.6265 -> 0.6126 (-0.0138), well past the
  agreed 0.005 tolerance. `bat_order` carries real signal (batting order
  correlates -0.16 with target_tb_2plus, the strongest single correlation of
  any feature) and isn't safe to drop.
- Adding `extra_base_hit_rate_15` (this file): AUC 0.6265 -> 0.6266, a
  statistical tie. `bat_order`'s gain share didn't move (27.5% -> 28.9%,
  if anything higher). Live-tested against 2026-07-20's actual matchups:
  Ohtani and Bobby Witt Jr. moved up in rank, but Matt Olson moved *down*
  (rank 23 -> 40), and Nick Gonzales still ranked above all three. Mixed
  result, doesn't clear the bar of "elite power hitters should outrank a
  modest-power leadoff hitter."

Conclusion at the time: Gonzales' high rank isn't obviously a bug -- he was
batting leadoff (max expected PA) against a pitcher allowing a .430 SLG /
1.68 HR9, a genuinely favorable matchup context. The model weighing
"weak pitcher + leadoff slot tonight" against "elite full-season power" is
a real modeling tradeoff, not a clean defect, and this feature addition
didn't resolve it either way. Revisit once more settled results accumulate
to audit against, or if a more structural change (e.g. monotone/interaction
constraints on `bat_order`) is worth the larger investment.

## Full training details

See `models/saved/total_bases_metrics.json` for the deployed model's numbers;
this candidate was trained identically (same LightGBM params, same
2021-2024 train / 2025-2026 test split, same isotonic CV=3 calibration) via
`models/train_batter_props.py`'s trainer, just with the one extra feature.
