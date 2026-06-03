import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { ThemeReport } from '../types'

interface ThemeChartProps {
  themeReport: ThemeReport
}

const sentimentColor: Record<string, string> = {
  positive: 'var(--accent-1)',
  negative: 'var(--sev-high)',
  mixed: 'var(--accent-2)',
}

const sentimentHex: Record<string, string> = {
  positive: '#2C5F4A',
  negative: '#BF3B2F',
  mixed: '#E8A23A',
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ payload: { label: string; sentiment: string; count: number; quotes: string[] } }>
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      style={{
        background: 'var(--surface)',
        boxShadow: 'var(--shadow-card)',
        borderRadius: 'var(--radius)',
        padding: '12px 16px',
        fontFamily: 'var(--font-body)',
        maxWidth: 220,
        border: '1px solid var(--border)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 15,
          fontWeight: 600,
          color: 'var(--text)',
          marginBottom: 4,
          lineHeight: 1.3,
        }}
      >
        {d.label}
      </div>
      <div className="flex items-center gap-2 mb-2">
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: sentimentColor[d.sentiment],
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 12,
            color: 'var(--text-muted)',
            textTransform: 'capitalize',
          }}
        >
          {d.sentiment} · {d.count} mention{d.count !== 1 ? 's' : ''}
        </span>
      </div>
      {d.quotes.slice(0, 1).map((q, i) => (
        <p
          key={i}
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 13,
            color: 'var(--text-muted)',
            lineHeight: 1.4,
            borderLeft: '2px solid var(--border)',
            paddingLeft: 8,
            margin: 0,
          }}
        >
          "{q}"
        </p>
      ))}
    </div>
  )
}

export default function ThemeChart({ themeReport }: ThemeChartProps) {
  const data = themeReport.themes.map(t => ({
    label: t.label,
    sentiment: t.sentiment,
    count: t.count,
    quotes: t.sample_quotes,
    // short label for axis
    shortLabel: t.label.length > 22 ? t.label.slice(0, 20) + '…' : t.label,
  }))

  return (
    <article
      style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-card)',
        padding: '20px 24px',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-muted)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginBottom: 4,
        }}
      >
        Theme Overview
      </div>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 18,
          fontWeight: 600,
          color: 'var(--text)',
          marginBottom: 16,
        }}
      >
        Mentions by topic
      </h2>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart
          data={data}
          margin={{ top: 4, right: 4, left: -24, bottom: 0 }}
          barSize={22}
        >
          <CartesianGrid
            vertical={false}
            stroke="var(--border)"
            strokeDasharray="0"
          />
          <XAxis
            dataKey="shortLabel"
            tick={{
              fontFamily: 'var(--font-body)',
              fontSize: 11,
              fill: 'var(--text-muted)',
            }}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
          <YAxis
            tick={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fill: 'var(--text-muted)',
            }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ fill: 'var(--surface-2)' }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={sentimentHex[entry.sentiment]}
                fillOpacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        {(['positive', 'negative', 'mixed'] as const).map(s => (
          <div key={s} className="flex items-center gap-1.5">
            <span
              style={{
                display: 'inline-block',
                width: 10,
                height: 10,
                borderRadius: 2,
                background: sentimentColor[s],
              }}
            />
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 12,
                color: 'var(--text-muted)',
                textTransform: 'capitalize',
              }}
            >
              {s}
            </span>
          </div>
        ))}
      </div>
    </article>
  )
}
