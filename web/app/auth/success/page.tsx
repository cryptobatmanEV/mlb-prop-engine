'use client';

import { useEffect } from 'react';

const LABEL: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '11px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  color:         'var(--ev-muted)',
};

// Lands here after Discord OAuth completes. If this page was opened in a new
// tab (e.g. from an iframe embed, where in-place OAuth redirects are
// blocked), notify the opener and close. Otherwise just go to the tracker.
export default function AuthSuccessPage() {
  useEffect(() => {
    if (window.opener) {
      window.opener.postMessage('discord-auth-success', '*');
      window.close();
    } else {
      window.location.href = '/tracker';
    }
  }, []);

  return (
    <main style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--ev-bg)', padding: '20px', textAlign: 'center',
    }}>
      <div style={LABEL}>Login successful! Returning you to the tool&hellip;</div>
    </main>
  );
}
