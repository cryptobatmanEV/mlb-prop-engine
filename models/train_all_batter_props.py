"""
Retrains the Hits / Total Bases / Batter Ks models via the shared trainer in
models/train_batter_props.py, using the updated feature set: platoon splits,
L5 momentum features (k_rate_last_5, xba_last_5 -- batting_avg_last_5/
xslg_last_5 were already in use), the static PARK_FACTORS constants
(hit_factor/tb_factor), and the refined wind_out (direction ratio + >8mph).

Each candidate feature list below is the previously-deployed feature set
(from models/saved/*_metrics.json) plus the new candidates relevant to that
stat. The shared trainer's own gain-based pruning (drops anything < 0.5% of
total importance) and its promote-only-if-AUC->=-previous-deployed-model
check are what actually decide whether a new feature sticks -- nothing here
is kept just because it's listed.

Usage:
    python models/train_all_batter_props.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.train_batter_props import run

HITS_FEATURES = [
    'batting_avg_15', 'obp_15', 'contact_rate_15', 'hard_hit_pct_15',
    'line_drive_pct_15', 'xba_15', 'babip_15', 'k_rate_15', 'gb_pct_15',
    'batting_avg_vs_R_15', 'batting_avg_vs_L_15', 'batting_avg_last_5',
    'k_rate_last_5', 'xba_last_5',
    'p_hits_per9_10', 'p_babip_allowed_10', 'p_contact_rate_allowed_10',
    'p_k_rate_10', 'p_gb_pct_10',
    'bat_order', 'is_home', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
    'is_dome', 'wind_out', 'hit_factor',
]

TOTAL_BASES_FEATURES = [
    'avg_total_bases_15', 'xslg_15', 'barrel_pct_15', 'hard_hit_pct_15',
    'fly_ball_pct_15', 'iso_15', 'xba_15', 'hr_rate_15', 'doubles_rate_15',
    'slg_vs_R_15', 'slg_vs_L_15', 'xslg_last_5', 'xba_last_5',
    'p_slg_allowed_10', 'p_iso_allowed_10', 'p_barrel_pct_allowed_10',
    'p_fb_pct_10', 'p_hr_per9_10',
    'bat_order', 'is_home', 'stand_R', 'p_throws_R',
    'tb_factor', 'wind_out',
]

BATTER_KS_FEATURES = [
    'k_rate_15', 'avg_k_per_game_15', 'k_rate_vs_R_15', 'k_rate_vs_L_15',
    'k_rate_last_5',
    'p_k_per9_10', 'p_k_rate_10',
    'bat_order', 'opp_k_pct_15', 'stand_R', 'p_throws_R',
]


def main():
    run(
        features=HITS_FEATURES,
        targets=('target_hit_1plus', 'target_hit_2plus'),
        model_paths=('models/saved/hits_1plus_model.pkl', 'models/saved/hits_2plus_model.pkl'),
        metrics_path='models/saved/hits_metrics.json',
        label='Hits',
    )
    run(
        features=TOTAL_BASES_FEATURES,
        targets=('target_tb_1plus', 'target_tb_2plus'),
        model_paths=('models/saved/total_bases_1plus_model.pkl', 'models/saved/total_bases_2plus_model.pkl'),
        metrics_path='models/saved/total_bases_metrics.json',
        label='Total Bases',
    )
    run(
        features=BATTER_KS_FEATURES,
        targets=('target_k_1plus', 'target_k_2plus'),
        model_paths=('models/saved/batter_ks_1plus_model.pkl', 'models/saved/batter_ks_2plus_model.pkl'),
        metrics_path='models/saved/batter_ks_metrics.json',
        label='Batter Ks',
    )


if __name__ == '__main__':
    main()
