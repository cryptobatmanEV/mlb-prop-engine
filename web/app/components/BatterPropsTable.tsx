'use client';

import { useState, useMemo, Fragment } from 'react';

// ── Book logos (same set as PropsTable) ─────────────────────────────────────

const LOGO_URLS: Record<string, string[]> = {
  pinnacle:   ['https://cdn.brandfetch.io/pinnacle.com/w/400/h/400',   'https://www.google.com/s2/favicons?domain=pinnacle.com&sz=32'],
  fanduel:    ['https://cdn.brandfetch.io/fanduel.com/w/400/h/400',    'https://www.google.com/s2/favicons?domain=fanduel.com&sz=32'],
  draftkings: ['https://cdn.brandfetch.io/draftkings.com/w/400/h/400', 'https://www.google.com/s2/favicons?domain=draftkings.com&sz=32'],
  betrivers:  ['https://cdn.brandfetch.io/betrivers.com/w/400/h/400',  'https://www.google.com/s2/favicons?domain=betrivers.com&sz=32'],
  novig:      ['https://cdn.brandfetch.io/novig.us/w/400/h/400',       'https://www.google.com/s2/favicons?domain=novig.us&sz=32'],
  betmgm:     ['https://cdn.brandfetch.io/betmgm.com/w/400/h/400',    'https://www.google.com/s2/favicons?domain=betmgm.com&sz=32'],
  bet365:     ['https://cdn.brandfetch.io/bet365.com/w/400/h/400',     'https://www.google.com/s2/favicons?domain=bet365.com&sz=32'],
};
const BOOK_BADGE_COLORS: Record<string, string> = {
  pinnacle: '#ffcc00', fanduel: '#1493ff', draftkings: '#53d338',
  betrivers: '#e31c1c', novig: '#7c3aed', betmgm: '#bf9b30', bet365: '#027b5b',
};

function BookLogo({ book, size = 16 }: { book: string | null | undefined; size?: number }) {
  const [urlIdx, setUrlIdx] = useState(0);
  const key = (book ?? '').toLowerCase().trim();
  const urls = LOGO_URLS[key];
  const badge = BOOK_BADGE_COLORS[key] ?? 'rgba(255,255,255,0.15)';
  const letter = key.charAt(0).toUpperCase() || '?';
  const badgeStyle: React.CSSProperties = {
    width: size, height: size, borderRadius: '50%', flexShrink: 0,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    verticalAlign: 'middle', fontSize: Math.round(size * 0.48), fontWeight: 700,
    color: '#fff', fontFamily: 'var(--font-mono)', lineHeight: 1,
  };
  if (!urls || urlIdx >= urls.length) {
    return <span style={{ ...badgeStyle, background: urls ? badge : 'rgba(255,255,255,0.15)' }}>{letter}</span>;
  }
  return (
    <img src={urls[urlIdx]} alt={key} width={size} height={size}
      style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover', flexShrink: 0, display: 'inline-block', verticalAlign: 'middle' }}
      onError={() => setUrlIdx(i => i + 1)} />
  );
}

// ── Types ────────────────────────────────────────────────────────────────────

export type PropRow = {
  id: number;
  game_date: string;
  game_pk: number;
  batter: number;
  player_name: string;
  team_abbr: string;
  opp_team: string | null;
  bat_order: number | null;
  is_home: string | null;
  game_time: string | null;
  stadium: string | null;
  pitcher_name: string | null;
  p_throws: string | null;
  pred_stat: number | null;
  p_stat_1plus: number | null;
  p_stat_2plus: number | null;
  adj_prob: number;
  primary_line: number | null;
  primary_has_line: boolean;
  primary_best_book: string | null;
  primary_best_odds: number | null;
  primary_edge: number | null;
  secondary_line: number | null;
  secondary_has_line: boolean;
  secondary_best_book: string | null;
  secondary_best_odds: number | null;
  secondary_edge: number | null;
  book_markets: string | null;
};

