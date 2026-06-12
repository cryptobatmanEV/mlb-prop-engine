'use client';

import { useMemo } from 'react';
import TrackButton from './TrackButton';
import type { Row } from './PropsTable';

// ── Config ─────────────────────────────────────────────────────────────────

const MIN_EDGE   = 0.02; // HR edges run smaller than K edges -- 2% minimum to qualify
const MAX_PICKS  = 5;

// We don't track season-long plate appearances, so approximate the PA a
// regular-lineup hitter has accumulated by mid-season. season_hr / this
// estimate stands in for the "season HR rate" term in the scoring formula.
const SEASON_PA_ESTIMATE = 280;

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
  if (row.adj_prob == null) return null;

  const edgeScore = row.edge;

  const barrel       = row.barrel_pct_15 ?? 0;
  const barrelBonus  = (barrel - 0.08) * 3;

  const hardhit       = row.hardhit_pct_15 ?? 0;
  const hardHitBonus  = (hardhit - 0.35) * 1.5;

  const park       = row.hr_park_factor ?? 100;
  const parkBonus  = (park - 100) * 0.002;

  const bo           = row.bat_order;
  const lineupBonus  = bo != null && bo <= 4 ? 0.01 : bo != null && bo <= 6 ? 0.005 : 0;

  const seasonHr           = row.season_hr ?? 0;
  const seasonHrRateBonus  = (seasonHr / SEASON_PA_ESTIMATE - 0.03) * 2;

  const score = edgeScore + barrelBonus + hardHitBonus + parkBonus + lineupBonus + seasonHrRateBonus;

  // Build a one-line "why" from the strongest positive contributors
  const candidates: { label: string; value: number }[] = [
    { label: 'strong market edge',       value: edgeScore > 0.04 ? edgeScore       : 0 },
    { label: 'elite barrel rate',        value: barrel    >= 0.12 ? barrelBonus    : 0 },
    { label: 'consistent hard contact',  value: hardhit   >= 0.45 ? hardHitBonus   : 0 },
    { label: 'HR-friendly park',         value: park      >= 105  ? parkBonus      : 0 },
    {
      label: bo != null && bo <= 4 ? 'top of the lineup' : 'middle of the lineup',
      value: lineupBonus > 0 ? lineupBonus : 0,
    },
    { label: 'proven power this season', value: seasonHr  >= 12   ? seasonHrRateBonus : 0 },
  ];

  const top = candidates
    .filter(c => c.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 3)
    .map(c => c.label);

  const joined = top.length > 0 ? top.join(', ') : 'positive market edge';
  const reason = joined.charAt(0).toUpperCase() + joined.slice(1) + '.';

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

export default function AiPicks({ rows }: { rows: Row[] }) {
  // Opponent lookup: game_id + team_abbr -> opposing team_abbr
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

  const picks = useMemo(() => {
    return rows
      .map(scorePick)
      .filter((p): p is Pick => p !== null)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_PICKS);
  }, [rows]);

  if (picks.length === 0) {
    return (
      <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
        <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO AI PICKS TODAY</div>
        <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
          Nothing clears the +{(MIN_EDGE * 100).toFixed(0)}% edge threshold yet. Check back after lineups/odds refresh.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ ...LABEL, marginBottom: '10px', letterSpacing: '2px' }}>
        TOP {picks.length} HR PLAY{picks.length !== 1 ? 'S' : ''} &mdash; RANKED BY COMPOSITE CONFIDENCE SCORE
      </div>
      <div style={{
        display:             'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap:                 '12px',
      }}>
        {picks.map(({ row, score, reason }, idx) => {
          const opponent = opponents.get(`${row.game_id}-${row.team_abbr}`);
          const edgePct  = (row.edge as number) * 100;
          const edgeColor = edgePct > 5 ? 'var(--ev-green)' : 'var(--ev-green)';

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
                    {row.team_abbr} {row.is_home === 'H' ? 'vs' : '@'} {opponent ?? '???'}
                    {row.game_time && <> &middot; {row.game_time}</>}
                  </div>
                  {row.pitcher_name && (
                    <div style={{ ...LABEL, marginTop: '2px', fontSize: '9px', color: 'var(--ev-dim)' }}>
                      VS {row.pitcher_name}{row.p_throws ? ` (${row.p_throws})` : ''}
                    </div>
                  )}
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px',
                  color: 'var(--ev-green)', border: '1px solid rgba(0,220,110,0.3)',
                  borderRadius: '2px', padding: '3px 6px', whiteSpace: 'nowrap',
                }}>
                  #{idx + 1} PICK
                </div>
              </div>

              {/* Odds / Adj / Edge */}
              <div style={{ display: 'flex', gap: '20px' }}>
                <StatChip label="ODDS" value={fmtOdds(row.best_odds)} sub={row.best_book ?? undefined} color="var(--ev-blue)" />
                <StatChip label="ADJ%" value={fmtPct(row.adj_prob)} />
                <StatChip
                  label="EDGE"
                  value={`+${edgePct.toFixed(1)}%`}
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
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
