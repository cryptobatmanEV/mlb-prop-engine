'use client';

import { useState, useMemo } from 'react';
import TrackButton from './TrackButton';

// ── Types ──────────────────────────────────────────────────────────────────

export type Row = {
  id: number;
  game_date: string;
  batter: number;
  game_id: number;
  player_name: string;
  team_abbr: string;
  stand: string | null;
  pitcher_name: string | null;
  p_throws: string | null;
  home_team: string | null;
  adj_prob: number;
  fair_odds: number | null;
  has_line: boolean;
  best_book: string | null;
  best_odds: number | null;
  edge: number | null;
  hr_park_factor: number | null;
  wind_favor: number | null;
  is_dome: boolean;
};

type SortKey =
  | 'player_name' | 'team_abbr' | 'pitcher_name'
  | 'adj_prob' | 'fair_odds' | 'best_odds' | 'edge'
  | 'hr_park_factor' | 'wind_sort';

type SortDir = 'asc' | 'desc';

// ── Helpers ────────────────────────────────────────────────────────────────

function americanToImplied(odds: number): number {
  if (odds > 0) return 100 / (odds + 100);
  return Math.abs(odds) / (Math.abs(odds) + 100);
}

function fmtOdds(o: number | null) {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

function fmtProb(p: number) { return (p * 100).toFixed(1) + '%'; }

function edgeDisplay(edge: number | null, hasLine: boolean) {
  if (!hasLine || edge == null) return { text: '—', color: 'var(--ev-dim)', weight: 400 };
  const sign = edge > 0 ? '+' : '';
  const text = `${sign}${(edge * 100).toFixed(1)}%`;
  if (edge > 0.05)  return { text, color: 'var(--ev-green)', weight: 600 };
  if (edge > 0)     return { text, color: 'var(--ev-green)', weight: 400 };
  if (edge > -0.03) return { text, color: 'var(--ev-muted)',  weight: 400 };
                    return { text, color: 'var(--ev-red)',   weight: 400 };
}

function fmtWind(windFavor: number | null, isDome: boolean) {
  if (isDome) return 'DOME';
  if (windFavor == null) return '—';
  const abs = Math.abs(windFavor).toFixed(0);
  if (windFavor >  2) return `^${abs}`;
  if (windFavor < -2) return `v${abs}`;
  return `~${abs}`;
}

function windSortVal(row: Row): number {
  if (row.is_dome) return 0;
  return row.wind_favor ?? 0;
}

function getSortVal(row: Row, key: SortKey): string | number | null {
  if (key === 'wind_sort')    return windSortVal(row);
  if (key === 'pitcher_name') return row.pitcher_name;
  return row[key as keyof Row] as string | number | null;
}

// ── Style tokens ───────────────────────────────────────────────────────────

const LABEL: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '10px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  color:         'var(--ev-dim)',
};

const TH_BASE: React.CSSProperties = {
  ...LABEL,
  padding:     '10px 14px',
  fontWeight:   500,
  background:  'rgba(255,255,255,0.02)',
  cursor:      'pointer',
  userSelect:  'none',
  whiteSpace:  'nowrap',
};

// ── Column definitions ─────────────────────────────────────────────────────

type ColDef = {
  key:      SortKey | null;
  label:    string;
  align:    'left' | 'right';
};

const COLS: ColDef[] = [
  { key: 'player_name',    label: 'PLAYER',  align: 'left'  },
  { key: 'team_abbr',      label: 'TEAM',    align: 'left'  },
  { key: 'pitcher_name',   label: 'VS',      align: 'left'  },
  { key: 'adj_prob',       label: 'ADJ%',    align: 'right' },
  { key: 'fair_odds',      label: 'FAIR',    align: 'right' },
  { key: 'best_odds',      label: 'BOOK',    align: 'right' },
  { key: 'edge',           label: 'EDGE',    align: 'right' },
  { key: 'hr_park_factor', label: 'PARK',    align: 'right' },
  { key: 'wind_sort',      label: 'WIND',    align: 'right' },
  { key: null,             label: 'MY LINE', align: 'right' },
  { key: null,             label: '',        align: 'right' },
];

// ── Component ──────────────────────────────────────────────────────────────

