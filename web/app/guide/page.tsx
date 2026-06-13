import Nav from '../components/Nav';

// ── Style tokens ───────────────────────────────────────────────────────────

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

const TERM: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '11px',
  letterSpacing: '2px',
  textTransform: 'uppercase',
  color:         'var(--ev-green)',
  fontWeight:    600,
};

const DEF: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize:   '12px',
  lineHeight: 1.6,
  color:      'var(--ev-text)',
};

// ── Glossary content ────────────────────────────────────────────────────────

const GLOSSARY: { term: string; def: string }[] = [
  {
    term: 'ADJ%',
    def: "Model's predicted probability the batter hits a HR today. Higher = more likely.",
  },
  {
    term: 'FAIR',
    def: "What the betting line should be if the model's probability is correct.",
  },
  {
    term: 'BOOK',
    def: 'Best available line from sportsbooks (ProphetX, Novig, BetRivers).',
  },
  {
    term: 'EDGE',
    def: "The model's edge over the book's price. Green = model sees more value than the book. Red = book is already priced above the model's estimate. This is the key column for finding +EV plays.",
  },
  {
    term: 'MY LINE',
    def: 'Enter a line you found at any book. The tool recalculates your real edge at that price.',
  },
  {
    term: 'O/U',
    def: 'Game over/under total. Higher totals correlate with more HR-friendly environments.',
  },
  {
    term: 'BO',
    def: 'Batting order position (1-9). Lower numbers get more plate appearances.',
  },
  {
    term: 'H/A',
    def: 'Home or Away.',
  },
  {
    term: 'SZN HR',
    def: 'Season home run count.',
  },
  {
    term: 'PARK',
    def: 'Park factor for HRs. 100 = neutral. Above 100 = hitter-friendly.',
  },
  {
    term: 'WIND',
    def: 'Wind impact on HRs. ^ = toward outfield (helps). v = toward home plate (hurts). ~ = crosswind. DOME = indoor.',
  },
  {
    term: 'HOT',
    def: 'Batter hit a HR in their last 5 games.',
  },
];

// ── Page ───────────────────────────────────────────────────────────────────

export default function GuidePage() {
  return (
    <main style={{ minHeight: '100vh', background: 'var(--ev-bg)', padding: '32px 20px 60px' }}>
      <div style={{ maxWidth: '1380px', margin: '0 auto' }}>

        {/* Header */}
        <header style={{ marginBottom: '28px' }}>
          <div style={{ ...LABEL, color: 'var(--ev-green)', letterSpacing: '3px', marginBottom: '8px' }}>
            THE +EV CAVE
          </div>
          <h1 style={{
            fontFamily: 'var(--font-syne)', fontWeight: 800, fontSize: '26px',
            margin: 0, letterSpacing: '-0.5px', color: 'var(--ev-text)',
          }}>
            GUIDE
          </h1>
        </header>

        {/* Nav */}
        <Nav active="guide" />

        {/* How it works */}
        <div style={{ ...CARD, padding: '20px 24px', marginBottom: '24px' }}>
          <div style={{ ...LABEL, marginBottom: '10px' }}>HOW IT WORKS</div>
          <p style={{ ...DEF, margin: 0, color: 'var(--ev-muted)' }}>
            Our proprietary AI model analyzes Statcast batted-ball data, pitcher matchups, park
            factors, and real-time conditions to identify the hitters most likely to homer.
            Updated daily with confirmed lineups.
          </p>
        </div>

        {/* Glossary */}
        <div style={{ ...CARD, padding: '20px 24px' }}>
          <div style={{ ...LABEL, marginBottom: '16px' }}>COLUMN GLOSSARY</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px 32px' }}>
            {GLOSSARY.map(({ term, def }) => (
              <div key={term}>
                <div style={{ ...TERM, marginBottom: '4px' }}>{term}</div>
                <div style={DEF}>{def}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </main>
  );
}
