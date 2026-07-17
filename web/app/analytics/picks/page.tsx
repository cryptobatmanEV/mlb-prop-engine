import { getDb } from '@/lib/db';
import Nav from '../../components/Nav';

export const dynamic = 'force-dynamic';

// ── Types ──────────────────────────────────────────────────────────────────

type PicksStats = {
  total_picks:   number;
  settled_picks: number;
  hits:          number;
  total_profit:  number;
};

type StatBlock = {
  key:   string;
  label: string;
  table: string;
};

const STAT_BLOCKS: StatBlock[] = [
  { key: 'home_runs',   label: 'HOME RUNS',   table: 'hr_ai_picks_log' },
  { key: 'hits',        label: 'HITS',        table: 'hits_ai_picks_log' },
  { key: 'total_bases', label: 'TOTAL BASES', table: 'total_bases_ai_picks_log' },
  { key: 'batter_ks',   label: 'STRIKEOUTS',  table: 'batter_ks_ai_picks_log' },
];

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

async function fetchStatsFor(sql: ReturnType<typeof getDb>, table: string): Promise<PicksStats> {
  try {
    // First snapshot per player per day -- matches tracker-data's HR query,
    // generalized to any of the 4 ai_picks_log tables.
    const rows = await sql(
      `WITH first_snap AS (
        SELECT DISTINCT ON (game_date, batter)
          game_date, best_odds, result
        FROM ${table}
        ORDER BY game_date, batter, captured_at ASC
      )
      SELECT
        COUNT(*)::int                                   AS total_picks,
        COUNT(*) FILTER (WHERE result IS NOT NULL)::int AS settled_picks,
        COUNT(*) FILTER (WHERE result = 'HIT')::int      AS hits,
        COALESCE(SUM(CASE
          WHEN result = 'HIT' AND best_odds >  0 THEN best_odds::float / 100.0
          WHEN result = 'HIT' AND best_odds <= 0 THEN 100.0 / ABS(best_odds::float)
          WHEN result = 'MISS'                    THEN -1.0
          ELSE 0
        END), 0)::float AS total_profit
      FROM first_snap`,
      [],
    ) as unknown as PicksStats[];
    return rows[0] ?? { total_picks: 0, settled_picks: 0, hits: 0, total_profit: 0 };
  } catch {
    return { total_picks: 0, settled_picks: 0, hits: 0, total_profit: 0 };
  }
}

export default async function AiPicksAnalyticsPage() {
  let statsByKey: Record<string, PicksStats> = {};
  let dbError: string | null = null;

  try {
    const sql = getDb();
    const results = await Promise.all(STAT_BLOCKS.map(b => fetchStatsFor(sql, b.table)));
    statsByKey = Object.fromEntries(STAT_BLOCKS.map((b, i) => [b.key, results[i]]));
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
    // eslint-disable-next-line no-console
    console.error('[analytics/picks] DB error:', dbError);
  }

  return (
    <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
      <div style={{ maxWidth: '1380px', margin: '0 auto' }}>

        <header style={{ marginBottom: '28px' }}>
          <div style={{ ...LABEL, color: 'var(--ev-green)', letterSpacing: '3px', marginBottom: '8px' }}>
            THE +EV CAVE
          </div>
          <h1 style={{
            fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '26px',
            margin: 0, letterSpacing: '-0.5px', color: 'var(--ev-text)',
          }}>
            AI PICKS PERFORMANCE
          </h1>
          <div style={{ ...LABEL, color: 'var(--ev-muted)', marginTop: '6px', letterSpacing: '1px' }}>
            MODEL-GENERATED PICKS &middot; ALL 4 STAT TYPES
          </div>
        </header>

        <Nav active="picks" />

        {dbError ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>
              Unable to load AI Picks performance right now — please try again shortly.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {STAT_BLOCKS.map(({ key, label }) => {
              const s = statsByKey[key] ?? { total_picks: 0, settled_picks: 0, hits: 0, total_profit: 0 };
              const hitRate = s.settled_picks > 0 ? (s.hits / s.settled_picks * 100).toFixed(1) + '%' : '—';
              const roi = s.settled_picks > 0 ? (s.total_profit / s.settled_picks * 100) : null;
              return (
                <div key={key}>
                  <div style={{ ...LABEL, letterSpacing: '3px', marginBottom: '12px' }}>{label}</div>
                  {s.total_picks === 0 ? (
                    <div style={{ ...CARD, padding: '24px', textAlign: 'center' }}>
                      <div style={{ ...LABEL, color: 'var(--ev-dim)' }}>NO AI PICKS LOGGED YET</div>
                    </div>
                  ) : (
                    <div style={{
                      display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1px',
                      background: 'var(--ev-border)', border: '1px solid var(--ev-border)',
                      borderRadius: '2px', overflow: 'hidden',
                    }}>
                      {([
                        { label: 'PICKS LOGGED', value: String(s.total_picks), sub: `${s.total_picks - s.settled_picks} PENDING`, color: 'var(--ev-text)' },
                        { label: 'HIT RATE', value: hitRate, sub: `${s.hits}W / ${s.settled_picks - s.hits}L`, color: 'var(--ev-text)' },
                        { label: 'MODEL P/L', value: `${s.total_profit >= 0 ? '+' : ''}${s.total_profit.toFixed(1)}u`, sub: `${s.settled_picks} SETTLED`, color: s.settled_picks === 0 ? 'var(--ev-dim)' : s.total_profit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)' },
                        { label: 'MODEL ROI', value: roi != null ? `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%` : '—', sub: '1U PER PICK', color: roi == null ? 'var(--ev-dim)' : roi >= 0 ? 'var(--ev-green)' : 'var(--ev-red)' },
                      ] as { label: string; value: string; sub: string; color: string }[]).map(({ label: l, value, sub, color }) => (
                        <div key={l} style={{ background: 'var(--ev-bg)', padding: '16px 18px' }}>
                          <div style={LABEL}>{l}</div>
                          <div style={{ fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '22px', color, margin: '8px 0 4px', letterSpacing: '-0.5px' }}>
                            {value}
                          </div>
                          <div style={{ ...LABEL, fontSize: '9px' }}>{sub}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          FIRST MORNING ODDS SNAPSHOT PER PICK &nbsp;&middot;&nbsp; 1 UNIT FLAT STAKE PER PICK &nbsp;&middot;&nbsp; RESULTS UPDATED DAILY
        </div>

      </div>
    </main>
  );
}