export type PropConfig = {
  label: string;          // "Hits"
  prob1Label: string;     // "P(1+ H)"
  prob2Label: string;     // "P(2+ H)"
  projLabel: string;      // "PROJ HITS"
};

function fmtProj(v: number | null): string { return v == null ? '—' : v.toFixed(2); }

type SortKey = 'player_name' | 'p_stat_1plus' | 'p_stat_2plus' | 'primary_edge';
type SortDir = 'asc' | 'desc';

function fmtOdds(o: number | null): string { if (o == null) return '—'; return o > 0 ? `+${o}` : `${o}`; }
function fmtProb(p: number | null): string { if (p == null || isNaN(p)) return '—'; return (p * 100).toFixed(1) + '%'; }
function adjProbColor(p: number): string {
  if (p >= 0.55) return 'var(--ev-green)';
  if (p >= 0.40) return 'var(--ev-gold)';
  return 'var(--ev-text)';
}
function edgeDisplay(edge: number | null, hasLine: boolean) {
  if (!hasLine || edge == null) return { text: '—', color: 'var(--ev-dim)', weight: 400 };
  const sign = edge > 0 ? '+' : '';
  const text = `${sign}${(edge * 100).toFixed(1)}%`;
  if (edge > 0.05) return { text, color: 'var(--ev-green)', weight: 600 };
  if (edge > 0)    return { text, color: 'var(--ev-green)', weight: 400 };
  if (edge > -0.03) return { text, color: 'var(--ev-muted)', weight: 400 };
  return { text, color: 'var(--ev-red)', weight: 400 };
}

const LABEL: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '2px',
  textTransform: 'uppercase', color: 'var(--ev-dim)',
};
const TH_BASE: React.CSSProperties = {
  ...LABEL, padding: '9px var(--cell-px)', fontWeight: 500,
  background: 'rgba(255,255,255,0.02)', userSelect: 'none', whiteSpace: 'nowrap',
};
const STICKY_BG = '#0a0d0f';

