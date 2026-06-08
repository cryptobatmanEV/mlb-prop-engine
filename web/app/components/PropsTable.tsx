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
  is_home: string | null;
  adj_prob: number;
  fair_odds: number | null;
  has_line: boolean;
  best_book: string | null;
  best_odds: number | null;
  edge: number | null;
  hr_park_factor: number | null;
  wind_favor: number | null;
  is_dome: boolean;
  season_hr: number | null;
  bat_order: number | null;
  game_total: number | null;
  recent_hr: number | null;
};

type SortKey =
  | 'player_name' | 'team_abbr' | 'pitcher_name'
  | 'adj_prob' | 'fair_odds' | 'best_odds' | 'edge'
  | 'hr_park_factor' | 'wind_sort'
  | 'bat_order' | 'season_hr' | 'game_total' | 'is_home';

type SortDir = 'asc' | 'desc';

// ── Helpers ────────────────────────────────────────────────────────────────

function americanToImplied(odds: number): number {
  if (odds > 0) return 100 / (odds + 100);
  return Math.abs(odds) / (Math.abs(odds) + 100);
}

function parseCustomOdds(raw: string): number | null {
  const stripped = raw.trim().replace(/^\+/, '');
  if (!stripped) return null;
  const n = parseInt(stripped, 10);
  if (isNaN(n)) return null;
  if (n >= 100 || n <= -100) return n;
  return null;
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
                    return { text, color: 'var(--ev-red)',    weight: 400 };
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
  return row.is_dome ? 0 : (row.wind_favor ?? 0);
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
  padding:    '10px 12px',
  fontWeight:  500,
  background: 'rgba(255,255,255,0.02)',
  userSelect: 'none',
  whiteSpace: 'nowrap',
};

// Solid bg for sticky column cells (prevents content bleed-through when scrolling)
const STICKY_BG = '#0a0d0f';

// ── Column definitions ─────────────────────────────────────────────────────

type ColDef = { key: SortKey | null; label: string; align: 'left' | 'right'; sticky?: boolean };

const COLS: ColDef[] = [
  { key: 'player_name',    label: 'PLAYER',  align: 'left',  sticky: true },
  { key: 'bat_order',      label: 'BO',      align: 'right' },
  { key: 'is_home',        label: 'H/A',     align: 'right' },
  { key: 'team_abbr',      label: 'TEAM',    align: 'left'  },
  { key: 'pitcher_name',   label: 'VS',      align: 'left'  },
  { key: 'adj_prob',       label: 'ADJ%',    align: 'right' },
  { key: 'season_hr',      label: 'SZN HR',  align: 'right' },
  { key: 'fair_odds',      label: 'FAIR',    align: 'right' },
  { key: 'best_odds',      label: 'BOOK',    align: 'right' },
  { key: null,             label: 'MY LINE', align: 'right' },
  { key: 'edge',           label: 'EDGE',    align: 'right' },
  { key: 'game_total',     label: 'O/U',     align: 'right' },
  { key: 'hr_park_factor', label: 'PARK',    align: 'right' },
  { key: 'wind_sort',      label: 'WIND',    align: 'right' },
  { key: null,             label: '',        align: 'right' },
];

// ── Component ──────────────────────────────────────────────────────────────

