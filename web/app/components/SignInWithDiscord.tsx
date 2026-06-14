const BTN: React.CSSProperties = {
  display:       'inline-block',
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
  textDecoration: 'none',
};

// Plain <a> tag pointing directly at Discord's OAuth authorize URL.
// Mobile browsers (especially in-app browsers) block JS-triggered
// redirects from signIn(), but always allow a direct link tap.
export default function SignInWithDiscord({ discordAuthUrl }: { discordAuthUrl: string }) {
  return (
    <a href={discordAuthUrl} target="_self" style={BTN}>
      Sign in with Discord
    </a>
  );
}
