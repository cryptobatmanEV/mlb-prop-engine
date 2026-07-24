'use client';

import { useState, useMemo, useEffect, Fragment } from 'react';
import TrackButton, { trackedKey, type StatType } from './TrackButton';
import { useIframeIdentity, identityHeaders } from '../lib/iframeIdentity';

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
  primary_side: string | null;  // 'over' | 'under' -- whichever the model favors for this player
  primary_best_book: string | null;
  primary_best_odds: number | null;
  primary_edge: number | null;
  secondary_line: number | null;
  secondary_has_line: boolean;
  secondary_side: string | null;
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
  statType: StatType;     // 'hits' | 'total_bases' | 'batter_ks'
};

export type AiPickRow = {
  batter: number;
  player_name: string;
  team_abbr: string | null;
  bat_order: number | null;
  best_odds: number | null;
  best_book: string | null;
  edge: number | null;
  adj_prob: number | null;
  book_line: number | null;
  book_side: string | null;
  composite_score: number | null;
  result: string | null;  // 'HIT' | 'MISS' | null (pending)
};

type SortKey = 'player_name' | 'p_stat_1plus' | 'p_stat_2plus' | 'primary_edge';
type SortDir = 'asc' | 'desc';

function fmtOdds(o: number | null): string { if (o == null) return '—'; return o > 0 ? `+${o}` : `${o}`; }
function sideLabel(side: string | null | undefined): string { return (side ?? 'over') === 'under' ? 'U' : 'O'; }
// p_stat_1plus/p_stat_2plus are always keyed to the 0.5-line / 1.5-line
// probability respectively (see predict/batter_props_fair_odds.py's
// prob_for_line = {0.5: c1, 1.5: c2}) -- NOT to "primary"/"secondary", since
// which line is primary varies by model (Total Bases' primary is 1.5, the
// reverse of Hits/Batter Ks). Track/display code must look this up per-line
// rather than assuming primary always means p_stat_1plus.
function probForLine(row: PropRow, line: number | null): number | null {
  if (line == null) return null;
  return line >= 1 ? row.p_stat_2plus : row.p_stat_1plus;
}
function adjProbForSide(prob: number | null, side: string | null | undefined): number {
  if (prob == null) return 0;
  return sideLabel(side) === 'U' ? 1 - prob : prob;
}

// ── Client-side favored-side odds (over/under) ──────────────────────────────
// predict/shared_fair_odds.py intentionally always writes 'over' as
// primary_side/secondary_side (a deliberate simplification -- see that
// file's docstring). book_markets already carries BOTH over_price and
// under_price per book/line, so the REAL market favorite can be computed
// entirely here from data already sent to the browser, without touching the
// Python pipeline or regenerating any data.
type BookMarkets = Record<string, Record<string, { over?: number; under?: number }>>;

function parseBookMarkets(raw: string | null): BookMarkets {
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return {}; }
}

function impliedFromAmerican(o: number): number {
  return o > 0 ? 100 / (o + 100) : Math.abs(o) / (Math.abs(o) + 100);
}

function bestOddsForSide(books: BookMarkets, line: number | null, side: 'over' | 'under', negativeOnly = false): { book: string | null; odds: number | null } {
  if (line == null) return { book: null, odds: null };
  let bestBook: string | null = null;
  let bestOdds: number | null = null;
  for (const [bk, lines] of Object.entries(books)) {
    const o = lines[String(line)]?.[side];
    if (o == null) continue;
    if (negativeOnly && o >= 0) continue;
    if (bestOdds == null || o > bestOdds) { bestOdds = o; bestBook = bk; }
  }
  return { book: bestBook, odds: bestOdds };
}

type LineDisplay = { side: 'over' | 'under'; book: string | null; odds: number | null; hasLine: boolean; edge: number | null };

