import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      game_date, batter, player_name, team_abbr,
      adj_prob, best_odds, edge, stake_units,
    } = body;

    if (!game_date || batter == null || stake_units == null || stake_units <= 0) {
      return NextResponse.json({ error: 'Missing or invalid fields' }, { status: 400 });
    }

    const sql = getDb();

    // Create table with full schema (new installs)
    await sql`
      CREATE TABLE IF NOT EXISTS tracked_bets (
        id          SERIAL PRIMARY KEY,
        game_date   DATE        NOT NULL,
        batter      BIGINT      NOT NULL,
        player_name TEXT,
        team_abbr   TEXT,
        adj_prob    FLOAT,
        best_odds   INTEGER,
        edge        FLOAT,
        stake_units FLOAT       NOT NULL,
        hit_hr      BOOLEAN,
        settled     BOOLEAN     NOT NULL DEFAULT false,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (game_date, batter)
      )
    `;

    // Idempotent migrations for tables created before settled / UNIQUE were added
    try {
      await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS settled BOOLEAN NOT NULL DEFAULT false`;
    } catch { /* already exists */ }

    try {
      await sql`ALTER TABLE tracked_bets ADD CONSTRAINT tracked_bets_date_batter_key UNIQUE (game_date, batter)`;
    } catch { /* already exists or duplicates prevent it */ }

    // Upsert: re-tracking the same player today updates the bet details
    const result = await sql`
      INSERT INTO tracked_bets
        (game_date, batter, player_name, team_abbr, adj_prob, best_odds, edge, stake_units, settled)
      VALUES
        (${game_date}, ${batter}, ${player_name ?? null}, ${team_abbr ?? null},
         ${adj_prob ?? null}, ${best_odds ?? null}, ${edge ?? null}, ${stake_units}, false)
      ON CONFLICT (game_date, batter) DO UPDATE SET
        player_name = EXCLUDED.player_name,
        adj_prob    = EXCLUDED.adj_prob,
        best_odds   = EXCLUDED.best_odds,
        edge        = EXCLUDED.edge,
        stake_units = EXCLUDED.stake_units,
        hit_hr      = NULL,
        settled     = false,
        created_at  = NOW()
      RETURNING id
    `;

    return NextResponse.json({ success: true, id: result[0].id });
  } catch (err) {
    console.error('track-bet error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
