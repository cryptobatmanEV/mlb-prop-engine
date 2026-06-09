import { getDb } from '@/lib/db';
import PropsTable, { Row } from './components/PropsTable';
import DateNav from './components/DateNav';
import Nav from './components/Nav';

export const dynamic = 'force-dynamic';

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

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const params = await searchParams;

  // Date context (ET)
  const now      = new Date();
  const todayISO = now.toLocaleDateString('en-CA', { timeZone: 'America/New_York' }); // YYYY-MM-DD
  const dateStr  = params.date ?? todayISO;

  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? dateStr : todayISO;

  const displayDate = new Date(validDate + 'T12:00:00Z').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'UTC',
  }).toUpperCase();

  const isViewingToday = validDate === todayISO;
  const etHourStr = now.toLocaleString('en-US', {
    timeZone: 'America/New_York', hour: 'numeric', hour12: false,
  });
  const isBeforeLineups = isViewingToday && parseInt(etHourStr, 10) < 15;

  let rows:        Row[]         = [];
  let dbError:     string | null = null;
  let lastUpdated: string | null = null;

  try {
    const sql = getDb();
    rows = (await sql`
      SELECT * FROM hr_predictions
      WHERE game_date = ${validDate}::date
      ORDER BY adj_prob DESC
    `) as Row[];

    const lu = await sql`
      SELECT MAX(created_at) AS ts
      FROM hr_predictions
      WHERE game_date = ${validDate}::date
    `;
    if (lu[0]?.ts) {
      lastUpdated = new Date(lu[0].ts as string).toLocaleTimeString('en-US', {
        hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/New_York',
      });
    }
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
  }

  const withLine = rows.filter(r => r.has_line).length;
  const posEdge  = rows.filter(r => r.edge != null && r.edge > 0).length;

  // ── Render ───────────────────────────────────────────────────────────────

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
            MLB HR PROPS
          </h1>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', marginTop: '6px', flexWrap: 'wrap' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', letterSpacing: '1px' }}>
              {displayDate}
            </div>
            {lastUpdated && (
              <div style={{ ...LABEL, color: 'var(--ev-dim)', letterSpacing: '1px' }}>
                UPDATED {lastUpdated} ET
              </div>
            )}
          </div>
          {rows.length > 0 && (
            <div style={{ ...LABEL, color: 'var(--ev-dim)', marginTop: '4px', letterSpacing: '1px' }}>
              {rows.length} STARTERS &middot; {withLine} W/ LINES &middot; {posEdge} +EV
            </div>
          )}
        </header>

        {/* Nav */}
        <Nav active="card" />

        {/* Date navigation */}
        <DateNav date={validDate} today={todayISO} />

        {/* Predictions table */}
        {dbError ? (
          <div style={{ ...CARD, padding: '40px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>NO DATA LOADED</div>
            <div style={{ fontSize: '11px', color: 'var(--ev-dim)', marginBottom: '8px' }}>
              Check DATABASE_URL in Vercel environment variables.
            </div>
            <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.15)', wordBreak: 'break-all' }}>
              {dbError}
            </div>
          </div>
        ) : rows.length === 0 ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            {isBeforeLineups ? (
              <>
                <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px', fontSize: '11px', letterSpacing: '3px' }}>
                  LINEUPS NOT POSTED YET
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
                  MLB lineups typically post around 3 PM ET. Run the pipeline after they drop.
                </div>
              </>
            ) : (
              <>
                <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '8px' }}>
                  NO PREDICTIONS YET
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
                  <code style={{ fontFamily: 'var(--font-mono)' }}>python scripts/daily_pipeline.py</code>
                </div>
              </>
            )}
          </div>
        ) : (
          <PropsTable rows={rows} />
        )}

        {/* Legend */}
        <div style={{ display: 'flex', gap: '20px', marginTop: '8px', flexWrap: 'wrap' }}>
          <span style={{ ...LABEL, color: 'var(--ev-green)' }}>+EV GREEN</span>
          <span style={LABEL}>&gt;5% BOLD</span>
          <span style={{ ...LABEL, color: 'var(--ev-red)' }}>&lt;-3% RED</span>
          <span style={LABEL}>^ TAIL  v INTO  ~ NEUTRAL</span>
          <span style={{ ...LABEL, color: 'var(--ev-gold)' }}>MY LINE = CUSTOM ODDS</span>
        </div>

        {/* Footer */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          ADJ% = MODEL PROB x P(CONTACT) &nbsp;&middot;&nbsp;
          EDGE = ADJ% - BOOK IMPLIED &nbsp;&middot;&nbsp;
          P/L SETTLES AFTER LOG RUN
        </div>

      </div>
    </main>
  );
}
