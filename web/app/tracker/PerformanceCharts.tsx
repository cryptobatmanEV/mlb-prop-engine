'use client';

import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts';

export type PLPoint    = { date: string; cumPL: number };
export type CalibPoint = { label: string; predicted_pct: number; actual_pct: number; count: number };

type Props = {
  plData:    PLPoint[];
  calibData: CalibPoint[];
};

const MONO   = '"IBM Plex Mono", monospace';
const DIM    = 'rgba(255,255,255,0.3)';
const GRID   = 'rgba(255,255,255,0.06)';
const GREEN  = '#00dc6e';
const RED    = '#ff4d4d';
const BLUE   = '#80a8ff';
const CARD_BG = '#0a0d0f';
const BORDER  = 'rgba(255,255,255,0.07)';

const tickStyle = { fill: DIM, fontSize: 10, fontFamily: MONO };

const tooltipContentStyle = {
  background:   CARD_BG,
  border:       `1px solid ${BORDER}`,
  borderRadius: 2,
  fontFamily:   MONO,
  fontSize:     11,
};

const cardStyle: React.CSSProperties = {
  background:   'var(--ev-card)',
  border:       `1px solid ${BORDER}`,
  borderRadius: '2px',
  padding:      '20px 20px 12px',
};

const labelStyle: React.CSSProperties = {
  fontFamily:    MONO,
  fontSize:      '10px',
  letterSpacing: '2px',
  color:         DIM,
  marginBottom:  '12px',
};

function CalibTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string; payload: CalibPoint }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const n = payload[0]?.payload?.count;
  return (
    <div style={{ ...tooltipContentStyle, padding: '8px 12px' }}>
      <div style={{ color: '#fff', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toFixed(1)}%
        </div>
      ))}
      {n != null && (
        <div style={{ color: DIM, marginTop: 4, fontSize: 10 }}>n = {n}</div>
      )}
    </div>
  );
}

export default function PerformanceCharts({ plData, calibData }: Props) {
  if (plData.length === 0 && calibData.length === 0) {
    return (
      <div style={{ ...cardStyle, textAlign: 'center', padding: '36px', color: DIM, fontSize: '11px', fontFamily: MONO }}>
        Performance charts appear after your first settled play
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* Cumulative P/L */}
      {plData.length > 0 && (
        <div style={cardStyle}>
          <div style={labelStyle}>CUMULATIVE P/L (UNITS)</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={plData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis dataKey="date" tick={tickStyle} axisLine={false} tickLine={false} />
              <YAxis
                tick={tickStyle}
                axisLine={false}
                tickLine={false}
                width={48}
                tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v}u`}
              />
              <Tooltip
                contentStyle={tooltipContentStyle}
                labelStyle={{ color: DIM, marginBottom: 4 }}
                formatter={(v) => [`${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}u`, 'CUM P/L']}
              />
              <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
              <Line
                type="monotone"
                dataKey="cumPL"
                stroke={GREEN}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: GREEN }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Calibration */}
      {calibData.length > 0 && (
        <div style={cardStyle}>
          <div style={labelStyle}>CALIBRATION — PREDICTED VS ACTUAL HR RATE</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={calibData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={tickStyle} axisLine={false} tickLine={false} />
              <YAxis
                tick={tickStyle}
                axisLine={false}
                tickLine={false}
                width={36}
                tickFormatter={(v: number) => `${v}%`}
              />
              <Tooltip content={<CalibTooltip />} />
              <Bar dataKey="predicted_pct" name="PREDICTED" fill={BLUE} fillOpacity={0.35} radius={[2, 2, 0, 0]} />
              <Bar dataKey="actual_pct" name="ACTUAL" radius={[2, 2, 0, 0]}>
                {calibData.map((d, i) => (
                  <Cell key={i} fill={d.actual_pct >= d.predicted_pct ? GREEN : RED} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{
            display: 'flex', gap: '16px', marginTop: '4px', paddingLeft: '40px',
            fontFamily: MONO, fontSize: '9px', color: DIM, letterSpacing: '1.5px',
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 8, height: 8, background: BLUE, opacity: 0.6, display: 'inline-block', borderRadius: 1 }} />
              PREDICTED
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 8, height: 8, background: GREEN, display: 'inline-block', borderRadius: 1 }} />
              ACTUAL &ge; PREDICTED
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 8, height: 8, background: RED, display: 'inline-block', borderRadius: 1 }} />
              ACTUAL &lt; PREDICTED
            </span>
          </div>
        </div>
      )}

    </div>
  );
}
