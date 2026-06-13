import { getDb } from '@/lib/db';
import Nav from '../components/Nav';

export const dynamic = 'force-dynamic';

// ── Types ──────────────────────────────────────────────────────────────────

type LeaderboardRow = {
  discord_user_id:  string;
  discord_username: string;
  total_bets:       number;
  settled_bets:     number;
  wins:             number;
  losses:           number;
  settled_staked:   number;
  total_profit:     number;
  roi:              number;
};

// ── Formatters ─────────────────────────────────────────────────────────────

function fmtPL(profit: number) {
  return `${profit >= 0 ? '+' : ''}${profit.toFixed(1)}u`;
}

function fmtROI(roi: number) {
  const pct = roi * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
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

export default async function LeaderboardPage() {
  let rows: LeaderboardRow[] = [];
  let dbError: string | null = null;

  try {
    const sql = getDb();

    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_user_id TEXT`;
    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_username TEXT`;

    rows = (await sql`
      WITH agg AS (
        SELECT
          discord_user_id,
          MAX(discord_username)                                                              AS discord_username,
          COUNT(*)::int                                                                       AS total_bets,
          COUNT(*) FILTER (WHERE hit_hr IS NOT NULL)::int                                     AS settled_bets,
          COUNT(*) FILTER (WHERE hit_hr = true)::int                                          AS wins,
          COUNT(*) FILTER (WHERE hit_hr = false)::int                                         AS losses,
          COALESCE(SUM(CASE WHEN hit_hr IS NOT NULL THEN stake_units ELSE 0 END), 0)::float   AS settled_staked,
          COALESCE(SUM(CASE
            WHEN hit_hr = true  AND tracked_odds >  0 THEN stake_units * (tracked_odds::float / 100.0)
            WHEN hit_hr = true  AND tracked_odds <= 0 THEN stake_units * (100.0 / ABS(tracked_odds::float))
            WHEN hit_hr = false                       THEN -stake_units
            ELSE 0
          END), 0)::float AS total_profit
        FROM tracked_bets
        WHERE discord_user_id IS NOT NULL
        GROUP BY discord_user_id
      )
      SELECT *,
        CASE WHEN settled_staked > 0 THEN total_profit / settled_staked ELSE 0 END AS roi
      FROM agg
      WHERE settled_bets >= 5
      ORDER BY roi DESC
    `) as LeaderboardRow[];
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
  }

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
            LEADERBOARD
          </h1>
          <div style={{ ...LABEL, color: 'var(--ev-muted)', marginTop: '6px', letterSpacing: '1px' }}>
            RANKED BY ROI &middot; MIN 5 SETTLED BETS
          </div>
        </header>

        {/* Nav */}
        <Nav active="leaderboard" />

        {/* Content */}
        {dbError ? (
          <div style={{ ...CARD, padding: '40px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>DATABASE ERROR</div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.15)', wordBreak: 'break-all' }}>
              {dbError}
            </div>
          </div>
        ) : rows.length === 0 ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '6px' }}>NO QUALIFYING USERS YET</div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
              Users need at least 5 settled tracked bets to appear on the leaderboard.
            </div>
          </div>
        ) : (
          <div style={{ ...CARD, overflowX: 'auto' }}>
            <table style={{
              width: '100%', borderCollapse: 'collapse',
              fontFamily: 'var(--font-mono)', fontSize: '11px',
            }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
                  {(['#', 'USER', 'BETS', 'W', 'L', 'WIN RATE', 'P/L', 'ROI'] as const).map((h, i) => (
                    <th key={h} style={{ ...TH, textAlign: i >= 2 ? 'right' : 'left' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => {
                  const decided = row.wins + row.losses;
                  const winRate = decided > 0 ? `${(row.wins / decided * 100).toFixed(1)}%` : '—';
                  const plColor = row.total_profit > 0 ? 'var(--ev-green)' : row.total_profit < 0 ? 'var(--ev-red)' : 'var(--ev-muted)';
                  const roiColor = row.roi > 0 ? 'var(--ev-green)' : row.roi < 0 ? 'var(--ev-red)' : 'var(--ev-muted)';
                  return (
                    <tr key={row.discord_user_id} style={{ borderBottom: '1px solid var(--ev-border)' }}>
                      <td style={{ padding: '9px 14px', color: 'var(--ev-dim)' }}>{idx + 1}</td>
                      <td style={{ padding: '9px 14px', color: 'var(--ev-text)', fontWeight: 600 }}>
                        {row.discord_username ?? 'Unknown'}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-muted)' }}>
                        {row.total_bets}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-green)' }}>
                        {row.wins}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-red)' }}>
                        {row.losses}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-text)' }}>
                        {winRate}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: plColor }}>
                        {fmtPL(row.total_profit)}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: roiColor, fontWeight: 600 }}>
                        {fmtROI(row.roi)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          P/L SETTLES AFTER LOG RUN &nbsp;&middot;&nbsp;
          ROI = TOTAL P/L &divide; TOTAL STAKED ON SETTLED BETS
        </div>

      </div>
    </main>
  );
}
