'use client';

import { useState, useMemo, useEffect, Fragment } from 'react';
import TrackButton from './TrackButton';
import AiPicks from './AiPicks';
import { useIframeIdentity, identityHeaders } from '../lib/iframeIdentity';

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
  opp_team: string | null;
  is_home: string | null;
  adj_prob: number;
  model_prob: number | null;
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
  // Pitcher season profile for detail card
  pitcher_era: number | null;
  pitcher_hr9: number | null;
  pitcher_hr_allowed: number | null;
  pitcher_ip: number | null;
  // Batter-vs-pitcher career matchup for detail card
  vs_pitcher_ab: number | null;
  vs_pitcher_h: number | null;
  vs_pitcher_hr: number | null;
  vs_pitcher_avg: number | null;
  // Season HR by opposing pitcher hand for detail card
  hr_vs_r: number | null;
  hr_vs_l: number | null;
  // Game environment for detail card
  temp_f: number | null;
  humidity_pct: number | null;
  precip_pct: number | null;
  wind_description: string | null;
  // Game info for detail card
  game_time: string | null;
  stadium: string | null;
  // Per-book market odds for detail card
  book_markets: string | null;
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

// ── Pitcher profile (season ERA, HR/9, HR allowed, IP) ──────────────────────

type PitcherProfileKey = 'pitcher_era' | 'pitcher_hr9' | 'pitcher_hr_allowed' | 'pitcher_ip';

const PITCHER_PROFILE_STATS: { key: PitcherProfileKey; label: string }[] = [
  { key: 'pitcher_era',        label: 'ERA'        },
  { key: 'pitcher_hr9',        label: 'HR/9'       },
  { key: 'pitcher_hr_allowed', label: 'HR ALLOWED' },
  { key: 'pitcher_ip',         label: 'IP'         },
];

function fmtPitcherProfile(key: PitcherProfileKey, val: number | null): string {
  if (val == null || isNaN(val)) return '—';
  if (key === 'pitcher_hr_allowed') return String(Math.round(val));
  if (key === 'pitcher_ip') return val.toFixed(1);
  return val.toFixed(2);
}

// ── Batter vs pitcher career matchup ────────────────────────────────────────

type VsPitcherKey = 'vs_pitcher_ab' | 'vs_pitcher_h' | 'vs_pitcher_hr' | 'vs_pitcher_avg';

const VS_PITCHER_STATS: { key: VsPitcherKey; label: string }[] = [
  { key: 'vs_pitcher_ab',  label: 'AB'  },
  { key: 'vs_pitcher_h',   label: 'H'   },
  { key: 'vs_pitcher_hr',  label: 'HR'  },
  { key: 'vs_pitcher_avg', label: 'AVG' },
];

function fmtVsPitcher(key: VsPitcherKey, val: number | null): string {
  if (val == null || isNaN(val)) return '—';
  if (key === 'vs_pitcher_avg') {
    const rounded = Math.round(val * 1000);
    return '.' + String(rounded).padStart(3, '0');
  }
  return String(Math.round(val));
}

// ── Platoon splits (season HR vs RHP / vs LHP) ──────────────────────────────

const PLATOON_STATS: { key: 'hr_vs_r' | 'hr_vs_l'; label: string }[] = [
  { key: 'hr_vs_r', label: 'VS R' },
  { key: 'hr_vs_l', label: 'VS L' },
];