export default function PropsTable({ rows }: { rows: Row[] }) {
  const [sortKey,    setSortKey]    = useState<SortKey>('adj_prob');
  const [sortDir,    setSortDir]    = useState<SortDir>('desc');
  const [customOdds, setCustomOdds] = useState<Record<number, string>>({});
  const [evOnly,     setEvOnly]     = useState(false);

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
    const base = evOnly
      ? rows.filter(r => r.has_line && r.edge != null && r.edge > 0)
      : rows;
    return [...base].sort((a, b) => {
      const av = getSortVal(a, sortKey);
      const bv = getSortVal(b, sortKey);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [rows, sortKey, sortDir, evOnly]);

  const evCount = rows.filter(r => r.has_line && r.edge != null && r.edge > 0).length;

  return (
    <div>
      {/* Filter toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
        <button
          onClick={() => setEvOnly(v => !v)}
          style={{
            fontFamily:    'var(--font-mono)',
            fontSize:      '10px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            padding:       '5px 12px',
            borderRadius:  '2px',
            cursor:        'pointer',
            background:    evOnly ? 'rgba(0, 220, 110, 0.12)' : 'transparent',
            border:        evOnly ? '1px solid var(--ev-green)' : '1px solid rgba(255,255,255,0.12)',
            color:         evOnly ? 'var(--ev-green)' : 'var(--ev-dim)',
          }}
        >
          +EV ONLY
        </button>
        <span style={{ ...LABEL, fontSize: '10px' }}>
          {evOnly
            ? `SHOWING ${evCount} +EV PLAY${evCount !== 1 ? 'S' : ''}`
            : `${evCount} +EV / ${rows.length} TOTAL`}
        </span>
      </div>

      {/* Table */}
      <div style={{
        background: 'var(--ev-card)', border: '1px solid var(--ev-border)',
        borderRadius: '2px', overflowX: 'auto',
      }}>
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
                      ...(col.sticky ? {
                        position:    'sticky',
                        left:        0,
                        zIndex:      2,
                        background:  STICKY_BG,
                        borderRight: '1px solid var(--ev-border)',
                      } : {}),
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
              const { text: edgeText, color: edgeColor, weight: edgeWeight } =
                edgeDisplay(row.edge, row.has_line);

              const rawInput  = customOdds[row.batter] ?? '';
              const customNum = parseCustomOdds(rawInput);
              const myEdge    = customNum != null
                ? row.adj_prob - americanToImplied(customNum)
                : null;
              const myEdgeDisp = edgeDisplay(myEdge, customNum != null);

              const trackedOdds = customNum ?? row.best_odds;
              const trackedEdge = customNum != null ? myEdge : row.edge;

              return (
                <tr key={row.id ?? i} className="pred-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>

                  {/* PLAYER — sticky */}
                  <td style={{
                    padding:     '9px 12px',
                    color:       'var(--ev-text)',
                    fontWeight:  500,
                    position:    'sticky',
                    left:        0,
                    zIndex:      1,
                    background:  STICKY_BG,
                    borderRight: '1px solid var(--ev-border)',
                    whiteSpace:  'nowrap',
                  }}>
                    {row.player_name}
                    {row.recent_hr === 1 && (
                      <span style={{
                        marginLeft:    '6px',
                        fontSize:      '9px',
                        letterSpacing: '1px',
                        color:         'var(--ev-gold)',
                        fontWeight:    600,
                      }}>
                        HOT
                      </span>
                    )}
                  </td>

                  {/* BO */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {row.bat_order ?? '—'}
                  </td>

                  {/* H/A */}
                  <td style={{
                    padding:   '9px 12px',
                    textAlign: 'right',
                    fontSize:  '11px',
                    color:     row.is_home === 'H' ? 'var(--ev-green)' : 'var(--ev-muted)',
                  }}>
                    {row.is_home ?? '—'}
                  </td>

                  {/* TEAM */}
                  <td style={{ padding: '9px 12px', color: 'var(--ev-muted)' }}>
                    {row.team_abbr}
                    {row.stand && (
                      <span style={{ color: 'var(--ev-dim)', marginLeft: '5px', fontSize: '10px' }}>
                        {row.stand}
                      </span>
                    )}
                  </td>

                  {/* VS */}
                  <td style={{ padding: '9px 12px', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {row.pitcher_name ?? 'TBD'}
                    {row.p_throws && (
                      <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '3px' }}>
                        ({row.p_throws})
                      </span>
                    )}
                  </td>

                  {/* ADJ% */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-text)', fontWeight: 500 }}>
                    {fmtProb(row.adj_prob)}
                  </td>

                  {/* SZN HR */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {row.season_hr ?? '—'}
                  </td>

                  {/* FAIR */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)' }}>
                    {fmtOdds(row.fair_odds)}
                  </td>

                  {/* BOOK */}
                  <td style={{ padding: '9px 12px', textAlign: 'right' }}>
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

                  {/* MY LINE */}
                  <td style={{ padding: '6px 10px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                      <input
                        type="text"
                        placeholder="+1000"
                        value={rawInput}
                        onChange={e => setCustomOdds(prev => ({ ...prev, [row.batter]: e.target.value }))}
                        style={{
                          width:        '72px',
                          background:   'rgba(255,255,255,0.04)',
                          border:       `1px solid ${customNum != null ? 'rgba(255,200,0,0.4)' : 'rgba(255,255,255,0.08)'}`,
                          borderRadius: '2px',
                          color:        customNum != null ? 'var(--ev-gold)' : 'rgba(255,255,255,0.25)',
                          fontFamily:   'var(--font-mono)',
                          fontSize:     '11px',
                          padding:      '3px 7px',
                          textAlign:    'right',
                          outline:      'none',
                        }}
                      />
                      {customNum != null && (
                        <span style={{
                          fontSize: '10px', letterSpacing: '1px',
                          color: myEdgeDisp.color, fontWeight: myEdgeDisp.weight,
                        }}>
                          {myEdgeDisp.text} EV
                        </span>
                      )}
                    </div>
                  </td>

                  {/* EDGE */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: edgeColor, fontWeight: edgeWeight }}>
                    {edgeText}
                  </td>

                  {/* O/U */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {row.game_total != null ? row.game_total : '—'}
                  </td>

                  {/* PARK */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {row.hr_park_factor != null ? Math.round(row.hr_park_factor) : '—'}
                  </td>

                  {/* WIND */}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                    {fmtWind(row.wind_favor, row.is_dome)}
                  </td>

                  {/* TRACK */}
                  <td style={{ padding: '6px 14px', textAlign: 'right' }}>
                    <TrackButton
                      gameDate={String(row.game_date).slice(0, 10)}
                      batter={row.batter}
                      playerName={row.player_name}
                      teamAbbr={row.team_abbr}
                      adjProb={row.adj_prob}
                      trackedOdds={trackedOdds}
                      trackedEdge={trackedEdge}
                    />
                  </td>

                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