function computeLineDisplay(books: BookMarkets, line: number | null, prob: number | null): LineDisplay {
  // The market favorite is determined using only NEGATIVE (favorite-priced)
  // odds per side -- a book pricing a side at +money doesn't consider that
  // side its favorite, so comparing one book's underdog price against a
  // *different* book's favorite price (comparing best-available-per-side
  // across all books, regardless of sign) could surface a book's own
  // +money price as if it were "the favorite". E.g. for Lars Nootbaar's
  // 1.5 TB, betmgm's under +105 doesn't mean under is favored -- betmgm
  // itself prices over as its favorite (-145); draftkings' -130 on over is
  // the correct comparison against draftkings' own -105 on under.
  const overNeg  = bestOddsForSide(books, line, 'over', true);
  const underNeg = bestOddsForSide(books, line, 'under', true);

  let side: 'over' | 'under';
  let book: string | null;
  let odds: number | null;

  if (overNeg.odds != null && underNeg.odds != null) {
    side = impliedFromAmerican(underNeg.odds) > impliedFromAmerican(overNeg.odds) ? 'under' : 'over';
    ({ book, odds } = side === 'under' ? underNeg : overNeg);
  } else if (overNeg.odds != null) {
    side = 'over'; book = overNeg.book; odds = overNeg.odds;
  } else if (underNeg.odds != null) {
    side = 'under'; book = underNeg.book; odds = underNeg.odds;
  } else {
    // Rare: no book prices either side as a clear favorite (all +money, or
    // no odds at all) -- fall back to comparing best-available price per
    // side regardless of sign, same as before this fix.
    const overBest  = bestOddsForSide(books, line, 'over');
    const underBest = bestOddsForSide(books, line, 'under');
    const overImplied  = overBest.odds  != null ? impliedFromAmerican(overBest.odds)  : null;
    const underImplied = underBest.odds != null ? impliedFromAmerican(underBest.odds) : null;
    side = 'over'; book = overBest.book; odds = overBest.odds;
    if (underImplied != null && (overImplied == null || underImplied > overImplied)) {
      side = 'under'; book = underBest.book; odds = underBest.odds;
    }
  }

  const hasLine = odds != null;
  let edge: number | null = null;
  if (hasLine && prob != null) {
    const sideProb = side === 'under' ? 1 - prob : prob;
    edge = Math.round((sideProb - impliedFromAmerican(odds as number)) * 10000) / 10000;
  }
  return { side, book, odds, hasLine, edge };
}

// ── Market/model disagreement badge (Total Bases only) ──────────────────────
// Total Bases' P(2+ TB) model is well-calibrated but rarely crosses 50% even
// for elite hitters (audited against 83K historical rows: max ever seen is
// ~64%, and >50% happens for well under 1% of predictions) -- so the book
// pricing OVER 1.5 as the true favorite (negative odds) while our own model
// still calls it <50% is a real, fairly common disagreement worth flagging,
// not something to silently resolve one way or the other. Purely
// informational: does not change primary/secondary side selection or edge.
function hasMarketModelDisagreement(row: PropRow & { _primary: LineDisplay }, statType: StatType): boolean {
  if (statType !== 'total_bases' || row.primary_line !== 1.5) return false;
  if (row._primary.side !== 'over' || row._primary.odds == null || row._primary.odds >= 0) return false;
  const modelProb = probForLine(row, row.primary_line);
  return modelProb != null && modelProb < 0.5;
}

