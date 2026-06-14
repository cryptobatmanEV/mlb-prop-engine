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

const STEP_TITLE: React.CSSProperties = {
  fontFamily:    'var(--font-syne)',
  fontWeight:    800,
  fontSize:      '14px',
  letterSpacing: '-0.3px',
  color:         'var(--ev-text)',
  marginBottom:  '6px',
};

const STEP_NUM: React.CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      '11px',
  fontWeight:    700,
  letterSpacing: '1px',
  color:         'var(--ev-green)',
  border:        '1px solid var(--ev-green)',
  borderRadius:  '50%',
  width:         '24px',
  height:        '24px',
  display:       'flex',
  alignItems:    'center',
  justifyContent: 'center',
  flexShrink:    0,
};

// ── How to find plays content ───────────────────────────────────────────────

const STEPS: { title: string; def: string }[] = [
  {
    title: 'Start with ADJ%',
    def:   'This is your primary signal for who is most likely to homer today. Look for 15%+ as a starting point — the higher the number, the more the model likes the play.',
  },
  {
    title: 'Check EDGE',
    def:   "Positive edge means the book is underpricing the probability relative to the model. Green edge = value — the bigger the green number, the more the model and the book disagree in your favor.",
  },
  {
    title: 'Confirm with Statcast',
    def:   'Open the expanded card and check BARREL% and HARD HIT%. An elite barrel rate (12%+) confirms the underlying power is real, not just a favorable matchup on paper.',
  },
  {
    title: 'Check the matchup',
    def:   "Look at the opposing pitcher's FIP and the park factor. A high park factor (105+) amplifies everything — a good matchup in a hitter-friendly park is the strongest combination.",
  },
  {
    title: 'Use AI PICKS',
    def:   'The AI PICKS tab does all of this automatically and surfaces the top plays ranked by confidence — a fast way to see what the model likes most without working through the table yourself.',
  },
];

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

        {/* How to find plays */}
        <div style={{ ...CARD, padding: '20px 24px', marginBottom: '24px' }}>
          <div style={{ ...LABEL, marginBottom: '4px' }}>HOW TO FIND PLAYS</div>
          <p style={{ ...DEF, margin: '0 0 18px', color: 'var(--ev-muted)' }}>
            A simple five-step process for turning the CARD into a short list of plays worth a look.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {STEPS.map((step, i) => (
              <div key={step.title} style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                <div style={STEP_NUM}>{i + 1}</div>
                <div>
                  <div style={STEP_TITLE}>{step.title}</div>
                  <div style={{ ...DEF, color: 'var(--ev-muted)' }}>{step.def}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* How to use MY LINE */}
        <div style={{ ...CARD, padding: '20px 24px', marginBottom: '24px' }}>
          <div style={{ ...LABEL, marginBottom: '10px' }}>HOW TO USE MY LINE</div>
          <p style={{ ...DEF, margin: 0, color: 'var(--ev-muted)' }}>
            The FAIR column shows what a player&apos;s home run odds should be based on the model&apos;s
            probability. If you can get a better price than FAIR on an exchange like Novig or ProphetX,
            you&apos;re buying in at a discount. Enter that price into MY LINE to see your real edge at the
            odds you can actually get — a green MY LINE edge means the price you found beats the model&apos;s
            fair value, which is exactly the kind of spot worth taking.
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
