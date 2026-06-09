import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Brief, ThemeReport, ActionItem } from '../types'

interface BriefPanelProps {
  brief: Brief
  themeReport: ThemeReport
}

const sevConfig = {
  high:   { color: 'var(--neg)', bg: 'var(--neg-soft)', stripe: 'var(--neg)', label: 'High priority' },
  medium: { color: 'var(--mix)', bg: 'var(--mix-soft)', stripe: 'var(--mix)', label: 'Medium priority' },
  low:    { color: 'var(--pos)', bg: 'var(--pos-soft)', stripe: 'var(--pos)', label: 'Low priority' },
} as const

function ActionCard({ item, themeReport, index }: {
  item: ActionItem
  themeReport: ThemeReport
  index: number
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const sev = sevConfig[item.severity]
  const theme = themeReport.themes.find(t => t.theme_id === item.theme_id)
  const hasEvidence = !!theme?.sample_quotes.length

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut', delay: index * 0.06 }}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow)',
        padding: '20px 22px',
        position: 'relative',
        overflow: 'hidden',
        marginTop: index === 0 ? 0 : 16,
      }}
    >
      {/* Left severity stripe */}
      <div
        style={{
          position: 'absolute',
          left: 0, top: 0, bottom: 0,
          width: 4,
          background: sev.stripe,
        }}
      />

      {/* Rank + severity + evidence button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--ink-faint)',
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 7,
            padding: '2px 9px',
          }}
        >
          #{item.rank}
        </span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '.06em',
            textTransform: 'uppercase' as const,
            padding: '3px 10px',
            borderRadius: 999,
            color: sev.color,
            background: sev.bg,
          }}
        >
          <span style={{ fontSize: 13, lineHeight: 1 }}>●</span>
          {sev.label}
        </span>

        {hasEvidence && (
          <button
            onClick={() => setEvidenceOpen(v => !v)}
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              fontWeight: 600,
              color: evidenceOpen ? 'var(--brand)' : 'var(--ink-soft)',
              background: 'transparent',
              border: `1px solid ${evidenceOpen ? 'var(--brand)' : 'var(--line-strong)'}`,
              borderRadius: 999,
              padding: '5px 12px',
              cursor: 'pointer',
              transition: 'all .15s',
            }}
            aria-expanded={evidenceOpen}
          >
            Evidence {evidenceOpen ? '▴' : '▾'}
          </button>
        )}
      </div>

      {/* Headline */}
      <h3
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 21,
          fontWeight: 600,
          lineHeight: 1.25,
          color: 'var(--ink)',
        }}
      >
        {item.headline}
      </h3>

      {/* Why it matters */}
      <p
        style={{
          fontSize: 14,
          color: 'var(--ink-soft)',
          marginTop: 8,
          lineHeight: 1.55,
          maxWidth: '64ch',
        }}
      >
        {item.why_it_matters}
      </p>

      {/* Do this */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          marginTop: 16,
          background: 'var(--surface-2)',
          borderRadius: 10,
          padding: '14px 16px',
        }}
      >
        <span
          style={{
            fontSize: 10,
            letterSpacing: '.14em',
            textTransform: 'uppercase' as const,
            fontWeight: 800,
            color: 'var(--pos)',
            whiteSpace: 'nowrap',
            paddingTop: 2,
          }}
        >
          Do this
        </span>
        <p style={{ fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.55, margin: 0 }}>
          {item.recommended_action}
        </p>
      </div>

      {/* Evidence drawer */}
      <AnimatePresence>
        {evidenceOpen && hasEvidence && (
          <motion.div
            key="evidence"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ borderTop: '1px dashed var(--line-strong)', paddingTop: 12, marginTop: 14 }}>
              <div
                style={{
                  fontSize: 10,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase' as const,
                  color: 'var(--ink-faint)',
                  fontWeight: 700,
                  marginBottom: 8,
                }}
              >
                Sourced from {theme!.review_ids.length} review{theme!.review_ids.length !== 1 ? 's' : ''}
              </div>
              {theme!.sample_quotes.map((q, i) => (
                <div
                  key={i}
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontStyle: 'italic',
                    fontSize: 14,
                    color: 'var(--ink)',
                    padding: '8px 0 8px 14px',
                    borderLeft: '2px solid var(--line-strong)',
                    marginBottom: i < theme!.sample_quotes.length - 1 ? 8 : 0,
                    lineHeight: 1.5,
                  }}
                >
                  "{q}"
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}

export default function BriefPanel({ brief, themeReport }: BriefPanelProps) {
  return (
    <section aria-label="Action brief" style={{ marginTop: 30 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
        <span
          style={{
            fontSize: 11,
            letterSpacing: '.16em',
            textTransform: 'uppercase' as const,
            color: 'var(--ink-faint)',
            fontWeight: 700,
          }}
        >
          Action Items
        </span>
        <span style={{ fontSize: 11, color: 'var(--ink-faint)' }}>
          {brief.action_items.length} this week · ranked by severity
        </span>
      </div>

      <AnimatePresence>
        {brief.action_items.map((item, i) => (
          <ActionCard key={item.theme_id} item={item} themeReport={themeReport} index={i} />
        ))}
      </AnimatePresence>

      {brief.action_items.length === 0 && (
        <div
          style={{
            padding: '24px 20px',
            background: 'var(--surface)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--line)',
            fontSize: 14,
            color: 'var(--ink-soft)',
            textAlign: 'center',
          }}
        >
          No negative themes identified this week — nice work.
        </div>
      )}
    </section>
  )
}
