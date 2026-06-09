'use client';

import { useRouter } from 'next/navigation';

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function fmtLabel(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00Z')
    .toLocaleDateString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
      timeZone: 'UTC',
    })
    .toUpperCase();
}

const BTN: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '11px',
  letterSpacing: '1px',
  background:    'transparent',
  border:        '1px solid var(--ev-border)',
  color:         'var(--ev-muted)',
  padding:       '5px 12px',
  cursor:        'pointer',
  borderRadius:  '2px',
};

export default function DateNav({ date, today }: { date: string; today: string }) {
  const router  = useRouter();
  const prev    = addDays(date, -1);
  const next    = addDays(date, +1);
  const isToday = date >= today;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
      <button style={BTN} onClick={() => router.push(`/?date=${prev}`)}>
        ← PREV
      </button>

      <span style={{
        fontFamily:  'var(--font-mono)',
        fontSize:    '11px',
        letterSpacing: '2px',
        color:       'var(--ev-text)',
        minWidth:    '170px',
        textAlign:   'center',
      }}>
        {fmtLabel(date)}
      </span>

      <button
        style={{ ...BTN, opacity: isToday ? 0.3 : 1, cursor: isToday ? 'default' : 'pointer' }}
        onClick={() => { if (!isToday) router.push(`/?date=${next}`); }}
        disabled={isToday}
      >
        NEXT →
      </button>

      {date !== today && (
        <button
          style={{ ...BTN, color: 'var(--ev-green)', borderColor: 'var(--ev-green)' }}
          onClick={() => router.push('/')}
        >
          TODAY
        </button>
      )}
    </div>
  );
}
