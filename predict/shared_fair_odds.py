"""
Shared odds-joining logic for the Hits / Total Bases / Batter Ks models:
match ParlayAPI events to today's games, pick best odds per (player, line),
and compute edge against model probability. Mirrors the proven patterns in
predict/fair_odds.py (HR model), generalized for two lines per model instead
of one. The HR pipeline is untouched and does not import this module.
"""
import json
import math
import numpy as np
import pandas as pd

_TEAM_KEYS = [
    ('AZ', ['diamondbacks']), ('ATL', ['atlanta']), ('BAL', ['baltimore']),
    ('BOS', ['boston']), ('CHC', ['cubs']), ('CWS', ['white sox']),
    ('CIN', ['cincinnati']), ('CLE', ['cleveland']), ('COL', ['colorado']),
    ('DET', ['detroit']), ('HOU', ['houston']), ('KC', ['kansas city']),
    ('LAA', ['angels']), ('LAD', ['dodgers']), ('MIA', ['miami']),
    ('MIL', ['milwaukee']), ('MIN', ['minnesota']), ('NYM', ['mets']),
    ('NYY', ['yankees']), ('ATH', ['athletics']), ('PHI', ['philadelphia']),
    ('PIT', ['pittsburgh']), ('SD', ['san diego', 'padres']), ('SEA', ['seattle']),
    ('SF', ['san francisco', 'giants']), ('STL', ['cardinals']), ('TB', ['tampa bay']),
    ('TEX', ['texas', 'rangers']), ('TOR', ['toronto']), ('WSH', ['washington']),
]
_ABBR_KEYS = {abbr: keys for abbr, keys in _TEAM_KEYS}


def _team_matches_abbr(abbr, odds_name):
    keys = _ABBR_KEYS.get(abbr, [abbr.lower()])
    return any(k in odds_name.lower() for k in keys)


def match_games_to_events(games, events):
    """{game_id: parlay_event_id} by matching home+away team names."""
    mapping = {}
    for game in games:
        for ev in events:
            if (_team_matches_abbr(game['home_abbr'], ev.get('home_team', '')) and
                    _team_matches_abbr(game['away_abbr'], ev.get('away_team', ''))):
                mapping[game['game_id']] = ev['id']
                break
    return mapping


def best_lines_per_player(all_df, line):
    """One row per player for a specific line value: the book with the highest American odds."""
    if all_df.empty:
        return pd.DataFrame()
    sub = all_df[all_df['line'] == line]
    if sub.empty:
        return pd.DataFrame()
    return (sub.sort_values('odds_american', ascending=False)
            .groupby('name_norm', as_index=False).first())


def build_book_markets(all_df):
    """{name_norm: JSON_str} with per-book, per-line odds: {"draftkings": {"0.5": -150, "1.5": 200}}"""
    if all_df.empty:
        return {}
    result = {}
    for name_norm, grp in all_df.groupby('name_norm'):
        books = {}
        for _, r in grp.iterrows():
            bk = str(r.get('bookmaker', '')).lower().strip()
            odds = r.get('odds_american')
            line = r.get('line')
            if bk and odds is not None and not (isinstance(odds, float) and math.isnan(odds)):
                books.setdefault(bk, {})[str(line)] = int(odds)
        if books:
            result[name_norm] = json.dumps(books)
    return result


def join_odds(pred_df, all_df, prob_col_primary, prob_col_secondary,
              primary_line, secondary_line):
    """
    Adds primary_/secondary_ line/has_line/best_book/best_odds/book_implied/edge
    columns to pred_df, matched on normalized player name.
    """
    df = pred_df.copy()
    from predict.shared_parlay import norm_name
    df['name_norm'] = df['player_name'].apply(norm_name)

    book_markets = build_book_markets(all_df)
    df['book_markets'] = df['name_norm'].map(book_markets)

    for line, prob_col, prefix in [
        (primary_line, prob_col_primary, 'primary'),
        (secondary_line, prob_col_secondary, 'secondary'),
    ]:
        best = best_lines_per_player(all_df, line)
        df[f'{prefix}_line'] = line
        if best.empty:
            df[f'{prefix}_has_line'] = False
            df[f'{prefix}_best_book'] = None
            df[f'{prefix}_best_odds'] = None
            df[f'{prefix}_book_implied'] = None
            df[f'{prefix}_edge'] = None
            continue
        merge_src = best[['name_norm', 'bookmaker', 'odds_american', 'implied']].rename(
            columns={'bookmaker': f'{prefix}_best_book', 'odds_american': f'{prefix}_best_odds',
                     'implied': f'{prefix}_book_implied'})
        df = df.merge(merge_src, on='name_norm', how='left')
        df[f'{prefix}_has_line'] = df[f'{prefix}_best_odds'].notna()
        df[f'{prefix}_edge'] = (df[prob_col] - df[f'{prefix}_book_implied']).where(
            df[f'{prefix}_has_line']).round(4)

    return df.drop(columns=['name_norm'])
