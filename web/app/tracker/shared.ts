export type TrackedBet = {
  id:           number;
  game_date:    string;
  batter:       number;
  player_name:  string;
  team_abbr:    string;
  adj_prob:     number | null;
  tracked_odds: number | null;
  edge:         number | null;
  stake_units:  number;
  hit_hr:       boolean | null;
  settled:      boolean;
  created_at:   string;
  discord_user_id:  string | null;
  discord_username: string | null;
};

// Postgres DATE columns come back from Neon as JS Date objects, not strings.
// String(date) (e.g. "Mon Jun 09 2026 ...") is not YYYY-MM-DD, so always go
// through toISOString() before slicing out month/day.
export function toISODate(d: unknown): string {
  if (d instanceof Date) return d.toISOString().slice(0, 10);
  return String(d).slice(0, 10);
}

export function fmtDate(d: unknown) {
  return toISODate(d).slice(5).replace('-', '/');
}

export function fmtOdds(o: number | null) {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

export function fmtEdge(edge: number | null, hasLine: boolean): { text: string; color: string } {
  if (!hasLine || edge == null) return { text: '—', color: 'var(--ev-dim)' };
  const text = `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`;
  const color = edge > 0 ? 'var(--ev-green)' : edge > -0.03 ? 'var(--ev-muted)' : 'var(--ev-red)';
  return { text, color };
}

export function betPL(bet: Pick<TrackedBet, 'hit_hr' | 'tracked_odds' | 'stake_units'>): string {
  if (bet.hit_hr === null) return '—';
  if (!bet.hit_hr) return `-${bet.stake_units.toFixed(1)}u`;
  if (bet.tracked_odds == null) return '—';
  const odds = bet.tracked_odds;
  const profit = odds > 0
    ? bet.stake_units * (odds / 100)
    : bet.stake_units * (100 / Math.abs(odds));
  return `+${profit.toFixed(2)}u`;
}