function fmtPlatoon(val: number | null): string {
  if (val == null || isNaN(val)) return '—';
  return `${Math.round(val)} HR`;
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

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Pitcher profile section */}
        <div>
          <div style={SECTION_LABEL}>PITCHER PROFILE</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {PITCHER_PROFILE_STATS.map(({ key, label }) => {
              const val = row[key as keyof Row] as number | null;
              return (
                <div key={key} style={{ minWidth: '56px' }}>
                  <div style={STAT_LABEL}>{label}</div>
                  <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                    {fmtPitcherProfile(key, val)}
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

        {/* Batter vs pitcher section */}
        <div>
          <div style={SECTION_LABEL}>BATTER VS PITCHER</div>
          {row.vs_pitcher_ab != null && row.vs_pitcher_ab > 0 ? (
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {VS_PITCHER_STATS.map(({ key, label }) => {
                const val = row[key as keyof Row] as number | null;
                return (
                  <div key={key} style={{ minWidth: '56px' }}>
                    <div style={STAT_LABEL}>{label}</div>
                    <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                      {fmtVsPitcher(key, val)}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ ...STAT_VAL, color: 'var(--ev-muted)' }}>NO HISTORY</div>
          )}
        </div>

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Platoon splits section */}
        <div>
          <div style={SECTION_LABEL}>PLATOON SPLITS</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {PLATOON_STATS.map(({ key, label }) => {
              const val = row[key as keyof Row] as number | null;
              return (
                <div key={key} style={{ minWidth: '56px' }}>
                  <div style={STAT_LABEL}>{label}</div>
                  <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                    {fmtPlatoon(val)}
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

        {/* Game environment section */}
        <div>
          <div style={SECTION_LABEL}>GAME ENVIRONMENT</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>TEMP</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.temp_f == null || isNaN(row.temp_f) ? '—' : `${Math.round(row.temp_f)}°F`}
              </div>
            </div>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>HUMIDITY</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.humidity_pct == null || isNaN(row.humidity_pct) ? '—' : `${Math.round(row.humidity_pct)}%`}
              </div>
            </div>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>PRECIP</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.precip_pct == null || isNaN(row.precip_pct) ? '—' : `${Math.round(row.precip_pct)}%`}
              </div>
            </div>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>WIND</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.wind_description ?? '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Game info section */}
        <div>
          <div style={SECTION_LABEL}>GAME INFO</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>GAME TIME</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.game_time ?? '—'}
              </div>
            </div>
            <div style={{ minWidth: '56px' }}>
              <div style={STAT_LABEL}>STADIUM</div>
              <div style={{ ...STAT_VAL, color: 'var(--ev-text)' }}>
                {row.stadium ?? '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div style={{
          width: '1px', background: 'var(--ev-border)',
          alignSelf: 'stretch', margin: '0 4px',
        }} />

        {/* Market odds section */}
        <div>
          <div style={SECTION_LABEL}>MARKET ODDS</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {(() => {
              const BOOKS: { key: string; label: string }[] = [
                { key: 'pinnacle',   label: 'PINNACLE'  },
                { key: 'fanduel',    label: 'FANDUEL'   },
                { key: 'novig',      label: 'NOVIG'     },
                { key: 'draftkings', label: 'DRAFTKINGS' },
                { key: 'betrivers',  label: 'BETRIVERS' },
                { key: 'betmgm',     label: 'BETMGM'    },
              ];
              let parsed: Record<string, { odds: number }> = {};
              try {
                if (row.book_markets) parsed = JSON.parse(row.book_markets);
              } catch { /* ignore */ }
              return BOOKS.map(({ key, label }) => {
                const entry = parsed[key];
                const oddsVal = entry?.odds ?? null;
                const display = oddsVal == null ? '—' : oddsVal > 0 ? `+${oddsVal}` : String(oddsVal);
                return (
                  <div key={key} style={{ minWidth: '64px' }}>
                    <div style={STAT_LABEL}>{label}</div>
                    <div style={{ ...STAT_VAL, color: oddsVal == null ? 'var(--ev-dim)' : 'var(--ev-blue)' }}>
                      {display}
                    </div>
                  </div>
                );
              });
            })()}
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
  padding:    '10px var(--cell-px)',
  fontWeight:  500,
  background: 'rgba(255,255,255,0.02)',
  userSelect: 'none',
  whiteSpace: 'nowrap',
};

const STICKY_BG = '#0a0d0f';

// ── Column definitions ─────────────────────────────────────────────────────

type ColDef = { key: SortKey | null; label: string; align: 'left' | 'right'; sticky?: boolean };

// Mobile sort dropdown options — mirrors the most useful desktop sort columns
const MOBILE_SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'adj_prob',       label: 'ADJ%'   },
  { key: 'edge',           label: 'EDGE'   },
  { key: 'season_hr',      label: 'SZN HR' },
  { key: 'hr_park_factor', label: 'PARK'   },
];

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
  const [viewMode,        setViewMode]        = useState<'edge' | 'game' | 'ai'>('edge');
  const [trackedSet,      setTrackedSet]      = useState<Set<string>>(new Set());
  const identity = useIframeIdentity();
  const authHeaders = identityHeaders(identity);

  // Fetch already-tracked (game_date, batter) pairs so TRACK buttons can
  // render as TRACKED for plays the user has already logged.
  useEffect(() => {
    if (identity === undefined) return;
    let cancelled = false;
    fetch('/api/tracked', { headers: identityHeaders(identity) })
      .then(res => res.json())
      .then(data => {
        if (cancelled || !Array.isArray(data.bets)) return;
        const set = new Set<string>(
          data.bets.map((b: { game_date: unknown; batter: unknown }) =>
            `${toISODate(b.game_date)}-${String(b.batter)}`)
        );
        setTrackedSet(set);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [identity]);

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
        map.set(row.game_id, `${row.opp_team ?? '???'} @ ${row.home_team}`);
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
          {(['edge', 'game', 'ai'] as const).map((mode, i, arr) => (
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
                borderRight:   i < arr.length - 1 ? '1px solid rgba(255,255,255,0.12)' : 'none',
                background:    viewMode === mode ? 'rgba(255,255,255,0.07)' : 'transparent',
                color:         viewMode === mode ? 'var(--ev-text)' : 'var(--ev-dim)',
              }}
            >
              {mode === 'edge' ? 'BY EDGE' : mode === 'game' ? 'BY GAME' : 'AI PICKS'}
            </button>
          ))}
        </div>

        <span style={{ ...LABEL, fontSize: '10px' }}>
          {evOnly
            ? `SHOWING ${evCount} +EV PLAY${evCount !== 1 ? 'S' : ''}`
            : `${evCount} +EV / ${rows.length} TOTAL`}
        </span>
      </div>

      {/* AI Picks */}
      {viewMode === 'ai' && <AiPicks rows={rows} trackedSet={trackedSet} authHeaders={authHeaders} />}

      {/* Table */}
      {viewMode !== 'ai' && (
      <>
      <div className="desktop-table-wrap" style={{
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
                      padding:     '9px var(--cell-px)',
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
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                      {row.bat_order ?? '—'}
                    </td>

                    {/* H/A */}
                    <td style={{
                      padding:   '9px var(--cell-px)',
                      textAlign: 'right',
                      fontSize:  '11px',
                      color:     row.is_home === 'H' ? 'var(--ev-green)' : 'var(--ev-muted)',
                    }}>
                      {row.is_home ?? '—'}
                    </td>

                    {/* TEAM */}
                    <td style={{ padding: '9px var(--cell-px)', color: 'var(--ev-muted)' }}>
                      {row.team_abbr}
                      {row.stand && (
                        <span style={{ color: 'var(--ev-dim)', marginLeft: '5px', fontSize: '10px' }}>
                          {row.stand}
                        </span>
                      )}
                    </td>

                    {/* VS */}
                    <td style={{ padding: '9px var(--cell-px)', color: 'var(--ev-dim)', fontSize: '11px' }}>
                      {row.pitcher_name ?? 'TBD'}
                      {row.p_throws && (
                        <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '3px' }}>
                          ({row.p_throws})
                        </span>
                      )}
                    </td>

                    {/* ADJ% */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-text)', fontWeight: 500 }}>
                      {fmtProb(row.adj_prob)}
                    </td>

                    {/* SZN HR */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                      {row.season_hr ?? '—'}
                    </td>

                    {/* FAIR */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)' }}>
                      {fmtOdds(row.fair_odds)}
                    </td>

                    {/* BOOK */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right' }}>
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
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: edgeColor, fontWeight: edgeWeight }}>
                      {edgeText}
                    </td>

                    {/* O/U */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                      {row.game_total != null ? row.game_total : '—'}
                    </td>

                    {/* PARK */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
                      {row.hr_park_factor != null ? Math.round(row.hr_park_factor) : '—'}
                    </td>

                    {/* WIND */}
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>
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
                        isTracked={trackedSet.has(`${toISODate(row.game_date)}-${row.batter}`)}
                        authHeaders={authHeaders}
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

      {/* Mobile sort bar */}
      <div className="mobile-sort-bar" style={{ alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ ...LABEL, fontSize: '9px', flexShrink: 0 }}>SORT</span>
        <select
          value={sortKey}
          onChange={e => { setSortKey(e.target.value as SortKey); setSortDir('desc'); }}
          style={{
            flex:          1,
            background:    'rgba(255,255,255,0.04)',
            border:        '1px solid rgba(255,255,255,0.1)',
            borderRadius:  '2px',
            color:         'var(--ev-text)',
            fontFamily:    'var(--font-mono)',
            fontSize:      '11px',
            letterSpacing: '1.5px',
            padding:       '6px 8px',
            outline:       'none',
          }}
        >
          {MOBILE_SORT_OPTIONS.map(({ key, label }) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <button
          onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
          style={{
            fontFamily:    'var(--font-mono)',
            fontSize:      '11px',
            padding:       '6px 12px',
            borderRadius:  '2px',
            cursor:        'pointer',
            background:    'transparent',
            border:        '1px solid rgba(255,255,255,0.12)',
            color:         'var(--ev-dim)',
          }}
        >
          {sortDir === 'desc' ? '▼ HIGH-LOW' : '▲ LOW-HIGH'}
        </button>
      </div>

      {/* Mobile card-stack */}
      <div className="mobile-card-list">
        {tableItems.map(item => {
          if (item.type === 'header') {
            return (
              <div key={`m-hdr-${item.gameId}`} style={{
                padding:       '8px 2px',
                marginBottom:  '8px',
                fontFamily:    'var(--font-mono)',
                fontSize:      '10px',
                letterSpacing: '2.5px',
                textTransform: 'uppercase',
                color:         'var(--ev-text)',
              }}>
                {item.label}
                <span style={{ color: 'var(--ev-dim)', marginLeft: '12px', letterSpacing: '1px', fontSize: '9px' }}>
                  {item.count} STARTERS
                </span>
              </div>
            );
          }

          const row = item.row;
          const isExpanded = expandedBatter === row.batter;
          const { text: edgeText, color: edgeColor, weight: edgeWeight } =
            edgeDisplay(row.edge, row.has_line);

          const rawInput   = customOdds[row.batter] ?? '';
          const customNum  = parseCustomOdds(rawInput);
          const myEdge     = customNum != null
            ? row.adj_prob - americanToImplied(customNum)
            : null;
          const myEdgeDisp = edgeDisplay(myEdge, customNum != null);
          const trackedOdds = customNum ?? row.best_odds;
          const trackedEdge = customNum != null ? myEdge : row.edge;

          return (
            <Fragment key={`m-${row.game_id}-${row.batter}`}>
              <div
                className="mobile-pred-card"
                onClick={() => toggleExpand(row.batter)}
                style={{
                  background:   'var(--ev-card)',
                  border:       '1px solid var(--ev-border)',
                  borderRadius: '2px',
                  padding:      '12px 14px',
                  marginBottom: '8px',
                  cursor:       'pointer',
                }}
              >
                {/* Name / matchup */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '10px' }}>
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '14px',
                      color: 'var(--ev-text)', letterSpacing: '-0.3px',
                    }}>
                      {row.player_name}
                      {row.hit_hr === true && (
                        <span style={{
                          marginLeft: '7px', fontSize: '9px', letterSpacing: '1px', color: '#0a0d0f',
                          background: 'var(--ev-green)', borderRadius: '2px', padding: '1px 4px', fontWeight: 700,
                        }}>
                          HR
                        </span>
                      )}
                      {row.recent_hr === 1 && row.hit_hr !== true && (
                        <span
                          title="Hit a HR in last 5 games"
                          style={{
                            display: 'inline-block', marginLeft: '6px', width: '6px', height: '6px',
                            borderRadius: '50%', background: 'var(--ev-gold)', verticalAlign: 'middle',
                          }}
                        />
                      )}
                    </div>
                    <div style={{ ...LABEL, fontSize: '9px', marginTop: '3px' }}>
                      {row.team_abbr} {row.is_home === 'H' ? 'vs' : '@'} {row.pitcher_name ?? 'TBD'}
                      {row.p_throws && ` (${row.p_throws})`}
                    </div>
                  </div>
                  <span style={{
                    fontSize: '9px',
                    color: isExpanded ? 'var(--ev-green)' : 'var(--ev-dim)',
                    transition: 'transform 0.15s',
                    transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    flexShrink: 0,
                  }}>▶</span>
                </div>

                {/* Stats + TRACK */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '10px' }}>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>ADJ%</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 500, color: 'var(--ev-text)' }}>
                        {fmtProb(row.adj_prob)}
                      </div>
                    </div>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>FAIR</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 500, color: 'var(--ev-dim)' }}>
                        {fmtOdds(row.fair_odds)}
                      </div>
                    </div>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>BOOK</div>
                      <div style={{
                        fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 500,
                        color: row.has_line ? 'var(--ev-blue)' : 'var(--ev-dim)',
                      }}>
                        {row.has_line ? fmtOdds(row.best_odds) : '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>EDGE</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: edgeWeight, color: edgeColor }}>
                        {edgeText}
                      </div>
                    </div>
                  </div>
                  <div onClick={e => e.stopPropagation()}>
                    <TrackButton
                      gameDate={toISODate(row.game_date)}
                      batter={row.batter}
                      playerName={row.player_name}
                      teamAbbr={row.team_abbr}
                      adjProb={row.adj_prob}
                      trackedOdds={trackedOdds}
                      trackedEdge={trackedEdge}
                      isTracked={trackedSet.has(`${toISODate(row.game_date)}-${row.batter}`)}
                      authHeaders={authHeaders}
                    />
                  </div>
                </div>
              </div>

              {isExpanded && (
                <div style={{ marginBottom: '8px', border: '1px solid var(--ev-border)', borderRadius: '2px' }}>
                  {/* PROJ / ADJ / MY LINE bar */}
                  <div style={{
                    display: 'flex', alignItems: 'flex-start', gap: '16px',
                    padding: '12px 14px 10px 14px',
                    borderBottom: '1px solid var(--ev-border)',
                  }}>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>PROJ%</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 500, color: 'var(--ev-dim)' }}>
                        {row.model_prob != null ? fmtProb(row.model_prob) : '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>ADJ%</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 500, color: 'var(--ev-text)' }}>
                        {fmtProb(row.adj_prob)}
                      </div>
                    </div>
                    <div style={{ marginLeft: 'auto' }} onClick={e => e.stopPropagation()}>
                      <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px', color: 'var(--ev-gold)' }}>MY LINE</div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                        <input
                          type="text"
                          placeholder="ODDS"
                          value={rawInput}
                          onChange={e => setCustomOdds(prev => ({ ...prev, [row.batter]: e.target.value }))}
                          style={{
                            width:        '80px',
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
                    </div>
                  </div>
                  <DetailCard row={row} />
                </div>
              )}
            </Fragment>
          );
        })}
      </div>
      </>
      )}
    </div>
  );
}
