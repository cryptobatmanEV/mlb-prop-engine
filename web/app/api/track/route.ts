import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { getDb } from '@/lib/db';
import { authOptions } from '@/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      game_date, batter, player_name, team_abbr,
      adj_prob, tracked_odds, edge, stake_units,
    } = body;

    if (!game_date || batter == null || stake_units == null || stake_units <= 0) {
      return NextResponse.json({ error: 'Missing or invalid fields' }, { status: 400 });
    }

    const sql = getDb();

    // Safety net: create table if the pipeline hasn't run yet on this environment.
    // On normal usage the Python pipeline creates this table; this is a fallback.
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
        discord_user_id  TEXT,
        discord_username TEXT,
        UNIQUE (game_date, batter)
      )
    `;
    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_user_id TEXT`;
    await sql`ALTER TABLE tracked_bets ADD COLUMN IF NOT EXISTS discord_username TEXT`;

    const session = await getServerSession(authOptions);
    const discordUserId   = session?.user?.id ?? null;
    const discordUsername = session?.user?.username ?? null;

    const result = await sql`
      INSERT INTO tracked_bets
        (game_date, batter, player_name, team_abbr, adj_prob, tracked_odds, edge, stake_units, settled, discord_user_id, discord_username)
      VALUES
        (${game_date}, ${batter}, ${player_name ?? null}, ${team_abbr ?? null},
         ${adj_prob ?? null}, ${tracked_odds ?? null}, ${edge ?? null}, ${stake_units}, false, ${discordUserId}, ${discordUsername})
      ON CONFLICT (game_date, batter) DO UPDATE SET
        player_name      = EXCLUDED.player_name,
        adj_prob          = EXCLUDED.adj_prob,
        tracked_odds      = EXCLUDED.tracked_odds,
        edge              = EXCLUDED.edge,
        stake_units       = EXCLUDED.stake_units,
        hit_hr            = NULL,
        settled           = false,
        created_at        = NOW(),
        discord_user_id   = EXCLUDED.discord_user_id,
        discord_username  = EXCLUDED.discord_username
      RETURNING id
    `;

    return NextResponse.json({ success: true, id: result[0].id });
  } catch (err) {
    // Surface the real error message so browser console shows the actual cause
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[/api/track] POST error:', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const id = req.nextUrl.searchParams.get('id');
    if (!id) {
      return NextResponse.json({ error: 'Missing id' }, { status: 400 });
    }

    const sql = getDb();
    const result = await sql`
      DELETE FROM tracked_bets WHERE id = ${Number(id)} RETURNING id
    `;

    if (result.length === 0) {
      return NextResponse.json({ error: 'Bet not found' }, { status: 404 });
    }

    return NextResponse.json({ success: true });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[/api/track] DELETE error:', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
