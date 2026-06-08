'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

type Props = {
  gameDate:    string;
  batter:      number;
  playerName:  string;
  teamAbbr:    string;
  adjProb:     number;
  trackedOdds: number | null;
  trackedEdge: number | null;
};

type Phase = 'idle' | 'open' | 'submitting' | 'done' | 'error';

const BTN: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '10px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  borderRadius:  '2px',
  padding:       '4px 9px',
  cursor:        'pointer',
  whiteSpace:    'nowrap',
};

export default function TrackButton({
  gameDate, batter, playerName, teamAbbr, adjProb, trackedOdds, trackedEdge,
}: Props) {
  const router = useRouter();
  const [phase,      setPhase]      = useState<Phase>('idle');
  const [stake,      setStake]      = useState('1');
  const [savedStake, setSavedStake] = useState('1');

  async function submit() {
    const units = parseFloat(stake);
    if (!units || units <= 0) return;
    setSavedStake(stake);
    setPhase('submitting');
    try {
      const res = await fetch('/api/track', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game_date:    gameDate,
          batter,
          player_name:  playerName,
          team_abbr:    teamAbbr,
          adj_prob:     adjProb,
          tracked_odds: trackedOdds,
          edge:         trackedEdge,
          stake_units:  units,
        }),
      });
      if (!res.ok) throw new Error('bad response');
      setPhase('done');
      router.refresh();
    } catch {
      setPhase('error');
      setTimeout(() => setPhase('idle'), 2000);
    }
  }

  // IDLE: single green TRACK button
  if (phase === 'idle') {
    return (
      <button
        onClick={() => setPhase('open')}
        style={{
          ...BTN,
          color:      'var(--ev-green)',
          background: 'transparent',
          border:     '1px solid rgba(0, 220, 110, 0.25)',
        }}
      >
        TRACK
      </button>
    );
  }

  // OPEN: compact stake input + OK button
  if (phase === 'open') {
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
        <input
          type="number"
          min="0.1"
          step="0.5"
          value={stake}
          onChange={e => setStake(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter')  submit();
            if (e.key === 'Escape') setPhase('idle');
          }}
          autoFocus
          style={{
            width:        '52px',
            background:   'rgba(255,255,255,0.06)',
            border:       '1px solid rgba(255,255,255,0.15)',
            borderRadius: '2px',
            color:        'var(--ev-text)',
            fontFamily:   'var(--font-mono)',
            fontSize:     '12px',
            fontWeight:   500,
            padding:      '3px 6px',
            textAlign:    'right',
            outline:      'none',
          }}
        />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ev-dim)' }}>u</span>
        <button
          onClick={submit}
          style={{
            ...BTN,
            padding:    '4px 8px',
            color:      'var(--ev-green)',
            background: 'rgba(0, 220, 110, 0.08)',
            border:     '1px solid rgba(0, 220, 110, 0.4)',
          }}
        >
          OK
        </button>
      </div>
    );
  }

  // SUBMITTING
  if (phase === 'submitting') {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ev-dim)', letterSpacing: '2px' }}>
        ...
      </span>
    );
  }

  // DONE
  if (phase === 'done') {
    return (
      <span
        style={{
          fontFamily:    'var(--font-mono)',
          fontSize:      '10px',
          letterSpacing: '1px',
          color:         'var(--ev-green)',
          fontWeight:    600,
          textTransform: 'uppercase',
        }}
      >
        {savedStake}u TRACKED
      </span>
    );
  }

  // ERROR
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ev-red)', letterSpacing: '2px' }}>
      ERROR
    </span>
  );
}
