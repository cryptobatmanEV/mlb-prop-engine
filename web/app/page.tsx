import { getDb } from '@/lib/db';

// Always render at request time — this page depends on CURRENT_DATE and DB state
export const dynamic = 'force-dynamic';

type Row = {
  player_name: string;
  team_abbr: string;
  stand: string;
  pitcher_name: string | null;
  p_throws: string | null;
  home_team: string;
  lineup_source: string | null;
  adj_prob: number;
  fair_odds: number | null;
  has_line: boolean;
  best_book: string | null;
  best_odds: number | null;
  book_implied: number | null;
  edge: number | null;
  model_prob: number;
  hr_park_factor: number | null;
  temp_f: number | null;
  wind_speed: number | null;
  wind_favor: number | null;
  is_dome: boolean;
};

function fmtProb(p: number) {
  return (p * 100).toFixed(1) + '%';
}

function fmtOdds(o: number | null) {
  if (o == null) return '—';
  return o > 0 ? `+${o}` : `${o}`;
}

function fmtEdge(edge: number | null, hasLine: boolean) {
  if (!hasLine || edge == null) return null;
  const sign = edge > 0 ? '+' : '';
  return `${sign}${(edge * 100).toFixed(1)}%`;
}

function edgeClass(edge: number | null, hasLine: boolean) {
  if (!hasLine || edge == null) return 'text-gray-600 italic';
  if (edge > 0.05) return 'text-emerald-400 font-bold';
  if (edge > 0) return 'text-emerald-600';
  if (edge > -0.03) return 'text-gray-400';
  return 'text-red-400';
}

function fmtWind(windFavor: number | null, isDome: boolean) {
  if (isDome) return 'Dome';
  if (windFavor == null) return '—';
  const abs = Math.abs(windFavor).toFixed(0);
  if (windFavor > 2) return `^ ${abs}`;
  if (windFavor < -2) return `v ${abs}`;
  return `~ ${abs}`;
}

export default async function Home() {
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'America/New_York',
  });

  let rows: Row[] = [];
  let dbError: string | null = null;

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

  const withLine = rows.filter((r) => r.has_line).length;
  const posEdge = rows.filter((r) => r.edge != null && r.edge > 0).length;

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">MLB HR Props</h1>
          <p className="text-gray-400 text-sm mt-1">{today}</p>
          {rows.length > 0 && (
            <p className="text-gray-600 text-xs mt-1">
              {rows.length} confirmed starters &middot; {withLine} with market lines &middot; {posEdge} positive-edge plays
            </p>
          )}
        </div>

        {dbError ? (
          <div className="text-center py-20">
            <p className="text-gray-400 text-lg">No predictions loaded yet.</p>
            <p className="text-gray-600 text-sm mt-2">
              Run the daily pipeline to generate today&apos;s card.
            </p>
            <p className="text-gray-800 text-xs mt-4 font-mono">{dbError}</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-gray-400 text-lg">No predictions for today yet.</p>
            <p className="text-gray-600 text-sm mt-2">
              Run{' '}
              <code className="bg-gray-900 text-gray-300 px-2 py-0.5 rounded text-xs">
                python scripts/daily_pipeline.py
              </code>{' '}
              to generate them.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-900 text-gray-500 text-xs uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">Player</th>
                  <th className="text-left px-4 py-3 font-medium">Team</th>
                  <th className="text-left px-4 py-3 font-medium">vs Pitcher</th>
                  <th className="text-right px-4 py-3 font-medium">Adj Prob</th>
                  <th className="text-right px-4 py-3 font-medium">Fair Odds</th>
                  <th className="text-right px-4 py-3 font-medium">Book Odds</th>
                  <th className="text-right px-4 py-3 font-medium">Edge</th>
                  <th className="text-right px-4 py-3 font-medium">Park</th>
                  <th className="text-right px-4 py-3 font-medium">Wind</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={i}
                    className={`border-t border-gray-800/60 hover:bg-gray-900/60 transition-colors ${
                      i % 2 === 0 ? 'bg-gray-950' : 'bg-gray-900/20'
                    }`}
                  >
                    {/* Player */}
                    <td className="px-4 py-2.5 font-medium text-gray-100">
                      {row.player_name}
                    </td>

                    {/* Team + bats */}
                    <td className="px-4 py-2.5">
                      <span className="font-mono text-xs text-gray-300">{row.team_abbr}</span>
                      {row.stand && (
                        <span className="ml-1.5 text-gray-600 text-xs">{row.stand}</span>
                      )}
                    </td>

                    {/* Pitcher */}
                    <td className="px-4 py-2.5 text-gray-400 text-xs">
                      {row.pitcher_name ?? 'TBD'}
                      {row.p_throws && (
                        <span className="ml-1 text-gray-600">({row.p_throws})</span>
                      )}
                    </td>

                    {/* Adj Prob */}
                    <td className="px-4 py-2.5 text-right font-mono font-semibold text-gray-100">
                      {fmtProb(row.adj_prob)}
                    </td>

                    {/* Fair Odds */}
                    <td className="px-4 py-2.5 text-right font-mono text-gray-400">
                      {fmtOdds(row.fair_odds)}
                    </td>

                    {/* Book Odds */}
                    <td className="px-4 py-2.5 text-right font-mono">
                      {row.has_line ? (
                        <span className="text-gray-300">
                          {fmtOdds(row.best_odds)}
                          {row.best_book && (
                            <span className="ml-1 text-gray-600 text-xs hidden lg:inline">
                              {row.best_book}
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-gray-700 italic text-xs">no line</span>
                      )}
                    </td>

                    {/* Edge */}
                    <td className={`px-4 py-2.5 text-right font-mono text-xs ${edgeClass(row.edge, row.has_line)}`}>
                      {fmtEdge(row.edge, row.has_line) ?? '—'}
                    </td>

                    {/* Park factor */}
                    <td className="px-4 py-2.5 text-right font-mono text-gray-500 text-xs">
                      {row.hr_park_factor != null ? Math.round(row.hr_park_factor) : '—'}
                    </td>

                    {/* Wind */}
                    <td className="px-4 py-2.5 text-right font-mono text-gray-500 text-xs">
                      {fmtWind(row.wind_favor, row.is_dome)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Legend */}
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-700">
          <span>Edge = adj_prob - book implied</span>
          <span className="text-emerald-400 font-bold">bold green = edge &gt; 5%</span>
          <span className="text-emerald-600">green = edge &gt; 0%</span>
          <span className="text-red-400">red = edge &lt; -3%</span>
          <span>Wind: ^ = toward OF (helps HRs) / v = toward home plate</span>
        </div>
      </div>
    </main>
  );
}
