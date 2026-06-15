'use client';

import { useEffect, useState } from 'react';
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

const HINT: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize:   '11px',
  color:      'var(--ev-dim)',
  marginTop:  '12px',
};

function isMobileDevice() {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

export default function SignInWithDiscord({ callbackUrl }: { callbackUrl?: string }) {
  const [inIframe, setInIframe] = useState(false);

  useEffect(() => {
    setInIframe(window.self !== window.top);
  }, []);

  // OAuth redirects are blocked inside an iframe on mobile browsers, so open
  // NextAuth's sign-in flow in a new tab instead of redirecting in place.
  const handleClick = () => {
    if (inIframe || isMobileDevice()) {
      window.open('/api/auth/signin/discord', '_blank');
      return;
    }
    signIn('discord', { callbackUrl });
  };

  return (
    <div>
      <button onClick={handleClick} style={BTN}>
        Sign in with Discord
      </button>
      {inIframe && (
        <div style={HINT}>
          A new tab will open for sign-in — return here after completing.
        </div>
      )}
    </div>
  );
}
