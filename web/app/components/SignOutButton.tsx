'use client';

import { signOut } from 'next-auth/react';

const LABEL: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '10px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  color:         'var(--ev-dim)',
};

export default function SignOutButton() {
  return (
    <button
      onClick={() => signOut({ callbackUrl: '/tracker' })}
      style={{
        ...LABEL,
        background:   'transparent',
        border:       'none',
        cursor:       'pointer',
        textDecoration: 'underline',
        padding:      0,
      }}
    >
      Sign Out
    </button>
  );
}
