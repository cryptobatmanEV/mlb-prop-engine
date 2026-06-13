'use client';

import { signIn } from 'next-auth/react';

const BTN: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '11px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  borderRadius:  '2px',
  padding:       '10px 20px',
  cursor:        'pointer',
  color:         '#fff',
  background:    '#5865F2',
  border:        '1px solid #5865F2',
  fontWeight:    600,
};

export default function SignInWithDiscord({ callbackUrl }: { callbackUrl?: string }) {
  return (
    <button onClick={() => signIn('discord', { callbackUrl })} style={BTN}>
      Sign in with Discord
    </button>
  );
}