export default function BatterPropsTable({ rows, config }: { rows: PropRow[]; config: PropConfig }) {
  const [sortKey, setSortKey]   = useState<SortKey>('p_stat_1plus');
  const [sortDir, setSortDir]   = useState<SortDir>('desc');
  const [evOnly, setEvOnly]     = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const searchFiltered = useMemo(() => {
    if (!searchQuery.trim()) return rows;
    const q = searchQuery.trim().toLowerCase();
    return rows.filter(r => r.player_name.toLowerCase().includes(q) || r.team_abbr.toLowerCase().includes(q));
  }, [rows, searchQuery]);

  const evCount = useMemo(
    () => searchFiltered.filter(r => r.primary_has_line && r.primary_edge != null && r.primary_edge > 0).length,
    [searchFiltered]
  );

  const filtered = useMemo(() => {
    if (!evOnly) return searchFiltered;
    return searchFiltered.filter(r => r.primary_has_line && r.primary_edge != null && r.primary_edge > 0);
  }, [searchFiltered, evOnly]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = a[sortKey] as string | number | null;
      const bv = b[sortKey] as string | number | null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [filtered, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortKey(key); setSortDir('desc'); }
  }

  const COLS: { key: SortKey | null; label: string; align: 'left' | 'right'; sticky?: boolean }[] = [
    { key: 'player_name', label: 'PLAYER', align: 'left', sticky: true },
    { key: null, label: 'BO', align: 'right' },
    { key: null, label: 'H/A', align: 'right' },
    { key: null, label: 'TEAM', align: 'left' },
    { key: null, label: 'VS', align: 'left' },
    { key: 'p_stat_1plus', label: config.prob1Label, align: 'right' },
    { key: 'p_stat_2plus', label: config.prob2Label, align: 'right' },
    { key: null, label: config.projLabel, align: 'right' },
    { key: null, label: `BOOK (${rows[0]?.primary_line ?? '0.5'})`, align: 'right' },
    { key: null, label: `BOOK (${rows[0]?.secondary_line ?? '1.5'})`, align: 'right' },
    { key: 'primary_edge', label: 'EDGE', align: 'right' },
  ];

  return (
    <div>
      <input
        type="text"
        placeholder="SEARCH PLAYER OR TEAM..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        style={{
          display: 'block', width: '100%', boxSizing: 'border-box', marginBottom: '10px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '2px', color: 'var(--ev-text)', fontFamily: 'var(--font-mono)',
          fontSize: '11px', letterSpacing: '1.5px', padding: '8px 12px', outline: 'none',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
        <button
          onClick={() => setEvOnly(v => !v)}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '2px',
            textTransform: 'uppercase', padding: '5px 12px', borderRadius: '2px', cursor: 'pointer',
            background: evOnly ? 'rgba(0,220,110,0.12)' : 'transparent',
            border: evOnly ? '1px solid var(--ev-green)' : '1px solid rgba(255,255,255,0.12)',
            color: evOnly ? 'var(--ev-green)' : 'var(--ev-dim)',
          }}
        >
          +EV ONLY
        </button>
        <span style={{ ...LABEL, fontSize: '10px' }}>
          {evOnly ? `SHOWING ${evCount} +EV PLAY${evCount !== 1 ? 'S' : ''}` : `${evCount} +EV / ${rows.length} TOTAL`}
        </span>
      </div>

      <div className="desktop-table-wrap" style={{
        background: 'var(--ev-card)', border: '1px solid var(--ev-border)', borderRadius: '2px', overflowX: 'auto',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
              {COLS.map((col, ci) => {
                const isActive = col.key !== null && sortKey === col.key;
                return (
                  <th key={ci} onClick={() => col.key && handleSort(col.key)}
                    style={{
                      ...TH_BASE, textAlign: col.align, cursor: col.key ? 'pointer' : 'default',
                      color: isActive ? 'var(--ev-text)' : 'var(--ev-dim)',
                      ...(col.sticky ? { position: 'sticky', left: 0, zIndex: 2, background: STICKY_BG, borderRight: '1px solid var(--ev-border)' } : {}),
                    }}>
                    {col.label}
                    {isActive && <span style={{ marginLeft: '4px', fontSize: '9px', color: 'var(--ev-green)' }}>{sortDir === 'desc' ? '▼' : '▲'}</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map(row => {
              const isExpanded = expanded === row.batter;
              const { text: edgeText, color: edgeColor, weight: edgeWeight } = edgeDisplay(row.primary_edge, row.primary_has_line);
              let books: Record<string, Record<string, number>> = {};
              try { if (row.book_markets) books = JSON.parse(row.book_markets); } catch { /* ignore */ }

              return (
                <Fragment key={`${row.game_pk}-${row.batter}`}>
                  <tr className="pred-row" onClick={() => setExpanded(p => p === row.batter ? null : row.batter)}
                    style={{ height: '52px', borderBottom: isExpanded ? 'none' : '1px solid rgba(255,255,255,0.06)', cursor: 'pointer', background: isExpanded ? 'rgba(255,255,255,0.03)' : undefined }}>
                    <td style={{
                      padding: '9px var(--cell-px)', color: 'rgba(255,255,255,0.95)', fontFamily: 'var(--font-syne)',
                      fontWeight: 800, fontSize: '13px', position: 'sticky', left: 0, zIndex: 1,
                      background: isExpanded ? 'rgba(20,24,28,1)' : STICKY_BG, borderRight: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap',
                    }}>
                      <span style={{ display: 'inline-block', marginRight: '6px', fontSize: '9px', color: isExpanded ? 'var(--ev-green)' : 'var(--ev-dim)', transition: 'transform 0.15s', transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
                      {row.player_name}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)', fontSize: '11px' }}>{row.bat_order ?? '—'}</td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', fontSize: '11px', color: row.is_home === '1' || row.is_home === 'True' ? 'var(--ev-green)' : 'var(--ev-muted)' }}>
                      {row.is_home === '1' || row.is_home === 'True' ? 'H' : 'A'}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', color: 'var(--ev-muted)' }}>{row.team_abbr}</td>
                    <td style={{ padding: '9px var(--cell-px)', color: 'var(--ev-dim)', fontSize: '11px', whiteSpace: 'nowrap' }}>
                      {row.pitcher_name ?? 'TBD'}{row.p_throws && <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '3px' }}>({row.p_throws})</span>}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', fontWeight: 700, fontSize: '13px', color: adjProbColor(row.p_stat_1plus ?? 0) }}>{fmtProb(row.p_stat_1plus)}</td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-muted)' }}>{fmtProb(row.p_stat_2plus)}</td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-dim)' }}>{fmtProj(row.pred_stat)}</td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right' }}>
                      {row.primary_has_line ? (
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end' }}>
                          <BookLogo book={row.primary_best_book} size={16} />
                          <span style={{ color: 'var(--ev-blue)', fontWeight: 600, fontSize: '12px' }}>{fmtOdds(row.primary_best_odds)}</span>
                        </div>
                      ) : <span style={{ color: 'var(--ev-dim)', fontSize: '11px' }}>—</span>}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right' }}>
                      {row.secondary_has_line ? (
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end' }}>
                          <BookLogo book={row.secondary_best_book} size={16} />
                          <span style={{ color: 'var(--ev-blue)', fontWeight: 600, fontSize: '12px' }}>{fmtOdds(row.secondary_best_odds)}</span>
                        </div>
                      ) : <span style={{ color: 'var(--ev-dim)', fontSize: '11px' }}>—</span>}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: edgeColor, fontWeight: edgeWeight }}>{edgeText}</td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                      <td colSpan={COLS.length} style={{ padding: 0 }}>
                        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.012)', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          <div style={{ background: '#111416', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '10px 12px' }}>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)', marginBottom: '8px' }}>MARKET ODDS (ALL BOOKS)</div>
                            {Object.keys(books).length === 0 ? (
                              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(255,255,255,0.25)' }}>NO MARKET LINES YET</div>
                            ) : (
                              <table style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', width: '100%', borderCollapse: 'collapse' }}>
                                <thead><tr>
                                  <th style={{ textAlign: 'left', color: 'rgba(255,255,255,0.35)', fontSize: '9px', fontWeight: 400, padding: '0 0 6px' }}>BOOK</th>
                                  <th style={{ textAlign: 'right', color: 'rgba(255,255,255,0.35)', fontSize: '9px', fontWeight: 400, padding: '0 0 6px' }}>{row.primary_line}</th>
                                  <th style={{ textAlign: 'right', color: 'rgba(255,255,255,0.35)', fontSize: '9px', fontWeight: 400, padding: '0 0 6px' }}>{row.secondary_line}</th>
                                </tr></thead>
                                <tbody>
                                  {Object.entries(books).map(([bk, lines]) => (
                                    <tr key={bk} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                                      <td style={{ padding: '6px 0', color: 'rgba(255,255,255,0.8)' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><BookLogo book={bk} size={14} />{bk}</div>
                                      </td>
                                      <td style={{ textAlign: 'right', color: 'rgba(255,255,255,0.8)' }}>{lines[String(row.primary_line)] != null ? fmtOdds(lines[String(row.primary_line)]) : '—'}</td>
                                      <td style={{ textAlign: 'right', color: 'rgba(255,255,255,0.8)' }}>{lines[String(row.secondary_line)] != null ? fmtOdds(lines[String(row.secondary_line)]) : '—'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </div>
                          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(255,255,255,0.3)', letterSpacing: '1px' }}>
                            {row.game_time && <span>{row.game_time}</span>}
                            {row.stadium && <span>{row.stadium}</span>}
                            {row.opp_team && <span>VS {row.opp_team}</span>}
                          </div>
                        </div>
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
