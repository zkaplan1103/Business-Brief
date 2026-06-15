/**
 * CostTab — Phase 4 cost-engineering dashboard.
 *
 * Fetches GET /api/metrics and renders:
 *   - Top stat cards: total cost + total calls
 *   - Routing mix donut (Recharts PieChart)
 *   - Cost by model bar chart (Recharts BarChart)
 *   - Avg latency by model bar chart (Recharts BarChart)
 *   - Idempotency cache skips count
 *   - Prompt cache savings summary
 *   - Last-updated timestamp
 *
 * Styled consistently with STYLE.md / index.css variables (warm ivory, forest
 * green brand, glass-morphism cards).
 */

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  PieChart, Pie, Cell, Tooltip as RechTooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { api } from '../api'
import type { MetricsData } from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt$(n: number): string {
  if (n >= 1) return `$${n.toFixed(4)}`
  if (n >= 0.0001) return `$${n.toFixed(6)}`
  return `$${n.toFixed(8)}`
}

function shortModelName(full: string): string {
  if (full.includes('haiku'))  return 'Haiku'
  if (full.includes('sonnet')) return 'Sonnet'
  if (full.includes('opus'))   return 'Opus'
  return full
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const CARD: React.CSSProperties = {
  background: 'var(--glass-bg)',
  backdropFilter: 'blur(16px) saturate(1.6)',
  WebkitBackdropFilter: 'blur(16px) saturate(1.6)',
  border: '1px solid var(--glass-border)',
  boxShadow: 'var(--glass-shadow)',
  borderRadius: 'var(--radius)',
  padding: '22px 24px',
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ ...CARD, flex: 1 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-faint)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>{label}</div>
      <div className="tnum" style={{ fontSize: 28, fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--ink-soft)', marginTop: 8 }}>{sub}</div>}
    </div>
  )
}

// Donut for routing mix
const TIER_COLORS = {
  Haiku:  'var(--pos)',
  Sonnet: 'var(--brand)',
  Opus:   'var(--cta)',
}

