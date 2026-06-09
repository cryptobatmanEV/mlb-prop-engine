import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const sql = getDb();

    // Ensure table exists before querying
    await sql`
      CREATE TABLE IF NOT EXISTS tracked_bets (
        id           SERIAL PRIMARY KEY,
        game_date    DATE        NOT NULL,
        batter       BIGINT      NOT NULL,
        player_name  TEXT,
        team_abbr    TEXT,
        adj_prob     FLOAT,
        tracked_odds INTEGER,
        edge         FLOAT,
        stake_units  FLOAT       NOT NULL,
        hit_hr       BOOLEAN     DEFAULT NULL,
        settled      BOOLEAN     NOT NULL DEFAULT false,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (game_date, batter)
      )
    `;

    const bets = await sql`
      SELECT * FROM tracked_bets
      ORDER BY created_at DESC
    `;

    const stats = await sql`
      SELECT
        COUNT(*)::int                                                                      AS total_bets,
        COUNT(*) FILTER (WHERE hit_hr IS NOT NULL)::int                                   AS settled_bets,
        COUNT(*) FILTER (WHERE hit_hr = true)::int                                        AS wins,
        COALESCE(SUM(CASE WHEN hit_hr IS NOT NULL THEN stake_units ELSE 0 END), 0)::float AS settled_staked,
        COALESCE(SUM(CASE
          WHEN hit_hr = true  AND tracked_odds >  0 THEN stake_units * (tracked_odds::float / 100.0)
          WHEN hit_hr = true  AND tracked_odds <= 0 THEN stake_units * (100.0 / ABS(tracked_odds::float))
          WHEN hit_hr = false                       THEN -stake_units
          ELSE 0
        END), 0)::float AS total_profit
      FROM tracked_bets
    `;

    return NextResponse.json({ bets, stats: stats[0] });
  } catch (err) {
    console.error('tracked error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
