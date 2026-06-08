import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

const CREATE_TRACKED_BETS = `
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
    created_at  TIMESTAMPTZ DEFAULT NOW()
  )
`;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { game_date, batter, player_name, team_abbr, adj_prob, best_odds, edge, stake_units } = body;

    if (!game_date || batter == null || stake_units == null || stake_units <= 0) {
      return NextResponse.json({ error: 'Missing or invalid fields' }, { status: 400 });
    }

    const sql = getDb();

    await sql`CREATE TABLE IF NOT EXISTS tracked_bets (
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
      created_at  TIMESTAMPTZ DEFAULT NOW()
    )`;

    const result = await sql`
      INSERT INTO tracked_bets
        (game_date, batter, player_name, team_abbr, adj_prob, best_odds, edge, stake_units)
      VALUES
        (${game_date}, ${batter}, ${player_name ?? null}, ${team_abbr ?? null},
         ${adj_prob ?? null}, ${best_odds ?? null}, ${edge ?? null}, ${stake_units})
      RETURNING id
    `;

    return NextResponse.json({ success: true, id: result[0].id });
  } catch (err) {
    console.error('track-bet error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

// Silence unused import warning
void CREATE_TRACKED_BETS;
