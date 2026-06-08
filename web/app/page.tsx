import { getDb } from '@/lib/db';
import TrackButton from './components/TrackButton';

export const dynamic = 'force-dynamic';

// ── Types ──────────────────────────────────────────────────────────────────

type Row = {
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

type TrackedBet = {
  id: number;
  game_date: string;
  batter: number;
  player_name: string;
  team_abbr: string;
  adj_prob: number | null;
  best_odds: number | null;
  edge: number | null;
  stake_units: number;
  hit_hr: boolean | null;
  created_at: string;
};

type TrackerStats = {
  total_bets:     number;
  settled_bets:   number;
  wins:           number;
  settled_staked: number;
  total_profit:   number;
};

// ── Formatters ─────────────────────────────────────────────────────────────

function fmtProb(p: number)  { return (p * 100).toFixed(1) + '%'; }

function fmtOdds(o: number | null) {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

function edgeDisplay(edge: number | null, hasLine: boolean) {
  if (!hasLine || edge == null) return { text: '—', color: 'var(--ev-dim)', weight: 400 };
  const sign = edge > 0 ? '+' : '';
  const text = `${sign}${(edge * 100).toFixed(1)}%`;
  if (edge > 0.05)       return { text, color: 'var(--ev-green)', weight: 600 };
  if (edge > 0)          return { text, color: 'var(--ev-green)', weight: 400 };
  if (edge > -0.03)      return { text, color: 'var(--ev-muted)',  weight: 400 };
                         return { text, color: 'var(--ev-red)',   weight: 400 };
}

function fmtWind(windFavor: number | null, isDome: boolean) {
  if (isDome)            return 'DOME';
  if (windFavor == null) return '—';
  const abs = Math.abs(windFavor).toFixed(0);
  if (windFavor >  2)    return `^${abs}`;
  if (windFavor < -2)    return `v${abs}`;
                         return `~${abs}`;
}

function fmtPL(profit: number, settled: number) {
  if (settled === 0) return '—';
  const sign = profit >= 0 ? '+' : '';
  return `${sign}${profit.toFixed(1)}u`;
}

function fmtROI(profit: number, staked: number) {
  if (staked === 0) return '—';
  const pct  = (profit / staked) * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

function fmtDate(d: string) {
  // "2026-06-08" → "06/08"
  return String(d).slice(5).replace('-', '/');
}

// ── Shared style tokens ────────────────────────────────────────────────────

const LABEL = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '10px',
  letterSpacing: '2px',
  textTransform: 'uppercase' as const,
  color:         'var(--ev-dim)',
};

const CARD = {
  background:   'var(--ev-card)',
  border:       '1px solid var(--ev-border)',
  borderRadius: '2px',
} as const;

const TH = {
  ...LABEL,
  padding:    '10px 14px',
  fontWeight:  500,
  background: 'rgba(255,255,255,0.02)',
} as const;

// ── Page ───────────────────────────────────────────────────────────────────

export default async function Home() {
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'America/New_York',
  }).toUpperCase();

  let rows:      Row[]         = [];
  let dbError:   string | null = null;
  let tracker:   TrackerStats | null = null;
  let bets:      TrackedBet[]  = [];

  // Primary: predictions
  try {
    const sql = getDb();
    rows = (await sql`
      SELECT * FROM hr_predictions
      WHERE game_date = CURRENT_DATE
      ORDER BY adj_prob DESC
    `) as Row[];
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
  }

  // Secondary: tracker stats (silent fail if table doesn't exist yet)
  if (!dbError) {
    try {
      const sql = getDb();
      const stats = await sql`
        SELECT
          COUNT(*)::int                                                                   AS total_bets,
          COUNT(*) FILTER (WHERE hit_hr IS NOT NULL)::int                                AS settled_bets,
          COUNT(*) FILTER (WHERE hit_hr = true)::int                                     AS wins,
          COALESCE(SUM(CASE WHEN hit_hr IS NOT NULL THEN stake_units ELSE 0 END),0)::float AS settled_staked,
          COALESCE(SUM(CASE
            WHEN hit_hr = true  AND best_odds >  0 THEN stake_units * (best_odds::float / 100.0)
            WHEN hit_hr = true  AND best_odds <= 0 THEN stake_units * (100.0 / ABS(best_odds::float))
            WHEN hit_hr = false                    THEN -stake_units
            ELSE 0
          END), 0)::float AS total_profit
        FROM tracked_bets
      `;
      tracker = stats[0] as TrackerStats;
      bets    = (await sql`SELECT * FROM tracked_bets ORDER BY created_at DESC LIMIT 20`) as TrackedBet[];
    } catch {
      // tracked_bets doesn't exist yet — empty state
    }
  }

  const withLine = rows.filter(r => r.has_line).length;
  const posEdge  = rows.filter(r => r.edge != null && r.edge > 0).length;

  const totalBets     = tracker ? Number(tracker.total_bets)     : 0;
  const settledBets   = tracker ? Number(tracker.settled_bets)   : 0;
  const wins          = tracker ? Number(tracker.wins)           : 0;
  const settledStaked = tracker ? Number(tracker.settled_staked) : 0;
  const totalProfit   = tracker ? Number(tracker.total_profit)   : 0;
  const winRate       = settledBets > 0 ? (wins / settledBets * 100).toFixed(1) + '%' : '—';

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
      <div style={{ maxWidth: '1280px', margin: '0 auto' }}>

        {/* ── Header ─────────────────────────────────────────── */}
        <header style={{ marginBottom: '28px' }}>
          <div style={{ ...LABEL, color: 'var(--ev-green)', letterSpacing: '3px', marginBottom: '8px' }}>
            THE +EV CAVE
          </div>
          <h1 style={{
            fontFamily: 'var(--font-syne)', fontWeight: 800,
            fontSize: '26px', margin: 0, letterSpacing: '-0.5px', color: 'var(--ev-text)',
          }}>
            MLB HR PROPS
          </h1>
          <div style={{ ...LABEL, color: 'var(--ev-muted)', marginTop: '6px', letterSpacing: '1px' }}>
            {today}
          </div>
          {rows.length > 0 && (
            <div style={{ ...LABEL, color: 'var(--ev-dim)', marginTop: '4px', letterSpacing: '1px' }}>
              {rows.length} STARTERS &middot; {withLine} W/ LINES &middot; {posEdge} +EV
            </div>
          )}
        </header>

        {/* ── Predictions table ──────────────────────────────── */}
        {dbError ? (
          <div style={{ ...CARD, padding: '40px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>NO DATA LOADED</div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
              Check DATABASE_URL in Vercel env vars, then run pipeline.
            </div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.15)', marginTop: '8px', wordBreak: 'break-all' }}>
              {dbError}
            </div>
          </div>
        ) : rows.length === 0 ? (
          <div style={{ ...CARD, padding: '40px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>NO PREDICTIONS YET</div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
              <code>python scripts/daily_pipeline.py</code>
            </div>
          </div>
        ) : (
          <div style={{ ...CARD, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
                  <th style={{ ...TH, textAlign: 'left'  }}>PLAYER</th>
                  <th style={{ ...TH, textAlign: 'left'  }}>TEAM</th>
                  <th style={{ ...TH, textAlign: 'left'  }}>VS</th>
                  <th style={{ ...TH, textAlign: 'right' }}>ADJ%</th>
                  <th style={{ ...TH, textAlign: 'right' }}>FAIR</th>
                  <th style={{ ...TH, textAlign: 'right' }}>BOOK</th>
                  <th style={{ ...TH, textAlign: 'right' }}>EDGE</th>
                  <th style={{ ...TH, textAlign: 'right' }}>PARK</th>
                  <th style={{ ...TH, textAlign: 'right' }}>WIND</th>
                  <th style={{ ...TH, textAlign: 'right' }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const { text: edgeText, color: edgeColor, weight: edgeWeight } = edgeDisplay(row.edge, row.has_line);
                  return (
                    <tr key={row.id ?? i} className="pred-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>
                      <td style={{ padding: '9px 14px', color: 'var(--ev-text)', fontWeight: 500 }}>
                        {row.player_name}
                      </td>
                      <td style={{ padding: '9px 14px', color: 'var(--ev-muted)' }}>
                        {row.team_abbr}
                        {row.stand && <span style={{ color: 'var(--ev-dim)', marginLeft: '5px', fontSize: '10px' }}>{row.stand}</span>}
                      </td>
                      <td style={{ padding: '9px 14px', color: 'var(--ev-dim)', fontSize: '11px' }}>
                        {row.pitcher_name ?? 'TBD'}
                        {row.p_throws && <span style={{ color: 'rgba(255,255,255,0.2)', marginLeft: '3px' }}>({row.p_throws})</span>}
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
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Legend ─────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: '20px', marginTop: '8px', flexWrap: 'wrap' }}>
          <span style={{ ...LABEL, color: 'var(--ev-green)' }}>+EV GREEN</span>
          <span style={LABEL}>&gt;5% BOLD</span>
          <span style={{ ...LABEL, color: 'var(--ev-red)' }}>&lt;-3% RED</span>
          <span style={LABEL}>^ TAIL  v INTO  ~ NEUTRAL</span>
        </div>

        {/* ── Tracker dashboard ──────────────────────────────── */}
        <section style={{ marginTop: '48px' }}>
          <div style={{ ...LABEL, letterSpacing: '3px', color: 'var(--ev-dim)', marginBottom: '16px' }}>
            TRACKER
          </div>

          {totalBets === 0 ? (
            <div style={{ ...CARD, padding: '36px', textAlign: 'center' }}>
              <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO BETS TRACKED YET</div>
              <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
                Hit TRACK on any play to start paper-trading.
              </div>
            </div>
          ) : (
            <>
              {/* Stats grid */}
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '1px', background: 'var(--ev-border)',
                border: '1px solid var(--ev-border)', borderRadius: '2px',
                overflow: 'hidden', marginBottom: '12px',
              }}>
                {([
                  {
                    label: 'BETS',
                    value: String(totalBets),
                    sub:   totalBets - settledBets > 0 ? `${totalBets - settledBets} PENDING` : 'ALL SETTLED',
                    color: 'var(--ev-text)',
                  },
                  {
                    label: 'WIN RATE',
                    value: winRate,
                    sub:   `${wins}W / ${settledBets - wins}L`,
                    color: 'var(--ev-text)',
                  },
                  {
                    label: 'P/L',
                    value: fmtPL(totalProfit, settledBets),
                    sub:   `${settledBets} SETTLED`,
                    color: settledBets === 0 ? 'var(--ev-dim)' : totalProfit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
                  },
                  {
                    label: 'ROI',
                    value: fmtROI(totalProfit, settledStaked),
                    sub:   `${settledStaked.toFixed(1)}u STAKED`,
                    color: settledStaked === 0 ? 'var(--ev-dim)' : totalProfit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
                  },
                ] as { label: string; value: string; sub: string; color: string }[]).map(({ label, value, sub, color }) => (
                  <div key={label} style={{ background: 'var(--ev-bg)', padding: '16px 18px' }}>
                    <div style={LABEL}>{label}</div>
                    <div style={{
                      fontFamily: 'var(--font-syne)', fontWeight: 800,
                      fontSize: '22px', color, margin: '8px 0 4px',
                      letterSpacing: '-0.5px',
                    }}>
                      {value}
                    </div>
                    <div style={{ ...LABEL, fontSize: '9px' }}>{sub}</div>
                  </div>
                ))}
              </div>

              {/* Recent bets */}
              {bets.length > 0 && (
                <div style={{ ...CARD, overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
                        {(['DATE', 'PLAYER', 'TEAM', 'ODDS', 'EDGE', 'STAKE', 'RESULT'] as const).map((h, i) => (
                          <th key={h} style={{ ...TH, padding: '8px 14px', textAlign: i >= 3 ? 'right' : 'left' }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {bets.map(bet => {
                        const ed = edgeDisplay(bet.edge, bet.best_odds != null);
                        const resultColor =
                          bet.hit_hr == null ? 'var(--ev-dim)' :
                          bet.hit_hr         ? 'var(--ev-green)' : 'var(--ev-red)';
                        const resultText =
                          bet.hit_hr == null ? 'PENDING' :
                          bet.hit_hr         ? 'HIT'     : 'MISS';
                        return (
                          <tr key={bet.id} className="bet-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>
                            <td style={{ padding: '8px 14px', color: 'var(--ev-dim)' }}>{fmtDate(bet.game_date)}</td>
                            <td style={{ padding: '8px 14px', color: 'var(--ev-text)' }}>{bet.player_name}</td>
                            <td style={{ padding: '8px 14px', color: 'var(--ev-muted)' }}>{bet.team_abbr}</td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--ev-blue)' }}>
                              {fmtOdds(bet.best_odds)}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', color: ed.color }}>
                              {ed.text}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--ev-muted)' }}>
                              {bet.stake_units}u
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', color: resultColor, fontWeight: bet.hit_hr != null ? 600 : 400 }}>
                              {resultText}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </section>

        {/* ── Footer ─────────────────────────────────────────── */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          ADJ% = MODEL PROB x P(CONTACT) &nbsp;&middot;&nbsp; EDGE = ADJ% - BOOK IMPLIED &nbsp;&middot;&nbsp; P/L SETTLES AFTER LOG RUN
        </div>
      </div>
    </main>
  );
}
