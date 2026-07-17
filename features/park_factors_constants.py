"""
Static PARK_FACTORS lookup for the Hits / Total Bases / Batter Ks models.

Values are baked in (not recomputed at runtime) per Decision 4: park factors
don't change meaningfully within a season, so there's no need to hit the
Statcast store or an external API on every pipeline run. The numbers
themselves ARE real, though -- each one was computed from this project's own
Statcast PA-outcome data (3-year recency-weighted, same methodology as the
existing HR model's park_factors.py), not memorized/approximate figures:

  - hit_factor: features/park_hit_factor.py  (H/PA vs league average)
  - tb_factor:  features/park_tb_factor.py   (TB/PA vs league average)
  - hr_factor:  features/park_factors.py     (actual HR / expected HR, bat_side='ALL')

100 = neutral. 110 = 10% more of that stat than league average at this park.
Re-run the three scripts above and regenerate this dict if a park's dimensions
change (rare) or once enough of a new season has accumulated to shift the
3-year window meaningfully -- not on any regular schedule.
"""

PARK_FACTORS = {
    'ATH': dict(hit_factor=106.1, tb_factor=109.2, hr_factor=113.8),
    'ATL': dict(hit_factor=100.6, tb_factor=98.4, hr_factor=97.1),
    'AZ':  dict(hit_factor=105.5, tb_factor=106.3, hr_factor=89.5),
    'BAL': dict(hit_factor=102.7, tb_factor=105.0, hr_factor=101.5),
    'BOS': dict(hit_factor=102.5, tb_factor=97.9, hr_factor=86.2),
    'CHC': dict(hit_factor=98.5, tb_factor=100.5, hr_factor=105.7),
    'CIN': dict(hit_factor=97.3, tb_factor=101.4, hr_factor=113.2),
    'CLE': dict(hit_factor=96.8, tb_factor=95.8, hr_factor=102.3),
    'COL': dict(hit_factor=117.3, tb_factor=118.0, hr_factor=105.2),
    'CWS': dict(hit_factor=95.5, tb_factor=94.6, hr_factor=96.9),
    'DET': dict(hit_factor=97.6, tb_factor=97.8, hr_factor=106.5),
    'HOU': dict(hit_factor=97.4, tb_factor=100.1, hr_factor=118.7),
    'KC':  dict(hit_factor=103.7, tb_factor=102.1, hr_factor=85.4),
    'LAA': dict(hit_factor=95.9, tb_factor=96.6, hr_factor=99.3),
    'LAD': dict(hit_factor=96.8, tb_factor=101.9, hr_factor=115.2),
    'MIA': dict(hit_factor=99.1, tb_factor=96.1, hr_factor=86.7),
    'MIL': dict(hit_factor=96.2, tb_factor=95.7, hr_factor=110.9),
    'MIN': dict(hit_factor=102.9, tb_factor=101.6, hr_factor=95.4),
    'NYM': dict(hit_factor=96.9, tb_factor=97.2, hr_factor=97.5),
    'NYY': dict(hit_factor=94.4, tb_factor=100.1, hr_factor=100.3),
    'PHI': dict(hit_factor=103.7, tb_factor=104.6, hr_factor=118.0),
    'PIT': dict(hit_factor=100.5, tb_factor=96.8, hr_factor=86.2),
    'SD':  dict(hit_factor=95.4, tb_factor=94.6, hr_factor=96.5),
    'SEA': dict(hit_factor=90.9, tb_factor=92.7, hr_factor=102.0),
    'SF':  dict(hit_factor=100.6, tb_factor=96.8, hr_factor=86.1),
    'STL': dict(hit_factor=102.1, tb_factor=95.0, hr_factor=81.5),
    'TB':  dict(hit_factor=100.7, tb_factor=100.8, hr_factor=107.1),
    'TEX': dict(hit_factor=94.8, tb_factor=94.6, hr_factor=93.8),
    'TOR': dict(hit_factor=101.0, tb_factor=102.3, hr_factor=107.9),
    'WSH': dict(hit_factor=104.8, tb_factor=103.6, hr_factor=97.1),
}

DEFAULT_FACTOR = dict(hit_factor=100.0, tb_factor=100.0, hr_factor=100.0)


def get_park_factors(team_abbr):
    """Returns {'hit_factor', 'tb_factor', 'hr_factor'} for a home team abbr, 100/100/100 if unknown."""
    return PARK_FACTORS.get(team_abbr, DEFAULT_FACTOR)
