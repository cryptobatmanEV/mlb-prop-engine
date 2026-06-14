import { getServerSession } from 'next-auth';
import { getDb } from '@/lib/db';
import { authOptions } from '@/lib/auth';
import Nav from '../components/Nav';
import SignInWithDiscord from '../components/SignInWithDiscord';
import SignOutButton from '../components/SignOutButton';
import PerformanceCharts, { type PLPoint, type CalibPoint } from './PerformanceCharts';
import BetsTable from './BetsTable';
import { type TrackedBet, toISODate } from './shared';

export const dynamic = 'force-dynamic';

// ── Types ──────────────────────────────────────────────────────────────────

type TrackerStats = {
  total_bets:     number;
  settled_bets:   number;
  wins:           number;
  settled_staked: number;
  total_profit:   number;
};

// ── Formatters ─────────────────────────────────────────────────────────────

function fmtPL(profit: number, settled: number) {
  if (settled === 0) return '—';
  return `${profit >= 0 ? '+' : ''}${profit.toFixed(1)}u`;
}

function fmtROI(profit: number, staked: number) {
  if (staked === 0) return '—';
  const pct = (profit / staked) * 100;
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

// ── Page ───────────────────────────────────────────────────────────────────

export default async function TrackerPage() {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
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

          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '16px' }}>
              SIGN IN TO VIEW YOUR TRACKER
            </div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)', marginBottom: '20px' }}>
              Sign in with Discord to track your picks and see your personal performance history.
            </div>
            <SignInWithDiscord callbackUrl="/tracker" />
          </div>

        </div>
      </main>
    );
  }

  const discordUserId   = session.user.id;
  const discordUsername = session.user.username ?? session.user.name ?? 'Unknown';
  const discordImage    = session.user.image ?? null;

  let tracker: TrackerStats | null = null;
  let bets: TrackedBet[] = [];
  let plData: PLPoint[] = [];
  let calibData: CalibPoint[] = [];
  let dbError: string | null = null;

  try {
    const sql = getDb();

    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_user_id TEXT`;
    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_username TEXT`;

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
      WHERE discord_user_id = ${discordUserId}
    `;
    tracker = stats[0] as TrackerStats;

    bets = (await sql`
      SELECT * FROM tracked_bets WHERE discord_user_id = ${discordUserId} ORDER BY created_at DESC
    `) as TrackedBet[];

    // Cumulative P/L over time — settled bets, chronological order
    const settled = (await sql`
      SELECT game_date, hit_hr, tracked_odds, stake_units
      FROM tracked_bets
      WHERE hit_hr IS NOT NULL AND discord_user_id = ${discordUserId}
      ORDER BY game_date ASC, created_at ASC
    `) as { game_date: string; hit_hr: boolean; tracked_odds: number | null; stake_units: number }[];

    let cum = 0;
    const byDate = new Map<string, number>();
    for (const b of settled) {
      const pl = b.hit_hr
        ? (b.tracked_odds != null
            ? (b.tracked_odds > 0
                ? b.stake_units * (b.tracked_odds / 100)
                : b.stake_units * (100 / Math.abs(b.tracked_odds)))
            : 0)
        : -b.stake_units;
      cum += pl;
      const date = toISODate(b.game_date).slice(5).replace('-', '/');
      byDate.set(date, Math.round(cum * 100) / 100); // last write per date = end-of-day cumulative
    }
    plData = Array.from(byDate.entries()).map(([date, cumPL]) => ({ date, cumPL }));

    // Calibration — predicted probability buckets vs actual HR rate
    const calibRaw = (await sql`
      SELECT adj_prob::float AS adj_prob, hit_hr
      FROM tracked_bets
      WHERE hit_hr IS NOT NULL AND adj_prob IS NOT NULL AND discord_user_id = ${discordUserId}
    `) as { adj_prob: number; hit_hr: boolean }[];

    const BUCKETS = [
      { label: '<10%',   min: 0,    max: 0.10, mid: 0.07  },
      { label: '10-15%', min: 0.10, max: 0.15, mid: 0.125 },
      { label: '15-20%', min: 0.15, max: 0.20, mid: 0.175 },
      { label: '20-25%', min: 0.20, max: 0.25, mid: 0.225 },
      { label: '25-30%', min: 0.25, max: 0.30, mid: 0.275 },
      { label: '30%+',   min: 0.30, max: 1.00, mid: 0.35  },
    ];

    calibData = BUCKETS.flatMap(b => {
      const inBucket = calibRaw.filter(x => x.adj_prob >= b.min && x.adj_prob < b.max);
      if (inBucket.length === 0) return [];
      const hits = inBucket.filter(x => x.hit_hr).length;
      return [{
        label:         b.label,
        predicted_pct: Math.round(b.mid * 1000) / 10,
        actual_pct:    Math.round((hits / inBucket.length) * 1000) / 10,
        count:         inBucket.length,
      }];
    });
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
    // eslint-disable-next-line no-console
    console.error('[tracker] DB error:', dbError);
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
        <header style={{ marginBottom: '28px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
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
          </div>

          {/* Discord identity */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {discordImage && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={discordImage}
                alt={discordUsername}
                width={32}
                height={32}
                style={{ borderRadius: '50%', border: '1px solid var(--ev-border)' }}
              />
            )}
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ev-text)', fontWeight: 600 }}>
                {discordUsername}
              </div>
              <SignOutButton />
            </div>
          </div>
        </header>

        {/* Nav */}
        <Nav active="tracker" />

        {/* Content */}
        {dbError ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>
              Unable to load your tracker right now — please try again shortly.
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

            {/* Performance charts */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ ...LABEL, letterSpacing: '3px', marginBottom: '12px' }}>
                PERFORMANCE
              </div>
              <PerformanceCharts plData={plData} calibData={calibData} />
            </div>

            {/* Bets table */}
            <BetsTable bets={bets} />
          </>
        )}

        {/* Footer */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          P/L SETTLES AFTER GAMES ARE FINAL &nbsp;&middot;&nbsp;
          EDGE = MODEL VS BOOK PRICE &nbsp;&middot;&nbsp;
          RESULTS UPDATED DAILY
        </div>

      </div>
    </main>
  );
}