function RoutingDonut({ mix }: { mix: MetricsData['routing_mix'] }) {
  const data = [
    { name: 'Haiku',  value: mix.haiku_pct },
    { name: 'Sonnet', value: mix.sonnet_pct },
    { name: 'Opus',   value: mix.opus_pct },
  ].filter(d => d.value > 0)

  const hasData = data.length > 0

  return (
    <div style={{ ...CARD }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>Routing mix</div>
      <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 16 }}>% of calls by model tier</div>

      {!hasData ? (
        <div style={{ fontSize: 13, color: 'var(--ink-faint)', fontStyle: 'italic', padding: '24px 0', textAlign: 'center' }}>No calls recorded yet</div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <ResponsiveContainer width={110} height={110}>
            <PieChart>
              <Pie data={data} cx="50%" cy="50%" innerRadius={28} outerRadius={48} dataKey="value" strokeWidth={0}>
                {data.map((entry) => (
                  <Cell key={entry.name} fill={TIER_COLORS[entry.name as keyof typeof TIER_COLORS] ?? '#aaa'} />
                ))}
              </Pie>
              <RechTooltip formatter={(v) => [`${Number(v).toFixed(1)}%`, '']} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.map(d => (
              <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: TIER_COLORS[d.name as keyof typeof TIER_COLORS] ?? '#aaa', flexShrink: 0, display: 'inline-block' }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-soft)', width: 52 }}>{d.name}</span>
                <div style={{ flex: 1, height: 5, background: 'var(--surface-2)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 999, background: TIER_COLORS[d.name as keyof typeof TIER_COLORS] ?? '#aaa', width: `${d.value}%` }} />
                </div>
                <span className="tnum" style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)', width: 36, textAlign: 'right' }}>{d.value.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Generic bar chart card
interface BarItem { name: string; value: number; displayValue: string }

function BarCard({ title, subtitle, data, color }: { title: string; subtitle: string; data: BarItem[]; color: string }) {
  const hasData = data.length > 0 && data.some(d => d.value > 0)

  return (
    <div style={{ ...CARD }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>{title}</div>
      <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 18 }}>{subtitle}</div>
      {!hasData ? (
        <div style={{ fontSize: 13, color: 'var(--ink-faint)', fontStyle: 'italic', padding: '20px 0', textAlign: 'center' }}>No data yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'var(--ink-soft)', fontFamily: 'var(--font-body)' }} axisLine={false} tickLine={false} />
            <YAxis hide />
            <RechTooltip
              formatter={(_v, _n, item) => [(item as { payload?: BarItem }).payload?.displayValue ?? '', '']}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }}
              cursor={{ fill: 'var(--surface-2)' }}
            />
            <Bar dataKey="value" fill={color} radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty / loading states
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {[180, 100, 140].map((h, i) => (
        <div key={i} style={{ ...CARD, height: h, background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite' }} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main tab
// ---------------------------------------------------------------------------

export default function CostTab() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.metrics()
      .then(data => { setMetrics(data); setLoading(false) })
      .catch(() => { setError('Could not load metrics — is the API running?'); setLoading(false) })
  }, [])

  if (loading) return <Skeleton />

  if (error || !metrics) {
    return (
      <div style={{ ...CARD, textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--neg)', marginBottom: 8 }}>Metrics unavailable</div>
        <div style={{ fontSize: 13, color: 'var(--ink-faint)' }}>{error ?? 'No data returned.'}</div>
      </div>
    )
  }

  // Derived chart data
  const costByModel: BarItem[] = Object.entries(metrics.by_model).map(([m, v]) => ({
    name: shortModelName(m),
    value: v.total_cost_usd,
    displayValue: fmt$(v.total_cost_usd),
  }))

  const latencyByModel: BarItem[] = Object.entries(metrics.by_model).map(([m, v]) => ({
    name: shortModelName(m),
    value: v.avg_latency_ms,
    displayValue: `${v.avg_latency_ms.toFixed(0)} ms avg`,
  }))

  const totalCacheReadTokens = Object.values(metrics.by_model).reduce((s, v) => s + v.cache_read_tokens, 0)
  const totalPromptCacheSaved = Object.values(metrics.by_model).reduce((s, v) => s + v.prompt_cache_saved_usd, 0)

  const generatedAt = new Date(metrics.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: 'easeOut' }}>

      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Cost Engineering</h2>
        <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 4 }}>
          {metrics.days_covered} day{metrics.days_covered !== 1 ? 's' : ''} of log data · last updated {generatedAt}
        </div>
      </div>

      {/* Stat row */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <StatCard
          label="Total cost"
          value={fmt$(metrics.total_cost_usd)}
          sub={`${metrics.total_calls} model call${metrics.total_calls !== 1 ? 's' : ''}`}
        />
        <StatCard
          label="Idempotency saves"
          value={metrics.idempotency_skips.toString()}
          sub="calls skipped via idempotency cache"
        />
        <StatCard
          label="Prompt cache savings"
          value={fmt$(totalPromptCacheSaved)}
          sub={`${totalCacheReadTokens.toLocaleString()} cache-read tokens`}
        />
      </div>

      {/* Routing donut + cost bar side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <RoutingDonut mix={metrics.routing_mix} />
        <BarCard
          title="Cost by model"
          subtitle="Total USD spend per tier"
          data={costByModel}
          color="var(--brand)"
        />
      </div>

      {/* Latency bar (full width) */}
      <div style={{ marginBottom: 20 }}>
        <BarCard
          title="Avg latency by model"
          subtitle="Mean response time in milliseconds"
          data={latencyByModel}
          color="var(--cta)"
        />
      </div>

      {/* Stage breakdown */}
      {Object.keys(metrics.by_stage).length > 0 && (
        <div style={{ ...CARD, marginBottom: 20 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>By pipeline stage</div>
          <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 16 }}>Cost and call count per stage</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Object.entries(metrics.by_stage).map(([stage, sv]) => (
              <div key={stage} style={{ display: 'grid', gridTemplateColumns: '100px 1fr 80px 80px', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', textTransform: 'capitalize' }}>{stage}</span>
                <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 999, background: 'var(--brand)', width: `${Math.min(100, (sv.total_cost_usd / (metrics.total_cost_usd || 1)) * 100)}%` }} />
                </div>
                <span className="tnum" style={{ fontSize: 12, color: 'var(--ink-soft)', textAlign: 'right' }}>{sv.calls} call{sv.calls !== 1 ? 's' : ''}</span>
                <span className="tnum" style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink)', textAlign: 'right' }}>{fmt$(sv.total_cost_usd)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Prompt cache info box */}
      <div style={{ ...CARD, borderLeft: '3px solid var(--brand)', background: 'var(--surface)' }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>
          Prompt caching
        </div>
        <div style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.6 }}>
          The ~2,300-token system prompt is sent with <code style={{ fontSize: 12, background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 4 }}>cache_control: ephemeral</code> on every analysis call, so repeat batches reuse the cached prefix at 1/10th the input rate.
          Caching is live on Sonnet and Opus (their 1,024-token minimum is cleared); Haiku has a higher minimum cacheable prefix and is left uncached, since its input rate is already 4–18× cheaper.
          {totalCacheReadTokens > 0
            ? ` This window: ${totalCacheReadTokens.toLocaleString()} tokens served from cache — ${fmt$(totalPromptCacheSaved)} saved vs. uncached.`
            : ' Cache-read tokens appear here once a batch repeats within the 5-minute cache window.'}
        </div>
      </div>

    </motion.div>
  )
}
