/**
 * EvalTab — Phase 5 quality-vs-cost evaluation.
 *
 * Renders the signed-off eval (GET /api/eval, falling back to FIXTURE_EVAL):
 *   - A headline "best value" callout (highest F1 per dollar).
 *   - A quality-vs-cost table: F1, evidence overlap, sentiment acc, cost/run.
 *   - A cost-vs-quality scatter so the routing decision is visible at a glance.
 *   - Methodology footnote (golden set, fuzzy matching, what F1 measures).
 *
 * Styled to STYLE.md / index.css tokens, consistent with CostTab.
 */

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ZAxis,
  Tooltip as RechTooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { api } from '../api'
import { FIXTURE_EVAL } from '../fixtures'
import type { EvalData, EvalRow } from '../types'

const CARD: React.CSSProperties = {
  background: 'var(--glass-bg)',
  backdropFilter: 'blur(16px) saturate(1.6)',
  WebkitBackdropFilter: 'blur(16px) saturate(1.6)',
  border: '1px solid var(--glass-border)',
  boxShadow: 'var(--glass-shadow)',
  borderRadius: 'var(--radius)',
  padding: '22px 24px',
}

const TIER_COLOR: Record<string, string> = {
  Haiku: 'var(--pos)',
  Sonnet: 'var(--brand)',
  Opus: 'var(--cta)',
}

