import pandas as pd
import os

# 2024 Statcast HR park factors (100 = league average)
# Source: Baseball Savant statcast-park-factors leaderboard
PARK_FACTORS_HR = {
    'COL': 124, 'CIN': 118, 'GABP': 118, 'NYY': 113, 'PHI': 110,
    'MIL': 108, 'BOS': 107, 'CWS': 106, 'BAL': 105, 'HOU': 104,
    'TEX': 103, 'ARI': 103, 'ATL': 102, 'TOR': 101, 'LAA': 101,
    'MIN': 100, 'STL': 100, 'WSH': 99, 'CHC': 99, 'TB': 98,
    'SEA': 97, 'NYM': 97, 'LAD': 96, 'KC': 95, 'DET': 94,
    'CLE': 94, 'SD': 92, 'MIA': 91, 'PIT': 90, 'SF': 88, 'OAK': 87,
}

def get_hr_park_factor(team_code):
    """Return the HR park factor for a team (100 = average)."""
    return PARK_FACTORS_HR.get(team_code, 100)

def save_park_factors():
    """Save park factors to a CSV for the pipeline."""
    df = pd.DataFrame([
        {'team': team, 'hr_park_factor': factor}
        for team, factor in PARK_FACTORS_HR.items()
    ])
    os.makedirs('data/raw', exist_ok=True)
    df.to_csv('data/raw/park_factors_2024.csv', index=False)
    print(f"Saved {len(df)} park factors.")
    print(df.sort_values('hr_park_factor', ascending=False).to_string(index=False))
    return df

if __name__ == "__main__":
    save_park_factors()