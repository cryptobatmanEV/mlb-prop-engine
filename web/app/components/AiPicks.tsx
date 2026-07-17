'use client';

import { useMemo } from 'react';
import TrackButton, { trackedKey } from './TrackButton';
import type { Row } from './PropsTable';

// ── Config ─────────────────────────────────────────────────────────────────

const MIN_ADJ_PROB = 0.12;   // don't surface low-probability longshots
const MIN_EDGE     = -0.03;  // allow slight negative edge; users can shop lines on Novig
const MAX_PICKS    = 5;

// ── Helpers ────────────────────────────────────────────────────────────────

function toISODate(d: unknown): string {
  if (d instanceof Date) return d.toISOString().slice(0, 10);
  return String(d).slice(0, 10);
}

function fmtPct(v: number | null): string {
  if (v == null || isNaN(v)) return '—';
  return (v * 100).toFixed(1) + '%';
}

function fmtOdds(o: number | null): string {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

// ── Scoring ────────────────────────────────────────────────────────────────

type Pick = {
  row: Row;
  score: number;
  reason: string;
};

function scorePick(row: Row): Pick | null {
  if (!row.has_line || row.edge == null || row.edge <= MIN_EDGE) return null;
  if (row.adj_prob == null || row.adj_prob <= MIN_ADJ_PROB) return null;
  if (row.best_odds == null || row.best_odds > 500) return null;
  if (row.barrel_pct_15 === 0) return null;  // zero barrels in 15 games = not an HR threat

  // Primary signal: who is most likely to homer tonight.
  const probScore = row.adj_prob * 5;

  const barrel       = row.barrel_pct_15 ?? 0;
  const barrelBonus  = (barrel - 0.08) * 2;

  const hardhit       = row.hardhit_pct_15 ?? 0;
  const hardHitBonus  = (hardhit - 0.35) * 1;

  const bo           = row.bat_order;
  const lineupBonus  = bo != null && bo <= 3 ? 0.25 : bo != null && bo <= 5 ? 0.10 : bo != null && bo <= 7 ? 0.02 : 0;

  // Secondary signal: market consensus is a stronger predictor than our own edge claim.
  const bookBonus = (row.book_implied ?? 0) * 2;

  const score = probScore + barrelBonus + hardHitBonus + lineupBonus + bookBonus;

  // Build a one-line "why", always leading with the HR probability itself.
  const supporting: { label: string; value: number }[] = [
    { label: 'elite barrel rate',       value: barrel  >= 0.12 ? barrelBonus : 0 },
    { label: 'consistent hard contact', value: hardhit >= 0.45 ? hardHitBonus : 0 },
    {
      label: bo != null && bo <= 3 ? 'top of the order' : bo != null && bo <= 5 ? 'middle of the lineup' : 'lower lineup',
      value: lineupBonus > 0 ? lineupBonus : 0,
    },
    { label: 'market pricing aligned',  value: (row.book_implied ?? 0) >= 0.15 ? bookBonus : 0 },
  ];

  const top = supporting
    .filter(c => c.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 2)
    .map(c => c.label);

  const lead = `${(row.adj_prob * 100).toFixed(1)}% HR probability`;
  const reason = [lead, ...top].join(', ') + '.';

  return { row, score, reason };
}

// ── Style tokens ───────────────────────────────────────────────────────────

const LABEL: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '10px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  color:         'var(--ev-dim)',
};

const CARD: React.CSSProperties = {
  background:   'var(--ev-card)',
  border:       '1px solid var(--ev-border)',
  borderRadius: '2px',
};

// ── Stat chip ──────────────────────────────────────────────────────────────

function StatChip({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ minWidth: '52px' }}>
      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: color ?? 'var(--ev-text)' }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.18)', marginTop: '1px' }}>{sub}</div>
      )}
    </div>
  );
}

// ── Component ──────────────────────────────────────────────────────────────

