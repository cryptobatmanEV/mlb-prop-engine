'use client';

import { useState } from 'react';
import { type TrackedBet, fmtDate, fmtOdds, fmtEdge, betPL } from './shared';

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

const TH: React.CSSProperties = {
  ...LABEL,
  padding:    '8px 14px',
  fontWeight:  500,
  background: 'rgba(255,255,255,0.02)',
};

export default function BetsTable({ bets: initialBets }: { bets: TrackedBet[] }) {
  const [bets, setBets] = useState(initialBets);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDelete(id: number) {
    if (!window.confirm('DELETE THIS BET?')) return;

    setDeletingId(id);
    try {
      const res = await fetch(`/api/track?id=${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const text = await res.text();
        // eslint-disable-next-line no-console
        console.error('[BetsTable] delete failed:', res.status, text);
        alert(`Failed to delete bet (${res.status}).`);
        setDeletingId(null);
        return;
      }
      setBets(prev => prev.filter(b => b.id !== id));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // eslint-disable-next-line no-console
      console.error('[BetsTable] delete error:', msg);
      alert('Failed to delete bet.');
      setDeletingId(null);
    }
  }

  if (bets.length === 0) return null;

  return (
    <div style={{ ...CARD, overflowX: 'auto' }}>
      <table style={{
        width: '100%', borderCollapse: 'collapse',
        fontFamily: 'var(--font-mono)', fontSize: '11px',
      }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--ev-border)' }}>
            {(['DATE', 'PLAYER', 'TEAM', 'ODDS', 'STAKE', 'EDGE', 'P/L', 'RESULT'] as const).map(
              (h, i) => (
                <th key={h} style={{ ...TH, textAlign: i >= 3 ? 'right' : 'left' }}>{h}</th>
              )
            )}
            <th style={{ ...TH, textAlign: 'right', width: '32px' }}></th>
          </tr>
        </thead>
        <tbody>
          {bets.map(bet => {
            const { text: edgeText, color: edgeCol } = fmtEdge(bet.edge, bet.tracked_odds != null);
            const pl        = betPL(bet);
            const result    = bet.hit_hr === null ? 'PENDING' : bet.hit_hr ? 'WIN' : 'LOSS';
            const resColor  = bet.hit_hr === null ? 'var(--ev-dim)' : bet.hit_hr ? 'var(--ev-green)' : 'var(--ev-red)';
            const plColor   = pl === '—' ? 'var(--ev-dim)' : pl.startsWith('+') ? 'var(--ev-green)' : 'var(--ev-red)';
            const deleting  = deletingId === bet.id;
            return (
              <tr key={bet.id} className="bet-row" style={{ borderBottom: '1px solid var(--ev-border)' }}>
                <td style={{ padding: '9px 14px', color: 'var(--ev-dim)' }}>{fmtDate(bet.game_date)}</td>
                <td style={{ padding: '9px 14px', color: 'var(--ev-text)' }}>{bet.player_name}</td>
                <td style={{ padding: '9px 14px', color: 'var(--ev-muted)' }}>{bet.team_abbr}</td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-blue)' }}>
                  {fmtOdds(bet.tracked_odds)}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: 'var(--ev-muted)' }}>
                  {bet.stake_units}u
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: edgeCol }}>
                  {edgeText}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: plColor }}>
                  {pl}
                </td>
                <td style={{
                  padding: '9px 14px', textAlign: 'right',
                  color: resColor, fontWeight: bet.hit_hr != null ? 600 : 400,
                }}>
                  {result}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right' }}>
                  <button
                    onClick={() => handleDelete(bet.id)}
                    disabled={deleting}
                    title="Delete bet"
                    style={{
                      background:   'transparent',
                      border:       'none',
                      color:        'var(--ev-red)',
                      opacity:      deleting ? 0.4 : 0.6,
                      cursor:       deleting ? 'default' : 'pointer',
                      fontFamily:   'var(--font-mono)',
                      fontSize:     '13px',
                      lineHeight:   1,
                      padding:      '2px 4px',
                    }}
                  >
                    {deleting ? '...' : '✕'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
