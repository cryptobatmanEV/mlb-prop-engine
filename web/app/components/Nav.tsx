import Link from 'next/link';

const links = [
  { href: '/',            label: 'CARD',        id: 'card'        },
  { href: '/tracker',     label: 'TRACKER',     id: 'tracker'     },
  { href: '/leaderboard', label: 'LEADERBOARD', id: 'leaderboard' },
  { href: '/guide',       label: 'GUIDE',       id: 'guide'       },
] as const;

type Page = (typeof links)[number]['id'];

export default function Nav({ active }: { active: Page }) {
  return (
    <div className="prop-type-tabs" style={{
      display:      'flex',
      maxWidth:     '100%',
      overflowX:    'auto',
      marginBottom: '24px',
      border:       '1px solid var(--ev-border)',
      borderRadius: '2px',
    }}>
      {links.map(({ href, label, id }, idx) => (
        <Link key={href} href={href} style={{
          fontFamily:     'var(--font-mono)',
          fontSize:       '10px',
          letterSpacing:  '2.5px',
          textDecoration: 'none',
          display:        'block',
          padding:        '7px 18px',
          whiteSpace:     'nowrap',
          flexShrink:     0,
          color:          active === id ? 'var(--ev-text)' : 'var(--ev-dim)',
          background:     active === id ? 'rgba(255,255,255,0.07)' : 'transparent',
          borderRight:    idx < links.length - 1 ? '1px solid var(--ev-border)' : 'none',
        }}>
          {label}
        </Link>
      ))}
    </div>
  );
}
