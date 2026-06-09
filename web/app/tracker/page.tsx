import { getDb } from '@/lib/db';
import Nav from '../components/Nav';

export const dynamic = 'force-dynamic';

// ── Types ──────────────────────────────────────────────────────────────────

type TrackedBet = {
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
};

type TrackerStats = {
  total_bets:     number;
  settled_bets:   number;
  wins:           number;
  settled_staked: number;
  total_profit:   number;
};

// ── Formatters ─────────────────────────────────────────────────────────────

function fmtOdds(o: number | null) {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

function fmtEdge(edge: number | null, hasLine: boolean): { text: string; color: string } {
  if (!hasLine || edge == null) return { text: '—', color: 'var(--ev-dim)' };
  const text = `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`;
  const color = edge > 0 ? 'var(--ev-green)' : edge > -0.03 ? 'var(--ev-muted)' : 'var(--ev-red)';
  return { text, color };
}

function fmtPL(profit: number, settled: number) {
  if (settled === 0) return '—';
  return `${profit >= 0 ? '+' : ''}${profit.toFixed(1)}u`;
}

function fmtROI(profit: number, staked: number) {
  if (staked === 0) return '—';
  const pct = (profit / staked) * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function fmtDate(d: string) {
  return String(d).slice(5).replace('-', '/');
}

function betPL(bet: TrackedBet): string {
  if (bet.hit_hr === null) return '—';
  if (!bet.hit_hr) return `-${bet.stake_units.toFixed(1)}u`;
  if (bet.tracked_odds == null) return '—';
  const odds = bet.tracked_odds;
  const profit = odds > 0
    ? bet.stake_units * (odds / 100)
    : bet.stake_units * (100 / Math.abs(odds));
  return `+${profit.toFixed(2)}u`;
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

const TH: React.CSSProperties = {
  ...LABEL,
  padding:    '8px 14px',
  fontWeight:  500,
  background: 'rgba(255,255,255,0.02)',
};

// ── Page ───────────────────────────────────────────────────────────────────

export default async function TrackerPage() {
  let tracker: TrackerStats | null = null;
  let bets: TrackedBet[] = [];
  let dbError: string | null = null;

  try {
    const sql = getDb();

    const stats = await sql`
      SELECT
        COUNT(*)::int                                                                           AS total_bets,
        COUNT(*) FILTER (WHERE hit_hr IS NOT NULL)::int                                        AS settled_bets,
        COUNT(*) FILTER (WHERE hit_hr = true)::int                                             AS wins,
        COALESCE(SUM(CASE WHEN hit_hr IS NOT NULL THEN stake_units ELSE 0 END), 0)::float      AS settled_staked,
        COALESCE(SUM(CASE
          WHEN hit_hr = true  AND tracked_odds >  0 THEN stake_units * (tracked_odds::float / 100.0)
          WHEN hit_hr = true  AND tracked_odds <= 0 THEN stake_units * (100.0 / ABS(tracked_odds::float))
          WHEN hit_hr = false                       THEN -stake_units
          ELSE 0
        END), 0)::float AS total_profit
      FROM tracked_bets
    `;
    tracker = stats[0] as TrackerStats;

    bets = (await sql`
      SELECT * FROM tracked_bets ORDER BY created_at DESC
    `) as TrackedBet[];
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
  }

  const totalBets   = tracker ? Number(tracker.total_bets)     : 0;
  const settledBets = tracker ? Number(tracker.settled_bets)   : 0;
  const wins        = tracker ? Number(tracker.wins)           : 0;
  const staked      = tracker ? Number(tracker.settled_staked) : 0;
  const profit      = tracker ? Number(tracker.total_profit)   : 0;
  const winRate     = settledBets > 0 ? (wins / settledBets * 100).toFixed(1) + '%' : '—';

  return (
    <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
      <div style={{ maxWidth: '1380px', margin: '0 auto' }}>

        {/* Header */}
        <header style={{ marginBottom: '28px' }}>
          <div style={{ ...LABEL, color: 'var(--ev-green)', letterSpacing: '3px', marginBottom: '8px' }}>
            THE +EV CAVE
          </div>
          <h1 style={{
            fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '26px',
            margin: 0, letterSpacing: '-0.5px', color: 'var(--ev-text)',
          }}>
            TRACKER
          </h1>
          <div style={{ ...LABEL, color: 'var(--ev-muted)', marginTop: '6px', letterSpacing: '1px' }}>
            PERFORMANCE HISTORY
          </div>
        </header>

        {/* Nav */}
        <Nav active="tracker" />

        {/* Content */}
        {dbError ? (
          <div style={{ ...CARD, padding: '40px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>DATABASE ERROR</div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.15)', wordBreak: 'break-all' }}>
              {dbError}
            </div>
          </div>
        ) : totalBets === 0 ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO BETS TRACKED YET</div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
              Hit TRACK on any play from the CARD page to start.
            </div>
          </div>
        ) : (
          <>
            {/* Stats grid */}
            <div style={{
              display:             'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap:                 '1px',
              background:          'var(--ev-border)',
              border:              '1px solid var(--ev-border)',
              borderRadius:        '2px',
              overflow:            'hidden',
              marginBottom:        '16px',
            }}>
              {([
                {
                  label: 'BETS',
                  value: String(totalBets),
                  sub:   totalBets - settledBets > 0
                    ? `${totalBets - settledBets} PENDING`
                    : 'ALL SETTLED',
                  color: 'var(--ev-text)',
                },
                {
                  label: 'WIN RATE',
                  value: winRate,
                  sub:   settledBets > 0 ? `${wins}W / ${settledBets - wins}L` : `${settledBets} SETTLED`,
                  color: 'var(--ev-text)',
                },
                {
                  label: 'P/L',
                  value: fmtPL(profit, settledBets),
                  sub:   `${settledBets} SETTLED`,
                  color: settledBets === 0
                    ? 'var(--ev-dim)'
                    : profit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
                },
                {
                  label: 'ROI',
                  value: fmtROI(profit, staked),
                  sub:   `${staked.toFixed(1)}u STAKED`,
                  color: staked === 0
                    ? 'var(--ev-dim)'
                    : profit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
                },
              ] as { label: string; value: string; sub: string; color: string }[]).map(
                ({ label, value, sub, color }) => (
                  <div key={label} style={{ background: 'var(--ev-bg)', padding: '16px 18px' }}>
                    <div style={LABEL}>{label}</div>
                    <div style={{
                      fontFamily: 'var(--font-syne)', fontWeight: 800,
                      fontSize: '22px', color, margin: '8px 0 4px', letterSpacing: '-0.5px',
                    }}>
                      {value}
                    </div>
                    <div style={{ ...LABEL, fontSize: '9px' }}>{sub}</div>
                  </div>
                )
              )}
            </div>

            {/* Bets table */}
            {bets.length > 0 && (
              <div style={{ ...CARD, overflowX: 'auto' }}>
                <table style={{
                  width: '100%', borderCollapse: 'collapse',
                  fontFamily: 'var(--font-mono)', fontSize: '11px',
                }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
                      {(['DATE', 'PLAYER', 'TEAM', 'ODDS', 'STAKE', 'EDGE', 'P/L', 'RESULT'] as const).map(
                        (h, i) => (
                          <th key={h} style={{ ...TH, textAlign: i >= 3 ? 'right' : 'left' }}>{h}</th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {bets.map(bet => {
                      const { text: edgeText, color: edgeCol } = fmtEdge(bet.edge, bet.tracked_odds != null);
                      const pl        = betPL(bet);
                      const result    = bet.hit_hr === null ? 'PENDING' : bet.hit_hr ? 'WIN' : 'LOSS';
                      const resColor  = bet.hit_hr === null ? 'var(--ev-dim)' : bet.hit_hr ? 'var(--ev-green)' : 'var(--ev-red)';
                      const plColor   = pl === '—' ? 'var(--ev-dim)' : pl.startsWith('+') ? 'var(--ev-green)' : 'var(--ev-red)';
                      return (
                        <tr key={bet.id} className="bet-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>
                          <td style={{ padding: '9px 14px', color: 'var(--ev-dim)' }}>{fmtDate(bet.game_date)}</td>
                          <td style={{ padding: '9px 14px', color: 'var(--ev-text)' }}>{bet.player_name}</td>
                          <td style={{ padding: '9px 14px', color: 'var(--ev-muted)' }}>{bet.team_abbr}</td>
                          <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-blue)' }}>
                            {fmtOdds(bet.tracked_odds)}
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-muted)' }}>
                            {bet.stake_units}u
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'right', color: edgeCol }}>
                            {edgeText}
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'right', color: plColor }}>
                            {pl}
                          </td>
                          <td style={{
                            padding: '9px 14px', textAlign: 'right',
                            color: resColor, fontWeight: bet.hit_hr != null ? 600 : 400,
                          }}>
                            {result}
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

        {/* Footer */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          P/L SETTLES AFTER LOG RUN &nbsp;&middot;&nbsp;
          EDGE = ADJ% - BOOK IMPLIED &nbsp;&middot;&nbsp;
          RESULTS UPDATED DAILY
        </div>

      </div>
    </main>
  );
}
