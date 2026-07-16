'use client';

import { useRouter, useSearchParams, usePathname } from 'next/navigation';

export type StatType = 'hr' | 'hits' | 'total_bases' | 'batter_ks';

const TABS: { id: StatType; label: string }[] = [
  { id: 'hr',           label: 'HOME RUNS'   },
  { id: 'hits',         label: 'HITS'        },
  { id: 'total_bases',  label: 'TOTAL BASES' },
  { id: 'batter_ks',    label: 'STRIKEOUTS'  },
];

export default function PropTypeTabs({ active }: { active: StatType }) {
  const router     = useRouter();
  const pathname   = usePathname();
  const searchParams = useSearchParams();

  function go(stat: StatType) {
    const params = new URLSearchParams(searchParams.toString());
    if (stat === 'hr') params.delete('stat');
    else params.set('stat', stat);
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <div style={{
      display:      'flex',
      width:        'fit-content',
      marginBottom: '16px',
      border:       '1px solid var(--ev-border)',
      borderRadius: '2px',
      overflow:     'hidden',
    }}>
      {TABS.map(({ id, label }, idx) => (
        <button
          key={id}
          onClick={() => go(id)}
          style={{
            fontFamily:     'var(--font-mono)',
            fontSize:       '10px',
            letterSpacing:  '2.5px',
            border:         'none',
            cursor:         'pointer',
            padding:        '7px 18px',
            color:          active === id ? 'var(--ev-text)' : 'var(--ev-dim)',
            background:     active === id ? 'rgba(255,255,255,0.07)' : 'transparent',
            borderRight:    idx < TABS.length - 1 ? '1px solid var(--ev-border)' : 'none',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