export default function AiPicks({ rows, trackedSet, authHeaders }: { rows: Row[]; trackedSet: Set<string>; authHeaders?: HeadersInit }) {
  // Opponent lookup: game_id + team_abbr -> opposing team_abbr.
  // Falls back to grouping by game_id for rows written before opp_team existed.
  const opponents = useMemo(() => {
    const byGame = new Map<number, Set<string>>();
    for (const r of rows) {
      if (!byGame.has(r.game_id)) byGame.set(r.game_id, new Set());
      byGame.get(r.game_id)!.add(r.team_abbr);
    }
    const map = new Map<string, string>();
    for (const [gameId, teams] of byGame) {
      const arr = Array.from(teams);
      if (arr.length === 2) {
        map.set(`${gameId}-${arr[0]}`, arr[1]);
        map.set(`${gameId}-${arr[1]}`, arr[0]);
      }
    }
    return map;
  }, [rows]);

  function opponentFor(row: Row): string {
    return row.opp_team ?? opponents.get(`${row.game_id}-${row.team_abbr}`) ?? 'TBD';
  }

  const picks = useMemo(() => {
    return rows
      .map(scorePick)
      .filter((p): p is Pick => p !== null)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_PICKS);
  }, [rows]);

  const wins    = picks.filter(p => p.row.hit_hr === true).length;
  const losses  = picks.filter(p => p.row.hit_hr === false).length;
  const settled = wins + losses;

  if (picks.length === 0) {
    return (
      <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
        <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO AI PICKS TODAY</div>
        <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
          Nothing clears the {(MIN_ADJ_PROB * 100).toFixed(0)}%+ HR probability / edge &gt; −3% threshold yet.
          Check back after lineups/odds refresh.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ ...LABEL, letterSpacing: '2px' }}>
          TOP {picks.length} HR PLAY{picks.length !== 1 ? 'S' : ''} &mdash; RANKED BY LIKELIHOOD TO HOMER
        </div>
        {settled > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '2px', fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 700 }}>
            <span style={{ color: 'var(--ev-green)' }}>{wins}W</span>
            <span style={{ color: 'rgba(255,255,255,0.2)', margin: '0 2px' }}>-</span>
            <span style={{ color: 'var(--ev-red)' }}>{losses}L</span>
            {picks.length > settled && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ev-dim)', fontWeight: 400, marginLeft: '6px', letterSpacing: '1px' }}>
                {picks.length - settled} PENDING
              </span>
            )}
          </div>
        )}
      </div>
      <div className="ai-picks-grid" style={{
        display:             'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap:                 '12px',
      }}>
        {picks.map(({ row, score, reason }, idx) => {
          const opponent = opponentFor(row);
          const edgePct  = (row.edge as number) * 100;
          const edgeColor = edgePct > 0 ? 'var(--ev-green)' : 'var(--ev-muted)';

          return (
            <div
              key={`${row.game_id}-${row.batter}`}
              style={{ ...CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '10px' }}
            >
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                <div>
                  <div style={{
                    fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '15px',
                    color: 'var(--ev-text)', letterSpacing: '-0.3px',
                  }}>
                    {row.player_name}
                  </div>
                  <div style={{ ...LABEL, marginTop: '4px', fontSize: '9px' }}>
                    {row.team_abbr} {row.is_home === 'H' ? 'vs' : '@'} {opponent}
                    {row.game_time && <> &middot; {row.game_time}</>}
                  </div>
                  {row.pitcher_name && (
                    <div style={{ ...LABEL, marginTop: '2px', fontSize: '9px', color: 'var(--ev-dim)' }}>
                      VS {row.pitcher_name}{row.p_throws ? ` (${row.p_throws})` : ''}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '5px' }}>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px',
                    color: 'var(--ev-green)', border: '1px solid rgba(0,220,110,0.3)',
                    borderRadius: '2px', padding: '3px 6px', whiteSpace: 'nowrap',
                  }}>
                    #{idx + 1} PICK
                  </div>
                  {row.hit_hr === true && (
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700,
                      color: '#0a0d0f', background: 'var(--ev-green)',
                      borderRadius: '2px', padding: '2px 8px', letterSpacing: '1px',
                    }}>
                      W
                    </div>
                  )}
                  {row.hit_hr === false && (
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700,
                      color: '#fff', background: 'var(--ev-red)',
                      borderRadius: '2px', padding: '2px 8px', letterSpacing: '1px',
                    }}>
                      L
                    </div>
                  )}
                </div>
              </div>

              {/* Odds / Adj / Edge */}
              <div style={{ display: 'flex', gap: '20px' }}>
                <StatChip label="ODDS" value={fmtOdds(row.best_odds)} sub={row.best_book ?? undefined} color="var(--ev-blue)" />
                <StatChip label="ADJ%" value={fmtPct(row.adj_prob)} />
                <StatChip
                  label="EDGE"
                  value={`${edgePct >= 0 ? '+' : ''}${edgePct.toFixed(1)}%`}
                  color={edgeColor}
                />
              </div>

              {/* Key stats that drove the pick */}
              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <StatChip label="BARREL%" value={fmtPct(row.barrel_pct_15)} />
                <StatChip label="HARD HIT%" value={fmtPct(row.hardhit_pct_15)} />
                <StatChip label="PARK" value={row.hr_park_factor != null ? String(Math.round(row.hr_park_factor)) : '—'} />
                <StatChip label="BO" value={row.bat_order != null ? String(row.bat_order) : '—'} />
                <StatChip label="SZN HR" value={row.season_hr != null ? String(row.season_hr) : '—'} />
              </div>

              {/* Reason */}
              <div style={{
                fontSize: '11px', color: 'var(--ev-muted)', fontStyle: 'italic',
                lineHeight: 1.4, borderTop: '1px solid var(--ev-border)', paddingTop: '8px',
              }}>
                {reason}
              </div>

              {/* Track button */}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <TrackButton
                  gameDate={toISODate(row.game_date)}
                  batter={row.batter}
                  playerName={row.player_name}
                  teamAbbr={row.team_abbr}
                  adjProb={row.adj_prob}
                  trackedOdds={row.best_odds}
                  trackedEdge={row.edge}
                  isTracked={trackedSet.has(trackedKey(toISODate(row.game_date), row.batter))}
                  authHeaders={authHeaders}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
