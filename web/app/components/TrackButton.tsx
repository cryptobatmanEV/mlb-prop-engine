'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

type Props = {
  gameDate:    string;
  batter:      number;
  playerName:  string;
  teamAbbr:    string;
  adjProb:     number;
  bestOdds:    number | null;
  edge:        number | null;
  hasLine:     boolean;
  customOdds:  number | null;
  customEdge:  number | null;
};

function fmtOdds(o: number | null) {
  if (o == null) return 'NO LINE';
  return o > 0 ? `+${o}` : `${o}`;
}

function fmtEdge(e: number | null) {
  if (e == null) return '—';
  return `${e > 0 ? '+' : ''}${(e * 100).toFixed(1)}%`;
}

export default function TrackButton({
  gameDate, batter, playerName, teamAbbr, adjProb,
  bestOdds, edge, hasLine, customOdds, customEdge,
}: Props) {
  const router = useRouter();
  const [open,   setOpen]   = useState(false);
  const [stake,  setStake]  = useState('1');
  const [status, setStatus] = useState<'idle' | 'submitting' | 'done' | 'error'>('idle');

  function close() { setOpen(false); setStatus('idle'); }

  // Which odds + edge to actually track
  const trackOdds = customOdds ?? bestOdds;
  const trackEdge = customOdds != null ? customEdge : edge;
  const usingCustom = customOdds != null;

  async function submit() {
    const units = parseFloat(stake);
    if (!units || units <= 0) return;
    setStatus('submitting');
    try {
      const res = await fetch('/api/track-bet', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game_date:   String(gameDate).slice(0, 10),
          batter,
          player_name: playerName,
          team_abbr:   teamAbbr,
          adj_prob:    adjProb,
          best_odds:   trackOdds,
          edge:        trackEdge,
          stake_units: units,
        }),
      });
      if (!res.ok) throw new Error('bad response');
      setStatus('done');
      setTimeout(() => { close(); router.refresh(); }, 900);
    } catch {
      setStatus('error');
    }
  }

  const btnLabel =
    status === 'submitting' ? '...'     :
    status === 'done'       ? 'TRACKED' :
    status === 'error'      ? 'ERROR'   : 'CONFIRM';

  const confirmBorder =
    status === 'done'  ? 'var(--ev-green)' :
    status === 'error' ? 'var(--ev-red)'   :
    'rgba(0, 220, 110, 0.4)';

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          fontFamily:    'var(--font-mono)',
          fontSize:      '10px',
          letterSpacing: '2px',
          color:         'var(--ev-green)',
          background:    'transparent',
          border:        '1px solid rgba(0, 220, 110, 0.25)',
          borderRadius:  '2px',
          padding:       '3px 8px',
          cursor:        'pointer',
          textTransform: 'uppercase',
          whiteSpace:    'nowrap',
        }}
      >
        TRACK
      </button>

      {open && (
        <div
          className="modal-overlay"
          onClick={e => { if (e.target === e.currentTarget) close(); }}
        >
          <div style={{
            background:   '#0d1117',
            border:       '1px solid var(--ev-border)',
            borderRadius: '2px',
            padding:      '28px 24px',
            width:        '360px',
            fontFamily:   'var(--font-mono)',
          }}>
            {/* Header */}
            <div style={{
              fontSize: '10px', letterSpacing: '3px',
              color: 'var(--ev-green)', marginBottom: '20px', textTransform: 'uppercase',
            }}>
              TRACK BET
            </div>

            {/* Player */}
            <div style={{ fontSize: '15px', fontWeight: 500, color: 'var(--ev-text)', marginBottom: '4px' }}>
              {playerName}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--ev-muted)', letterSpacing: '1px', marginBottom: '16px' }}>
              {teamAbbr}
            </div>

            {/* Odds being tracked */}
            <div style={{
              background:   'rgba(255,255,255,0.03)',
              border:       '1px solid var(--ev-border)',
              borderRadius: '2px',
              padding:      '10px 12px',
              marginBottom: '20px',
              display:      'flex',
              justifyContent: 'space-between',
              alignItems:   'center',
            }}>
              <div>
                <div style={{ fontSize: '9px', letterSpacing: '2px', color: 'var(--ev-dim)', marginBottom: '4px' }}>
                  {usingCustom ? 'MY LINE' : (hasLine ? 'BOOK ODDS' : 'NO LINE')}
                </div>
                <div style={{
                  fontSize: '16px', fontWeight: 600,
                  color: usingCustom ? 'var(--ev-gold)' : (hasLine ? 'var(--ev-blue)' : 'var(--ev-dim)'),
                }}>
                  {fmtOdds(trackOdds)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '9px', letterSpacing: '2px', color: 'var(--ev-dim)', marginBottom: '4px' }}>
                  EDGE
                </div>
                <div style={{
                  fontSize: '14px', fontWeight: 600,
                  color: trackEdge != null && trackEdge > 0 ? 'var(--ev-green)' : 'var(--ev-dim)',
                }}>
                  {fmtEdge(trackEdge)}
                </div>
              </div>
            </div>

            {/* Stake input */}
            <div style={{
              fontSize: '10px', letterSpacing: '2px', color: 'var(--ev-dim)',
              textTransform: 'uppercase', marginBottom: '8px',
            }}>
              STAKE (UNITS)
            </div>
            <input
              type="number"
              min="0.1"
              step="0.5"
              value={stake}
              onChange={e => setStake(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') close(); }}
              autoFocus
              style={{
                width:        '100%',
                background:   'rgba(255,255,255,0.04)',
                border:       '1px solid rgba(255,255,255,0.1)',
                borderRadius: '2px',
                color:        'var(--ev-text)',
                fontFamily:   'var(--font-mono)',
                fontSize:     '18px',
                fontWeight:   500,
                padding:      '10px 12px',
                marginBottom: '20px',
                outline:      'none',
              }}
            />

            {/* Buttons */}
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={close}
                style={{
                  flex:          1,
                  background:    'transparent',
                  border:        '1px solid rgba(255,255,255,0.1)',
                  borderRadius:  '2px',
                  color:         'var(--ev-muted)',
                  fontFamily:    'var(--font-mono)',
                  fontSize:      '11px',
                  letterSpacing: '2px',
                  textTransform: 'uppercase',
                  padding:       '10px',
                  cursor:        'pointer',
                }}
              >
                CANCEL
              </button>
              <button
                onClick={submit}
                disabled={status === 'submitting' || status === 'done'}
                style={{
                  flex:          1,
                  background:    status === 'done' ? 'rgba(0,220,110,0.08)' : 'transparent',
                  border:        `1px solid ${confirmBorder}`,
                  borderRadius:  '2px',
                  color:         status === 'error' ? 'var(--ev-red)' : 'var(--ev-green)',
                  fontFamily:    'var(--font-mono)',
                  fontSize:      '11px',
                  letterSpacing: '2px',
                  textTransform: 'uppercase',
                  padding:       '10px',
                  cursor:        status === 'submitting' ? 'wait' : 'pointer',
                }}
              >
                {btnLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