// ── Market odds table (matches HR's DetailCard style: one row per book,
// logo + name left, odds right, green for positive odds, muted white for
// negative) -- shows EVERY available price (both sides, both lines) per
// book, not just whichever side/line we've decided is "favored" elsewhere
// in the UI. Users need the full picture to make their own call.
function MarketOddsTable({ books, primaryLine, secondaryLine }: {
  books: BookMarkets; primaryLine: number | null; secondaryLine: number | null;
}) {
  const lines = [primaryLine, secondaryLine]
    .filter((l): l is number => l != null)
    .sort((a, b) => a - b);

  const chipStyle = (odds: number): React.CSSProperties => ({
    fontFamily: 'var(--font-mono)', fontSize: '11px', padding: '3px 7px', borderRadius: '3px',
    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
    color: odds > 0 ? 'var(--ev-green)' : 'rgba(255,255,255,0.85)', whiteSpace: 'nowrap',
  });

  const bookRows = Object.entries(books)
    .map(([bk, bkLines]) => {
      const chips: { key: string; label: string; odds: number }[] = [];
      for (const line of lines) {
        const sides = bkLines[String(line)];
        if (!sides) continue;
        if (sides.over != null)  chips.push({ key: `${line}-over`,  label: `O ${line}`, odds: sides.over });
        if (sides.under != null) chips.push({ key: `${line}-under`, label: `U ${line}`, odds: sides.under });
      }
      return { bk, chips };
    })
    .filter(r => r.chips.length > 0);

  if (bookRows.length === 0) {
    return <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(255,255,255,0.25)' }}>NO MARKET LINES YET</div>;
  }

  return (
    <div>
      {bookRows.map(({ bk, chips }) => (
        <div key={bk} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', padding: '7px 0', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'rgba(255,255,255,0.8)' }}>
            <BookLogo book={bk} size={16} />
            {bk}
          </div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {chips.map(c => (
              <span key={c.key} style={chipStyle(c.odds)}>{c.label}: {fmtOdds(c.odds)}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function DisagreementBadge() {
  return (
    <span
      title="Book favors OVER but model probability is under 50%. Worth investigating before betting."
      style={{
        marginLeft: '5px', fontSize: '12px', cursor: 'help', color: 'var(--ev-gold)',
        display: 'inline-block', verticalAlign: 'middle',
      }}
    >
      ⚡
    </span>
  );
}

// ── MY LINE (custom odds) ───────────────────────────────────────────────────
function parseCustomOdds(raw: string): number | null {
  const stripped = raw.trim().replace(/^\+/, '');
  if (!stripped) return null;
  const n = parseInt(stripped, 10);
  if (isNaN(n)) return null;
  if (n >= 100 || n <= -100) return n;
  return null;
}

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

function toISODate(d: unknown): string {
  if (d instanceof Date) return d.toISOString().slice(0, 10);
  return String(d).slice(0, 10);
}

// ── AI Picks view ──────────────────────────────────────────────────────────
// Reads pre-computed picks from {model}_ai_picks_log (scripts/log_ai_picks_*.py)
// rather than re-deriving each model's composite-score formula in TS -- those
// formulas differ meaningfully per model (see the Python scripts), so a
// single source of truth avoids drift.

function BatterAiPicks({ picks, config, gameDate, trackedSet, authHeaders }: {
  picks: AiPickRow[]; config: PropConfig; gameDate: string;
  trackedSet: Set<string>; authHeaders?: HeadersInit;
}) {
  if (picks.length === 0) {
    return (
      <div style={{ background: 'var(--ev-card)', border: '1px solid var(--ev-border)', borderRadius: '2px', padding: '48px', textAlign: 'center' }}>
        <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO AI PICKS TODAY</div>
        <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
          Nothing cleared {config.label}&rsquo;s qualification threshold yet. Check back after lineups/odds refresh.
        </div>
      </div>
    );
  }

  const wins    = picks.filter(p => p.result === 'HIT').length;
  const losses  = picks.filter(p => p.result === 'MISS').length;
  const settled = wins + losses;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ ...LABEL, letterSpacing: '2px' }}>
          TOP {picks.length} {config.label.toUpperCase()} PLAY{picks.length !== 1 ? 'S' : ''}
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
      <div className="ai-picks-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px' }}>
        {picks.map((p, idx) => {
          const edgePct = p.edge != null ? p.edge * 100 : null;
          return (
            <div key={p.batter} style={{ background: 'var(--ev-card)', border: '1px solid var(--ev-border)', borderRadius: '2px', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '15px', color: 'var(--ev-text)', letterSpacing: '-0.3px' }}>
                    {p.player_name}
                  </div>
                  <div style={{ ...LABEL, marginTop: '4px', fontSize: '9px' }}>
                    {p.team_abbr ?? '—'}{p.bat_order != null && <> &middot; BO {p.bat_order}</>}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '5px' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px', color: 'var(--ev-green)', border: '1px solid rgba(0,220,110,0.3)', borderRadius: '2px', padding: '3px 6px', whiteSpace: 'nowrap' }}>
                    #{idx + 1} PICK
                  </div>
                  {p.result === 'HIT' && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700, color: '#0a0d0f', background: 'var(--ev-green)', borderRadius: '2px', padding: '2px 8px', letterSpacing: '1px' }}>W</div>
                  )}
                  {p.result === 'MISS' && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700, color: '#fff', background: 'var(--ev-red)', borderRadius: '2px', padding: '2px 8px', letterSpacing: '1px' }}>L</div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '20px' }}>
                <div>
                  <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>LINE</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600 }}>
                    {p.book_line != null ? `${sideLabel(p.book_side)} ${p.book_line}` : '—'}
                  </div>
                </div>
                <div>
                  <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>ODDS</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--ev-blue)' }}>
                    {fmtOdds(p.best_odds)}{p.best_book && <span style={{ color: 'var(--ev-dim)', fontWeight: 400 }}> {p.best_book}</span>}
                  </div>
                </div>
                <div>
                  <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>ADJ%</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600 }}>{fmtProb(p.adj_prob)}</div>
                </div>
                <div>
                  <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>EDGE</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: edgePct != null && edgePct > 0 ? 'var(--ev-green)' : 'var(--ev-muted)' }}>
                    {edgePct != null ? `${edgePct >= 0 ? '+' : ''}${edgePct.toFixed(1)}%` : '—'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <TrackButton
                  gameDate={gameDate}
                  batter={p.batter}
                  playerName={p.player_name}
                  teamAbbr={p.team_abbr ?? ''}
                  adjProb={p.adj_prob ?? 0}
                  trackedOdds={p.best_odds}
                  trackedEdge={p.edge}
                  statType={config.statType}
                  line={p.book_line ?? 0.5}
                  side={(p.book_side as 'over' | 'under' | undefined) ?? 'over'}
                  isTracked={trackedSet.has(trackedKey(gameDate, p.batter, config.statType, p.book_line ?? 0.5))}
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

type EnrichedRow = PropRow & { _books: BookMarkets; _primary: LineDisplay; _secondary: LineDisplay };

// Which line/side/edge to show in the "low" (0.5) vs "high" (1.5) position,
// regardless of which one the model designates "primary" -- Total Bases'
// primary line is 1.5, the reverse of Hits/Batter Ks, which meant the main
// row's stacked BOOK column showed 1.5 above 0.5 for Total Bases only.
// Always display numeric-ascending (0.5 first) instead.
type OrderedLine = { line: number | null; side: 'over' | 'under'; hasLine: boolean; book: string | null; odds: number | null; edge: ReturnType<typeof edgeDisplay> };

function orderedLines(row: EnrichedRow, primarySide: 'over' | 'under', secondarySide: 'over' | 'under'): [OrderedLine, OrderedLine] {
  const primaryInfo: OrderedLine = {
    line: row.primary_line, side: primarySide, hasLine: row._primary.hasLine,
    book: row._primary.book, odds: row._primary.odds, edge: edgeDisplay(row._primary.edge, row._primary.hasLine),
  };
  const secondaryInfo: OrderedLine = {
    line: row.secondary_line, side: secondarySide, hasLine: row._secondary.hasLine,
    book: row._secondary.book, odds: row._secondary.odds, edge: edgeDisplay(row._secondary.edge, row._secondary.hasLine),
  };
  const primaryIsLower = (row.primary_line ?? 0.5) <= (row.secondary_line ?? 1.5);
  return primaryIsLower ? [primaryInfo, secondaryInfo] : [secondaryInfo, primaryInfo];
}

export default function BatterPropsTable({ rows, config, aiPicks }: { rows: PropRow[]; config: PropConfig; aiPicks: AiPickRow[] }) {
  const [sortKey, setSortKey]   = useState<SortKey>('p_stat_1plus');
  const [sortDir, setSortDir]   = useState<SortDir>('desc');
  const [evOnly, setEvOnly]     = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'edge' | 'ai'>('edge');
  const [trackedSet, setTrackedSet]   = useState<Set<string>>(new Set());
  const [customOdds, setCustomOdds]   = useState<Record<number, string>>({});
  const identity    = useIframeIdentity();
  const authHeaders = identityHeaders(identity);

  const enriched: EnrichedRow[] = useMemo(() => rows.map(row => {
    const books = parseBookMarkets(row.book_markets);
    const primary = computeLineDisplay(books, row.primary_line, probForLine(row, row.primary_line));
    const secondary = computeLineDisplay(books, row.secondary_line, probForLine(row, row.secondary_line));
    return { ...row, _books: books, _primary: primary, _secondary: secondary };
  }), [rows]);

  useEffect(() => {
    if (identity === undefined) return;
    let cancelled = false;
    fetch('/api/tracked', { headers: identityHeaders(identity) })
      .then(res => res.json())
      .then(data => {
        if (cancelled || !Array.isArray(data.bets)) return;
        const set = new Set<string>(
          data.bets.map((b: { game_date: unknown; batter: unknown; stat_type?: string; line?: number }) =>
            trackedKey(toISODate(b.game_date), Number(b.batter), (b.stat_type as StatType) ?? 'home_runs', b.line ?? 0.5))
        );
        setTrackedSet(set);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [identity]);

  const searchFiltered = useMemo(() => {
    if (!searchQuery.trim()) return enriched;
    const q = searchQuery.trim().toLowerCase();
    return enriched.filter(r => r.player_name.toLowerCase().includes(q) || r.team_abbr.toLowerCase().includes(q));
  }, [enriched, searchQuery]);

  const evCount = useMemo(
    () => searchFiltered.filter(r => r._primary.hasLine && r._primary.edge != null && r._primary.edge > 0).length,
    [searchFiltered]
  );

  const filtered = useMemo(() => {
    if (!evOnly) return searchFiltered;
    return searchFiltered.filter(r => r._primary.hasLine && r._primary.edge != null && r._primary.edge > 0);
  }, [searchFiltered, evOnly]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = sortKey === 'primary_edge' ? a._primary.edge : (a[sortKey] as string | number | null);
      const bv = sortKey === 'primary_edge' ? b._primary.edge : (b[sortKey] as string | number | null);
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

  // Total Bases' primary line is 1.5 (the reverse of Hits/Batter Ks) --
  // keep the sortable "primary_edge" key attached to whichever line it
  // actually represents, but always position/label the columns in numeric
  // (0.5, then 1.5) order so the header matches the row content below it.
  const primaryIsLower = (rows[0]?.primary_line ?? 0.5) <= (rows[0]?.secondary_line ?? 1.5);

  const COLS: { key: SortKey | null; label: string; align: 'left' | 'right'; sticky?: boolean }[] = [
    { key: 'player_name', label: 'PLAYER', align: 'left', sticky: true },
    { key: null, label: 'BO', align: 'right' },
    { key: null, label: 'H/A', align: 'right' },
    { key: null, label: 'TEAM', align: 'left' },
    { key: null, label: 'VS', align: 'left' },
    { key: 'p_stat_1plus', label: config.prob1Label, align: 'right' },
    { key: 'p_stat_2plus', label: config.prob2Label, align: 'right' },
    { key: null, label: 'BOOK', align: 'right' },
    { key: primaryIsLower ? 'primary_edge' : null, label: 'EDGE (0.5)', align: 'right' },
    { key: primaryIsLower ? null : 'primary_edge', label: 'EDGE (1.5)', align: 'right' },
    { key: null, label: 'MY LINE', align: 'right' },
    { key: null, label: 'TRACK', align: 'right' },
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

        <div style={{ display: 'flex', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '2px', overflow: 'hidden' }}>
          {(['edge', 'ai'] as const).map((mode, i, arr) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '10px', letterSpacing: '2px',
                textTransform: 'uppercase', padding: '5px 11px', cursor: 'pointer',
                border: 'none', borderRight: i < arr.length - 1 ? '1px solid rgba(255,255,255,0.12)' : 'none',
                background: viewMode === mode ? 'rgba(255,255,255,0.07)' : 'transparent',
                color: viewMode === mode ? 'var(--ev-text)' : 'var(--ev-dim)',
              }}
            >
              {mode === 'edge' ? 'BY EDGE' : 'AI PICKS'}
            </button>
          ))}
        </div>

        <span style={{ ...LABEL, fontSize: '10px' }}>
          {evOnly ? `SHOWING ${evCount} +EV PLAY${evCount !== 1 ? 'S' : ''}` : `${evCount} +EV / ${rows.length} TOTAL`}
        </span>
      </div>

      {viewMode === 'ai' && (
        <BatterAiPicks
          picks={aiPicks}
          config={config}
          gameDate={rows[0] ? toISODate(rows[0].game_date) : ''}
          trackedSet={trackedSet}
          authHeaders={authHeaders}
        />
      )}

      {viewMode !== 'ai' && (
      <>
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
              const books = row._books;
              const primarySide = row._primary.side;
              const secondarySide = row._secondary.side;
              const [lowLine, highLine] = orderedLines(row, primarySide, secondarySide);
              const rawInput  = customOdds[row.batter] ?? '';
              const customNum = parseCustomOdds(rawInput);
              const myEdge     = customNum != null ? adjProbForSide(probForLine(row, row.primary_line), primarySide) - impliedFromAmerican(customNum) : null;
              const myEdgeDisp = edgeDisplay(myEdge, customNum != null);
              const trackedOdds = customNum ?? row._primary.odds;
              const trackedEdge = customNum != null ? myEdge : row._primary.edge;

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
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: 'var(--ev-muted)' }}>
                      {fmtProb(row.p_stat_2plus)}
                      {hasMarketModelDisagreement(row, config.statType) && <DisagreementBadge />}
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '5px' }}>
                        {[lowLine, highLine].map((l, i) => (
                          <div key={i} style={{
                            display: 'inline-flex', alignItems: 'center', gap: '5px',
                            paddingTop: i === 1 ? '5px' : 0,
                            borderTop: i === 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                            width: '100%', justifyContent: 'flex-end',
                          }}>
                            {l.hasLine ? (
                              <>
                                <BookLogo book={l.book} size={13} />
                                <span style={{ color: 'var(--ev-dim)', fontSize: '9px' }}>{sideLabel(l.side)} {l.line}</span>
                                <span style={{ color: 'var(--ev-blue)', fontWeight: 600, fontSize: '12px' }}>{fmtOdds(l.odds)}</span>
                              </>
                            ) : (
                              <span style={{ color: 'var(--ev-dim)', fontSize: '10px' }}>{l.line} —</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: lowLine.edge.color, fontWeight: lowLine.edge.weight }}>{lowLine.edge.text}</td>
                    <td style={{ padding: '9px var(--cell-px)', textAlign: 'right', color: highLine.edge.color, fontWeight: highLine.edge.weight }}>{highLine.edge.text}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                        <input
                          type="text"
                          placeholder="ODDS"
                          value={rawInput}
                          onChange={e => setCustomOdds(prev => ({ ...prev, [row.batter]: e.target.value }))}
                          style={{
                            width: '72px', background: 'rgba(255,255,255,0.04)',
                            border: `1px solid ${customNum != null ? 'rgba(255,200,0,0.4)' : 'rgba(255,255,255,0.08)'}`,
                            borderRadius: '2px',
                            color: customNum != null ? 'var(--ev-gold)' : 'rgba(255,255,255,0.25)',
                            fontFamily: 'var(--font-mono)', fontSize: '11px',
                            padding: '4px 7px', textAlign: 'right', outline: 'none',
                          }}
                        />
                        {customNum != null && (
                          <span style={{ fontSize: '10px', letterSpacing: '1px', color: myEdgeDisp.color, fontWeight: myEdgeDisp.weight }}>
                            {myEdgeDisp.text}
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                      <TrackButton
                        gameDate={toISODate(row.game_date)}
                        batter={row.batter}
                        playerName={row.player_name}
                        teamAbbr={row.team_abbr}
                        adjProb={adjProbForSide(probForLine(row, row.primary_line), primarySide)}
                        trackedOdds={trackedOdds}
                        trackedEdge={trackedEdge}
                        statType={config.statType}
                        line={row.primary_line ?? 0.5}
                        side={primarySide}
                        isTracked={trackedSet.has(trackedKey(toISODate(row.game_date), row.batter, config.statType, row.primary_line ?? 0.5))}
                        authHeaders={authHeaders}
                      />
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                      <td colSpan={COLS.length} style={{ padding: 0 }}>
                        <div style={{ padding: '16px', background: 'rgba(255,255,255,0.012)', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          <div style={{ background: '#111416', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '10px 12px' }}>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)', marginBottom: '8px' }}>MARKET ODDS (ALL BOOKS)</div>
                            <MarketOddsTable
                              books={books}
                              primaryLine={row.primary_line}
                              secondaryLine={row.secondary_line}
                            />
                          </div>

                          {row._secondary.hasLine && (() => {
                            const secEdge = edgeDisplay(row._secondary.edge, true);
                            return (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                              <span style={{ ...LABEL, fontSize: '9px' }}>{`SECOND LINE (${row.secondary_line})`}</span>
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                <BookLogo book={row._secondary.book} size={14} />
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ev-dim)' }}>{sideLabel(secondarySide)}</span>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: 'var(--ev-blue)' }}>{fmtOdds(row._secondary.odds)}</span>
                              </div>
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: secEdge.color, fontWeight: secEdge.weight }}>
                                {secEdge.text}
                              </span>
                              <span onClick={e => e.stopPropagation()} style={{ marginLeft: 'auto' }}>
                                <TrackButton
                                  gameDate={toISODate(row.game_date)}
                                  batter={row.batter}
                                  playerName={row.player_name}
                                  teamAbbr={row.team_abbr}
                                  adjProb={adjProbForSide(probForLine(row, row.secondary_line), secondarySide)}
                                  trackedOdds={row._secondary.odds}
                                  trackedEdge={row._secondary.edge}
                                  statType={config.statType}
                                  line={row.secondary_line ?? 1.5}
                                  side={secondarySide}
                                  isTracked={trackedSet.has(trackedKey(toISODate(row.game_date), row.batter, config.statType, row.secondary_line ?? 1.5))}
                                  authHeaders={authHeaders}
                                />
                              </span>
                            </div>
                            );
                          })()}

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

      {/* ── Mobile sort bar ── */}
      <div className="mobile-sort-bar" style={{ alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <select
          value={sortKey}
          onChange={e => { setSortKey(e.target.value as SortKey); setSortDir('desc'); }}
          style={{
            flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '2px', color: 'var(--ev-text)', fontFamily: 'var(--font-mono)',
            fontSize: '11px', letterSpacing: '1.5px', padding: '7px 10px', outline: 'none',
          }}
        >
          <option value="p_stat_1plus">SORT: {config.prob1Label}</option>
          <option value="p_stat_2plus">SORT: {config.prob2Label}</option>
          <option value="primary_edge">SORT: EDGE</option>
        </select>
        <button
          onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
          style={{
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '2px', color: 'var(--ev-dim)', fontFamily: 'var(--font-mono)',
            fontSize: '12px', padding: '7px 12px', cursor: 'pointer',
          }}
        >
          {sortDir === 'desc' ? '▼' : '▲'}
        </button>
      </div>

      {/* ── Mobile card stack ── */}
      <div className="mobile-card-list">
        {sorted.map(row => {
          const isExpanded = expanded === row.batter;
          const { text: edgeText, color: edgeColor, weight: edgeWeight } = edgeDisplay(row._primary.edge, row._primary.hasLine);
          const { text: edge2Text, color: edge2Color, weight: edge2Weight } = edgeDisplay(row._secondary.edge, row._secondary.hasLine);
          const books = row._books;
          const primarySide = row._primary.side;
          const secondarySide = row._secondary.side;
          const rawInput  = customOdds[row.batter] ?? '';
          const customNum = parseCustomOdds(rawInput);
          const myEdge     = customNum != null ? adjProbForSide(probForLine(row, row.primary_line), primarySide) - impliedFromAmerican(customNum) : null;
          const myEdgeDisp = edgeDisplay(myEdge, customNum != null);
          const trackedOdds = customNum ?? row._primary.odds;
          const trackedEdge = customNum != null ? myEdge : row._primary.edge;

          return (
            <Fragment key={`m-${row.game_pk}-${row.batter}`}>
              <div
                className="mobile-pred-card"
                onClick={() => setExpanded(p => p === row.batter ? null : row.batter)}
                style={{
                  background: '#111416', border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '4px', padding: '14px', marginBottom: '6px', cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <div style={{ fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '15px', color: 'rgba(255,255,255,0.95)' }}>
                      {row.player_name}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'rgba(255,255,255,0.4)', marginTop: '2px' }}>
                      {row.team_abbr} {row.is_home === '1' || row.is_home === 'True' ? 'vs' : '@'} {row.pitcher_name ?? 'TBD'}
                      {row.p_throws ? ` (${row.p_throws})` : ''}
                      {row.bat_order != null && <> &middot; BO {row.bat_order}</>}
                    </div>
                  </div>
                  {row.game_time && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'rgba(255,255,255,0.3)', whiteSpace: 'nowrap' }}>
                      {row.game_time}
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '14px', flexWrap: 'wrap', marginBottom: '8px' }}>
                  <div>
                    <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>{config.prob1Label}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '17px', color: adjProbColor(row.p_stat_1plus ?? 0), lineHeight: 1 }}>
                      {fmtProb(row.p_stat_1plus)}
                    </div>
                  </div>
                  <div>
                    <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>{config.prob2Label}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--ev-muted)' }}>
                      {fmtProb(row.p_stat_2plus)}
                      {hasMarketModelDisagreement(row, config.statType) && <DisagreementBadge />}
                    </div>
                  </div>
                  <div>
                    <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>{`BOOK (${row.primary_line ?? '0.5'})`}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {row._primary.hasLine ? (
                        <>
                          <BookLogo book={row._primary.book} size={16} />
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ev-dim)' }}>{sideLabel(primarySide)}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--ev-blue)' }}>{fmtOdds(row._primary.odds)}</span>
                        </>
                      ) : <span style={{ color: 'var(--ev-dim)', fontSize: '12px' }}>—</span>}
                    </div>
                  </div>
                  <div>
                    <div style={{ ...LABEL, fontSize: '9px', marginBottom: '3px' }}>EDGE</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', color: edgeColor, fontWeight: edgeWeight }}>
                      {edgeText}
                    </div>
                  </div>
                  <div onClick={e => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%', justifyContent: 'flex-end' }}>
                    <input
                      type="text"
                      placeholder="+350"
                      value={rawInput}
                      onChange={e => setCustomOdds(prev => ({ ...prev, [row.batter]: e.target.value }))}
                      style={{
                        width: '72px', background: 'rgba(255,255,255,0.06)',
                        border: `1px solid ${customNum != null ? 'rgba(255,200,0,0.5)' : 'rgba(255,255,255,0.1)'}`,
                        borderRadius: '4px',
                        color: customNum != null ? 'var(--ev-gold)' : 'rgba(255,255,255,0.3)',
                        fontFamily: 'var(--font-mono)', fontSize: '11px',
                        padding: '4px 7px', textAlign: 'right', outline: 'none',
                      }}
                    />
                    {customNum != null && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: myEdgeDisp.color, fontWeight: myEdgeDisp.weight }}>
                        {myEdgeDisp.text}
                      </span>
                    )}
                    <TrackButton
                      gameDate={toISODate(row.game_date)}
                      batter={row.batter}
                      playerName={row.player_name}
                      teamAbbr={row.team_abbr}
                      adjProb={adjProbForSide(probForLine(row, row.primary_line), primarySide)}
                      trackedOdds={trackedOdds}
                      trackedEdge={trackedEdge}
                      statType={config.statType}
                      line={row.primary_line ?? 0.5}
                      side={primarySide}
                      isTracked={trackedSet.has(trackedKey(toISODate(row.game_date), row.batter, config.statType, row.primary_line ?? 0.5))}
                      authHeaders={authHeaders}
                    />
                  </div>
                </div>

              </div>

              {isExpanded && (
                <div style={{ margin: '-2px 0 12px', padding: '12px', background: 'rgba(255,255,255,0.012)', border: '1px solid rgba(255,255,255,0.06)', borderTop: 'none', borderRadius: '0 0 4px 4px' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '2px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)', marginBottom: '8px' }}>
                    MARKET ODDS (ALL BOOKS)
                  </div>
                  <MarketOddsTable
                    books={books}
                    primaryLine={row.primary_line}
                    secondaryLine={row.secondary_line}
                  />

                  {row._secondary.hasLine && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                      <div style={{ ...LABEL, fontSize: '9px' }}>{`SECOND LINE (${row.secondary_line})`}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <BookLogo book={row._secondary.book} size={14} />
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ev-dim)' }}>{sideLabel(secondarySide)}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: 'var(--ev-blue)' }}>{fmtOdds(row._secondary.odds)}</span>
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: edge2Color, fontWeight: edge2Weight }}>{edge2Text}</span>
                      <div onClick={e => e.stopPropagation()} style={{ marginLeft: 'auto' }}>
                        <TrackButton
                          gameDate={toISODate(row.game_date)}
                          batter={row.batter}
                          playerName={row.player_name}
                          teamAbbr={row.team_abbr}
                          adjProb={adjProbForSide(probForLine(row, row.secondary_line), secondarySide)}
                          trackedOdds={row._secondary.odds}
                          trackedEdge={row._secondary.edge}
                          statType={config.statType}
                          line={row.secondary_line ?? 1.5}
                          side={secondarySide}
                          isTracked={trackedSet.has(trackedKey(toISODate(row.game_date), row.batter, config.statType, row.secondary_line ?? 1.5))}
                          authHeaders={authHeaders}
                        />
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginTop: '10px' }}>
                    {row.stadium && <span>{row.stadium}</span>}
                    {row.opp_team && <span>VS {row.opp_team}</span>}
                  </div>
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
