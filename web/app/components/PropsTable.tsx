'use client';

import { useState, useMemo, Fragment } from 'react';
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
  // Statcast rolling features for detail card
  barrel_pct_15: number | null;
  hardhit_pct_15: number | null;
  flyball_pct_15: number | null;
  avg_ev_15: number | null;
  xwoba_15: number | null;
  xslg_15: number | null;
  p_barrel_pct_allowed_10: number | null;
  p_hardhit_pct_allowed_10: number | null;
  p_hr_per_bb_allowed_10: number | null;
  days_since_hr: number | null;
  p_fip: number | null;
  hit_hr: boolean | null;
  actual_hr_count: number | null;
};

type SortKey =
  | 'player_name' | 'team_abbr' | 'pitcher_name'
  | 'adj_prob' | 'fair_odds' | 'best_odds' | 'edge'
  | 'hr_park_factor' | 'wind_sort'
  | 'bat_order' | 'season_hr' | 'game_total' | 'is_home';

type SortDir = 'asc' | 'desc';

// ── League averages + thresholds for detail card coloring ─────────────────

type StatKey =
  | 'barrel_pct_15' | 'hardhit_pct_15' | 'flyball_pct_15'
  | 'avg_ev_15' | 'xwoba_15' | 'xslg_15'
  | 'p_barrel_pct_allowed_10' | 'p_hardhit_pct_allowed_10' | 'p_hr_per_bb_allowed_10';

const LEAGUE_AVG: Record<StatKey, number> = {
  barrel_pct_15:            0.085,
  hardhit_pct_15:           0.410,
  flyball_pct_15:           0.350,
  avg_ev_15:                88.5,
  xwoba_15:                 0.320,
  xslg_15:                  0.430,
  p_barrel_pct_allowed_10:  0.085,
  p_hardhit_pct_allowed_10: 0.410,
  p_hr_per_bb_allowed_10:   0.075,
};

// Half-width of the "muted" neutral band around the average
const BAND: Record<StatKey, number> = {
  barrel_pct_15:            0.020,
  hardhit_pct_15:           0.040,
  flyball_pct_15:           0.040,
  avg_ev_15:                2.0,
  xwoba_15:                 0.025,
  xslg_15:                  0.035,
  p_barrel_pct_allowed_10:  0.020,
  p_hardhit_pct_allowed_10: 0.040,
  p_hr_per_bb_allowed_10:   0.020,
};

function statColor(key: StatKey, val: number | null): string {
  if (val == null || isNaN(val)) return 'var(--ev-dim)';
  const diff = val - LEAGUE_AVG[key];
  if (Math.abs(diff) <= BAND[key]) return 'var(--ev-muted)';
  return diff > 0 ? 'var(--ev-green)' : 'var(--ev-red)';
}

function fmtStat(key: StatKey, val: number | null): string {
  if (val == null || isNaN(val as number)) return '—';
  if (key === 'avg_ev_15') return val.toFixed(1);
  if (key === 'xwoba_15' || key === 'xslg_15') {
    const rounded = Math.round(val * 1000);
    return '.' + String(rounded).padStart(3, '0');
  }
  return (val * 100).toFixed(1) + '%';
}

const BATTER_STATS: { key: StatKey; label: string }[] = [
  { key: 'barrel_pct_15',  label: 'BARREL%'  },
  { key: 'hardhit_pct_15', label: 'HARD HIT%' },
  { key: 'flyball_pct_15', label: 'FLY BALL%' },
  { key: 'avg_ev_15',      label: 'AVG EV'    },
  { key: 'xwoba_15',       label: 'xwOBA'     },
  { key: 'xslg_15',        label: 'xSLG'      },
];

const PITCHER_STATS: { key: StatKey; label: string }[] = [
  { key: 'p_barrel_pct_allowed_10',  label: 'BARREL% ALLOWED'  },
  { key: 'p_hardhit_pct_allowed_10', label: 'HARD HIT% ALLOWED' },
  { key: 'p_hr_per_bb_allowed_10',   label: 'HR/BB ALLOWED'    },
];

