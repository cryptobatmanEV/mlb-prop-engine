import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getVerifiedIdentity } from '@/lib/iframeAuth';
import { toISODate } from '../../tracker/shared';

export async function GET(req: Request) {
  const identity = getVerifiedIdentity(req);
  if (!identity) {
    return NextResponse.json({ error: 'Not signed in' }, { status: 401 });
  }

  const discordUserId = identity.discordId;

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
    const tracker = stats[0];

    const bets = await sql`
      SELECT * FROM tracked_bets WHERE discord_user_id = ${discordUserId} ORDER BY created_at DESC
    `;

    // Per-stat-type breakdown, so the tracker page can show ALL / HR / HITS /
    // TOTAL BASES / STRIKEOUTS separately as well as combined.
    const byStatTypeRaw = (await sql`
      SELECT
        COALESCE(stat_type, 'home_runs')                                                         AS stat_type,
        COUNT(*)::int                                                                              AS total_bets,
        COUNT(*) FILTER (WHERE hit_hr IS NOT NULL)::int                                           AS settled_bets,
        COUNT(*) FILTER (WHERE hit_hr = true)::int                                                AS wins,
        COALESCE(SUM(CASE WHEN hit_hr IS NOT NULL THEN stake_units ELSE 0 END), 0)::float         AS settled_staked,
        COALESCE(SUM(CASE
          WHEN hit_hr = true  AND tracked_odds >  0 THEN stake_units * (tracked_odds::float / 100.0)
          WHEN hit_hr = true  AND tracked_odds <= 0 THEN stake_units * (100.0 / ABS(tracked_odds::float))
          WHEN hit_hr = false                       THEN -stake_units
          ELSE 0
        END), 0)::float AS total_profit
      FROM tracked_bets
      WHERE discord_user_id = ${discordUserId}
      GROUP BY COALESCE(stat_type, 'home_runs')
    `) as {
      stat_type: string; total_bets: number; settled_bets: number; wins: number;
      settled_staked: number; total_profit: number;
    }[];
    const byStatType = Object.fromEntries(byStatTypeRaw.map(r => [r.stat_type, r]));

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
    const plData = Array.from(byDate.entries()).map(([date, cumPL]) => ({ date, cumPL }));

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

    const calibData = BUCKETS.flatMap(b => {
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

    return NextResponse.json({ tracker, bets, plData, calibData, byStatType });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('[tracker-data] DB error:', message);
    return NextResponse.json({ error: 'DB error' }, { status: 500 });
  }
}