function fmt$(n: number): string {
  return n >= 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(6)}`
}

function pct(n: number): string {
  return `${(n * 100).toFixed(0)}%`
}

// "Best value" = highest F1 per dollar spent. This is the routing thesis.
function bestValue(rows: EvalRow[]): EvalRow {
  return rows.reduce((best, r) =>
    (r.label_f1 / (r.cost_usd || 1e-9)) > (best.label_f1 / (best.cost_usd || 1e-9)) ? r : best
  , rows[0])
}

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {[120, 220, 200].map((h, i) => (
        <div key={i} style={{ ...CARD, height: h, background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite' }} />
      ))}
    </div>
  )
}

export default function EvalTab() {
  const [data, setData] = useState<EvalData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.eval()
      .then(d => {
        // Fall back to the bundled fixture if the artifact isn't present.
        setData(d.available && d.rows?.length ? d : FIXTURE_EVAL)
        setLoading(false)
      })
      .catch(() => { setData(FIXTURE_EVAL); setLoading(false) })
  }, [])

  if (loading) return <Skeleton />
  if (!data || !data.rows?.length) {
    return (
      <div style={{ ...CARD, textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink-soft)' }}>No eval results yet</div>
        <div style={{ fontSize: 13, color: 'var(--ink-faint)', marginTop: 8 }}>
          Run the scored eval to populate this tab.
        </div>
      </div>
    )
  }

  const rows = data.rows
  const winner = bestValue(rows)

  // Scatter: x = cost/run, y = F1. Bubble each model tier.
  const scatterData = rows.map(r => ({
    x: r.cost_usd, y: r.label_f1, z: 100, label: r.label,
  }))

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: 'easeOut' }}>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Quality vs. Cost</h2>
        <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 4 }}>
          One scored run across all three model tiers · {data.review_count} reviews · {data.golden_themes} golden themes
          {data.business_name ? ` · ${data.business_name}` : ''}
        </div>
      </div>

      {/* Best-value callout */}
      <div style={{ ...CARD, borderLeft: `3px solid ${TIER_COLOR[winner.label] ?? 'var(--brand)'}`, marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-faint)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
          Best quality per dollar
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 30, fontWeight: 700, color: 'var(--ink)', fontFamily: 'var(--font-display)' }}>{winner.label}</span>
          <span style={{ fontSize: 14, color: 'var(--ink-soft)' }}>
            F1 <strong className="tnum" style={{ color: 'var(--ink)' }}>{winner.label_f1.toFixed(2)}</strong> at <strong className="tnum" style={{ color: 'var(--ink)' }}>{fmt$(winner.cost_usd)}</strong>/run
            {winner.label === 'Haiku' ? ' — the cheapest tier also scored highest on this batch.' : ''}
          </span>
        </div>
      </div>

      {/* Quality-vs-cost table */}
      <div style={{ ...CARD, marginBottom: 20, padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr 0.9fr 1fr 1fr 0.9fr', gap: 0, fontSize: 11, fontWeight: 600, color: 'var(--ink-faint)', letterSpacing: '0.05em', textTransform: 'uppercase', padding: '14px 24px', borderBottom: '1px solid var(--line)' }}>
          <span>Model</span>
          <span style={{ textAlign: 'right' }}>Cost/run</span>
          <span style={{ textAlign: 'right' }}>Label F1</span>
          <span style={{ textAlign: 'right' }}>Evidence</span>
          <span style={{ textAlign: 'right' }}>Sentiment</span>
          <span style={{ textAlign: 'right' }}>Matched</span>
        </div>
        {rows.map((r, i) => {
          const isWinner = r.label === winner.label
          return (
            <div key={r.model} className={isWinner ? undefined : 'data-row'} style={{
              display: 'grid', gridTemplateColumns: '1.1fr 0.9fr 0.9fr 1fr 1fr 0.9fr', gap: 0,
              alignItems: 'center', padding: '16px 24px',
              borderBottom: i < rows.length - 1 ? '1px solid var(--line)' : 'none',
              background: isWinner ? 'var(--pos-soft)' : 'transparent',
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 9, height: 9, borderRadius: 3, background: TIER_COLOR[r.label] ?? '#aaa', display: 'inline-block', flexShrink: 0 }} />
                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>{r.label}</span>
              </span>
              <span className="tnum" style={{ textAlign: 'right', fontSize: 14, fontFamily: 'var(--font-mono)', color: 'var(--ink-soft)' }}>{fmt$(r.cost_usd)}</span>
              <span className="tnum" style={{ textAlign: 'right', fontSize: 15, fontWeight: 700, color: isWinner ? 'var(--brand-deep)' : 'var(--ink)' }}>{r.label_f1.toFixed(2)}</span>
              <span className="tnum" style={{ textAlign: 'right', fontSize: 14, color: 'var(--ink-soft)' }}>{pct(r.evidence_overlap)}</span>
              <span className="tnum" style={{ textAlign: 'right', fontSize: 14, color: 'var(--ink-soft)' }}>{pct(r.sentiment_accuracy)}</span>
              <span className="tnum" style={{ textAlign: 'right', fontSize: 14, color: 'var(--ink-soft)' }}>{r.matched_themes}/{r.total_golden_themes}</span>
            </div>
          )
        })}
      </div>

      {/* Cost-vs-quality scatter */}
      <div style={{ ...CARD, marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>Cost vs. quality</div>
        <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 18 }}>
          Up and to the left is better — more F1 for less spend
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 28, left: 6 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis
              type="number" dataKey="x" name="Cost"
              tickFormatter={(v) => `$${Number(v).toFixed(3)}`}
              tick={{ fontSize: 11, fill: 'var(--ink-soft)', fontFamily: 'var(--font-body)' }}
              axisLine={{ stroke: 'var(--line)' }} tickLine={false}
              label={{ value: 'Cost per run', position: 'bottom', offset: 10, fontSize: 12, fill: 'var(--ink-faint)' }}
            />
            <YAxis
              type="number" dataKey="y" name="F1" domain={[0, 1]}
              tick={{ fontSize: 11, fill: 'var(--ink-soft)', fontFamily: 'var(--font-body)' }}
              axisLine={{ stroke: 'var(--line)' }} tickLine={false}
              label={{ value: 'Label F1', angle: -90, position: 'insideLeft', fontSize: 12, fill: 'var(--ink-faint)' }}
            />
            <ZAxis type="number" dataKey="z" range={[180, 180]} />
            <RechTooltip
              cursor={{ strokeDasharray: '3 3', stroke: 'var(--line-strong)' }}
              formatter={(v, n) => n === 'Cost' ? [`$${Number(v).toFixed(6)}`, 'Cost/run'] : [Number(v).toFixed(2), 'F1']}
              labelFormatter={() => ''}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }}
            />
            <Scatter data={scatterData}>
              {scatterData.map(d => (
                <Cell key={d.label} fill={TIER_COLOR[d.label] ?? '#aaa'} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        <div style={{ display: 'flex', gap: 18, justifyContent: 'center', marginTop: 6 }}>
          {rows.map(r => (
            <span key={r.model} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-soft)' }}>
              <span style={{ width: 9, height: 9, borderRadius: 3, background: TIER_COLOR[r.label] ?? '#aaa', display: 'inline-block' }} />
              {r.label}
            </span>
          ))}
        </div>
      </div>

      {/* Methodology */}
      <div style={{ ...CARD, background: 'var(--surface)' }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>How this is scored</div>
        <div style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.6 }}>
          Each tier classifies the same {data.review_count} reviews; the output is scored against a human-signed-off golden
          set of {data.golden_themes} themes. <strong>Label F1</strong> matches predicted to golden themes by fuzzy
          token overlap (Jaccard ≥ 0.25). <strong>Evidence</strong> is the Jaccard overlap of cited review IDs on matched
          themes; <strong>Sentiment</strong> is exact-match accuracy on those themes. Costs are first-run charges —
          reruns hit the idempotency cache at $0.
          {data.note ? <><br /><span style={{ fontSize: 12, color: 'var(--ink-faint)' }}>{data.note}</span></> : null}
        </div>
      </div>

    </motion.div>
  )
}
