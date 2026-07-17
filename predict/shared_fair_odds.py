"""
Shared odds-joining logic for the Hits / Total Bases / Batter Ks models:
match ParlayAPI events to today's games, pick the best odds for whichever
side (over/under) the MODEL actually favors per player and line, and compute
edge against that side's probability. Mirrors the proven patterns in
predict/fair_odds.py (HR model), generalized for two lines and two sides
instead of one. The HR pipeline is untouched and does not import this module.

"Favored side" matters because a batter's P(1+ hits) is often well above
50% (contact is common), which made every row look like a lock at a glance
with only the over price shown. Showing whichever side the model's own
probability actually favors (>= 50% -> over, < 50% -> under) is what makes
the line/odds pairing meaningful rather than just always displaying "over."
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


def _best_side_per_player(all_df, line, side):
    """Best (highest American) odds for one side ('over'/'under') at a given line, per player."""
    if all_df.empty:
        return pd.DataFrame()
    odds_col = 'over_odds' if side == 'over' else 'under_odds'
    sub = all_df[(all_df['line'] == line) & all_df[odds_col].notna()]
    if sub.empty:
        return pd.DataFrame()
    return (sub.sort_values(odds_col, ascending=False)
            .groupby('name_norm', as_index=False).first())


def build_book_markets(all_df):
    """{name_norm: JSON_str} with per-book, per-line, per-side odds:
    {"draftkings": {"0.5": {"over": -150, "under": 120}, "1.5": {...}}}"""
    if all_df.empty:
        return {}
    result = {}
    for name_norm, grp in all_df.groupby('name_norm'):
        books = {}
        for _, r in grp.iterrows():
            bk = str(r.get('bookmaker', '')).lower().strip()
            line = r.get('line')
            if not bk:
                continue
            sides = {}
            over_odds = r.get('over_odds')
            under_odds = r.get('under_odds')
            if over_odds is not None and not (isinstance(over_odds, float) and math.isnan(over_odds)):
                sides['over'] = int(over_odds)
            if under_odds is not None and not (isinstance(under_odds, float) and math.isnan(under_odds)):
                sides['under'] = int(under_odds)
            if sides:
                books.setdefault(bk, {})[str(line)] = sides
        if books:
            result[name_norm] = json.dumps(books)
    return result


def _pick_side_for_row(row, prefix, prob_col):
    """
    Choose which side (over/under) to surface for this player/line: whichever
    the model's own probability favors (>= 50% -> over, < 50% -> under),
    falling back to whatever side actually has a posted price if the
    favored side's price is missing.
    """
    prob = row.get(prob_col)
    favored = 'over' if (prob is None or prob >= 0.5) else 'under'

    over_odds  = row.get(f'_{prefix}_over_odds')
    under_odds = row.get(f'_{prefix}_under_odds')
    has_over  = pd.notna(over_odds)
    has_under = pd.notna(under_odds)

    if favored == 'over' and has_over:
        side = 'over'
    elif favored == 'under' and has_under:
        side = 'under'
    elif has_over:
        side = 'over'
    elif has_under:
        side = 'under'
    else:
        return pd.Series({'side': None, 'best_book': None, 'best_odds': None, 'book_implied': None})

    return pd.Series({
        'side': side,
        'best_book': row.get(f'_{prefix}_{side}_book'),
        'best_odds': row.get(f'_{prefix}_{side}_odds'),
        'book_implied': row.get(f'_{prefix}_{side}_implied'),
    })


def join_odds(pred_df, all_df, prob_col_primary, prob_col_secondary,
              primary_line, secondary_line):
    """
    Adds primary_/secondary_ line/side/has_line/best_book/best_odds/
    book_implied/edge columns to pred_df, matched on normalized player name.
    `edge` is computed against whichever side is actually shown (over or
    under), not always the over side.
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
        df[f'{prefix}_line'] = line

        over_best  = _best_side_per_player(all_df, line, 'over')
        under_best = _best_side_per_player(all_df, line, 'under')

        if not over_best.empty:
            df = df.merge(
                over_best[['name_norm', 'bookmaker', 'over_odds', 'over_implied']]
                .rename(columns={'bookmaker': f'_{prefix}_over_book', 'over_odds': f'_{prefix}_over_odds',
                                  'over_implied': f'_{prefix}_over_implied'}),
                on='name_norm', how='left')
        else:
            df[f'_{prefix}_over_book'] = None
            df[f'_{prefix}_over_odds'] = None
            df[f'_{prefix}_over_implied'] = None

        if not under_best.empty:
            df = df.merge(
                under_best[['name_norm', 'bookmaker', 'under_odds', 'under_implied']]
                .rename(columns={'bookmaker': f'_{prefix}_under_book', 'under_odds': f'_{prefix}_under_odds',
                                  'under_implied': f'_{prefix}_under_implied'}),
                on='name_norm', how='left')
        else:
            df[f'_{prefix}_under_book'] = None
            df[f'_{prefix}_under_odds'] = None
            df[f'_{prefix}_under_implied'] = None

        picked = df.apply(lambda row: _pick_side_for_row(row, prefix, prob_col), axis=1)
        df[f'{prefix}_side']         = picked['side']
        df[f'{prefix}_best_book']    = picked['best_book']
        df[f'{prefix}_best_odds']    = picked['best_odds']
        df[f'{prefix}_book_implied'] = picked['book_implied']
        df[f'{prefix}_has_line']     = df[f'{prefix}_best_odds'].notna()

        # Probability of whichever side is actually shown (under = 1 - P(over)).
        model_prob_for_side = df[prob_col].where(df[f'{prefix}_side'] != 'under', 1 - df[prob_col])
        df[f'{prefix}_edge'] = (model_prob_for_side - df[f'{prefix}_book_implied'].astype(float)).where(
            df[f'{prefix}_has_line']).round(4)

        df = df.drop(columns=[
            f'_{prefix}_over_book', f'_{prefix}_over_odds', f'_{prefix}_over_implied',
            f'_{prefix}_under_book', f'_{prefix}_under_odds', f'_{prefix}_under_implied',
        ])

    return df.drop(columns=['name_norm'])