type ContextKey = 'season_hr' | 'days_since_hr' | 'p_fip' | 'game_total';

const CONTEXT_STATS: { key: ContextKey; label: string }[] = [
  { key: 'season_hr',     label: 'SZN HR'       },
  { key: 'days_since_hr', label: 'DAYS SINCE HR' },
  { key: 'p_fip',         label: 'PITCHER FIP'  },
  { key: 'game_total',    label: 'O/U'          },
];

function fmtContext(key: ContextKey, val: number | null): string {
  if (val == null || isNaN(val)) return '—';
  if (key === 'p_fip' || key === 'game_total') return val.toFixed(2);
  return String(Math.round(val));
}

// ── Detail card ────────────────────────────────────────────────────────────

function DetailCard({ row }: { row: Row }) {
  const SECTION_LABEL: React.CSSProperties = {
    fontFamily:    'var(--font-mono)',
    fontSize:      '9px',
    letterSpacing: '2.5px',
    textTransform: 'uppercase',
    color:         'var(--ev-dim)',
    marginBottom:  '10px',
  };
  const STAT_LABEL: React.CSSProperties = {
    fontFamily:    'var(--font-mono)',
    fontSize:      '9px',
    letterSpacing: '1.5px',
    textTransform: 'uppercase',
    color:         'var(--ev-dim)',
    marginBottom:  '4px',
  };
  const STAT_VAL: React.CSSProperties = {
    fontFamily: 'var(--font-mono)',
    fontSize:   '13px',
    fontWeight: 500,
  };

  return (
    <div style={{
      padding:    '14px 16px 16px 16px',
      background: 'rgba(255,255,255,0.015)',
      borderTop:  '1px solid var(--ev-border)',
    }}>
      <div style={{ display: 'flex', gap: '40px', flexWrap: 'wrap' }}>

        {/* Batter section */}
        <div>
          <div style={SECTION_LABEL}>BATTER L15</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {BATTER_STATS.map(({ key, label }) => {
              const val = row[key as keyof Row] as number | null;
              return (
                <div key={key} style={{ minWidth: '56px' }}>
                  <div style={STAT_LABEL}>{label}</div>
                  <div style={{ ...STAT_VAL, color: statColor(key, val) }}>
                    {fmtStat(key, val)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Pitcher section */}
        <div>
          <div style={SECTION_LABEL}>PITCHER ALLOWED L10</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {PITCHER_STATS.map(({ key, label }) => {
              const val = row[key as keyof Row] as number | null;
              return (
                <div key={key} style={{ minWidth: '56px' }}>
                  <div style={STAT_LABEL}>{label}</div>
                  <div style={{ ...STAT_VAL, color: statColor(key, val) }}>
                    {fmtStat(key, val)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Context section */}
        <div>
          <div style={SECTION_LABEL}>CONTEXT</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {CONTEXT_STATS.map(({ key, label }) => {
              const val = row[key as keyof Row] as number | null;
              return (
                <div key={key} style={{ minWidth: '56px' }}>
                  <div style={STAT_LABEL}>{label}</div>
                  <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                    {fmtContext(key, val)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}

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

// Postgres DATE columns come back from Neon as JS Date objects, not strings.
// String(date) (e.g. "Mon Jun 09 2026 ...") is not a valid Postgres date,
// so always go through toISOString() to get YYYY-MM-DD.
function toISODate(d: unknown): string {
  if (d instanceof Date) return d.toISOString().slice(0, 10);
  return String(d).slice(0, 10);
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
  const [sortKey,         setSortKey]         = useState<SortKey>('adj_prob');
  const [sortDir,         setSortDir]         = useState<SortDir>('desc');
  const [customOdds,      setCustomOdds]      = useState<Record<number, string>>({});
  const [evOnly,          setEvOnly]          = useState(false);
  const [expandedBatter,  setExpandedBatter]  = useState<number | null>(null);
  const [searchQuery,     setSearchQuery]     = useState('');
  const [viewMode,        setViewMode]        = useState<'edge' | 'game'>('edge');

  function handleSort(key: SortKey | null) {
    if (!key) return;
    if (key === sortKey) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  function toggleExpand(batterId: number) {
    setExpandedBatter(prev => prev === batterId ? null : batterId);
  }

  // Game labels built from all rows so filters don't break them
  const gameLabels = useMemo(() => {
    const map = new Map<number, string>();
    for (const row of rows) {
      if (row.is_home === 'A') {
        map.set(row.game_id, `${row.team_abbr} @ ${row.home_team}`);
      } else if (!map.has(row.game_id) && row.home_team) {
        map.set(row.game_id, `??? @ ${row.home_team}`);
      }
    }
    return map;
  }, [rows]);

  const searchFiltered = useMemo(() => {
    if (!searchQuery.trim()) return rows;
    const q = searchQuery.trim().toLowerCase();
    return rows.filter(r =>
      r.player_name.toLowerCase().includes(q) ||
      r.team_abbr.toLowerCase().includes(q)
    );
  }, [rows, searchQuery]);

  const evCount = useMemo(
    () => searchFiltered.filter(r => r.has_line && r.edge != null && r.edge > 0).length,
    [searchFiltered]
  );

  const filtered = useMemo(() => {
    if (!evOnly) return searchFiltered;
    return searchFiltered.filter(r => r.has_line && r.edge != null && r.edge > 0);
  }, [searchFiltered, evOnly]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = getSortVal(a, sortKey);
      const bv = getSortVal(b, sortKey);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [filtered, sortKey, sortDir]);

  const grouped = useMemo(() => {
    const gameMap = new Map<number, Row[]>();
    for (const row of filtered) {
      if (!gameMap.has(row.game_id)) gameMap.set(row.game_id, []);
      gameMap.get(row.game_id)!.push(row);
    }
    for (const gameRows of gameMap.values()) {
      gameRows.sort((a, b) => b.adj_prob - a.adj_prob);
    }
    return Array.from(gameMap.values()).sort((a, b) => b[0].adj_prob - a[0].adj_prob);
  }, [filtered]);

  type TableItem =
    | { type: 'row';    row: Row }
    | { type: 'header'; label: string; count: number; gameId: number };

  const tableItems = useMemo((): TableItem[] => {
    if (viewMode === 'edge') return sorted.map(row => ({ type: 'row' as const, row }));
    return grouped.flatMap(gameRows => [
      {
        type:   'header' as const,
        label:  gameLabels.get(gameRows[0].game_id) ?? `GAME ${gameRows[0].game_id}`,
        count:  gameRows.length,
        gameId: gameRows[0].game_id,
      },
      ...gameRows.map(row => ({ type: 'row' as const, row })),
    ]);
  }, [viewMode, sorted, grouped, gameLabels]);

  return (
    <div>
      {/* Search */}
      <input
        type="text"
        placeholder="SEARCH PLAYER OR TEAM..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        style={{
          display:       'block',
          width:         '100%',
          boxSizing:     'border-box',
          marginBottom:  '10px',
          background:    'rgba(255,255,255,0.04)',
          border:        '1px solid rgba(255,255,255,0.1)',
          borderRadius:  '2px',
          color:         'var(--ev-text)',
          fontFamily:    'var(--font-mono)',
          fontSize:      '11px',
          letterSpacing: '1.5px',
          padding:       '8px 12px',
          outline:       'none',
        }}
      />

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

        {/* View mode toggle */}
        <div style={{
          display:      'flex',
          border:       '1px solid rgba(255,255,255,0.12)',
          borderRadius: '2px',
          overflow:     'hidden',
        }}>
          {(['edge', 'game'] as const).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                fontFamily:    'var(--font-mono)',
                fontSize:      '10px',
                letterSpacing: '2px',
                textTransform: 'uppercase',
                padding:       '5px 11px',
                cursor:        'pointer',
                border:        'none',
                borderRight:   mode === 'edge' ? '1px solid rgba(255,255,255,0.12)' : 'none',
                background:    viewMode === mode ? 'rgba(255,255,255,0.07)' : 'transparent',
                color:         viewMode === mode ? 'var(--ev-text)' : 'var(--ev-dim)',
              }}
            >
              {mode === 'edge' ? 'BY EDGE' : 'BY GAME'}
            </button>
          ))}
        </div>

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
            {tableItems.map(item => {
              if (item.type === 'header') {
                return (
                  <tr key={`hdr-${item.gameId}`}>
                    <td colSpan={COLS.length} style={{
                      padding:       '7px 16px',
                      background:    'rgba(255,255,255,0.03)',
                      borderTop:     '1px solid rgba(255,255,255,0.08)',
                      borderBottom:  '1px solid rgba(255,255,255,0.05)',
                      fontFamily:    'var(--font-mono)',
                      fontSize:      '10px',
                      letterSpacing: '2.5px',
                      textTransform: 'uppercase',
                      color:         'var(--ev-text)',
                    }}>
                      {item.label}
                      <span style={{ color: 'var(--ev-dim)', marginLeft: '14px', letterSpacing: '1px', fontSize: '9px' }}>
                        {item.count} STARTERS
                      </span>
                    </td>
                  </tr>
                );
              }
              const row = item.row;
              const isExpanded = expandedBatter === row.batter;
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
                <Fragment key={`${row.game_id}-${row.batter}`}>
                  <tr
                    className="pred-row"
                    onClick={() => toggleExpand(row.batter)}
                    style={{
                      borderBottom: isExpanded ? 'none' : '1px solid var(--ev-border)',
                      cursor: 'pointer',
                      background: isExpanded ? 'rgba(255,255,255,0.03)' : undefined,
                    }}
                  >

                    {/* PLAYER — sticky */}
                    <td style={{
                      padding:     '9px 12px',
                      color:       'var(--ev-text)',
                      fontWeight:  500,
                      position:    'sticky',
                      left:        0,
                      zIndex:      1,
                      background:  isExpanded ? 'rgba(20,24,28,1)' : STICKY_BG,
                      borderRight: '1px solid var(--ev-border)',
                      whiteSpace:  'nowrap',
                    }}>
                      <span style={{
                        display:     'inline-block',
                        marginRight: '6px',
                        fontSize:    '9px',
                        color:       isExpanded ? 'var(--ev-green)' : 'var(--ev-dim)',
                        transition:  'transform 0.15s',
                        transform:   isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                      }}>▶</span>
                      {row.player_name}
                      {row.hit_hr === true && (
                        <span style={{
                          marginLeft:    '7px',
                          fontSize:      '9px',
                          letterSpacing: '1px',
                          color:         '#0a0d0f',
                          background:    'var(--ev-green)',
                          borderRadius:  '2px',
                          padding:       '1px 4px',
                          fontWeight:    700,
                        }}>
                          HR
                        </span>
                      )}
                      {row.recent_hr === 1 && row.hit_hr !== true && (
                        <span
                          title="Hit a HR in last 5 games"
                          style={{
                            display:      'inline-block',
                            marginLeft:   '6px',
                            width:        '6px',
                            height:       '6px',
                            borderRadius: '50%',
                            background:   'var(--ev-gold)',
                            verticalAlign: 'middle',
                          }}
                        />
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
                    <td
                      style={{ padding: '6px 10px', textAlign: 'right' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                        <input
                          type="text"
                          placeholder="ODDS"
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
                    <td
                      style={{ padding: '6px 14px', textAlign: 'right' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <TrackButton
                        gameDate={toISODate(row.game_date)}
                        batter={row.batter}
                        playerName={row.player_name}
                        teamAbbr={row.team_abbr}
                        adjProb={row.adj_prob}
                        trackedOdds={trackedOdds}
                        trackedEdge={trackedEdge}
                      />
                    </td>

                  </tr>

                  {/* Expanded detail row */}
                  {isExpanded && (
                    <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
                      <td colSpan={COLS.length} style={{ padding: 0 }}>
                        <DetailCard row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
