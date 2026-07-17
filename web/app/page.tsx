import { getDb } from '@/lib/db';
import PropsTable, { Row } from './components/PropsTable';
import BatterPropsTable, { PropRow, PropConfig, AiPickRow } from './components/BatterPropsTable';
import DateNav from './components/DateNav';
import Nav from './components/Nav';
import PropTypeTabs, { StatType } from './components/PropTypeTabs';

export const dynamic = 'force-dynamic';

const STAT_CONFIG: Record<Exclude<StatType, 'hr'>, { table: string; config: PropConfig }> = {
  hits: {
    table: 'hits_predictions',
    config: { label: 'Hits', prob1Label: 'P(1+ H)', prob2Label: 'P(2+ H)', projLabel: 'PROJ HITS', statType: 'hits' },
  },
  total_bases: {
    table: 'total_bases_predictions',
    config: { label: 'Total Bases', prob1Label: 'P(1+ TB)', prob2Label: 'P(2+ TB)', projLabel: 'PROJ TB', statType: 'total_bases' },
  },
  batter_ks: {
    table: 'batter_ks_predictions',
    config: { label: 'Strikeouts', prob1Label: 'P(0.5+ K)', prob2Label: 'P(1.5+ K)', projLabel: 'PROJ K', statType: 'batter_ks' },
  },
};

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
  searchParams: Promise<{ date?: string; stat?: string }>;
}) {
  const params = await searchParams;
  const stat: StatType = (['hits', 'total_bases', 'batter_ks'].includes(params.stat ?? '')
    ? params.stat : 'hr') as StatType;

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
  let propRows:    PropRow[]     = [];
  let aiPickRows:  AiPickRow[]   = [];
  let dbError:     string | null = null;
  let lastUpdated: string | null = null;

  const isHrTab = stat === 'hr';

  try {
    const sql = getDb();

    if (isHrTab) {
      rows = (await sql`
        SELECT * FROM hr_predictions
        WHERE game_date = ${validDate}::date
        ORDER BY adj_prob DESC
      `) as Row[];

      const lu = await sql`
        SELECT MAX(created_at) AS ts FROM hr_predictions WHERE game_date = ${validDate}::date
      `;
      if (lu[0]?.ts) {
        lastUpdated = new Date(lu[0].ts as string).toLocaleTimeString('en-US', {
          hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/New_York',
        });
      }
    } else {
      // table/statPrefix come only from the fixed STAT_CONFIG whitelist above
      // (never from raw user input), so safe to interpolate directly --
      // the Neon serverless driver's tagged template doesn't support dynamic
      // identifiers the way postgres.js's sql(name) does, so sql.query() with
      // the identifier baked into the text (and only the date parameterized)
      // is the correct escape hatch here.
      const { table } = STAT_CONFIG[stat];
      const statPrefix = table.replace('_predictions', '');

      const propResult = await sql(
        `SELECT
           id, game_date, game_pk, batter, player_name, team_abbr, opp_team,
           bat_order, is_home, game_time, stadium, pitcher_name, p_throws,
           adj_prob, primary_line, primary_has_line, primary_best_book, primary_best_odds, primary_edge,
           secondary_line, secondary_has_line, secondary_best_book, secondary_best_odds, secondary_edge,
           book_markets,
           pred_${statPrefix} AS pred_stat,
           p_${statPrefix}_1plus AS p_stat_1plus,
           p_${statPrefix}_2plus AS p_stat_2plus
         FROM ${table}
         WHERE game_date = $1::date
         ORDER BY adj_prob DESC`,
        [validDate],
      );
      propRows = propResult as unknown as PropRow[];

      const lu = await sql(
        `SELECT MAX(created_at) AS ts FROM ${table} WHERE game_date = $1::date`,
        [validDate],
      );
      const luRow = (lu as unknown as { ts: string | null }[])[0];
      if (luRow?.ts) {
        lastUpdated = new Date(luRow.ts).toLocaleTimeString('en-US', {
          hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/New_York',
        });
      }

      const aiPicksTable = table.replace('_predictions', '_ai_picks_log');
      try {
        aiPickRows = await sql(
          `SELECT batter, player_name, team_abbr, bat_order, best_odds, best_book,
                  edge, adj_prob, book_line, book_side, composite_score, result
             FROM ${aiPicksTable}
            WHERE game_date = $1::date
            ORDER BY composite_score DESC`,
          [validDate],
        ) as unknown as AiPickRow[];
      } catch {
        aiPickRows = [];
      }
    }
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
    // eslint-disable-next-line no-console
    console.error('[page] DB error:', dbError);
  }

  const withLine = isHrTab ? rows.filter(r => r.has_line).length : propRows.filter(r => r.primary_has_line).length;
  const posEdge  = isHrTab
    ? rows.filter(r => r.edge != null && r.edge > 0).length
    : propRows.filter(r => r.primary_edge != null && r.primary_edge > 0).length;
  const rowCount = isHrTab ? rows.length : propRows.length;

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
            BATTER MODEL
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
          {rowCount > 0 && (
            <div style={{ ...LABEL, color: 'var(--ev-dim)', marginTop: '4px', letterSpacing: '1px' }}>
              {rowCount} STARTERS &middot; {withLine} W/ LINES &middot; {posEdge} +EV
            </div>
          )}
        </header>

        {/* Nav */}
        <Nav active="card" />

        {/* Prop type tabs */}
        <PropTypeTabs active={stat} />

        {/* Date navigation */}
        <DateNav date={validDate} today={todayISO} />

        {/* Predictions table */}
        {dbError || rowCount === 0 ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>
              {dbError
                ? 'No plays available for this date'
                : isBeforeLineups
                  ? "Today's card is loading — plays appear as lineups are confirmed"
                  : 'No plays available for this date'}
            </div>
          </div>
        ) : isHrTab ? (
          <PropsTable rows={rows} />
        ) : (
          <BatterPropsTable rows={propRows} config={STAT_CONFIG[stat].config} aiPicks={aiPickRows} />
        )}

        {/* Legend */}
        <div style={{ display: 'flex', gap: '20px', marginTop: '8px', flexWrap: 'wrap' }}>
          <span style={{ ...LABEL, color: 'var(--ev-green)' }}>+EV GREEN</span>
          <span style={LABEL}>&gt;5% BOLD</span>
          <span style={{ ...LABEL, color: 'var(--ev-red)' }}>&lt;-3% RED</span>
          {isHrTab && <span style={LABEL}>^ TAIL  v INTO  ~ NEUTRAL</span>}
          {isHrTab && <span style={{ ...LABEL, color: 'var(--ev-gold)' }}>MY LINE = CUSTOM ODDS</span>}
        </div>

        {/* Footer */}
        <div style={{ ...LABEL, textAlign: 'center', marginTop: '40px', fontSize: '9px', color: 'rgba(255,255,255,0.15)' }}>
          ADJ% = {isHrTab ? 'HR' : STAT_CONFIG[stat as Exclude<StatType,'hr'>].config.label.toUpperCase()} PROBABILITY &nbsp;&middot;&nbsp;
          EDGE = MODEL VS BOOK PRICE &nbsp;&middot;&nbsp;
          P/L SETTLES AFTER GAMES ARE FINAL
        </div>

      </div>
    </main>
  );
}
