'use client';

import { useEffect, useState } from 'react';
import Nav from '../components/Nav';
import PerformanceCharts, { type PLPoint, type CalibPoint } from './PerformanceCharts';
import BetsTable from './BetsTable';
import { type TrackedBet } from './shared';
import { useIframeIdentity, identityHeaders } from '../lib/iframeIdentity';

// ── Types ──────────────────────────────────────────────────────────────────

type TrackerStats = {
  total_bets:     number;
  settled_bets:   number;
  wins:           number;
  settled_staked: number;
  total_profit:   number;
};

type AiPicksStats = {
  total_picks:   number;
  settled_picks: number;
  hits:          number;
  total_profit:  number;
};

type TrackerData = {
  tracker:   TrackerStats;
  bets:      TrackedBet[];
  plData:    PLPoint[];
  calibData: CalibPoint[];
  aiPicks:   AiPicksStats;
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

export default function TrackerClient() {
  const identity = useIframeIdentity();
  const [data, setData] = useState<TrackerData | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [slowLoad, setSlowLoad] = useState(false);

  useEffect(() => {
    if (!identity) return;
    let cancelled = false;
    fetch('/api/tracker-data', { headers: identityHeaders(identity) })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: TrackerData) => {
        if (!cancelled) setData(json);
      })
      .catch(err => {
        if (!cancelled) setDataError(err instanceof Error ? err.message : String(err));
      });
    return () => { cancelled = true; };
  }, [identity]);

  // After 10s of waiting on the DB, let the user know the wait is normal
  // (Neon cold-starts can take a couple minutes on first load).
  useEffect(() => {
    if (!identity || data !== null || dataError !== null) {
      setSlowLoad(false);
      return;
    }
    const timer = setTimeout(() => setSlowLoad(true), 10000);
    return () => clearTimeout(timer);
  }, [identity, data, dataError]);

  const header = (
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
      {identity && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ev-text)', fontWeight: 600 }}>
          {identity.discordUser}
        </div>
      )}
    </header>
  );

  // No verified identity (still resolving, or opened outside theevcave.com) —
  // never show a blank page.
  if (!identity) {
    return (
      <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
        <div style={{ maxWidth: '1380px', margin: '0 auto' }}>
          {header}
          <Nav active="tracker" />

          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            {identity === undefined ? (
              <>
                <div className="ev-spinner" style={{ marginBottom: '16px' }} />
                <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>LOADING&hellip;</div>
              </>
            ) : (
              <>
                <div style={{ ...LABEL, color: 'var(--ev-muted)', marginBottom: '16px' }}>
                  SIGN IN ON THE +EV CAVE TO VIEW YOUR TRACKER
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ev-dim)' }}>
                  Open this tool from theevcave.com while signed in with Discord to track your
                  picks and see your personal performance history.
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    );
  }

  const tracker     = data?.tracker ?? null;
  const bets        = data?.bets ?? [];
  const plData      = data?.plData ?? [];
  const calibData   = data?.calibData ?? [];
  const aiPicks     = data?.aiPicks ?? null;
  const totalBets   = tracker ? Number(tracker.total_bets)     : 0;
  const settledBets = tracker ? Number(tracker.settled_bets)   : 0;
  const wins        = tracker ? Number(tracker.wins)           : 0;
  const staked      = tracker ? Number(tracker.settled_staked) : 0;
  const profit      = tracker ? Number(tracker.total_profit)   : 0;
  const winRate     = settledBets > 0 ? (wins / settledBets * 100).toFixed(1) + '%' : '—';

  return (
    <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
      <div style={{ maxWidth: '1380px', margin: '0 auto' }}>
        {header}

        {/* Nav */}
        <Nav active="tracker" />

        {/* Content */}
        {dataError ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>
              Unable to load your tracker right now — please try again shortly.
            </div>
          </div>
        ) : data === null ? (
          <div style={{ ...CARD, padding: '48px', textAlign: 'center' }}>
            <div className="ev-spinner" style={{ marginBottom: '16px' }} />
            <div style={{ ...LABEL, color: 'var(--ev-muted)' }}>
              LOADING YOUR TRACKER&hellip;
            </div>
            {slowLoad && (
              <div style={{ fontSize: '11px', color: 'var(--ev-dim)', marginTop: '12px' }}>
                Still loading — this can take a moment on first sign-in.
              </div>
            )}
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

        {/* AI PICKS system performance */}
        {aiPicks && aiPicks.settled_picks > 0 && (
          <div style={{ marginTop: '24px' }}>
            <div style={{ ...LABEL, letterSpacing: '3px', marginBottom: '12px' }}>
              AI PICKS MODEL PERFORMANCE
            </div>
            <div style={{
              display:             'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap:                 '1px',
              background:          'var(--ev-border)',
              border:              '1px solid var(--ev-border)',
              borderRadius:        '2px',
              overflow:            'hidden',
            }}>
              {([
                {
                  label: 'PICKS LOGGED',
                  value: String(aiPicks.total_picks),
                  sub:   `${aiPicks.total_picks - aiPicks.settled_picks} PENDING`,
                  color: 'var(--ev-text)',
                },
                {
                  label: 'HIT RATE',
                  value: aiPicks.settled_picks > 0
                    ? `${(aiPicks.hits / aiPicks.settled_picks * 100).toFixed(1)}%`
                    : '—',
                  sub:   `${aiPicks.hits}W / ${aiPicks.settled_picks - aiPicks.hits}L`,
                  color: 'var(--ev-text)',
                },
                {
                  label: 'MODEL P/L',
                  value: `${aiPicks.total_profit >= 0 ? '+' : ''}${aiPicks.total_profit.toFixed(1)}u`,
                  sub:   `${aiPicks.settled_picks} SETTLED`,
                  color: aiPicks.total_profit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
                },
                {
                  label: 'MODEL ROI',
                  value: aiPicks.settled_picks > 0
                    ? `${(aiPicks.total_profit / aiPicks.settled_picks * 100) >= 0 ? '+' : ''}${(aiPicks.total_profit / aiPicks.settled_picks * 100).toFixed(1)}%`
                    : '—',
                  sub:   '1U PER PICK',
                  color: aiPicks.total_profit >= 0 ? 'var(--ev-green)' : 'var(--ev-red)',
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
            <div style={{ ...LABEL, fontSize: '9px', color: 'rgba(255,255,255,0.25)', marginTop: '6px' }}>
              FIRST MORNING ODDS SNAPSHOT PER PICK &nbsp;&middot;&nbsp; 1 UNIT FLAT STAKE &nbsp;&middot;&nbsp; ADJ% &gt; 12% &middot; EDGE &gt; −3% &middot; ADJ% &gt; BREAK-EVEN + 2%
            </div>
          </div>
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