export default function PropsTable({ rows }: { rows: Row[] }) {
  const [sortKey, setSortKey]     = useState<SortKey>('adj_prob');
  const [sortDir, setSortDir]     = useState<SortDir>('desc');
  const [customOdds, setCustomOdds] = useState<Record<number, string>>({});

  function handleSort(key: SortKey | null) {
    if (!key) return;
    if (key === sortKey) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = getSortVal(a, sortKey);
      const bv = getSortVal(b, sortKey);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;   // nulls always last
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [rows, sortKey, sortDir]);

  return (
    <div style={{ background: 'var(--ev-card)', border: '1px solid var(--ev-border)', borderRadius: '2px', overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
            {COLS.map((col, ci) => {
              const isActive = col.key !== null && sortKey === col.key;
              const isMyLine = col.label === 'MY LINE';
              return (
                <th
                  key={ci}
                  onClick={() => handleSort(col.key)}
                  style={{
                    ...TH_BASE,
                    textAlign: col.align,
                    cursor: col.key ? 'pointer' : 'default',
                    color: isMyLine
                      ? 'var(--ev-gold)'
                      : isActive
                        ? 'var(--ev-text)'
                        : 'var(--ev-dim)',
                  }}
                >
                  {col.label}
                  {isActive && (
                    <span style={{ marginLeft: '4px', fontSize: '9px', color: 'var(--ev-green)' }}>
                      {sortDir === 'desc' ? '▼' : '▲'}
                    </span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => {
            const { text: edgeText, color: edgeColor, weight: edgeWeight } = edgeDisplay(row.edge, row.has_line);

            // Parse custom odds input
            const rawInput   = customOdds[row.batter] ?? '';
            const stripped   = rawInput.trim().replace(/^\+/, '');
            const parsedNum  = stripped !== '' ? parseInt(stripped, 10) : null;
            const customNum  = parsedNum != null && !isNaN(parsedNum) && (parsedNum >= 100 || parsedNum <= -100)
              ? parsedNum : null;
            const myEdge     = customNum != null ? row.adj_prob - americanToImplied(customNum) : null;
            const myEdgeDisp = edgeDisplay(myEdge, customNum != null);

            return (
              <tr key={row.id ?? i} className="pred-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>
                <td style={{ padding: '9px 14px', color: 'var(--ev-text)', fontWeight: 500 }}>
                  {row.player_name}
                </td>
                <td style={{ padding: '9px 14px', color: 'var(--ev-muted)' }}>
                  {row.team_abbr}
                  {row.stand && (
                    <span style={{ color: 'var(--ev-dim)', marginLeft: '5px', fontSize: '10px' }}>
                      {row.stand}
                    </span>
                  )}
                </td>
                <td style={{ padding: '9px 14px', color: 'var(--ev-dim)', fontSize: '11px' }}>
                  {row.pitcher_name ?? 'TBD'}
                  {row.p_throws && (
                    <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '3px' }}>
                      ({row.p_throws})
                    </span>
                  )}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-text)', fontWeight: 500 }}>
                  {fmtProb(row.adj_prob)}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-dim)' }}>
                  {fmtOdds(row.fair_odds)}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right' }}>
                  {row.has_line ? (
                    <>
                      <span style={{ color: 'var(--ev-blue)' }}>{fmtOdds(row.best_odds)}</span>
                      {row.best_book && (
                        <span style={{ color: 'rgba(255,255,255,0.18)', fontSize: '10px', marginLeft: '5px' }}>
                          {row.best_book}
                        </span>
                      )}
                    </>
                  ) : (
                    <span style={{ color: 'var(--ev-dim)', fontSize: '10px' }}>—</span>
                  )}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: edgeColor, fontWeight: edgeWeight }}>
                  {edgeText}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                  {row.hr_park_factor != null ? Math.round(row.hr_park_factor) : '—'}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                  {fmtWind(row.wind_favor, row.is_dome)}
                </td>

                {/* MY LINE cell */}
                <td style={{ padding: '6px 10px 6px 14px', textAlign: 'right' }}>
                  <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                    <input
                      type="text"
                      placeholder="+1000"
                      value={rawInput}
                      onChange={e => setCustomOdds(prev => ({ ...prev, [row.batter]: e.target.value }))}
                      style={{
                        width: '72px',
                        background: 'rgba(255,255,255,0.04)',
                        border: `1px solid ${customNum != null ? 'rgba(255,200,0,0.4)' : 'rgba(255,255,255,0.08)'}`,
                        borderRadius: '2px',
                        color: customNum != null ? 'var(--ev-gold)' : 'rgba(255,255,255,0.25)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '11px',
                        padding: '3px 7px',
                        textAlign: 'right',
                        outline: 'none',
                      }}
                    />
                    {customNum != null && (
                      <span style={{ fontSize: '10px', color: myEdgeDisp.color, fontWeight: myEdgeDisp.weight }}>
                        {myEdgeDisp.text}
                      </span>
                    )}
                  </div>
                </td>

                {/* TRACK cell */}
                <td style={{ padding: '9px 14px', textAlign: 'right' }}>
                  <TrackButton
                    gameDate={String(row.game_date).slice(0, 10)}
                    batter={row.batter}
                    playerName={row.player_name}
                    teamAbbr={row.team_abbr}
                    adjProb={row.adj_prob}
                    bestOdds={row.best_odds}
                    edge={row.edge}
                    hasLine={row.has_line}
                    customOdds={customNum}
                    customEdge={myEdge}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
